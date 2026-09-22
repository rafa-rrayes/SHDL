"""Word/lane placement for the bit-packed simulation state.

The generated C keeps gate outputs as bits of ``uint64_t`` words instead of
one byte per gate, so one C statement evaluates up to 64 gates of the same
type at once (shdlc_goals.md §5.2: "bit-level parallelism"). This module
decides, deterministically and from the :class:`~shdlc.model.Circuit` alone,
which gate lives in which word and lane, and how each word's operands are
gathered from the previous cycle's words.

It is a pure layout: it never changes *what* is computed or *when*. Every
gate still reads only the previous cycle's committed values and writes its
own bit of ``nxt`` -- the unit-delay model is untouched, nothing is settled
within a cycle. Unused lanes of every word are kept 0 in both buffers, so
the whole-state ``memcmp`` that detects a fixed point stays exact.

Placement is a heuristic (any placement is correct); its goal is that a
word's operand is one aligned run of another word's lanes (one shift) or
one replicated bit (one broadcast):

1. Gates are grouped into *classes* by a structural signature: the gate
   type, its name with digit runs removed (``fa3_ha1_x1`` -> ``fa_ha_x``:
   the same role in every instance of a repeated module, base_shdl.md
   §3.5 -- names are only a hint here, never a correctness dependency),
   refined :data:`ROUNDS` times by the signatures of the operand sources.
2. Classes are placed producers-first (a depth-first walk of the class
   graph; cycles are cut at the class declared first). Each gate *inherits*
   the lane of one of its operands: the gates of a class whose chosen
   operands sit in the same source word form a cohort that lands in one
   destination word at those very lanes (shifted by a constant when that
   lets it share a word). A pairwise reduction tree thereby reads its
   previous level with shifts 0 and +stride, a bus reads a bus with shift
   0, a register reads the input port bit it is wired to.
3. Gates with no usable operand (unplaced source, a fan-out lane another
   gate already inherited, or a constant) are packed contiguously in
   declaration order, so chains inside one class read with shift -1.

:func:`plan_gather` then greedily covers each word's lanes with the fewest
shift/broadcast groups. :func:`stats` reports packing quality.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .model import Circuit, Ref

#: Lanes per state word.
LANES = 64

#: All 64 lanes.
FULL = (1 << LANES) - 1

#: Cap on the rounds of operand-signature refinement when classing gates
#: (see module docstring); refinement stops early once the classes are
#: stable. 0 classes by type + name role only.
ROUNDS = 1

#: How many of the most recently opened, not yet full words of a type are
#: tried before a cohort or run opens a fresh word (bounds planning time).
_OPEN_SEARCH = 32

#: A lane's previous-cycle source: ``("c", word, lane)`` for a gate output,
#: ``("in", port, bit)`` for a poked input bit, or None for an input wire no
#: port covers (stuck at 0, shdlc_goals.md AMB-33).
Source = tuple[str, int, int] | None


@dataclass(frozen=True, slots=True)
class Group:
    """One term of an operand gather: a set of destination ``lanes`` that all
    read ``array[index]`` (``"c"`` = committed state, ``"in"`` = input port
    words).

    Vector (``bcast`` False): destination lane ``l`` reads source lane
    ``l + shift`` -- one shift of the source word, ``shift`` in -63..63.
    Broadcast (``bcast`` True): every destination lane reads source lane
    ``shift`` -- the bit is replicated across the group.

    ``masked`` says the term must be ANDed with ``lanes``: without it, bits
    that land outside the group would reach lanes the word actually uses.
    An unmasked term may still leave junk in the word's *unused* lanes;
    :attr:`Word.masked` cleans that up once per word.
    """

    array: str
    index: int
    shift: int
    bcast: bool
    lanes: int
    masked: bool


@dataclass(frozen=True, slots=True)
class Word:
    """One 64-lane state word. ``gates`` lists ``(lane, gate index)`` pairs
    in lane order; ``mask`` is the used lanes; ``a``/``b`` gather the
    operands; ``masked`` says the result needs ``& mask`` to keep unused
    lanes 0."""

    type: str
    gates: tuple[tuple[int, int], ...]
    mask: int
    label: str
    a: tuple[Group, ...]
    b: tuple[Group, ...]
    masked: bool


@dataclass(frozen=True, slots=True)
class Gather:
    """An output port's value: bit ``b`` of the result is lane ``b``."""

    groups: tuple[Group, ...]
    mask: int
    masked: bool


