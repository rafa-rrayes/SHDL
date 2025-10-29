"""
SHDL Compiler Library
=====================
A compiler for the Simple Hardware Description Language (SHDL).

This library provides:
- SHDLParser: Parse SHDL files into a component representation
- Component flattening: Inline hierarchical components down to primitive gates
- C code generation: Generate bit-packed, registered C simulator libraries

Usage:
    from pathlib import Path
    from shdl_compiler import SHDLParser, generate_c_bitpacked
    
    # Parse a SHDL file
    search_paths = [Path("SHDL_components")]
    parser = SHDLParser(search_paths)
    component = parser.parse_file(Path("adder16.shdl"))
    
    # Flatten to primitive gates
    component = parser.flatten_all_levels(component)
    
    # Generate C library code
    c_code = generate_c_bitpacked(component)
    with open("adder16.c", "w") as f:
        f.write(c_code)
"""

import re
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
from dataclasses import dataclass, field
from copy import deepcopy
from collections import defaultdict


@dataclass
class Port:
    """Represents an input or output port."""
    name: str
    width: int = 1  # Number of bits (default 1 for single-bit)
    is_input: bool = True


@dataclass
class Instance:
    """Represents a gate or component instance."""
    name: str
    component_type: str
    inputs: Dict[str, str] = field(default_factory=dict)  # port_name -> connected_signal


@dataclass
class Component:
    """Represents a SHDL component."""
    name: str
    inputs: List[Port] = field(default_factory=list)
    outputs: List[Port] = field(default_factory=list)
    instances: List[Instance] = field(default_factory=list)
    connections: List[Tuple[str, str]] = field(default_factory=list)  # (from, to)
    imports: Dict[str, List[str]] = field(default_factory=dict)  # module -> [components]


