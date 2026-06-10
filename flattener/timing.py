"""Timing analysis over the flat netlist (base_shdl.md §4.7).

Depth model: a top-level input is valid at cycle 0; a gate output is valid one
cycle after all of its inputs are (unit delay, one gate level per simulation
cycle). Power pins (__VCC__/__GND__) have depth 1 — their output holds the
default 0 at cycle 0 and only reflects the pin from cycle 1, so a consumer of
``max_depth`` (``settle()``) must wait for them like any other gate.

Feedback: gates are grouped into strongly connected components; an SCC with
more than one gate (or a self-loop) is feedback. Depths are computed on the
feedback-free subgraph — edges internal to a feedback SCC are excluded — so
``max_depth`` is the depth of the feedback-free shell only (§4.7).

``critical_path`` is a real edge path: each adjacent pair in the list is an
actual connection in the netlist, from a depth-0 start (an input wire, or a
power pin) through gates of strictly increasing depth to the deepest output.
"""

from __future__ import annotations

from .phases.flatten import FlatNetlist, Node


def compute_timing(netlist: FlatNetlist) -> dict:
    # Terminal predecessors of each gate, in netlist connection order.
    preds: dict[str, list[Node]] = {name: [] for name in netlist.gates}
    out_driver: dict[str, Node] = {}
    for src, dst, _pos in netlist.connections:
        match dst:
            case ("pin", gate, _pin):
                preds[gate].append(src)
            case ("out", wire):
                out_driver[wire] = src

    gate_preds = {
        g: [src[1] for src in srcs if src[0] == "pin"] for g, srcs in preds.items()
    }
    scc_of = _tarjan_sccs(gate_preds)
    feedback_sccs = {
        scc_of[g]
        for g, ps in gate_preds.items()
        if g in ps or any(scc_of[p] == scc_of[g] and p != g for p in ps)
    }
    has_feedback = bool(feedback_sccs)

    def excluded(g: str, p: str) -> bool:
        return scc_of[g] == scc_of[p] and scc_of[g] in feedback_sccs

    # Depths via memoized post-order DFS; with intra-feedback-SCC edges
    # excluded the remaining graph is a DAG, so this terminates.
    depth: dict[str, int] = {}

    def compute_depth(root: str) -> int:
        stack = [root]
        while stack:
            g = stack[-1]
            if g in depth:
                stack.pop()
                continue
            missing = [
                p for p in gate_preds[g] if p not in depth and not excluded(g, p)
            ]
            if missing:
                stack.extend(missing)
                continue
            depth[g] = 1 + max(
                (depth[p] for p in gate_preds[g] if not excluded(g, p)),
                default=0,
            )
            stack.pop()
        return depth[root]

    def node_depth(node: Node) -> int:
        return 0 if node[0] == "in" else compute_depth(node[1])

    output_depths = {wire: node_depth(out_driver[wire]) for wire in netlist.outputs}
    max_depth = max(output_depths.values(), default=0)

    critical_path: list[str] = []
    if netlist.outputs:
        deepest = next(w for w in netlist.outputs if output_depths[w] == max_depth)
        critical_path = _trace_path(deepest, out_driver[deepest], preds, depth, excluded)

    return {
        "max_depth": max_depth,
        "output_depths": output_depths,
        "is_combinational": not has_feedback,
        "has_feedback": has_feedback,
        "critical_path": critical_path,
    }


def _trace_path(out_wire, driver, preds, depth, excluded) -> list[str]:
    """Walk backward from an output's driver, at each gate stepping to the
    first predecessor exactly one level shallower, until a depth-0 start."""
    if driver[0] == "in":  # pass-through output
        return [driver[1], out_wire]
    rev = [out_wire]
    gate = driver[1]
    while True:
        rev.append(gate)
        want = depth[gate] - 1
        step = None
        for src in preds[gate]:
            if src[0] == "in":
                if want == 0:
                    step = src
                    break
            elif not excluded(gate, src[1]) and depth[src[1]] == want:
                step = src
                break
        if step is None:
            # No eligible shallower predecessor: a power pin, or a feedback
            # gate fed only from inside its SCC. The path starts here.
            break
        if step[0] == "in":
            rev.append(step[1])
            break
        gate = step[1]
    return rev[::-1]


def _tarjan_sccs(gate_preds: dict[str, list[str]]) -> dict[str, int]:
    """Iterative Tarjan; SCCs are identical on the reversed graph, so the
    predecessor lists serve directly as adjacency. Returns gate -> SCC id."""
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    scc_of: dict[str, int] = {}
    counter = 0
    scc_count = 0

    for root in gate_preds:
        if root in index:
            continue
        work: list[tuple[str, int]] = [(root, 0)]
        while work:
            node, pi = work[-1]
            if pi == 0:
                index[node] = lowlink[node] = counter
                counter += 1
                stack.append(node)
                on_stack.add(node)
            advanced = False
            neighbors = gate_preds[node]
            while pi < len(neighbors):
                n = neighbors[pi]
                pi += 1
                if n not in index:
                    work[-1] = (node, pi)
                    work.append((n, 0))
                    advanced = True
                    break
                if n in on_stack:
                    lowlink[node] = min(lowlink[node], index[n])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
            if lowlink[node] == index[node]:
                while True:
                    member = stack.pop()
                    on_stack.discard(member)
                    scc_of[member] = scc_count
                    if member == node:
                        break
                scc_count += 1
    return scc_of