@dataclass(frozen=True, slots=True)
class Layout:
    """Where every signal lives.

    - ``words``: the state words in emission order.
    - ``place[g]``: ``(word, lane)`` of gate ``g``.
    - ``in_place[i]``: ``(port, bit)`` of input wire ``i``, or None if no
      port covers it.
    - ``outputs[q]``: how output port ``q`` is gathered.
    """

    words: tuple[Word, ...]
    place: tuple[tuple[int, int], ...]
    in_place: tuple[tuple[int, int] | None, ...]
    outputs: tuple[Gather, ...]


_DIGITS = re.compile(r"\d+")


def _role(name: str) -> str:
    return _DIGITS.sub("", name)


def _popcount(x: int) -> int:
    return bin(x).count("1")


def _shifted(mask: int, shift: int) -> int:
    """``mask`` as seen through a vector group of ``shift`` (source lane =
    destination lane + shift)."""
    return (mask >> shift) if shift >= 0 else ((mask << -shift) & FULL)


def _longest_run(free: int) -> tuple[int, int]:
    """``(start, length)`` of the longest run of set bits in ``free``."""
    best = (0, 0)
    lane = 0
    while lane < LANES:
        if free >> lane & 1:
            start = lane
            while lane < LANES and free >> lane & 1:
                lane += 1
            if lane - start > best[1]:
                best = (start, lane - start)
        else:
            lane += 1
    return best


# --- classes -----------------------------------------------------------------


def _classes(circuit: Circuit, in_port_of: list[int | None], rounds: int) -> list[list[int]]:
    """Gate indices grouped by structural class, classes and members both in
    declaration order."""
    gates = circuit.gates
    keys: list[object] = [(g.type, _role(g.name)) for g in gates]

    def intern(raw: list[object]) -> list[int]:
        ids: dict[object, int] = {}
        return [ids.setdefault(k, len(ids)) for k in raw]

    def src(ref: Ref | None, sig: list[int]) -> object:
        if ref is None:
            return None
        if ref.kind == "in":
            return ("in", in_port_of[ref.index])
        return sig[ref.index]

    sig = intern(keys)
    for _ in range(rounds):
        refined = intern([(sig[i], src(g.a, sig), src(g.b, sig)) for i, g in enumerate(gates)])
        # Each round only ever splits classes; an unchanged count is a fixpoint.
        if max(refined, default=-1) == max(sig, default=-1):
            break
        sig = refined
    members: dict[int, list[int]] = {}
    for i, s in enumerate(sig):
        members.setdefault(s, []).append(i)
    return list(members.values())


# --- placement ---------------------------------------------------------------


@dataclass(slots=True)
class _Build:
    type: str
    labels: list[str] = field(default_factory=list)
    slots: dict[int, int] = field(default_factory=dict)  # lane -> gate
    free: int = FULL


