"""
Debug-Aware Bus Code Generator.

Extends BusCodeGenerator with debug features:
- Gate name table mapping gate names to group/singleton + bit position
- peek_gate() / peek_gate_previous() for inspecting internal gates
- Cycle counter and get_cycle()
- Previous state tracking for breakpoint change detection

Key difference from parent: all bus group and singleton gate results are stored
in static file-scope variables (not locals in tick), so peek_gate can read them.
"""

from ..compiler.ast import PrimitiveType
from .codegen import BusCodeGenerator, _select_c_type, _width_mask
from .analyzer import AnalysisResult, BusGroup


class BusDebugCodeGenerator(BusCodeGenerator):
    """Bus code generator with debug API additions.

    Overrides _emit_group_eval and _emit_unit to assign to static globals
    instead of declaring locals, so gate values persist after tick() returns.
    """

    def __init__(self, analysis: AnalysisResult):
        super().__init__(analysis)
        self._group_list: list[BusGroup] = []
        self._group_idx: dict[str, int] = {}

    def generate(self) -> str:
        self._emit_header()
        self._emit_state_struct()
        self._emit_gate_globals()
        self._emit_dut_context_debug()
        self._emit_gate_table()
        # Parent's tick — our overrides make it assign to statics
        self._emit_tick_function()
        self._emit_api_functions_debug()
        self._emit_debug_api()
        return self.output.getvalue()

    # ── Gate globals (static file-scope vars) ──

    def _emit_gate_globals(self):
        """Emit static variables for all groups and singletons."""
        self._group_list = list(self.analysis.bus_groups)
        self._group_idx = {g.name: i for i, g in enumerate(self._group_list)}

        self._w("/* Bus group values (persist between tick calls for debug) */")
        for group in self._group_list:
            c_type = _select_c_type(group.width)
            self._w(f"static {c_type} {group.name};")
            self._w(f"static {c_type} dbg_prev_{group.name};")

        if self.analysis.singleton_gates:
            self._w()
            self._w("/* Singleton gate values */")
            for gate in self.analysis.singleton_gates:
                self._w(f"static uint8_t s_{gate.name};")
                self._w(f"static uint8_t dbg_prev_s_{gate.name};")

        self._w()

    # ── DUT context (debug version with previous + cycle) ──

    def _emit_dut_context_debug(self):
        self._w("typedef struct {")
        self._indent()
        self._w("State current;")
        self._w("State previous;")
        for name, width in self.analysis.input_ports.items():
            self._w(f"{_select_c_type(width)} input_{name};")
        for name, width in self.analysis.output_ports.items():
            self._w(f"{_select_c_type(width)} output_{name};")
        self._w("int outputs_valid;")
        self._w("uint64_t cycle_count;")
        self._dedent()
        self._w("} DutContext;")
        self._w()
        self._w("static DutContext dut = {0};")
        self._w()

    # ── Gate table ──

    def _emit_gate_table(self):
        """Emit gate lookup table: name -> (is_group, index, bit_pos)."""
        self._w("typedef struct {")
        self._indent()
        self._w("const char *name;")
        self._w("uint8_t is_group;")
        self._w("uint16_t idx;")
        self._w("uint8_t bit_pos;")
        self._dedent()
        self._w("} GateEntry;")
        self._w()

        entries: list[tuple[str, int, int, int]] = []

        for group in self._group_list:
            gidx = self._group_idx[group.name]
            for pos, gate in enumerate(group.gates):
                entries.append((gate.name, 1, gidx, pos))

        for i, gate in enumerate(self.analysis.singleton_gates):
            entries.append((gate.name, 0, i, 0))

        self._w("static const GateEntry GATE_TABLE[] = {")
        self._indent()
        for name, is_grp, idx, bit in entries:
            self._w(f'{{"{name}", {is_grp}, {idx}, {bit}}},')
        if not entries:
            self._w('{NULL, 0, 0, 0},')
        self._dedent()
        self._w("};")
        self._w(f"static const size_t NUM_GATES = {len(entries)};")
        self._w()

    # ── Override group/unit emit to assign to statics ──

    def _emit_group_eval(self, group: BusGroup, is_feedback: bool):
        """Assign to static global instead of declaring a local."""
        var = group.name
        self._group_vars[group.name] = var

        ptype = PrimitiveType.from_string(group.primitive)
        mask = _width_mask(group.width)

        a_expr = self._source_to_expr(group.input_sources.get("A"), group, is_feedback)
        b_expr = self._source_to_expr(group.input_sources.get("B"), group, is_feedback)

        if ptype == PrimitiveType.NOT:
            self._w(f"{var} = (~({a_expr})) & {mask};")
        elif ptype == PrimitiveType.AND:
            self._w(f"{var} = ({a_expr}) & ({b_expr});")
        elif ptype == PrimitiveType.OR:
            self._w(f"{var} = ({a_expr}) | ({b_expr});")
        elif ptype == PrimitiveType.XOR:
            self._w(f"{var} = ({a_expr}) ^ ({b_expr});")

    def _emit_unit(self, unit):
        """Assign to static global instead of declaring a local."""
        if isinstance(unit, BusGroup):
            self._emit_group_eval(unit, is_feedback=False)
        else:
            var = f"s_{unit.name}"
            self._singleton_vars[unit.name] = var
            expr = self._build_singleton_expr(unit)
            self._w(f"{var} = {expr};")

    # ── API functions (debug versions) ──

    def _emit_api_functions_debug(self):
        self._emit_reset_debug()
        self._emit_poke()   # parent's
        self._emit_peek()   # parent's
        self._emit_step_debug()

    def _emit_reset_debug(self):
        self._w("void reset(void) {")
        self._indent()
        self._w("memset(&dut, 0, sizeof(dut));")
        # Zero all static gate variables
        for group in self._group_list:
            self._w(f"{group.name} = 0;")
            self._w(f"dbg_prev_{group.name} = 0;")
        for gate in self.analysis.singleton_gates:
            self._w(f"s_{gate.name} = 0;")
            self._w(f"dbg_prev_s_{gate.name} = 0;")
        self._dedent()
        self._w("}")
        self._w()

    def _emit_step_debug(self):
        self._w("void step(int cycles) {")
        self._indent()
        self._w("for (int i = 0; i < cycles; ++i) {")
        self._indent()

        # Save previous state for breakpoint detection
        self._w("dut.previous = dut.current;")
        for group in self._group_list:
            self._w(f"dbg_prev_{group.name} = {group.name};")
        for gate in self.analysis.singleton_gates:
            self._w(f"dbg_prev_s_{gate.name} = s_{gate.name};")

        self._w("tick();")
        self._w("dut.cycle_count++;")
        self._dedent()
        self._w("}")
        self._w("dut.outputs_valid = 1;")
        self._dedent()
        self._w("}")
        self._w()

    # ── Debug API functions ──

    def _emit_debug_api(self):
        self._emit_get_cycle()
        self._emit_peek_gate()
        self._emit_peek_gate_previous()
        self._emit_get_num_gates()

    def _emit_get_cycle(self):
        self._w("uint64_t get_cycle(void) {")
        self._indent()
        self._w("return dut.cycle_count;")
        self._dedent()
        self._w("}")
        self._w()

    def _emit_peek_gate(self):
        self._w("uint64_t peek_gate(const char *gate_name) {")
        self._indent()

        # Ensure circuit is evaluated
        self._w("if (!dut.outputs_valid) {")
        self._indent()
        self._w("tick();")
        self._w("dut.outputs_valid = 1;")
        self._dedent()
        self._w("}")
        self._w()

        self._w("for (size_t i = 0; i < NUM_GATES; i++) {")
        self._indent()
        self._w("if (strcmp(GATE_TABLE[i].name, gate_name) == 0) {")
        self._indent()

        self._w("if (GATE_TABLE[i].is_group) {")
        self._indent()
        self._w("uint64_t val;")
        self._emit_group_switch("val", is_prev=False)
        self._w("return (val >> GATE_TABLE[i].bit_pos) & 1ull;")
        self._dedent()

        self._w("} else {")
        self._indent()
        self._emit_singleton_switch(is_prev=False)
        self._dedent()
        self._w("}")

        self._dedent()
        self._w("}")
        self._dedent()
        self._w("}")
        self._w()
        self._w("return 0ull;")
        self._dedent()
        self._w("}")
        self._w()

    def _emit_peek_gate_previous(self):
        self._w("uint64_t peek_gate_previous(const char *gate_name) {")
        self._indent()

        self._w("for (size_t i = 0; i < NUM_GATES; i++) {")
        self._indent()
        self._w("if (strcmp(GATE_TABLE[i].name, gate_name) == 0) {")
        self._indent()

        self._w("if (GATE_TABLE[i].is_group) {")
        self._indent()
        self._w("uint64_t val;")
        self._emit_group_switch("val", is_prev=True)
        self._w("return (val >> GATE_TABLE[i].bit_pos) & 1ull;")
        self._dedent()

        self._w("} else {")
        self._indent()
        self._emit_singleton_switch(is_prev=True)
        self._dedent()
        self._w("}")

        self._dedent()
        self._w("}")
        self._dedent()
        self._w("}")
        self._w()
        self._w("return 0ull;")
        self._dedent()
        self._w("}")
        self._w()

    def _emit_get_num_gates(self):
        self._w("size_t get_num_gates(void) {")
        self._indent()
        self._w("return NUM_GATES;")
        self._dedent()
        self._w("}")
        self._w()

    # ── Helpers for peek_gate switch statements ──

    def _emit_group_switch(self, target_var: str, is_prev: bool):
        prefix = "dbg_prev_" if is_prev else ""
        self._w("switch (GATE_TABLE[i].idx) {")
        self._indent()
        for idx, group in enumerate(self._group_list):
            self._w(f"case {idx}: {target_var} = {prefix}{group.name}; break;")
        self._w(f"default: {target_var} = 0; break;")
        self._dedent()
        self._w("}")

    def _emit_singleton_switch(self, is_prev: bool):
        prefix = "dbg_prev_s_" if is_prev else "s_"
        self._w("switch (GATE_TABLE[i].idx) {")
        self._indent()
        for idx, gate in enumerate(self.analysis.singleton_gates):
            self._w(f"case {idx}: return (uint64_t){prefix}{gate.name};")
        self._w("default: return 0ull;")
        self._dedent()
        self._w("}")
