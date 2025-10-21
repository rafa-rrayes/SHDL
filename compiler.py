"""SHDL compiler with multi-bit signal support."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple

GATE_FUNCTIONS: Dict[str, str] = {
    "AND": "eval_and",
    "OR": "eval_or",
    "XOR": "eval_xor",
    "NOT": "eval_not",
    "NAND": "eval_nand",
    "NOR": "eval_nor",
    "XNOR": "eval_xnor",
}


def is_primitive_gate(gate_type: str) -> bool:
    return gate_type.upper() in GATE_FUNCTIONS


def gate_eval_name(gate_type: str) -> str:
    try:
        return GATE_FUNCTIONS[gate_type.upper()]
    except KeyError as exc:  # pragma: no cover - defensive guard
        raise ValueError(f"Unsupported gate type `{gate_type}`.") from exc

PORT_PRIORITY: Dict[str, int] = {
    "A": 0,
    "IN": 0,
    "B": 1,
    "C": 2,
    "D": 3,
    "E": 4,
    "F": 5,
    "G": 6,
    "H": 7,
    "I": 8,
}


@dataclass
class Port:
    name: str
    width: int = 1


@dataclass
class GateInstance:
    name: str
    gate_type: str


@dataclass
class Connection:
    source: str
    target: str


@dataclass
class Component:
    name: str
    inputs: List[Port] = field(default_factory=list)
    outputs: List[Port] = field(default_factory=list)
    instances: List[GateInstance] = field(default_factory=list)
    connections: List[Connection] = field(default_factory=list)
    imports: Dict[str, str] = field(default_factory=dict)

    HEADER_RE = re.compile(
        r"component\s+(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<inputs>[^)]*)\)\s*->\s*\((?P<outputs>[^)]*)\)\s*\{",
        re.IGNORECASE,
    )
    CONNECT_RE = re.compile(r"connect\s*\{", re.IGNORECASE)
    CONNECT_BLOCK_RE = re.compile(r"connect\s*\{(.*?)\}", re.IGNORECASE | re.DOTALL)
    INSTANCE_RE = re.compile(
        r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*([A-Za-z_][A-Za-z0-9_]*)",
        re.IGNORECASE,
    )
    IMPORT_RE = re.compile(
        r"use\s+([A-Za-z_][A-Za-z0-9_]*)::\{([^}]*)\};",
        re.IGNORECASE,
    )

    @classmethod
    def parse(cls, code: str) -> "Component":
        imports: Dict[str, str] = {}
        for module, symbols in cls.IMPORT_RE.findall(code):
            for item in _split_list(symbols):
                imports[item.strip()] = module

        header_match = cls.HEADER_RE.search(code)
        if not header_match:
            raise ValueError("Could not find a component header in SHDL source.")

        name = header_match.group("name")
        inputs = _parse_port_list(header_match.group("inputs"))
        outputs = _parse_port_list(header_match.group("outputs"))

        after_header = header_match.end()
        connect_match = cls.CONNECT_RE.search(code, after_header)
        if not connect_match:
            raise ValueError("SHDL source is missing a `connect { … }` block.")

        instance_region = code[after_header:connect_match.start()]
        instances = [
            GateInstance(name=m.group(1), gate_type=m.group(2))
            for m in cls.INSTANCE_RE.finditer(instance_region)
        ]

        block_match = cls.CONNECT_BLOCK_RE.search(code, connect_match.start())
        if not block_match:
            raise ValueError("Could not parse the `connect { … }` block contents.")

        connections: List[Connection] = []
        for raw_stmt in block_match.group(1).split(";"):
            stmt = raw_stmt.strip()
            if not stmt:
                continue
            if "->" not in stmt:
                raise ValueError(f"Malformed connection statement: {stmt}")
            source, target = [part.strip() for part in stmt.split("->", 1)]
            connections.append(Connection(source=source, target=target))

        return cls(
            name=name,
            inputs=inputs,
            outputs=outputs,
            instances=instances,
            connections=connections,
            imports=imports,
        )


@dataclass
class FlattenedNode:
    alias: str
    gate_type: str
    display_name: str


@dataclass
class FlatComponent:
    name: str
    inputs: List[Port]
    outputs: List[Port]
    nodes: List[FlattenedNode]
    node_inputs: Dict[str, List[Tuple[str, str]]]
    input_bits: Dict[Tuple[str, int], str]
    output_bits: Dict[Tuple[str, int], str]


class ComponentLibrary:
    def __init__(self, components_dir: Path):
        self.components_dir = components_dir
        self._cache: Dict[Path, Component] = {}

    def load_from_path(self, path: Path) -> Component:
        return self._parse_component(path)

    def load(self, module: str, component_name: str) -> Component:
        candidate = self.components_dir / f"{module}.shdl"
        component = self._parse_component(candidate)
        if component.name != component_name:
            raise ValueError(
                f"Component `{component_name}` not found in `{candidate}` (found `{component.name}` instead)."
            )
        return component

    def _parse_component(self, path: Path) -> Component:
        path = path.resolve()
        if path in self._cache:
            return self._cache[path]
        if not path.exists():
            raise FileNotFoundError(f"Component file `{path}` does not exist.")
        code = path.read_text()
        component = Component.parse(code)
        self._cache[path] = component
        return component


def _split_list(segment: str) -> List[str]:
    if not segment:
        return []
    return [item.strip() for item in segment.split(",") if item.strip()]


_PORT_DECL_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(?:\[(\d+)\])?$")


def _parse_port_list(segment: str) -> List[Port]:
    ports: List[Port] = []
    for token in _split_list(segment):
        normalized = token.replace(" ", "")
        match = _PORT_DECL_RE.fullmatch(normalized)
        if not match:
            raise ValueError(f"Malformed port declaration `{token}`.")
        name = match.group(1)
        width = int(match.group(2)) if match.group(2) else 1
        if width <= 0:
            raise ValueError(f"Port `{name}` must have positive width (got {width}).")
        ports.append(Port(name=name, width=width))
    return ports


def sanitize_identifier(name: str) -> str:
    sanitized = re.sub(r"\W+", "_", name)
    if not sanitized:
        raise ValueError("Encountered an empty identifier after sanitization.")
    if sanitized[0].isdigit():
        sanitized = f"_{sanitized}"
    return sanitized


def prefixed_name(prefix: str, name: str) -> str:
    return f"{prefix}_{name}" if prefix else name


def bit_key(base: str, index: int) -> str:
    return f"{base}[{index}]"


def _split_owner_and_member(expr: str) -> Tuple[str | None, str]:
    expr = expr.strip()
    if not expr:
        raise ValueError("Empty signal expression encountered.")
    if "." in expr:
        owner, member = expr.split(".", 1)
        return owner.strip(), member.strip()
    return None, expr


def _split_name_and_range(token: str) -> Tuple[str, str | None]:
    token = token.strip()
    if not token:
        raise ValueError("Empty signal token.")
    if "[" not in token:
        return token, None
    name, remainder = token.split("[", 1)
    if not remainder.endswith("]"):
        raise ValueError(f"Malformed slice in `{token}`.")
    range_expr = remainder[:-1].strip()
    name = name.strip()
    if not name:
        raise ValueError(f"Missing identifier in `{token}`.")
    return name, range_expr or None


def _expand_range(range_expr: str | None, width: int) -> List[int]:
    if width <= 0:
        raise ValueError("Signal width must be positive.")
    if range_expr is None:
        return list(range(1, width + 1))
    if ":" in range_expr:
        start_str, end_str = range_expr.split(":", 1)
        start = int(start_str) if start_str else 1
        end = int(end_str) if end_str else width
    else:
        start = end = int(range_expr)
    if start < 1 or end > width or start > end:
        slice_repr = range_expr if range_expr is not None else ""
        raise ValueError(f"Slice `[{slice_repr}]` is out of bounds for width {width}.")
    return list(range(start, end + 1))


def _expand_signal(
    expr: str,
    signal_map: Dict[str, str],
    signal_widths: Dict[str, int],
) -> List[str]:
    owner, member = _split_owner_and_member(expr)
    name, range_expr = _split_name_and_range(member)
    base = f"{owner}.{name}" if owner else name
    width = signal_widths.get(base, 1)
    indices = _expand_range(range_expr, width)
    aliases: List[str] = []
    for idx in indices:
        alias = signal_map.get(bit_key(base, idx))
        if alias is None and width == 1:
            alias = signal_map.get(base)
        if alias is None:
            raise ValueError(f"Unable to resolve signal reference `{expr}`.")
        aliases.append(alias)
    return aliases


def _sorted_inputs(entries: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    return sorted(entries, key=lambda entry: (PORT_PRIORITY.get(entry[0].upper(), 100), entry[0].upper()))


def flatten_component(
    component: Component,
    library: ComponentLibrary,
    *,
    prefix: str,
    input_signal_map: Dict[Tuple[str, int], str],
    ancestry: Tuple[str, ...],
) -> FlatComponent:
    signal_map: Dict[str, str] = {}
    signal_widths: Dict[str, int] = {}

    def register_scalar(base: str, alias: str) -> None:
        signal_widths[base] = 1
        signal_map[base] = alias
        signal_map[bit_key(base, 1)] = alias

    input_widths = {port.name: port.width for port in component.inputs}
    output_widths = {port.name: port.width for port in component.outputs}

    for port in component.inputs:
        signal_widths[port.name] = port.width
        for idx in range(1, port.width + 1):
            key = bit_key(port.name, idx)
            alias = input_signal_map[(port.name, idx)]
            signal_map[key] = alias
        if port.width == 1:
            signal_map[port.name] = input_signal_map[(port.name, 1)]

    instance_names = {inst.name for inst in component.instances}
    raw_node_inputs: Dict[str, List[Tuple[str, str]]] = {}
    raw_output_assignments: List[Tuple[str, str]] = []

    for connection in component.connections:
        owner, member = _split_owner_and_member(connection.target)
        if owner:
            if owner not in instance_names:
                raise ValueError(
                    f"Connection targets unknown instance `{owner}` in component `{component.name}`."
                )
            raw_node_inputs.setdefault(owner, []).append((member, connection.source))
        else:
            output_name, _ = _split_name_and_range(member)
            if output_name not in output_widths:
                raise ValueError(
                    f"Connection targets unknown output `{output_name}` in component `{component.name}`."
                )
            raw_output_assignments.append((connection.target, connection.source))

    flat_nodes: List[FlattenedNode] = []
    flat_node_inputs: Dict[str, List[Tuple[str, str]]] = {}
    output_bits: Dict[Tuple[str, int], str] = {}

    for instance in component.instances:
        connections = raw_node_inputs.get(instance.name, [])
        if is_primitive_gate(instance.gate_type):
            display_name = prefixed_name(prefix, instance.name)
            alias = sanitize_identifier(display_name)
            flat_nodes.append(FlattenedNode(alias=alias, gate_type=instance.gate_type.upper(), display_name=display_name))
            register_scalar(instance.name, alias)
            register_scalar(display_name, alias)
            register_scalar(f"{instance.name}.O", alias)

            resolved_inputs: List[Tuple[str, str]] = []
            for port_expr, source_expr in connections:
                port_name, port_range = _split_name_and_range(port_expr)
                indices = _expand_range(port_range, 1)
                if len(indices) != 1:
                    raise ValueError(
                        f"Port `{port_name}` of primitive `{instance.name}` expects a single-bit connection."
                    )
                source_aliases = _expand_signal(source_expr, signal_map, signal_widths)
                if len(source_aliases) != 1:
                    raise ValueError(
                        f"Connection `{source_expr}` to `{instance.name}.{port_name}` must resolve to a single bit."
                    )
                resolved_inputs.append((port_name, source_aliases[0]))

            flat_node_inputs[alias] = resolved_inputs
        else:
            module = component.imports.get(instance.gate_type)
            if not module:
                raise ValueError(
                    f"Unknown component `{instance.gate_type}` referenced as `{instance.name}` in component `{component.name}`."
                )
            if instance.gate_type in ancestry:
                cycle = " -> ".join(ancestry + (instance.gate_type,))
                raise ValueError(f"Recursive component dependency detected: {cycle}")

            child_component = library.load(module, instance.gate_type)
            child_prefix = prefixed_name(prefix, instance.name)
            child_input_widths = {port.name: port.width for port in child_component.inputs}

            child_input_bits: Dict[Tuple[str, int], str] = {}
            for port_expr, source_expr in connections:
                port_owner, port_member = _split_owner_and_member(port_expr)
                if port_owner:
                    raise ValueError(
                        f"Nested member reference `{port_expr}` is not supported for instance `{instance.name}`."
                    )
                input_name, port_range = _split_name_and_range(port_member)
                if input_name not in child_input_widths:
                    raise ValueError(
                        f"Connection targets unknown input `{input_name}` of instance `{instance.name}`."
                    )
                indices = _expand_range(port_range, child_input_widths[input_name])
                source_aliases = _expand_signal(source_expr, signal_map, signal_widths)
                if len(indices) != len(source_aliases):
                    raise ValueError(
                        f"Connection `{source_expr}` does not match width of `{instance.name}.{input_name}`."
                    )
                for idx, alias in zip(indices, source_aliases):
                    key = (input_name, idx)
                    if key in child_input_bits:
                        raise ValueError(
                            f"Input `{instance.name}.{input_name}[{idx}]` is driven multiple times."
                        )
                    child_input_bits[key] = alias

            for port in child_component.inputs:
                for idx in range(1, port.width + 1):
                    if (port.name, idx) not in child_input_bits:
                        raise ValueError(
                            f"Input `{instance.name}.{port.name}[{idx}]` is undriven."
                        )

            child_flat = flatten_component(
                child_component,
                library,
                prefix=child_prefix,
                input_signal_map=child_input_bits,
                ancestry=ancestry + (component.name,),
            )

            flat_nodes.extend(child_flat.nodes)
            flat_node_inputs.update(child_flat.node_inputs)

            for port in child_component.outputs:
                base = f"{instance.name}.{port.name}"
                signal_widths[base] = port.width
                for idx in range(1, port.width + 1):
                    alias = child_flat.output_bits[(port.name, idx)]
                    signal_map[bit_key(base, idx)] = alias
                if port.width == 1:
                    signal_map[base] = child_flat.output_bits[(port.name, 1)]

    for node in flat_nodes:
        flat_node_inputs.setdefault(node.alias, [])

    for target_expr, source_expr in raw_output_assignments:
        owner, member = _split_owner_and_member(target_expr)
        if owner:
            raise ValueError(f"Component outputs cannot have an owner qualifier: `{target_expr}`.")
        output_name, range_expr = _split_name_and_range(member)
        indices = _expand_range(range_expr, output_widths[output_name])
        source_aliases = _expand_signal(source_expr, signal_map, signal_widths)
        if len(indices) != len(source_aliases):
            raise ValueError(
                f"Connection `{source_expr}` does not match width of output `{output_name}`."
            )
        for idx, alias in zip(indices, source_aliases):
            key = (output_name, idx)
            if key in output_bits:
                raise ValueError(
                    f"Output `{output_name}[{idx}]` is driven multiple times in component `{component.name}`."
                )
            output_bits[key] = alias

    for port in component.outputs:
        for idx in range(1, port.width + 1):
            if (port.name, idx) not in output_bits:
                raise ValueError(
                    f"Output `{port.name}[{idx}]` is undriven in component `{component.name}`."
                )

    return FlatComponent(
        name=component.name,
        inputs=list(component.inputs),
        outputs=list(component.outputs),
        nodes=flat_nodes,
        node_inputs=flat_node_inputs,
        input_bits=dict(input_signal_map),
        output_bits=output_bits,
    )


def generate_main_body(component: FlatComponent) -> str:
    indent = "    "
    lines: List[str] = [""]

    input_aliases: Dict[Tuple[str, int], str] = component.input_bits

    for port in component.inputs:
        for idx in range(1, port.width + 1):
            alias = input_aliases[(port.name, idx)]
            display = f"{port.name}[{idx}]" if port.width > 1 else port.name
            lines.append(f"{indent}Node {alias} = {{")
            lines.append(f'{indent}    .name = "{display}",')
            lines.append(f"{indent}    .output = 1,")
            lines.append(f"{indent}    .evaluate = NULL,")
            lines.append(f"{indent}    .inputs = NULL,")
            lines.append(f"{indent}    .input_count = 0")
            lines.append(f"{indent}}};")
            lines.append("")

    for node in component.nodes:
        inputs = component.node_inputs.get(node.alias, [])
        lines.append(f"{indent}Node {node.alias} = {{")
        lines.append(f'{indent}    .name = "{node.display_name}",')
        lines.append(f"{indent}    .output = 0,")
        lines.append(f"{indent}    .evaluate = {gate_eval_name(node.gate_type)},")
        lines.append(f"{indent}    .inputs = NULL,")
        lines.append(f"{indent}    .input_count = {len(inputs)}")
        lines.append(f"{indent}}};")
        lines.append("")

    pointer_lines: List[str] = []
    assignment_lines: List[str] = []
    for node in component.nodes:
        inputs = component.node_inputs.get(node.alias, [])
        if inputs:
            sorted_inputs = _sorted_inputs(inputs)
            pointer_values = [f"&{alias}.output" for _, alias in sorted_inputs]
            pointer_lines.append(
                f"{indent}const int *in_{node.alias}[] = {{ {', '.join(pointer_values)} }};"
            )
            assignment_lines.append(f"{indent}{node.alias}.inputs = (const int **)in_{node.alias};")
        else:
            assignment_lines.append(f"{indent}{node.alias}.inputs = NULL;")

    if pointer_lines:
        lines.extend(pointer_lines)
        lines.append("")

    if assignment_lines:
        lines.extend(assignment_lines)
        lines.append("")

    output_nodes_defs: List[str] = []
    output_node_aliases: List[str] = []
    for port in component.outputs:
        for idx in range(1, port.width + 1):
            output_alias = sanitize_identifier(f"output_{port.name}_{idx}")
            source_alias = component.output_bits[(port.name, idx)]
            display = f"{port.name}[{idx}]" if port.width > 1 else port.name
            output_nodes_defs.append(
                f"{indent}OutputNode {output_alias} = {{\n"
                f"{indent}    .name = \"{display}\",\n"
                f"{indent}    .output = &{source_alias}.output\n"
                f"{indent}}};"
            )
            output_node_aliases.append(output_alias)

    if output_nodes_defs:
        lines.extend(output_nodes_defs)
        lines.append("")

    node_entries = ", ".join(f"&{node.alias}" for node in component.nodes)
    lines.append(f"{indent}Node *nodes[] = {{ {node_entries} }};")

    output_entries = ", ".join(f"&{alias}" for alias in output_node_aliases)
    lines.append(f"{indent}OutputNode *output_nodes[] = {{ {output_entries} }};")

    input_entries = ", ".join(
        f"&{input_aliases[(port.name, idx)]}"
        for port in component.inputs
        for idx in range(1, port.width + 1)
    )
    lines.append(f"{indent}Node *input_nodes[] = {{ {input_entries} }};")

    lines.append("")
    return "\n".join(lines)


def compile_shdl_to_c(input_path: Path, output_path: Path, defaults_path: Path) -> None:
    library = ComponentLibrary(input_path.parent)
    component = library.load_from_path(input_path)

    input_bit_aliases: Dict[Tuple[str, int], str] = {}
    for port in component.inputs:
        for idx in range(1, port.width + 1):
            alias = sanitize_identifier(f"input_{port.name}_{idx}")
            input_bit_aliases[(port.name, idx)] = alias

    flat = flatten_component(
        component,
        library,
        prefix="",
        input_signal_map=input_bit_aliases,
        ancestry=(),
    )

    defaults_code = defaults_path.read_text()
    if "// LE CODE" not in defaults_code:
        raise ValueError("defaults.c is missing the `// LE CODE` placeholder for insertion.")

    main_body = generate_main_body(flat)
    generated_code = defaults_code.replace("// LE CODE", main_body)

    output_path.write_text(generated_code)
    print(f"Generated {output_path} for component {component.name}.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile SHDL components into C source code with multi-bit support.")
    parser.add_argument("-i", "--input", type=Path, required=True, help="Path to the SHDL source file.")
    parser.add_argument("-o", "--output", type=Path, required=True, help="Destination C file to generate.")
    parser.add_argument(
        "-d",
        "--defaults",
        type=Path,
        default=Path("defaults.c"),
        help="Path to the defaults C runtime to prepend to the generated file.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    compile_shdl_to_c(args.input, args.output, args.defaults)


if __name__ == "__main__":
    main()
