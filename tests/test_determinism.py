from helpers import FIXTURES, flatten_fixture

ALL_TOPS = sorted(p.stem for p in FIXTURES.glob("*.shdl") if p.stem != "stdgates")


def test_double_run_is_byte_identical():
    for name in ALL_TOPS:
        first = flatten_fixture(name)
        second = flatten_fixture(name)
        assert first.text == second.text, name
        assert first.meta == second.meta, name


def test_double_run_with_explicit_top():
    a = flatten_fixture("stdgates", top="XNOR")
    b = flatten_fixture("stdgates", top="XNOR")
    assert a.text == b.text


def test_source_date_epoch_pins_output(monkeypatch):
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "946684800")
    a = flatten_fixture("add2", timestamp=None)
    b = flatten_fixture("add2", timestamp=None)
    assert a.meta["doc"]["flattened_at"] == "2000-01-01T00:00:00Z"
    assert a.text == b.text