class SHDLParser:
    """Parser for SHDL files."""
    
    def __init__(self, search_paths: List[Path]):
        """
        Initialize the SHDL parser.
        
        Args:
            search_paths: List of directories to search for imported components
        """
        self.search_paths = search_paths
        self.components: Dict[str, Component] = {}
        self.STDGATES = {"AND", "OR", "NOT", "XOR", "NAND", "NOR", "XNOR"}
    
    def parse_file(self, filepath: Path) -> Component:
        """
        Parse a SHDL file and return the component.
        
        Args:
            filepath: Path to the SHDL file
            
        Returns:
            Parsed Component object
        """
        content = filepath.read_text()
        
        # Remove comments
        content = re.sub(r'#.*$', '', content, flags=re.MULTILINE)
        
        # Parse imports
        imports = self._parse_imports(content)
        
        # Parse component declaration
        comp = self._parse_component(content)
        comp.imports = imports
        
        # Cache the component
        self.components[comp.name] = comp
        self.parent = comp.name
        
        # Load imported components
        self._load_imports(comp, filepath.parent)

        return comp
    
    def _parse_imports(self, content: str) -> Dict[str, List[str]]:
        """Parse import statements."""
        imports = {}
        
        # Match: use module::{Component1, Component2};
        pattern = r'use\s+(\w+)\s*::\s*\{([^}]+)\}'
        for match in re.finditer(pattern, content):
            module = match.group(1)
            components_str = match.group(2)
            components = [c.strip() for c in components_str.split(',')]
            imports[module] = components
            
        return imports
    
    def _parse_component(self, content: str) -> Component:
        """Parse component declaration."""
        # Match: component Name(inputs) -> (outputs) { ... }
        pattern = r'component\s+(\w+)\s*\(([^)]*)\)\s*->\s*\(([^)]*)\)\s*\{(.*)\}'
        match = re.search(pattern, content, re.DOTALL)
        
        if not match:
            raise ValueError("Invalid component declaration")
        
        comp_name = match.group(1)
        inputs_str = match.group(2)
        outputs_str = match.group(3)
        body = match.group(4)
        
        comp = Component(name=comp_name)
        
        # Parse inputs
        comp.inputs = self._parse_ports(inputs_str, is_input=True)
        
        # Parse outputs
        comp.outputs = self._parse_ports(outputs_str, is_input=False)
        
        # Parse body (instances and connections)
        self._parse_body(comp, body)
        
        return comp
    
    def _parse_ports(self, ports_str: str, is_input: bool) -> List[Port]:
        """Parse port declarations."""
        ports = []
        
        if not ports_str.strip():
            return ports
        
        for port_decl in ports_str.split(','):
            port_decl = port_decl.strip()
            if not port_decl:
                continue
            
            # Check for bit width: Name[16]
            match = re.match(r'(\w+)\[(\d+)\]', port_decl)
            if match:
                name = match.group(1)
                width = int(match.group(2))
                ports.append(Port(name=name, width=width, is_input=is_input))
            else:
                # Single-bit port
                ports.append(Port(name=port_decl, width=1, is_input=is_input))
        
        return ports
    
    def _parse_body(self, comp: Component, body: str):
        """Parse component body (instances and connections)."""
        # Expand generators first
        body = self._expand_generators(body)
        
        # Split into instances and connections
        connect_match = re.search(r'connect\s*\{(.*)\}', body, re.DOTALL)
        
        if connect_match:
            instances_part = body[:connect_match.start()]
            connections_part = connect_match.group(1)
        else:
            instances_part = body
            connections_part = ""
        
        # Parse instances
        self._parse_instances(comp, instances_part)
        
        # Parse connections
        self._parse_connections(comp, connections_part)
    
    def _expand_generators(self, body: str) -> str:
        """
        Expand generator syntax:
        >i[2, 16]{ ... use {i}, {i-1}, {i+1}, etc. ... }
        >k[8]{ ... }
        """
        def expand_generator(match):
            var = match.group(1)      # e.g., "i"
            range_spec = match.group(2)
            content = match.group(3)

            # Parse range: either "N" or "start, end"
            if ',' in range_spec:
                start_str, end_str = range_spec.split(',')
                start = int(start_str.strip())
                end = int(end_str.strip())
            else:
                start = 1
                end = int(range_spec.strip())

            result_chunks = []

            # For each iteration bind var to i and expand {<expr using var>}
            for i in range(start, end + 1):
                def eval_braced_expr(m):
                    expr = m.group(1).strip()
                    # Allow only the loop var name (var) as 'i' in the expression.
                    # We map whatever the loop variable is to the name 'i' for simplicity.
                    # This lets "{i-1}" work regardless of the chosen variable name.
                    try:
                        value = eval(expr, {"__builtins__": None}, {"i": i})
                    except Exception as e:
                        raise ValueError(f"Invalid generator expression '{{{expr}}}' "
                                        f"with {var}={i}: {e}")
                    # Normalize ints/floats to string
                    if isinstance(value, float) and value.is_integer():
                        value = int(value)
                    return str(value)

                # Replace ALL {...} occurrences (names, indices, signal labels, etc.)
                expanded = re.sub(r'\{([^{}]+)\}', eval_braced_expr, content)
                result_chunks.append(expanded)

            return '\n'.join(result_chunks)

        # Keep expanding until no more generators (handle multiple generators in the body)
        prev_body = None
        max_iterations = 10
        iteration = 0
        while prev_body != body and iteration < max_iterations:
            prev_body = body
            body = re.sub(
                r'>\s*(\w+)\[([^\]]+)\]\s*\{((?:[^{}]|\{[^{}]*\})*)\}',
                expand_generator,
                body,
                count=1,
                flags=re.MULTILINE | re.DOTALL
            )
            iteration += 1

        return body

    def _parse_instances(self, comp: Component, instances_str: str):
        """Parse instance declarations."""
        # Match: name: Type;
        pattern = r'(\w+)\s*:\s*(\w+)\s*;'
        
        for match in re.finditer(pattern, instances_str):
            name = match.group(1)
            comp_type = match.group(2)
            comp.instances.append(Instance(name=name, component_type=comp_type))
    
    def _parse_connections(self, comp: Component, connections_str: str):
        """Parse connection statements."""
        # Match: signal -> port;
        pattern = r'([^\s;]+)\s*->\s*([^\s;]+)\s*;'
        
        for match in re.finditer(pattern, connections_str):
            from_sig = match.group(1).strip()
            to_sig = match.group(2).strip()
            comp.connections.append((from_sig, to_sig))
    
    def _load_imports(self, comp: Component, base_path: Path):
        """Load imported components from files."""
        for module, components in comp.imports.items():
            if module == "stdgates":
                continue  # Standard gates are built-in
            
            # Try to find the module file
            for search_path in [base_path] + self.search_paths:
                module_file = search_path / f"{module}.shdl"
                if module_file.exists():
                    imported_comp = self.parse_file(module_file)
                    break

    def flatten_component(self, parent: Component) -> Component:
        """
        Flatten the given component by inlining all instances of non-standard gate types.
        
        Args:
            parent: Component to flatten
            
        Returns:
            Flattened component with only standard gates
        """

        # --- Helpers -------------------------------------------------------------

        def ports_of(defn: "Component"):
            return {p.name for p in defn.inputs}, {p.name for p in defn.outputs}

        def output_drivers(defn: "Component"):
            """
            Map child output port -> internal driver pin (e.g., 'Sum' -> 'x2.O').
            """
            m = {}
            for src, dst in defn.connections:
                if '.' not in dst:  # bare output port
                    m[dst] = src
            return m

        def prefixed_internal(pin: str, inst_name: str):
            """
            Prefix internal instance pins: 'x1.O' -> 'fa1_x1.O'.
            Leave bare ports ('A', 'Sum') unchanged (handled elsewhere).
            """
            if '.' in pin:
                inst, port = pin.split('.', 1)
                return f"{inst_name}_{inst}.{port}"
            return pin

        def is_abstract_pin(token: str):
            # an abstract pin looks like 'fa1.Cin' or 'fa1.Cout'
            return '.' in token and '[' not in token and token.count('.') == 1

        # Index original connections
        conns_from = defaultdict(list)
        conns_to   = defaultdict(list)
        for c in parent.connections:
            s, d = c
            conns_from[s].append(c)
            conns_to[d].append(c)

        # Identify instances to inline and keep the rest
        instances_to_inline = [inst for inst in parent.instances if inst.component_type not in self.STDGATES]
        new_instances = [inst for inst in parent.instances if inst.component_type in self.STDGATES]
        new_connections = []

        # Prepare import merging (and later clean-up of now-unused target symbols)
        merged_imports = deepcopy(getattr(parent, "imports", {}))

        # Build per-instance metadata for all children that will be inlined
        inlined_meta = {}  # inst_name -> dict(...)
        for inst in instances_to_inline:
            child_def = self.components[inst.component_type]
            in_ports, out_ports = ports_of(child_def)
            out_drv = output_drivers(child_def)
            inlined_meta[inst.name] = {
                "def": child_def,
                "in_ports": in_ports,
                "out_ports": out_ports,
                "out_drivers": out_drv,
            }

        # Global maps for substitution
        # (1) Abstract OUTPUT -> concrete internal driver pin (prefixed)
        abstract_out_to_driver = {}
        for inst in instances_to_inline:
            meta = inlined_meta[inst.name]
            for outp, driver_pin in meta["out_drivers"].items():
                abstract = f"{inst.name}.{outp}"               # e.g., 'fa1.Cout'
                concrete = prefixed_internal(driver_pin, inst.name)  # 'fa1_o1.O'
                abstract_out_to_driver[abstract] = concrete

        def resolve_output_ref(token: str) -> str:
            """Replace 'inst.OutPort' with its internal driver pin, repeatedly if needed."""
            while token in abstract_out_to_driver:
                token = abstract_out_to_driver[token]
            return token

        # (2) Abstract INPUT -> resolved external net (after output resolution)
        abstract_in_to_net = {}
        for inst in instances_to_inline:
            meta = inlined_meta[inst.name]
            for inp in meta["in_ports"]:
                abs_input = f"{inst.name}.{inp}"  # e.g., 'fa2.Cin'
                if abs_input in conns_to and conns_to[abs_input]:
                    upstream = conns_to[abs_input][-1][0]  # last writer wins
                    upstream = resolve_output_ref(upstream)  # resolve if it was 'faX.Out'
                    abstract_in_to_net[abs_input] = upstream
                else:
                    # Unconnected input; leave unmapped. (Could default/raise as needed.)
                    pass

        def resolve_input_ref(token: str) -> str:
            """Replace 'inst.InPort' with its resolved external net, repeatedly if needed."""
            seen = set()
            while token in abstract_in_to_net and token not in seen:
                seen.add(token)
                token = abstract_in_to_net[token]
                token = resolve_output_ref(token)
            return token

        # Helper: is the destination an abstract INPUT of another inlined child?
        def is_inlined_abstract_input(dst: str) -> bool:
            if not is_abstract_pin(dst):
                return False
            inst_name, port = dst.split('.', 1)
            if inst_name not in inlined_meta:
                return False
            return port in inlined_meta[inst_name]["in_ports"]

        # Bring in internals for each inlined child
        for inst in instances_to_inline:
            meta = inlined_meta[inst.name]
            child_def = meta["def"]

            # (a) Add internal instances with prefix
            for cinst in child_def.instances:
                renamed = deepcopy(cinst)
                renamed.name = f"{inst.name}_{cinst.name}"
                new_instances.append(renamed)

            # (b) Merge child's imports
            if getattr(child_def, "imports", None):
                for lib, syms in child_def.imports.items():
                    merged_imports.setdefault(lib, [])
                    for s in syms:
                        if s not in merged_imports[lib]:
                            merged_imports[lib].append(s)

            # (c) Recreate child's internal wiring with substitutions:
            #     - child input ports -> resolved external net (input map)
            #     - internal pins -> prefixed_internal(...)
            #     - child output ports are NOT emitted as ports (we wire their drivers elsewhere)
            input_external = {p: abstract_in_to_net.get(f"{inst.name}.{p}") for p in meta["in_ports"]}

            for src, dst in child_def.connections:
                # Resolve source
                if '.' not in src:  # child input port
                    upstream = input_external.get(src)
                    if upstream is None:
                        # Skip unconnected; or raise if strict is desired
                        continue
                    flat_src = resolve_output_ref(upstream)
                else:
                    flat_src = prefixed_internal(src, inst.name)

                # Resolve destination
                if '.' not in dst:
                    # Child output port: skip here — parent edges will be created below
                    continue
                else:
                    flat_dst = prefixed_internal(dst, inst.name)
                    new_connections.append((flat_src, flat_dst))

            # (d) Rewire parent edges that referenced child OUTPUTS (e.g., 'fa1.Cout' -> X)
            #     But do NOT create edges into abstract inputs of other inlined children
            #     (those will be realized by that child's own internal wiring above).
            for outp in meta["out_ports"]:
                abs_out = f"{inst.name}.{outp}"
                if abs_out not in conns_from:
                    continue
                driver = resolve_output_ref(abs_out)  # should give prefixed internal pin
                for (_src, dst) in conns_from[abs_out]:
                    if is_inlined_abstract_input(dst):
                        # Skip; the receiving child will handle via its internal mapping.
                        continue
                    # Otherwise, we can keep the destination:
                    new_connections.append((driver, dst))

        # Keep original parent connections that don't touch any abstract pins of inlined children
        abstract_pins = set()
        for inst in instances_to_inline:
            meta = inlined_meta[inst.name]
            for p in meta["in_ports"] | meta["out_ports"]:
                abstract_pins.add(f"{inst.name}.{p}")

        def touches_any_abstract(conn):
            s, d = conn
            return (s in abstract_pins) or (d in abstract_pins)

        for conn in parent.connections:
            if not touches_any_abstract(conn):
                new_connections.append(conn)

        # Final sweep: substitute any leftover abstract references on either side
        finalized = []
        for s, d in new_connections:
            s2 = resolve_output_ref(s)
            s2 = resolve_input_ref(s2)   # just in case a chain pointed to an abstract input
            d2 = resolve_output_ref(d)   # unlikely for destinations, but safe
            d2 = resolve_input_ref(d2)
            # Drop any connection that still targets an abstract input (shouldn't happen)
            if is_inlined_abstract_input(d2):
                continue
            finalized.append((s2, d2))

        # Optional: prune imports of fully inlined component types (e.g., 'FullAdder')
        if merged_imports:
            cleaned_imports = {}
            for lib, syms in merged_imports.items():
                kept = [s for s in syms if s in self.STDGATES]
                if kept:
                    cleaned_imports[lib] = kept
            merged_imports = cleaned_imports

        # Commit
        parent.instances = new_instances
        parent.connections = finalized
        parent.imports = merged_imports
        return parent
    
    def flatten_all_levels(self, parent: Component, max_passes: int = 64) -> Component:
        """
        Repeatedly inline until no instances of non-standard gate types remain,
        or until max_passes is reached (to avoid accidental cycles).
        
        Args:
            parent: Component to flatten
            max_passes: Maximum number of flattening passes
            
        Returns:
            Fully flattened component
        """
        def count_targets(c):
            return sum(1 for i in c.instances if i.component_type not in self.STDGATES)

        for _ in range(max_passes):
            before = count_targets(parent)
            if before == 0:
                break
            self.flatten_component(parent)
            after = count_targets(parent)
            if after >= before:
                # No progress; likely cyclic or missing defs — bail out safely.
                break
        return parent


