"""Semver versions and ranges, exactly per CCircus INDEX_FORMAT.md §6.

Versions are strict ``X.Y.Z`` (no prerelease/build, no leading zeros).
Ranges use cargo semantics: exact, caret, the four comparators, and comma
as AND. Everything else — tilde, wildcards, partial versions, hyphen
ranges, ``||`` — is rejected loudly.

``tools/cc.py`` in the CCircus repo carries an accepted ~40-line duplicate
of this logic; INDEX_FORMAT.md is the arbiter if they ever disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering

from .errors import CliError


@total_ordering
@dataclass(frozen=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, s: str) -> Version:
        if not isinstance(s, str):
            raise CliError(f"invalid version {s!r} (want 'X.Y.Z')")
        parts = s.strip().split(".")
        if len(parts) != 3:
            raise CliError(f"invalid version {s!r} (want X.Y.Z)")
        nums = []
        for p in parts:
            # isascii(): isdigit() alone admits Unicode digits int() rejects
            if not (p.isascii() and p.isdigit()) or (len(p) > 1 and p[0] == "0"):
                raise CliError(f"invalid version {s!r} (want X.Y.Z, no leading zeros)")
            nums.append(int(p))
        return cls(*nums)

    def _key(self) -> tuple[int, int, int]:
        return (self.major, self.minor, self.patch)

    def __lt__(self, other: Version) -> bool:
        return self._key() < other._key()

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


#: (op, version) predicates a Range compiles to. "^" is kept symbolic so
#: __str__ round-trips the spec.
_COMPARATORS = (">=", "<=", ">", "<")


@dataclass(frozen=True)
class Range:
    spec: str
    parts: tuple[tuple[str, Version], ...]

    @classmethod
    def parse(cls, spec: str) -> Range:
        if not isinstance(spec, str) or not spec.strip():
            raise CliError(f"invalid version range {spec!r}")
        for bad, why in (
            ("~", "tilde ranges are not supported"),
            ("*", "wildcard ranges are not supported"),
            ("||", "'||' alternatives are not supported"),
            (" - ", "hyphen ranges are not supported"),
        ):
            if bad in spec:
                raise CliError(f"invalid version range {spec!r} ({why})")
        parts: list[tuple[str, Version]] = []
        for raw in spec.split(","):
            raw = raw.strip()
            if not raw:
                raise CliError(f"invalid version range {spec!r} (empty part)")
            if raw.startswith("^"):
                parts.append(("^", Version.parse(raw[1:])))
                continue
            for op in _COMPARATORS:
                if raw.startswith(op):
                    parts.append((op, Version.parse(raw[len(op):])))
                    break
            else:
                parts.append(("=", Version.parse(raw)))
        return cls(spec.strip(), tuple(parts))

    def contains(self, v: Version) -> bool:
        for op, ref in self.parts:
            if op == "^":
                if not (ref <= v < _caret_upper(ref)):
                    return False
            elif op == "=":
                if v != ref:
                    return False
            elif op == ">=":
                if not v >= ref:
                    return False
            elif op == "<=":
                if not v <= ref:
                    return False
            elif op == ">":
                if not v > ref:
                    return False
            elif op == "<":
                if not v < ref:
                    return False
        return True

    def __str__(self) -> str:
        return self.spec


def _caret_upper(v: Version) -> Version:
    """Exclusive upper bound of ``^v``: bump the leftmost non-zero component
    (``^0.0.Z`` admits only ``=0.0.Z``)."""
    if v.major:
        return Version(v.major + 1, 0, 0)
    if v.minor:
        return Version(0, v.minor + 1, 0)
    return Version(0, 0, v.patch + 1)


def caret(v: Version) -> str:
    """The default range ``shdl add`` records for latest version ``v``."""
    return f"^{v}"