class _Placer:
    def __init__(self, circuit: Circuit, classes: list[list[int]], in_place):
        self.gates = circuit.gates
        self.classes = classes
        self.in_place = in_place
        self.class_of = [0] * len(circuit.gates)
        for ci, members in enumerate(classes):
            for g in members:
                self.class_of[g] = ci
        self.words: list[_Build] = []
        self.open: dict[str, list[int]] = {}
        self.place: list[tuple[int, int] | None] = [None] * len(circuit.gates)

    def run(self) -> None:
        """Place every class, producers first (iterative DFS)."""
        state = [0] * len(self.classes)  # 0 new, 1 on the stack, 2 placed
        for root in range(len(self.classes)):
            if state[root]:
                continue
            state[root] = 1
            stack = [(root, iter(self._source_classes(root)))]
            while stack:
                ci, pending = stack[-1]
                for d in pending:
                    if state[d] == 0:
                        state[d] = 1
                        stack.append((d, iter(self._source_classes(d))))
                        break
                else:
                    stack.pop()
                    self._place_class(ci)
                    state[ci] = 2

    def _source_classes(self, ci: int) -> list[int]:
        seen: dict[int, None] = {}
        for g in self.classes[ci]:
            for ref in (self.gates[g].a, self.gates[g].b):
                if ref is not None and ref.kind == "gate":
                    seen.setdefault(self.class_of[ref.index], None)
        seen.pop(ci, None)
        return list(seen)

    def _source_pos(self, ref: Ref | None) -> Source:
        if ref is None:
            return None
        if ref.kind == "in":
            at = self.in_place[ref.index]
            return None if at is None else ("in", at[0], at[1])
        at = self.place[ref.index]
        return None if at is None else ("c", at[0], at[1])

    def _new_word(self, t: str) -> int:
        self.words.append(_Build(t))
        self.open.setdefault(t, []).append(len(self.words) - 1)
        return len(self.words) - 1

    def _candidates(self, t: str) -> list[int]:
        return list(reversed(self.open.get(t, [])[-_OPEN_SEARCH:]))

    def _put(self, w: int, lane: int, g: int, label: str) -> None:
        word = self.words[w]
        assert word.free >> lane & 1
        word.slots[lane] = g
        word.free &= ~(1 << lane)
        if label not in word.labels:
            word.labels.append(label)
        self.place[g] = (w, lane)
        if word.free == 0:
            self.open[word.type].remove(w)

    def _fit(self, t: str, lanes: int) -> tuple[int, int]:
        """A word and a shift placing the lane set ``lanes`` (shift 0 keeps
        the source lanes; the smallest shift that reuses an open word wins
        over opening a fresh one)."""
        lo = (lanes & -lanes).bit_length() - 1
        hi = lanes.bit_length() - 1
        shifts = sorted(range(-lo, LANES - hi), key=lambda d: (abs(d), -d))
        for w in self._candidates(t):
            free = self.words[w].free
            for d in shifts:
                moved = (lanes << d) if d >= 0 else (lanes >> -d)
                if moved & ~free == 0:
                    return w, d
        return self._new_word(t), 0

    def _place_class(self, ci: int) -> None:
        members = self.classes[ci]
        t = self.gates[members[0]].type
        label = _role(self.gates[members[0]].name)
        claimed: set[Source] = set()
        cohorts: dict[tuple[str, int], list[tuple[int, int]]] = {}
        loose: list[int] = []
        for g in members:
            for ref in (self.gates[g].a, self.gates[g].b):
                pos = self._source_pos(ref)
                if pos is not None and pos not in claimed:
                    claimed.add(pos)
                    cohorts.setdefault(pos[:2], []).append((pos[2], g))
                    break
            else:
                loose.append(g)
        for items in cohorts.values():
            lanes = 0
            for lane, _ in items:
                lanes |= 1 << lane
            w, d = self._fit(t, lanes)
            for lane, g in items:
                self._put(w, lane + d, g, label)
        i = 0
        while i < len(loose):
            best = (0, 0, -1)  # (length, start, word)
            for w in self._candidates(t):
                start, length = _longest_run(self.words[w].free)
                if length > best[0]:
                    best = (length, start, w)
            length, start, w = best
            if w < 0:
                w, start, length = self._new_word(t), 0, LANES
            n = min(length, len(loose) - i)
            for j in range(n):
                self._put(w, start + j, loose[i + j], label)
            i += n


# --- gathers -----------------------------------------------------------------


