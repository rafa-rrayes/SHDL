"""Version/Range grammar, exactly INDEX_FORMAT.md §6 (cargo caret semantics)."""

from __future__ import annotations

import pytest

from shdl_cli.errors import CliError
from shdl_cli.semver import Range, Version, caret


# --- versions ---------------------------------------------------------------
def test_version_parse_and_order():
    assert Version.parse("1.2.3") == Version(1, 2, 3)
    assert str(Version.parse("0.0.0")) == "0.0.0"
    assert Version.parse("0.9.9") < Version.parse("0.10.0") < Version.parse("1.0.0")
    assert Version.parse("10.0.0") > Version.parse("9.99.99")


@pytest.mark.parametrize(
    "bad",
    ["1", "1.2", "1.2.3.4", "01.2.3", "1.02.3", "1.2.03", "1.2.-3", "+1.2.3",
     "1.2.3-rc1", "1.2.3+build", "a.b.c", "", " ", "1..3"],
)
def test_version_rejections(bad):
    with pytest.raises(CliError):
        Version.parse(bad)


# --- caret: the hot path (every real package is 0.x today) -------------------
@pytest.mark.parametrize(
    ("spec", "version", "ok"),
    [
        ("^1.2.3", "1.2.3", True),
        ("^1.2.3", "1.9.0", True),
        ("^1.2.3", "2.0.0", False),
        ("^1.2.3", "1.2.2", False),
        ("^0.2.3", "0.2.3", True),
        ("^0.2.3", "0.2.9", True),
        ("^0.2.3", "0.3.0", False),
        ("^0.2.3", "1.0.0", False),
        ("^0.1.0", "0.1.0", True),
        ("^0.1.0", "0.1.7", True),
        ("^0.1.0", "0.2.0", False),
        ("^0.0.3", "0.0.3", True),
        ("^0.0.3", "0.0.4", False),
        ("^0.0.0", "0.0.0", True),
        ("^0.0.0", "0.0.1", False),
    ],
)
def test_caret_table(spec, version, ok):
    assert Range.parse(spec).contains(Version.parse(version)) is ok


# --- comparators, exact, comma-AND -------------------------------------------
@pytest.mark.parametrize(
    ("spec", "version", "ok"),
    [
        ("1.2.3", "1.2.3", True),
        ("1.2.3", "1.2.4", False),
        (">=1.0.0", "1.0.0", True),
        (">=1.0.0", "0.9.9", False),
        (">1.0.0", "1.0.0", False),
        (">1.0.0", "1.0.1", True),
        ("<=1.0.0", "1.0.0", True),
        ("<1.0.0", "1.0.0", False),
        (">=1.0.0, <2.0.0", "1.5.0", True),
        (">=1.0.0, <2.0.0", "2.0.0", False),
        (">=1.0.0,<2.0.0", "0.9.0", False),
        ("^0.1.0, >=0.1.2", "0.1.1", False),
        ("^0.1.0, >=0.1.2", "0.1.2", True),
    ],
)
def test_range_table(spec, version, ok):
    assert Range.parse(spec).contains(Version.parse(version)) is ok


@pytest.mark.parametrize(
    "bad",
    ["~1.2.3", "1.*", "*", "x", "1", "1.2", "^1.2", "1.0.0 - 2.0.0",
     "^1.0.0 || ^2.0.0", "", "   ", ">=1.0.0,,<2.0.0", "==1.2.3"],
)
def test_range_rejections(bad):
    with pytest.raises(CliError):
        Range.parse(bad)


def test_range_str_roundtrip():
    assert str(Range.parse(" >=1.0.0, <2.0.0 ")) == ">=1.0.0, <2.0.0"


def test_caret_default():
    assert caret(Version.parse("0.1.0")) == "^0.1.0"


def test_version_rejects_unicode_digits():
    # str.isdigit() alone would admit these; int() would then blow up
    for bad in ("１.２.３", "1.²derp.3", "1.²."):
        with pytest.raises(CliError):
            Version.parse(bad)
