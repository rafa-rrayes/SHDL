"""
Debug-Aware Code Generator for Base SHDL

Extends the standard code generator with debug features:
- Gate name table for runtime gate lookup
- peek_gate() function for inspecting internal gates
- Cycle counter
- Debug info generation
"""

from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
import json

from .ast import Port, Instance, PrimitiveType
from .analyzer import AnalysisResult, GateInfo
from .codegen import CodeGenerator


@dataclass
class DebugCodeGenOptions:
    """Options for debug code generation."""
    generate_gate_table: bool = True
    generate_peek_gate: bool = True
    generate_cycle_counter: bool = True
    generate_state_snapshot: bool = False
    waveform_support: bool = False


class DebugCodeGenerator(CodeGenerator):
    """
    Extended code generator with debug features.
    
    Adds:
    - Gate name table mapping names to lane/chunk
    - peek_gate() for reading any gate output
    - get_cycle() for cycle counting
    - Optional waveform recording
    """
    
    def __init__(self, analysis: AnalysisResult, options: Optional[DebugCodeGenOptions] = None):
        super().__init__(analysis)
        self.debug_options = options or DebugCodeGenOptions()
        
        # Build gate info list ordered by lane assignment
        self.gate_list: list[tuple[str, GateInfo]] = []
        for name, info in sorted(analysis.gate_info.items()):
            self.gate_list.append((name, info))
    
    def generate(self) -> str:
        """Generate complete C code with debug features."""
        self._precompute()
        
        self._emit_header()
        self._emit_debug_defines()
        self._emit_state_struct()
        self._emit_gate_table()
        self._emit_tick_function()
        self._emit_extract_functions()
        self._emit_dut_context_debug()
        self._emit_api_functions()
        self._emit_debug_api_functions()
        
        return self.output.getvalue()
    
    def _emit_debug_defines(self) -> None:
        """Emit debug-related preprocessor defines."""
        self._writeln("/* Debug build features */")
        self._writeln("#define SHDB_DEBUG 1")
        if self.debug_options.waveform_support:
            self._writeln("#define SHDB_WAVEFORM 1")
        self._writeln()
    
    def _emit_gate_table(self) -> None:
        """Emit the gate name table for runtime lookup."""
        if not self.debug_options.generate_gate_table:
            return
        
        self._writeln("/* Gate type enum */")
        self._writeln("enum GateType {")
        self._indent()
        self._writeln("GATE_XOR = 0,")
        self._writeln("GATE_AND = 1,")
        self._writeln("GATE_OR = 2,")
        self._writeln("GATE_NOT = 3,")
        self._writeln("GATE_VCC = 4,")
        self._writeln("GATE_GND = 5,")
        self._dedent()
        self._writeln("};")
        self._writeln()
        
        self._writeln("/* Gate information table */")
        self._writeln("typedef struct {")
        self._indent()
        self._writeln("const char *name;")
        self._writeln("uint8_t type;   /* GateType */")
        self._writeln("uint8_t chunk;")
        self._writeln("uint8_t lane;")
        self._dedent()
        self._writeln("} GateTableEntry;")
        self._writeln()
        
        self._writeln("static const GateTableEntry GATE_TABLE[] = {")
        self._indent()
        
        for name, info in self.gate_list:
            gate_type = self._primitive_to_gate_type(info.primitive)
            self._writeln(f'{{"{name}", {gate_type}, {info.chunk}, {info.lane}}},')
        
        self._dedent()
        self._writeln("};")
        self._writeln(f"static const size_t NUM_GATES = {len(self.gate_list)};")
        self._writeln()
    
    def _primitive_to_gate_type(self, ptype: PrimitiveType) -> str:
        """Convert PrimitiveType to gate type enum name."""
        mapping = {
            PrimitiveType.XOR: "GATE_XOR",
            PrimitiveType.AND: "GATE_AND",
            PrimitiveType.OR: "GATE_OR",
            PrimitiveType.NOT: "GATE_NOT",
            PrimitiveType.VCC: "GATE_VCC",
            PrimitiveType.GND: "GATE_GND",
        }
        return mapping.get(ptype, "GATE_XOR")
    
    def _emit_dut_context_debug(self) -> None:
        """Emit the DUT context structure with debug additions."""
        self._writeln("/* DUT simulation context (debug build) */")
        self._writeln("typedef struct {")
        self._indent()
        
        self._writeln("State current;")
        self._writeln("State previous;  /* For breakpoint change detection */")
        self._writeln()
        
        # Input storage
        self._writeln("/* Input storage */")
        for port in self.component.inputs:
            self._writeln(f"uint64_t input_{port.name};")
        self._writeln()
        
        # Output cache
        self._writeln("/* Cached outputs */")
        for port in self.component.outputs:
            self._writeln(f"uint64_t output_{port.name};")
        self._writeln()
        
        self._writeln("int outputs_valid;")
        self._writeln()
        
        # Debug additions
        if self.debug_options.generate_cycle_counter:
            self._writeln("/* Debug: cycle counter */")
            self._writeln("uint64_t cycle_count;")
        
        self._dedent()
        self._writeln("} DutContext;")
        self._writeln()
        
        self._writeln("static DutContext dut = {0};")
        self._writeln()
    
    def _emit_api_functions(self) -> None:
        """Emit the public API functions with debug enhancements."""
        self._emit_reset_function_debug()
        self._emit_poke_function()
        self._emit_peek_function()
        self._emit_step_function_debug()
    
    def _emit_reset_function_debug(self) -> None:
        """Emit reset() with cycle counter reset."""
        self._writeln("/* Reset all state to zero */")
        self._writeln("void reset(void) {")
        self._indent()
        self._writeln("memset(&dut, 0, sizeof(dut));")
        self._dedent()
        self._writeln("}")
        self._writeln()
    
    def _emit_step_function_debug(self) -> None:
        """Emit step() with cycle counter increment and previous state tracking."""
        self._writeln("/* Advance simulation by N cycles */")
        self._writeln("void step(int cycles) {")
        self._indent()
        
        # Build tick call
        tick_args = ["dut.current"]
        for port in self.component.inputs:
            tick_args.append(f"dut.input_{port.name}")
        
        self._writeln("for (int i = 0; i < cycles; ++i) {")
        self._indent()
        self._writeln("/* Save current state for breakpoint detection */")
        self._writeln("dut.previous = dut.current;")
        self._writeln(f"dut.current = tick({', '.join(tick_args)});")
        if self.debug_options.generate_cycle_counter:
            self._writeln("dut.cycle_count++;")
        self._dedent()
        self._writeln("}")
        self._writeln()
        
        # Update cached outputs
        for port in self.component.outputs:
            self._writeln(f"dut.output_{port.name} = extract_{port.name}(&dut.current);")
        
        self._writeln("dut.outputs_valid = 1;")
        
        self._dedent()
        self._writeln("}")
        self._writeln()
    
    def _emit_debug_api_functions(self) -> None:
        """Emit debug-specific API functions."""
        if self.debug_options.generate_cycle_counter:
            self._emit_get_cycle_function()
        
        if self.debug_options.generate_peek_gate:
            self._emit_peek_gate_function()
            self._emit_peek_gate_previous_function()
        
        self._emit_get_num_gates_function()
        self._emit_get_gate_info_function()
    
    def _emit_get_cycle_function(self) -> None:
        """Emit get_cycle() function."""
        self._writeln("/* Get current cycle count */")
        self._writeln("uint64_t get_cycle(void) {")
        self._indent()
        self._writeln("return dut.cycle_count;")
        self._dedent()
        self._writeln("}")
        self._writeln()
    
    def _emit_peek_gate_function(self) -> None:
        """Emit peek_gate() function for reading any gate output."""
        self._writeln("/* Read a gate output by name */")
        self._writeln("uint64_t peek_gate(const char *gate_name) {")
        self._indent()
        
        self._writeln("/* Ensure outputs are computed */")
        self._writeln("if (!dut.outputs_valid) {")
        self._indent()
        
        # Build tick call
        tick_args = ["dut.current"]
        for port in self.component.inputs:
            tick_args.append(f"dut.input_{port.name}")
        
        self._writeln(f"dut.current = tick({', '.join(tick_args)});")
        
        # Extract outputs
        for port in self.component.outputs:
            self._writeln(f"dut.output_{port.name} = extract_{port.name}(&dut.current);")
        
        self._writeln("dut.outputs_valid = 1;")
        
        self._dedent()
        self._writeln("}")
        self._writeln()
        
        self._writeln("/* Look up gate in table */")
        self._writeln("for (size_t i = 0; i < NUM_GATES; i++) {")
        self._indent()
        self._writeln("if (strcmp(GATE_TABLE[i].name, gate_name) == 0) {")
        self._indent()
        self._writeln("uint64_t chunk_val;")
        self._writeln("switch (GATE_TABLE[i].type) {")
        self._indent()
        
        # Handle each gate type
        for ptype in [PrimitiveType.XOR, PrimitiveType.AND, PrimitiveType.OR, 
                      PrimitiveType.NOT, PrimitiveType.VCC, PrimitiveType.GND]:
            num_chunks = self.analysis.get_chunks_for_type(ptype)
            if num_chunks > 0:
                gate_enum = self._primitive_to_gate_type(ptype)
                self._writeln(f"case {gate_enum}:")
                self._indent()
                if num_chunks == 1:
                    self._writeln(f"chunk_val = dut.current.{ptype.name}_O_0;")
                else:
                    self._writeln("switch (GATE_TABLE[i].chunk) {")
                    self._indent()
                    for chunk in range(num_chunks):
                        self._writeln(f"case {chunk}: chunk_val = dut.current.{ptype.name}_O_{chunk}; break;")
                    self._writeln("default: return 0ull;")
                    self._dedent()
                    self._writeln("}")
                self._writeln("break;")
                self._dedent()
        
        self._writeln("default: return 0ull;")
        self._dedent()
        self._writeln("}")
        self._writeln("return (chunk_val >> GATE_TABLE[i].lane) & 1ull;")
        self._dedent()
        self._writeln("}")
        self._dedent()
        self._writeln("}")
        self._writeln()
        
        self._writeln('fprintf(stderr, "Unknown gate \'%s\'\\n", gate_name);')
        self._writeln("return 0ull;")
        
        self._dedent()
        self._writeln("}")
        self._writeln()
    
    def _emit_peek_gate_previous_function(self) -> None:
        """Emit peek_gate_previous() for reading gate value before last step."""
        self._writeln("/* Read a gate output from before the last step (for breakpoint detection) */")
        self._writeln("uint64_t peek_gate_previous(const char *gate_name) {")
        self._indent()
        
        self._writeln("/* Look up gate in table */")
        self._writeln("for (size_t i = 0; i < NUM_GATES; i++) {")
        self._indent()
        self._writeln("if (strcmp(GATE_TABLE[i].name, gate_name) == 0) {")
        self._indent()
        self._writeln("uint64_t chunk_val;")
        self._writeln("switch (GATE_TABLE[i].type) {")
        self._indent()
        
        # Handle each gate type - read from previous state
        for ptype in [PrimitiveType.XOR, PrimitiveType.AND, PrimitiveType.OR, 
                      PrimitiveType.NOT, PrimitiveType.VCC, PrimitiveType.GND]:
            num_chunks = self.analysis.get_chunks_for_type(ptype)
            if num_chunks > 0:
                gate_enum = self._primitive_to_gate_type(ptype)
                self._writeln(f"case {gate_enum}:")
                self._indent()
                if num_chunks == 1:
                    self._writeln(f"chunk_val = dut.previous.{ptype.name}_O_0;")
                else:
                    self._writeln("switch (GATE_TABLE[i].chunk) {")
                    self._indent()
                    for chunk in range(num_chunks):
                        self._writeln(f"case {chunk}: chunk_val = dut.previous.{ptype.name}_O_{chunk}; break;")
                    self._writeln("default: return 0ull;")
                    self._dedent()
                    self._writeln("}")
                self._writeln("break;")
                self._dedent()
        
        self._writeln("default: return 0ull;")
        self._dedent()
        self._writeln("}")
        self._writeln("return (chunk_val >> GATE_TABLE[i].lane) & 1ull;")
        self._dedent()
        self._writeln("}")
        self._dedent()
        self._writeln("}")
        self._writeln()
        
        self._writeln("return 0ull;")
        
        self._dedent()
        self._writeln("}")
        self._writeln()
    
    def _emit_get_num_gates_function(self) -> None:
        """Emit function to get number of gates."""
        self._writeln("/* Get number of gates */")
        self._writeln("size_t get_num_gates(void) {")
        self._indent()
        self._writeln("return NUM_GATES;")
        self._dedent()
        self._writeln("}")
        self._writeln()
    
    def _emit_get_gate_info_function(self) -> None:
        """Emit function to get gate info by index."""
        self._writeln("/* Get gate info by index */")
        self._writeln("int get_gate_info(size_t index, const char **name, uint8_t *type, uint8_t *chunk, uint8_t *lane) {")
        self._indent()
        self._writeln("if (index >= NUM_GATES) return 0;")
        self._writeln("*name = GATE_TABLE[index].name;")
        self._writeln("*type = GATE_TABLE[index].type;")
        self._writeln("*chunk = GATE_TABLE[index].chunk;")
        self._writeln("*lane = GATE_TABLE[index].lane;")
        self._writeln("return 1;")
        self._dedent()
        self._writeln("}")
        self._writeln()


def generate_debug(analysis: AnalysisResult, options: Optional[DebugCodeGenOptions] = None) -> str:
    """Generate C code with debug features from analysis result."""
    generator = DebugCodeGenerator(analysis, options)
    return generator.generate()
