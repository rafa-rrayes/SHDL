"""
C Code Generator for Base SHDL

Generates optimized bit-packed C code for circuit simulation.

The key optimization is bit-packing: gates of the same type are packed into
64-bit lanes, allowing up to 64 gate instances to be evaluated in a single
CPU operation.
"""

from dataclasses import dataclass, field
from typing import Optional, TextIO
from io import StringIO
from collections import defaultdict

from .ast import Port, Instance, PrimitiveType
from .analyzer import AnalysisResult, GateInfo, SignalInfo, ConnectionInfo


@dataclass
class InputGathering:
    """Information about gathering a bit into an input vector."""
    gate_chunk: int          # Which chunk of this gate type
    input_port: str          # A or B
    lane_mask: str           # Hex mask for the lane
    source: SignalInfo       # Where the bit comes from


@dataclass
class OutputExtraction:
    """Information about extracting an output bit."""
    port_name: str           # Component output port name
    bit_index: Optional[int] # 0-based bit index (None for single-bit)
    gate_type: PrimitiveType # Which gate type
    gate_chunk: int          # Which chunk
    lane: int                # Which lane (bit position)


class CodeGenerator:
    """
    Generates optimized C code from analyzed Base SHDL.
    
    Output structure:
    1. Includes and typedefs
    2. State structure (packed gate outputs)
    3. tick() function (evaluates all gates)
    4. Extract functions (for output ports)
    5. DutContext structure
    6. API functions (reset, poke, peek, step)
    """
    
    def __init__(self, analysis: AnalysisResult):
        self.analysis = analysis
        self.component = analysis.component
        self.output = StringIO()
        self.indent_level = 0
        
        # Computed during generation
        self.input_gatherings: dict[PrimitiveType, dict[int, dict[str, list[InputGathering]]]] = defaultdict(
            lambda: defaultdict(lambda: defaultdict(list))
        )  # type -> chunk -> port -> gatherings
        
        self.output_extractions: list[OutputExtraction] = []
        
        # Track which outputs come from direct port-to-port connections
        self.direct_outputs: dict[str, SignalInfo] = {}  # output port -> source
    
    def generate(self) -> str:
        """Generate complete C code."""
        self._precompute()
        
        self._emit_header()
        self._emit_state_struct()
        self._emit_tick_function()
        self._emit_extract_functions()
        self._emit_dut_context()
        self._emit_api_functions()
        
        return self.output.getvalue()
    
    def _write(self, text: str) -> None:
        """Write text to output."""
        self.output.write(text)
    
    def _writeln(self, line: str = "") -> None:
        """Write an indented line."""
        if line:
            self._write("    " * self.indent_level + line + "\n")
        else:
            self._write("\n")
    
    def _indent(self) -> None:
        """Increase indentation."""
        self.indent_level += 1
    
    def _dedent(self) -> None:
        """Decrease indentation."""
        self.indent_level = max(0, self.indent_level - 1)
    
    def _precompute(self) -> None:
        """Precompute gathering and extraction information."""
        # Analyze each connection
        for conn_info in self.analysis.analyzed_connections:
            src = conn_info.source
            dst = conn_info.destination
            
            if dst.is_instance_port:
                # Gathering: source -> gate input
                self._add_gathering(src, dst)
            elif dst.is_component_port:
                if src.is_instance_port:
                    # Extraction: gate output -> component output
                    self._add_extraction(src, dst)
                elif src.is_component_port:
                    # Direct: component input -> component output
                    self._add_direct_output(src, dst)
    
    def _add_gathering(self, src: SignalInfo, dst: SignalInfo) -> None:
        """Add a gathering operation (source -> gate input)."""
        inst_name = dst.instance_name
        input_port = dst.instance_port
        
        if inst_name not in self.analysis.gate_info:
            return
        
        gate = self.analysis.gate_info[inst_name]
        ptype = gate.primitive
        chunk = gate.chunk
        lane_mask = f"0x{gate.lane_mask:016x}ull"
        
        gathering = InputGathering(
            gate_chunk=chunk,
            input_port=input_port,
            lane_mask=lane_mask,
            source=src
        )
        
        self.input_gatherings[ptype][chunk][input_port].append(gathering)
    
    def _add_extraction(self, src: SignalInfo, dst: SignalInfo) -> None:
        """Add an extraction operation (gate output -> component output)."""
        inst_name = src.instance_name
        
        if inst_name not in self.analysis.gate_info:
            return
        
        gate = self.analysis.gate_info[inst_name]
        
        extraction = OutputExtraction(
            port_name=dst.port_name,
            bit_index=dst.bit_index,
            gate_type=gate.primitive,
            gate_chunk=gate.chunk,
            lane=gate.lane
        )
        
        self.output_extractions.append(extraction)
    
    def _add_direct_output(self, src: SignalInfo, dst: SignalInfo) -> None:
        """Add a direct output (component input -> component output)."""
        key = dst.port_name
        if dst.bit_index is not None:
            key = f"{dst.port_name}_{dst.bit_index}"
        self.direct_outputs[key] = src
    
    def _emit_header(self) -> None:
        """Emit file header with includes."""
        comp_name = self.component.name
        
        self._writeln(f"/*")
        self._writeln(f" * Generated C simulation code for {comp_name}")
        self._writeln(f" * ")
        self._writeln(f" * This file was automatically generated by shdlc.")
        self._writeln(f" * Do not edit manually.")
        self._writeln(f" */")
        self._writeln()
        self._writeln("#include <stdint.h>")
        self._writeln("#include <string.h>")
        self._writeln("#include <stdio.h>")
        self._writeln()
    
    def _emit_state_struct(self) -> None:
        """Emit the State structure containing packed gate outputs."""
        self._writeln("/* Packed gate outputs */")
        self._writeln("typedef struct {")
        self._indent()
        
        # Emit a field for each gate type chunk
        for ptype in [PrimitiveType.XOR, PrimitiveType.AND, PrimitiveType.OR, PrimitiveType.NOT]:
            num_chunks = self.analysis.get_chunks_for_type(ptype)
            for chunk in range(num_chunks):
                self._writeln(f"uint64_t {ptype.name}_O_{chunk};")
        
        # VCC and GND are constants, but we include them for uniformity
        for ptype in [PrimitiveType.VCC, PrimitiveType.GND]:
            num_chunks = self.analysis.get_chunks_for_type(ptype)
            for chunk in range(num_chunks):
                self._writeln(f"uint64_t {ptype.name}_O_{chunk};")
        
        self._dedent()
        self._writeln("} State;")
        self._writeln()
    
    def _emit_tick_function(self) -> None:
        """Emit the tick function that evaluates all gates."""
        # Build input parameter list
        input_params = []
        for port in self.component.inputs:
            input_params.append(f"uint64_t {port.name}")
        
        params = ", ".join(["State s"] + input_params)
        
        self._writeln("/* Evaluate all gates for one cycle */")
        self._writeln(f"static inline State tick({params}) {{")
        self._indent()
        
        self._writeln("State n = s;")
        self._writeln()
        
        # Handle VCC and GND first (they're constants)
        self._emit_constant_gates()
        
        # For each gate type, emit gathering and evaluation
        for ptype in [PrimitiveType.XOR, PrimitiveType.AND, PrimitiveType.OR, PrimitiveType.NOT]:
            self._emit_gate_type_evaluation(ptype)
        
        self._writeln("return n;")
        
        self._dedent()
        self._writeln("}")
        self._writeln()
    
    def _emit_constant_gates(self) -> None:
        """Emit code for VCC and GND (constant) gates."""
        # VCC gates - all 1s in their lanes
        vcc_chunks = self.analysis.get_chunks_for_type(PrimitiveType.VCC)
        for chunk in range(vcc_chunks):
            gates = [g for g in self.analysis.gates_by_type.get(PrimitiveType.VCC, []) if g.chunk == chunk]
            if gates:
                mask = 0
                for gate in gates:
                    mask |= gate.lane_mask
                self._writeln(f"n.VCC_O_{chunk} = 0x{mask:016x}ull;  /* VCC constants */")
        
        # GND gates - all 0s (already 0 from state copy)
        gnd_chunks = self.analysis.get_chunks_for_type(PrimitiveType.GND)
        for chunk in range(gnd_chunks):
            self._writeln(f"/* n.GND_O_{chunk} = 0; */ /* GND constants (already 0) */")
        
        if vcc_chunks > 0 or gnd_chunks > 0:
            self._writeln()
    
    def _emit_gate_type_evaluation(self, ptype: PrimitiveType) -> None:
        """Emit gathering and evaluation code for a gate type."""
        num_chunks = self.analysis.get_chunks_for_type(ptype)
        if num_chunks == 0:
            return
        
        self._writeln(f"/* {ptype.name} gates */")
        
        for chunk in range(num_chunks):
            # Calculate active lanes mask
            gates = [g for g in self.analysis.gates_by_type.get(ptype, []) if g.chunk == chunk]
            active_mask = 0
            for gate in gates:
                active_mask |= gate.lane_mask
            
            # Build input vectors
            input_a_name = f"{ptype.name}_{chunk}_A"
            input_b_name = f"{ptype.name}_{chunk}_B"
            
            # Input A
            self._writeln(f"uint64_t {input_a_name} = 0ull;")
            gatherings_a = self.input_gatherings.get(ptype, {}).get(chunk, {}).get("A", [])
            for g in gatherings_a:
                gather_expr = self._make_gather_expr(g.source)
                self._writeln(f"{input_a_name} |= ({gather_expr}) & {g.lane_mask};")
            
            # Input B (for 2-input gates)
            if ptype not in (PrimitiveType.NOT, PrimitiveType.VCC, PrimitiveType.GND):
                self._writeln(f"uint64_t {input_b_name} = 0ull;")
                gatherings_b = self.input_gatherings.get(ptype, {}).get(chunk, {}).get("B", [])
                for g in gatherings_b:
                    gather_expr = self._make_gather_expr(g.source)
                    self._writeln(f"{input_b_name} |= ({gather_expr}) & {g.lane_mask};")
            
            # Evaluate
            mask_str = f"0x{active_mask:016x}ull"
            if ptype == PrimitiveType.AND:
                self._writeln(f"n.{ptype.name}_O_{chunk} = ({input_a_name} & {input_b_name}) & {mask_str};")
            elif ptype == PrimitiveType.OR:
                self._writeln(f"n.{ptype.name}_O_{chunk} = ({input_a_name} | {input_b_name}) & {mask_str};")
            elif ptype == PrimitiveType.XOR:
                self._writeln(f"n.{ptype.name}_O_{chunk} = ({input_a_name} ^ {input_b_name}) & {mask_str};")
            elif ptype == PrimitiveType.NOT:
                self._writeln(f"n.{ptype.name}_O_{chunk} = (~{input_a_name}) & {mask_str};")
            
            self._writeln()
    
    def _make_gather_expr(self, src: SignalInfo) -> str:
        """
        Generate the bit-gathering expression.
        
        The idiom: ((uint64_t)-( ((value >> bit_pos) & 1u) ))
        - Extract bit: (value >> bit_pos) & 1u -> 0 or 1
        - Broadcast: (uint64_t)-(x) -> 0x0 or 0xFFFFFFFFFFFFFFFF
        """
        if src.is_component_port:
            # Source is a component input
            port_name = src.port_name
            if src.bit_index is not None:
                return f"((uint64_t)-( (({port_name} >> {src.bit_index}) & 1u) ))"
            else:
                return f"((uint64_t)-( ({port_name} & 1u) ))"
        else:
            # Source is a gate output
            inst_name = src.instance_name
            if inst_name not in self.analysis.gate_info:
                return "0ull"
            
            gate = self.analysis.gate_info[inst_name]
            ptype = gate.primitive
            chunk = gate.chunk
            lane = gate.lane
            
            return f"((uint64_t)-( ((s.{ptype.name}_O_{chunk} >> {lane}) & 1u) ))"
    
    def _emit_extract_functions(self) -> None:
        """Emit functions to extract output port values."""
        # Group extractions by output port
        by_port: dict[str, list[OutputExtraction]] = defaultdict(list)
        for ext in self.output_extractions:
            by_port[ext.port_name].append(ext)
        
        for port in self.component.outputs:
            self._emit_extract_function(port, by_port.get(port.name, []))
    
    def _emit_extract_function(self, port: Port, extractions: list[OutputExtraction]) -> None:
        """Emit an extraction function for one output port."""
        func_name = f"extract_{port.name}"
        
        self._writeln(f"static inline uint64_t {func_name}(const State *s) {{")
        self._indent()
        
        if not extractions and port.name not in self.direct_outputs:
            # Check for direct output (port to port)
            key = port.name
            if key in self.direct_outputs:
                src = self.direct_outputs[key]
                if src.is_component_port:
                    self._writeln(f"/* Direct pass-through from input */")
                    self._writeln(f"return 0ull; /* Not available in tick() - handled in peek() */")
            else:
                self._writeln(f"return 0ull; /* No connections found */")
        elif len(extractions) == 0:
            # Single-bit port with no extractions - might be direct
            self._writeln(f"return 0ull;")
        elif port.width is None:
            # Single-bit output
            ext = extractions[0]
            self._writeln(f"return (s->{ext.gate_type.name}_O_{ext.gate_chunk} >> {ext.lane}) & 1ull;")
        else:
            # Multi-bit output
            self._writeln("return")
            self._indent()
            
            # Sort by bit index
            sorted_exts = sorted(extractions, key=lambda e: e.bit_index if e.bit_index else 0)
            
            for i, ext in enumerate(sorted_exts):
                bit_idx = ext.bit_index if ext.bit_index is not None else 0
                line = f"(((s->{ext.gate_type.name}_O_{ext.gate_chunk} >> {ext.lane}) & 1ull) << {bit_idx})"
                
                if i < len(sorted_exts) - 1:
                    line += " |"
                else:
                    line += ";"
                
                self._writeln(line)
            
            self._dedent()
        
        self._dedent()
        self._writeln("}")
        self._writeln()
    
    def _emit_dut_context(self) -> None:
        """Emit the DUT context structure."""
        self._writeln("/* DUT simulation context */")
        self._writeln("typedef struct {")
        self._indent()
        
        self._writeln("State current;")
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
        
        self._dedent()
        self._writeln("} DutContext;")
        self._writeln()
        
        self._writeln("static DutContext dut = {0};")
        self._writeln()
    
    def _emit_api_functions(self) -> None:
        """Emit the public API functions."""
        self._emit_reset_function()
        self._emit_poke_function()
        self._emit_peek_function()
        self._emit_step_function()
    
    def _emit_reset_function(self) -> None:
        """Emit the reset() function."""
        self._writeln("/* Reset all state to zero */")
        self._writeln("void reset(void) {")
        self._indent()
        self._writeln("memset(&dut, 0, sizeof(dut));")
        self._dedent()
        self._writeln("}")
        self._writeln()
    
    def _emit_poke_function(self) -> None:
        """Emit the poke() function."""
        self._writeln("/* Set an input signal value */")
        self._writeln("void poke(const char *signal, uint64_t value) {")
        self._indent()
        
        for i, port in enumerate(self.component.inputs):
            cond = "if" if i == 0 else "} else if"
            width = port.width if port.width else 1
            mask = (1 << width) - 1
            
            self._writeln(f'{cond} (strcmp(signal, "{port.name}") == 0) {{')
            self._indent()
            self._writeln(f"dut.input_{port.name} = value & 0x{mask:x}ull;")
            self._writeln("dut.outputs_valid = 0;")
            self._dedent()
        
        if self.component.inputs:
            self._writeln("} else {")
            self._indent()
            self._writeln('fprintf(stderr, "Unknown signal \'%s\'\\n", signal);')
            self._dedent()
            self._writeln("}")
        else:
            self._writeln('fprintf(stderr, "Unknown signal \'%s\'\\n", signal);')
        
        self._dedent()
        self._writeln("}")
        self._writeln()
    
    def _emit_peek_function(self) -> None:
        """Emit the peek() function."""
        self._writeln("/* Read a signal value */")
        self._writeln("uint64_t peek(const char *signal) {")
        self._indent()
        
        # Check inputs first
        for port in self.component.inputs:
            self._writeln(f'if (strcmp(signal, "{port.name}") == 0) return dut.input_{port.name};')
        
        self._writeln()
        
        # Ensure outputs are computed
        self._writeln("/* Compute outputs if needed */")
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
        
        # Check outputs
        for port in self.component.outputs:
            self._writeln(f'if (strcmp(signal, "{port.name}") == 0) return dut.output_{port.name};')
        
        self._writeln()
        self._writeln('fprintf(stderr, "Unknown signal \'%s\'\\n", signal);')
        self._writeln("return 0ull;")
        
        self._dedent()
        self._writeln("}")
        self._writeln()
    
    def _emit_step_function(self) -> None:
        """Emit the step() function."""
        self._writeln("/* Advance simulation by N cycles */")
        self._writeln("void step(int cycles) {")
        self._indent()
        
        # Build tick call
        tick_args = ["dut.current"]
        for port in self.component.inputs:
            tick_args.append(f"dut.input_{port.name}")
        
        self._writeln("for (int i = 0; i < cycles; ++i) {")
        self._indent()
        self._writeln(f"dut.current = tick({', '.join(tick_args)});")
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


def generate(analysis: AnalysisResult) -> str:
    """Generate C code from analysis result."""
    generator = CodeGenerator(analysis)
    return generator.generate()