def generate_c_bitpacked(component: Component) -> str:
    """
    Generate a fast, bit-packed, registered C simulator library for the given netlist.

    Generates a library API with:
      - void reset(): Reset all state to zero
      - void poke(const char *signal_name, uint64_t value): Set an input
      - uint64_t peek(const char *signal_name): Read an input or output
      - void eval(): Compute outputs combinationally (no state commit)
      - void step(int cycles): Advance simulation by N cycles
      - void dump_vcd(const char *filename): Placeholder for VCD generation
    
    Args:
        component: Flattened component with only standard gates
        
    Returns:
        C source code as a string
    """

    # ---------- helpers ----------
    def c_ident(s):
        s = s.replace('.', '_')
        s = s.replace('[', '_').replace(']', '')
        s = re.sub(r'[^a-zA-Z0-9_]', '_', s)
        if re.match(r'^[0-9]', s):
            s = '_' + s
        return s

    def is_bit(ref):
        return bool(re.match(r'^[A-Za-z_]\w*\[\d+\]$', ref))

    def parse_bit(ref):
        m = re.match(r'^([A-Za-z_]\w*)\[(\d+)\]$', ref)
        if not m:
            raise ValueError(f'Not a bit ref: {ref}')
        return m.group(1), int(m.group(2))

    def is_inst_pin(ref):
        return bool(re.match(r'^[A-Za-z_]\w*\.[A-Za-z_]\w*$', ref))

    def split_inst_pin(ref):
        m = re.match(r'^([A-Za-z_]\w*)\.([A-Za-z_]\w*)$', ref)
        if not m:
            raise ValueError(f'Not an instance pin: {ref}')
        return m.group(1), m.group(2)

    # ---------- model digest ----------
    inputs = {p.name: p for p in component.inputs if p.is_input}
    outputs = {p.name: p for p in component.outputs if not p.is_input}
    insts = {i.name: i for i in component.instances}

    # map: type -> ordered list of instance names (lane order)
    type_to_insts = defaultdict(list)
    for i in component.instances:
        type_to_insts[i.component_type].append(i.name)
    # lane index per instance: inst_name -> (type, chunk_idx, lane_within_chunk)
    inst_lane = {}
    type_chunks = {}  # type -> number of 64-bit chunks needed
    for t, lst in type_to_insts.items():
        num_chunks = (len(lst) + 63) // 64  # ceiling division
        type_chunks[t] = num_chunks
        for lane, name in enumerate(lst):
            chunk_idx = lane // 64
            lane_in_chunk = lane % 64
            inst_lane[name] = (t, chunk_idx, lane_in_chunk)

    # Collect per-instance input pin wiring: inst -> {pin: src_token}
    pin_wires = defaultdict(dict)
    # Collect top-level output bit drivers: 'Out[3]' -> src_token
    out_src = {}

    for src, dst in component.connections:
        if is_inst_pin(dst):
            i, pin = split_inst_pin(dst)
            pin_wires[i][pin] = src
        else:
            # must be top-level output bit or scalar
            if dst in outputs:
                out_src[f'{dst}[1]'] = src
            else:
                out_src[dst] = src

    # Gate pin sets (per primitive)
    BIN_OP = {
        'AND': '&',
        'OR':  '|',
        'XOR': '^',
        'NAND': None,  # computed as ~(A & B)
        'NOR':  None,  # computed as ~(A | B)
    }
    UNI_OP = {
        'NOT': None,   # computed as ~A
    }
    supported_types = set(BIN_OP) | set(UNI_OP)
    for i in component.instances:
        if i.component_type not in supported_types:
            raise ValueError(f"Unsupported gate type: {i.component_type}")

    # For each (type, chunk, pin, source_token) build a 64-bit mask
    masks = defaultdict(int)  # key = (type, chunk_idx, pin, source_token) -> uint64 mask
    type_chunk_active_mask = defaultdict(int)  # (type, chunk_idx) -> mask of lanes that exist

    # Special constant-0 source for unconnected pins
    CONST_ZERO = '__CONST_ZERO__'
    
    for t, lst in type_to_insts.items():
        for lane, iname in enumerate(lst):
            chunk_idx = lane // 64
            lane_in_chunk = lane % 64
            type_chunk_active_mask[(t, chunk_idx)] |= (1 << lane_in_chunk)
            # determine required pins
            if t in BIN_OP:
                for pin in ('A', 'B'):
                    if pin not in pin_wires[iname]:
                        # Use constant 0 for unconnected pins (graceful degradation)
                        src = CONST_ZERO
                    else:
                        src = pin_wires[iname][pin]
                    masks[(t, chunk_idx, pin, src)] |= (1 << lane_in_chunk)
            else:  # unary: NOT
                if 'A' not in pin_wires[iname]:
                    # Use constant 0 for unconnected pins (graceful degradation)
                    src = CONST_ZERO
                else:
                    src = pin_wires[iname]['A']
                masks[(t, chunk_idx, 'A', src)] |= (1 << lane_in_chunk)

    # Unique source tokens that appear anywhere
    sources = sorted({src for (_, _, _, src) in masks.keys()})

    # Build a small resolver to C-expr that yields a 0/1 value for a source token
    def bit_expr_0_1(src, state_var='s'):
        # constant zero for unconnected pins?
        if src == CONST_ZERO:
            return '0u'
        # input bit?
        if is_bit(src):
            base, idx = parse_bit(src)
            if base in inputs:
                # ((A >> (idx-1)) & 1u)
                return f'(({c_ident(base)} >> {idx-1}) & 1u)'
        # scalar input?
        if src in inputs and inputs[src].width == 1:
            return f'({c_ident(src)} & 1u)'
        # instance output?
        if is_inst_pin(src):
            iname, pin = split_inst_pin(src)
            if pin != 'O':
                # only outputs are read as sources
                raise ValueError(f"Unexpected non-output pin as source: {src}")
            t, chunk_idx, lane_in_chunk = inst_lane[iname]
            return f'(({state_var}.{c_ident(t)}_O_{chunk_idx} >> {lane_in_chunk}) & 1u)'
        # top-level output as source is unusual; if someone did it, treat like input error
        raise ValueError(f'Unrecognized source token: {src}')

    # ---------- emit C ----------
    out = []
    W = out.append

    W('#include <stdint.h>')
    W('#include <stdio.h>')
    W('#include <string.h>')
    W('')
    W(f'// Auto-generated bit-packed registered simulator for {component.name}')
    W('// Each gate family packs up to 64 instances into a 64-bit lane vector.')
    W('// Next state is computed from previous state and current inputs (2-phase update).')
    W('//')
    W('// Library API:')
    W('//   void reset(void);')
    W('//   void poke(const char *signal_name, uint64_t value);')
    W('//   uint64_t peek(const char *signal_name);')
    W('//   void eval(void);')
    W('//   void step(int cycles);')
    W('//   void dump_vcd(const char *filename);')
    W('')

    # State struct: one or more 64-bit vectors per gate type (chunks)
    W('typedef struct {')
    for t in type_to_insts:
        num_chunks = type_chunks[t]
        for chunk_idx in range(num_chunks):
            W(f'    uint64_t {c_ident(t)}_O_{chunk_idx};  // chunk {chunk_idx} of {t} outputs')
    W('} State;')
    W('')

    # tick signature: pass each input port as uint64_t (lower width bits used)
    params = ['State s']
    for p in component.inputs:
        params.append(f'uint64_t {c_ident(p.name)}')
    W(f'static inline State tick({", ".join(params)})' + ' {')
    W('    State n = s;')
    W('')

    # For each gate type and chunk, build input vectors from masks
    # Use branchless selection: vec |= (-(bit)) & MASK
    for t, inst_list in type_to_insts.items():
        num_chunks = type_chunks[t]
        for chunk_idx in range(num_chunks):
            active_mask = type_chunk_active_mask[(t, chunk_idx)]
            if t in BIN_OP:
                for pin in ('A', 'B'):
                    W(f'    uint64_t {c_ident(t)}_{chunk_idx}_{pin} = 0ull;')
                    for src in sources:
                        m = masks.get((t, chunk_idx, pin, src), 0)
                        if m == 0:
                            continue
                        bexpr = bit_expr_0_1(src, state_var='s')
                        W(f'    {c_ident(t)}_{chunk_idx}_{pin} |= ((uint64_t)-( {bexpr} )) & 0x{m:016x}ull;')
                # Compute next outputs
                if BIN_OP[t] is None:
                    # NAND/NOR
                    if t == 'NAND':
                        W(f'    n.{c_ident(t)}_O_{chunk_idx} = ~({c_ident(t)}_{chunk_idx}_A & {c_ident(t)}_{chunk_idx}_B) & 0x{active_mask:016x}ull;')
                    elif t == 'NOR':
                        W(f'    n.{c_ident(t)}_O_{chunk_idx} = ~({c_ident(t)}_{chunk_idx}_A | {c_ident(t)}_{chunk_idx}_B) & 0x{active_mask:016x}ull;')
                    else:
                        raise AssertionError('Unhandled BIN_OP None case')
                else:
                    op = BIN_OP[t]
                    W(f'    n.{c_ident(t)}_O_{chunk_idx} = ({c_ident(t)}_{chunk_idx}_A {op} {c_ident(t)}_{chunk_idx}_B) & 0x{active_mask:016x}ull;')
            else:
                # unary NOT
                W(f'    uint64_t {c_ident(t)}_{chunk_idx}_A = 0ull;')
                for src in sources:
                    m = masks.get((t, chunk_idx, 'A', src), 0)
                    if m == 0:
                        continue
                    bexpr = bit_expr_0_1(src, state_var='s')
                    W(f'    {c_ident(t)}_{chunk_idx}_A |= ((uint64_t)-( {bexpr} )) & 0x{m:016x}ull;')
                W(f'    n.{c_ident(t)}_O_{chunk_idx} = ~({c_ident(t)}_{chunk_idx}_A) & 0x{active_mask:016x}ull;')
            W('')

    W('    return n;')
    W('}')
    W('')

    # Generate helper functions to extract outputs from state
    for p in component.outputs:
        func_name = f'extract_{c_ident(p.name).lower()}'
        W(f'static inline uint64_t {func_name}(const State *s) {{')
        
        if p.width == 1:
            # Single-bit output
            key = f'{p.name}[1]'
            if key not in out_src and p.name in out_src:
                key = p.name
            src = out_src.get(key)
            if src is None:
                raise ValueError(f'No driver for output {p.name}')
            
            if is_bit(src):
                base, idx = parse_bit(src)
                if base not in inputs:
                    raise ValueError(f'Output {p.name} reads unknown bit source {src}')
                W(f'    // Output connected to input bit, not state-dependent')
                W(f'    return 0ull;  // Will be computed from inputs in peek()')
            elif is_inst_pin(src):
                iname, pin = split_inst_pin(src)
                if pin != 'O':
                    raise ValueError(f'Output {p.name} cannot read non-output pin {src}')
                t, chunk_idx, lane_in_chunk = inst_lane[iname]
                W(f'    return (s->{c_ident(t)}_O_{chunk_idx} >> {lane_in_chunk}) & 1ull;')
            else:
                # scalar input
                if src in inputs and inputs[src].width == 1:
                    W(f'    // Output connected to input, not state-dependent')
                    W(f'    return 0ull;  // Will be computed from inputs in peek()')
                else:
                    raise ValueError(f'Output {p.name} has unsupported driver {src}')
        else:
            # Multi-bit output: reconstruct from bit drivers
            terms = []
            for i in range(1, p.width + 1):
                key = f'{p.name}[{i}]'
                src = out_src.get(key)
                if src is None:
                    raise ValueError(f'No driver for output {key}')
                
                if is_bit(src):
                    # Will be handled in peek() since it's input-dependent
                    terms.append('0ull')
                elif is_inst_pin(src):
                    iname, pin = split_inst_pin(src)
                    if pin != 'O':
                        raise ValueError(f'Output {key} cannot read non-output pin {src}')
                    t, chunk_idx, lane_in_chunk = inst_lane[iname]
                    terms.append(f'(((s->{c_ident(t)}_O_{chunk_idx} >> {lane_in_chunk}) & 1ull) << {i-1})')
                else:
                    # scalar input routed to a bit
                    terms.append('0ull')
            
            W(f'    return {" | ".join(terms)};')
        
        W('}')
        W('')

    # DUT context structure
    W('typedef struct {')
    W('    State current;')
    W('    State pending;')
    for p in component.inputs:
        mask = (1 << p.width) - 1 if p.width < 64 else 0xFFFFFFFFFFFFFFFF
        W(f'    uint64_t input_{c_ident(p.name)};')
    for p in component.outputs:
        W(f'    uint64_t {c_ident(p.name).lower()};')
        if p.width == 1:
            W(f'    uint8_t {c_ident(p.name).lower()}_bit;')
    W('    int pending_valid;')
    W('    int outputs_valid;')
    W("} DutContext;")
    W('')
    W('static DutContext dut = {0};')
    W('')

    # Helper functions
    W('static void mark_dirty(void) {')
    W('    dut.outputs_valid = 0;')
    W('    dut.pending_valid = 0;')
    W('}')
    W('')

    W('static void compute_pending(void) {')
    tick_args = ['dut.current'] + [f'dut.input_{c_ident(p.name)}' for p in component.inputs]
    W(f'    dut.pending = tick({", ".join(tick_args)});')
    
    # Extract outputs from pending state
    for p in component.outputs:
        func_name = f'extract_{c_ident(p.name).lower()}'
        W(f'    dut.{c_ident(p.name).lower()} = {func_name}(&dut.pending);')
        
        # Handle input pass-through or additional computation for outputs
        if p.width == 1:
            key = f'{p.name}[1]'
            if key not in out_src and p.name in out_src:
                key = p.name
            src = out_src.get(key)
            
            if src and is_bit(src):
                base, idx = parse_bit(src)
                if base in inputs:
                    W(f'    dut.{c_ident(p.name).lower()} = ((dut.input_{c_ident(base)} >> {idx-1}) & 1ull);')
            elif src and src in inputs and inputs[src].width == 1:
                W(f'    dut.{c_ident(p.name).lower()} = (dut.input_{c_ident(src)} & 1ull);')
            
            if p.width == 1:
                W(f'    dut.{c_ident(p.name).lower()}_bit = (uint8_t)(dut.{c_ident(p.name).lower()} & 1u);')
        else:
            # For multi-bit outputs, add any input-dependent bits
            for i in range(1, p.width + 1):
                key = f'{p.name}[{i}]'
                src = out_src.get(key)
                if src and is_bit(src):
                    base, idx = parse_bit(src)
                    if base in inputs:
                        W(f'    dut.{c_ident(p.name).lower()} |= (((dut.input_{c_ident(base)} >> {idx-1}) & 1ull) << {i-1});')
                elif src and src in inputs and inputs[src].width == 1:
                    W(f'    dut.{c_ident(p.name).lower()} |= (((dut.input_{c_ident(src)} & 1ull)) << {i-1});')
    
    W('    dut.pending_valid = 1;')
    W('    dut.outputs_valid = 1;')
    W('}')
    W('')

    W('static void ensure_outputs(void) {')
    W('    if (!dut.outputs_valid) {')
    W('        compute_pending();')
    W('    }')
    W('}')
    W('')

    # Public API functions
    W('void reset(void) {')
    W('    memset(&dut, 0, sizeof(dut));')
    W('}')
    W('')

    W('void poke(const char *signal_name, uint64_t value) {')
    input_idx = 0
    for p in component.inputs:

        mask = (1 << p.width) - 1 if p.width < 64 else 0xFFFFFFFFFFFFFFFF
        if input_idx == 0:
            W(f'    if (strcmp(signal_name, "{p.name}") == 0) {{')
            W(f'        dut.input_{c_ident(p.name)} = value & 0x{mask:x}ull;')
        else:
            W(f'    }}else if (strcmp(signal_name, "{p.name}") == 0) {{')
            W(f'        dut.input_{c_ident(p.name)} = value & 0x{mask:x}ull;')
        input_idx += 1
    W('    }else {')
    W('        fprintf(stderr, "Unknown signal \'%s\'\\n", signal_name);')
    W('        return;')
    W('    }')
    W('    mark_dirty();')
    W('}')
    W('')

    W('uint64_t peek(const char *signal_name) {')
    # Allow peeking at inputs
    for p in component.inputs:
        W(f'    if (strcmp(signal_name, "{p.name}") == 0) {{')
        W(f'        return dut.input_{c_ident(p.name)};')
        W(f'    }}')
    W('')
    W('    ensure_outputs();')
    W('')
    W('    const State *visible_state = dut.pending_valid ? &dut.pending : &dut.current;')
    W('')
    # Allow peeking at outputs
    for p in component.outputs:
        W(f'    if (strcmp(signal_name, "{p.name}") == 0) {{')
        W(f'        return dut.{c_ident(p.name).lower()};')
        W(f'    }}')
    # Allow peeking at internal state chunks for debugging
    for t in type_to_insts:
        num_chunks = type_chunks[t]
        for chunk_idx in range(num_chunks):
            signal_name = f'{c_ident(t)}_O_{chunk_idx}'
            W(f'    if (strcmp(signal_name, "{signal_name}") == 0) {{')
            W(f'        return visible_state->{signal_name};')
            W(f'    }}')
    W('')
    W('    fprintf(stderr, "Unknown signal \'%s\'\\n", signal_name);')
    W('    return 0ull;')
    W('}')
    W('')

    W('void eval(void) {')
    W('    compute_pending();')
    W('}')
    W('')

    W('void step(int cycles) {')
    W('    if (cycles <= 0) {')
    W('        ensure_outputs();')
    W('        return;')
    W('    }')
    W('')
    W('    for (int i = 0; i < cycles; ++i) {')
    tick_args = ['dut.current'] + [f'dut.input_{c_ident(p.name)}' for p in component.inputs]
    W(f'        dut.current = tick({", ".join(tick_args)});')
    W('    }')
    W('')
    W('    dut.pending_valid = 0;')
    # Extract outputs from current state after stepping
    for p in component.outputs:
        func_name = f'extract_{c_ident(p.name).lower()}'
        W(f'    dut.{c_ident(p.name).lower()} = {func_name}(&dut.current);')
        
        # Handle input pass-through
        if p.width == 1:
            key = f'{p.name}[1]'
            if key not in out_src and p.name in out_src:
                key = p.name
            src = out_src.get(key)
            
            if src and is_bit(src):
                base, idx = parse_bit(src)
                if base in inputs:
                    W(f'    dut.{c_ident(p.name).lower()} = ((dut.input_{c_ident(base)} >> {idx-1}) & 1ull);')
            elif src and src in inputs and inputs[src].width == 1:
                W(f'    dut.{c_ident(p.name).lower()} = (dut.input_{c_ident(src)} & 1ull);')
            
            W(f'    dut.{c_ident(p.name).lower()}_bit = (uint8_t)(dut.{c_ident(p.name).lower()} & 1u);')
        else:
            # For multi-bit outputs, add any input-dependent bits
            for i in range(1, p.width + 1):
                key = f'{p.name}[{i}]'
                src = out_src.get(key)
                if src and is_bit(src):
                    base, idx = parse_bit(src)
                    if base in inputs:
                        W(f'    dut.{c_ident(p.name).lower()} |= (((dut.input_{c_ident(base)} >> {idx-1}) & 1ull) << {i-1});')
                elif src and src in inputs and inputs[src].width == 1:
                    W(f'    dut.{c_ident(p.name).lower()} |= (((dut.input_{c_ident(src)} & 1ull)) << {i-1});')
    W('    dut.outputs_valid = 1;')
    W('}')
    W('')

    W('void dump_vcd(const char *filename) {')
    W('    (void)filename;')
    W('    fprintf(stderr, "dump_vcd not implemented for this model\\n");')
    W('}')
    
    return '\n'.join(out)