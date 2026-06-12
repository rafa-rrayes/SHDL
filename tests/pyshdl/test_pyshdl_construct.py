"""Construction, lifecycle, artifact management, and instance independence.

Covers the V.2 context-manager obligation plus this brief's requirements:
explicit constructors (no content sniffing), the dlopen-independence trap,
and the no-leaked-temp-files trap.
"""

from __future__ import annotations

import gc
import tempfile
from pathlib import Path

import pytest

from pyshdl import (
    BuildError,
    Circuit,
    ClosedCircuitError,
    CompileError,
    FlattenError,
)

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

# One OR gate wired as a buffer: the smallest useful SHDL and Base SHDL.
BUF_SOURCE = """\
top component Buf(A) -> (O) {
    g: OR;
    connect { A -> g.A; A -> g.B; g.O -> O; }
}
"""

BUF_BASE = """\
component Buf(A) -> (O) {
    g: OR;

    connect {
        A -> g.A;
        A -> g.B;
        g.O -> O;
    }
}
"""


def _tempdir_contents(path: Path) -> list[str]:
    return sorted(p.name for p in path.iterdir())


# -- constructors --------------------------------------------------------------


def test_front_door_compiles_and_runs():
    with Circuit(EXAMPLES / "adder8.shdl") as c:
        assert c.name == "Adder8"
        c["A"] = 100
        c["B"] = 55
        c.settle()
        assert c["Sum"] == 155


def test_front_door_accepts_str_path():
    with Circuit(str(EXAMPLES / "inverter.shdl")) as c:
        c.poke("A", 1)
        c.step()
        assert c.peek("O") == 0


def test_missing_file_is_a_flatten_error(tmp_path):
    with pytest.raises(FlattenError, match="file not found"):
        Circuit(tmp_path / "nope.shdl")


def test_explicit_top_selection():
    # busOps defines several components; `top` picks a non-marked one.
    with Circuit(EXAMPLES / "busOps.shdl", top="SplitByte") as c:
        assert c.name == "SplitByte"
        assert c.inputs == ("In",)
        assert c.outputs == ("Low", "High")


def test_from_source():
    with Circuit.from_source(BUF_SOURCE) as c:
        c.poke("A", 1)
        c.step()
        assert c.peek("O") == 1


def test_from_source_resolves_imports_from_include_dirs():
    text = """\
    use fullAdder::{FullAdder};
    top component Wrap(A, B, Cin) -> (Sum, Cout) {
        fa: FullAdder;
        connect {
            A -> fa.A; B -> fa.B; Cin -> fa.Cin;
            fa.Sum -> Sum; fa.Cout -> Cout;
        }
    }
    """
    with Circuit.from_source(text, include_dirs=[EXAMPLES]) as c:
        c.poke("A", 1)
        c.poke("B", 1)
        c.settle()
        assert (c.peek("Sum"), c.peek("Cout")) == (0, 1)


def test_from_source_rejects_bad_module_name():
    with pytest.raises(ValueError, match="identifier"):
        Circuit.from_source(BUF_SOURCE, name="not a name")


def test_from_base_text():
    with Circuit.from_base(BUF_BASE) as c:
        c["A"] = 1
        c.step()
        assert c["O"] == 1


def test_from_base_path(tmp_path):
    artifact = tmp_path / "buf.base.shdl"
    artifact.write_text(BUF_BASE, encoding="utf-8")
    with Circuit.from_base(artifact) as c:
        c["A"] = 1
        c.step()
        assert c["O"] == 1


def test_from_base_str_is_always_text_never_a_filename(tmp_path):
    # Typed dispatch, not sniffing: a str that happens to be a path to a
    # valid artifact is still parsed as artifact *text* — and rejected.
    artifact = tmp_path / "buf.base.shdl"
    artifact.write_text(BUF_BASE, encoding="utf-8")
    with pytest.raises(CompileError):
        Circuit.from_base(str(artifact))