def plan_gather(
    sources: list[tuple[int, Source]],
    dest_mask: int,
    src_mask: dict[tuple[str, int], int],
) -> tuple[tuple[Group, ...], bool]:
    """Cover the destination lanes with gather groups.

    ``sources`` lists ``(dest_lane, source)`` for the used lanes; None sources
    contribute nothing (constant 0). ``src_mask[(array, index)]`` is the mask
    of lanes that can be nonzero in that source word. Returns the groups and
    whether their OR is *clean*: zero in every lane outside ``dest_mask``.

    Greedy: repeatedly take the vector or broadcast candidate covering the
    most still-uncovered lanes (vector wins ties, then lowest lane).
    """
    remaining: dict[int, tuple[str, int, int]] = {
        lane: src for lane, src in sources if src is not None
    }
    groups: list[Group] = []
    clean = True
    while remaining:
        vec: dict[tuple[str, int, int], int] = {}
        bc: dict[tuple[str, int, int], int] = {}
        for lane, (arr, idx, sl) in remaining.items():
            vec[(arr, idx, sl - lane)] = vec.get((arr, idx, sl - lane), 0) | (1 << lane)
            bc[(arr, idx, sl)] = bc.get((arr, idx, sl), 0) | (1 << lane)
        best_key, best_lanes, best_bcast = None, 0, False
        for key, lanes in vec.items():
            if _popcount(lanes) > _popcount(best_lanes):
                best_key, best_lanes = key, lanes
        for key, lanes in bc.items():
            if _popcount(lanes) > _popcount(best_lanes):
                best_key, best_lanes, best_bcast = key, lanes, True
        assert best_key is not None
        arr, idx, shift = best_key
        if best_bcast:
            junk = FULL & ~best_lanes
        else:
            junk = _shifted(src_mask[(arr, idx)], shift) & ~best_lanes
        masked = bool(junk & dest_mask)
        clean = clean and (masked or junk == 0)
        groups.append(Group(arr, idx, shift, best_bcast, best_lanes, masked))
        for lane in range(LANES):
            if best_lanes >> lane & 1:
                del remaining[lane]
    return tuple(groups), clean


def plan(circuit: Circuit, rounds: int = ROUNDS) -> Layout:
    """Lay out ``circuit`` (see the module docstring). Deterministic."""
    in_port_of: list[int | None] = [None] * len(circuit.inputs)
    in_place: list[tuple[int, int] | None] = [None] * len(circuit.inputs)
    for p, port in enumerate(circuit.in_ports):
        for b, ref in enumerate(port.refs):
            in_port_of[ref.index] = p
            in_place[ref.index] = (p, b)

    placer = _Placer(circuit, _classes(circuit, in_port_of, rounds), in_place)
    placer.run()
    place = placer.place
    assert all(at is not None for at in place)

    src_mask: dict[tuple[str, int], int] = {}
    for w, build in enumerate(placer.words):
        src_mask[("c", w)] = FULL & ~build.free
    for p, port in enumerate(circuit.in_ports):
        src_mask[("in", p)] = (1 << len(port.refs)) - 1

    words: list[Word] = []
    for build in placer.words:
        t = build.type
        mask = FULL & ~build.free
        slots = sorted(build.slots.items())
        a, clean_a = plan_gather(
            [(lane, placer._source_pos(circuit.gates[g].a)) for lane, g in slots], mask, src_mask
        )
        b, clean_b = plan_gather(
            [(lane, placer._source_pos(circuit.gates[g].b)) for lane, g in slots], mask, src_mask
        )
        if t == "AND":
            clean = clean_a or clean_b
        elif t in ("OR", "XOR"):
            clean = clean_a and clean_b
        elif t == "GND":
            clean = True
        else:  # NOT sets every unused lane; VCC is the mask itself
            clean = False
        label = "+".join(build.labels)
        words.append(Word(t, tuple(slots), mask, label, a, b, mask != FULL and not clean))

    outputs: list[Gather] = []
    for port in circuit.out_ports:
        mask = (1 << len(port.refs)) - 1
        groups, clean = plan_gather(
            [(bit, placer._source_pos(ref)) for bit, ref in enumerate(port.refs)], mask, src_mask
        )
        outputs.append(Gather(groups, mask, mask != FULL and not clean))

    return Layout(tuple(words), tuple(place), tuple(in_place), tuple(outputs))


def stats(layout: Layout) -> dict[str, float]:
    """Packing quality numbers for benchmarks and tests."""
    words = layout.words
    gates = sum(len(w.gates) for w in words)
    groups = sum(len(w.a) + len(w.b) for w in words)
    return {
        "gates": gates,
        "words": len(words),
        "full_words": sum(w.mask == FULL for w in words),
        "groups": groups,
        "groups_per_word": round(groups / len(words), 2) if words else 0.0,
        "bcast_groups": sum(g.bcast for w in words for g in w.a + w.b),
        "masked_groups": sum(g.masked for w in words for g in w.a + w.b),
        "masked_words": sum(w.masked for w in words),
        "lane_use": round(gates / (LANES * len(words)), 3) if words else 0.0,
    }