def test_from_library_with_base(examples):
    lib, base = examples.artifacts("adder8")
    with Circuit.from_library(lib, base=base) as c:
        assert c.inputs == ("A", "B", "Cin")
        c["A"], c["B"] = 1, 2
        c.settle()
        assert c["Sum"] == 3


def test_from_library_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        Circuit.from_library(tmp_path / "ghost.dylib")


# -- independence (the dlopen-caches-by-path trap) -------------------------------


def test_two_instances_over_one_source_are_independent(examples):
    with examples.fresh("adder8") as a, examples.fresh("adder8") as b:
        a["A"], a["B"] = 200, 55
        b["A"], b["B"] = 1, 1
        a.settle()
        b.settle()
        assert a["Sum"] == 255
        assert b["Sum"] == 2


def test_two_instances_over_one_library_file_are_independent(examples):
    lib, base = examples.artifacts("srLatch")
    with (
        Circuit.from_library(lib, base=base) as a,
        Circuit.from_library(lib, base=base) as b,
    ):
        a["S"] = 1
        a.step(4)
        assert a["Q"] == 1
        assert b["Q"] == 0  # b never saw a's poke and keeps its power-on state


# -- lifecycle ---------------------------------------------------------------------


def test_context_manager_closes(examples):
    with examples.fresh("inverter") as c:
        pass
    assert c.closed


def test_close_is_idempotent(examples):
    c = examples.fresh("inverter")
    c.close()
    c.close()
    assert c.closed


def test_use_after_close_raises(examples):
    c = examples.fresh("adder8")
    c.close()
    for call in (
        lambda: c.poke("A", 1),
        lambda: c.peek("Sum"),
        lambda: c["Sum"],
        lambda: c.step(),
        lambda: c.step_settle(4),
        lambda: c.settle(),
        lambda: c.reset(),
        lambda: c.run_batch([{"A": 1}]),
    ):
        with pytest.raises(ClosedCircuitError):
            call()
    # Introspection outlives the simulation: metadata needs no library.
    assert c.name == "Adder8"
    assert c.inputs == ("A", "B", "Cin")


def test_del_without_close_is_safe(examples):
    c = examples.fresh("inverter")
    del c
    gc.collect()  # must not raise (close runs via __del__)


# -- artifact management (the temp-lifecycle trap) ------------------------------------


def test_artifacts_cleaned_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    c = Circuit(EXAMPLES / "inverter.shdl")
    assert _tempdir_contents(tmp_path)  # the managed build dir exists while open
    c.close()
    assert _tempdir_contents(tmp_path) == []


def test_keep_artifacts_retains_managed_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    c = Circuit(EXAMPLES / "inverter.shdl", keep_artifacts=True)
    kept = c.build_dir
    c.close()
    names = _tempdir_contents(kept)
    assert "Inverter.base.shdl" in names
    assert "Inverter.c" in names
    assert any(
        n.startswith("Inverter.") and "copy" not in n and n.endswith((".so", ".dylib", ".dll"))
        for n in names
    )


def test_explicit_build_dir_is_retained(tmp_path):
    target = tmp_path / "out"
    c = Circuit(EXAMPLES / "inverter.shdl", build_dir=target)
    assert c.build_dir == target
    c.close()
    assert (target / "Inverter.base.shdl").is_file()
    assert (target / "Inverter.c").is_file()


def test_failed_build_leaves_no_temp_dirs(monkeypatch, tmp_path):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    with pytest.raises(BuildError):
        Circuit(EXAMPLES / "inverter.shdl", cc="definitely-not-a-compiler")
    assert _tempdir_contents(tmp_path) == []


# -- repr --------------------------------------------------------------------------------


def test_repr_shows_ports_and_state(examples):
    c = examples.fresh("adder8")
    assert repr(c) == "<pyshdl.Circuit 'Adder8' (A[8], B[8], Cin) -> (Sum[8], Cout)>"
    c.close()
    assert repr(c) == "<pyshdl.Circuit 'Adder8' (closed)>"


def test_repr_without_metadata(examples):
    lib, _ = examples.artifacts("inverter")
    with Circuit.from_library(lib) as bare:
        assert "(no metadata)" in repr(bare)
