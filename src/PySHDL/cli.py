#!/usr/bin/env python3
"""
SHDL Compiler - Command-line interface
Usage: shdlc [options] <input.shdl>
"""

import argparse
import subprocess
import sys
from pathlib import Path

from .shdlc import SHDLParser, generate_c_code


def main() -> int:
    parser = argparse.ArgumentParser(
        description='SHDL Compiler - Compile SHDL hardware description files to C',
        usage='%(prog)s [options] <input.shdl>'
    )
    
    parser.add_argument(
        'input',
        help='Input SHDL file'
    )
    
    parser.add_argument(
        '-o', '--output',
        help='Output C file (default: <input>.c)',
        default=None
    )
    
    parser.add_argument(
        '-I', '--include',
        action='append',
        dest='include_paths',
        help='Add directory to component search path',
        default=[]
    )
    
    parser.add_argument(
        '-c', '--compile-only',
        action='store_true',
        help='Generate C code only, do not compile to binary'
    )
    
    parser.add_argument(
        '-O', '--optimize',
        choices=['0', '1', '2', '3'],
        default='3',
        help='GCC optimization level (default: 3)'
    )
    
    parser.add_argument(
        '--no-flatten',
        action='store_true',
        help='Do not flatten component hierarchy'
    )
    
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output'
    )
    
    args = parser.parse_args()
    
    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"shdlc: error: {args.input}: No such file", file=sys.stderr)
        return 1
    
    if not input_path.suffix == '.shdl':
        print(f"shdlc: warning: {args.input}: File does not have .shdl extension", file=sys.stderr)
    
    # Determine output file
    if args.output:
        output_c = Path(args.output)
        if not output_c.suffix == '.c' and not args.compile_only:
            # Binary output
            output_bin = output_c
            output_c = input_path.with_suffix('.c')
        else:
            output_bin = output_c.with_suffix('')
    else:
        output_c = input_path.with_suffix('.c')
        output_bin = input_path.with_suffix('')
    
    # Setup search paths
    search_paths = [input_path.parent]
    
    # Add SHDL_components if it exists
    default_lib = input_path.parent / "SHDL_components"
    if default_lib.exists():
        search_paths.append(default_lib)
    
    # Add user-specified include paths
    for inc_path in args.include_paths:
        search_paths.append(Path(inc_path))
    
    if args.verbose:
        print(f"Input: {input_path}")
        print(f"Output C: {output_c}")
        if not args.compile_only:
            print(f"Output binary: {output_bin}")
        print(f"Search paths: {[str(p) for p in search_paths]}")
    
    try:
        # Parse SHDL file
        if args.verbose:
            print("Parsing SHDL file...")
        
        shdl_parser = SHDLParser(search_paths)
        component = shdl_parser.parse_file(input_path)
        
        if args.verbose:
            print(f"  Component: {component.name}")
            print(f"  Instances: {len(component.instances)}")
            print(f"  Connections: {len(component.connections)}")
        
        # Flatten component hierarchy
        if not args.no_flatten:
            if args.verbose:
                print("Flattening component hierarchy...")
            
            component = shdl_parser.flatten_all_levels(component)
            
            if args.verbose:
                print(f"  Instances after flattening: {len(component.instances)}")
                print(f"  Connections after flattening: {len(component.connections)}")
                print(f"  Gate types: {set(i.component_type for i in component.instances)}")
        
        # Generate C code
        if args.verbose:
            print("Generating C code...")
        
        c_code = generate_c_code(component)

        with open(output_c, 'w', encoding='utf-8') as file_handle:
            file_handle.write(c_code)
        
        if args.verbose:
            print(f"  Generated {output_c} ({len(c_code)} bytes)")
        
        # Compile to binary
        if not args.compile_only:
            if args.verbose:
                print("Compiling C code to binary...")
            
            # gcc -shared -fPIC -O3 your_design.c -o your_design.so
            gcc_cmd = [
                'gcc',
                '-shared',
                '-fPIC',
                f'-O{args.optimize}',
                str(output_c),
                '-o', str(output_bin)+".so"
            ]
            
            if args.verbose:
                print(f"  Command: {' '.join(gcc_cmd)}")
            
            result = subprocess.run(gcc_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"shdlc: error: gcc compilation failed", file=sys.stderr)
                if result.stderr:
                    print(result.stderr, file=sys.stderr)
                return 1
            
            if args.verbose:
                print(f"  Generated binary: {output_bin}")
        
        if not args.verbose:
            # Mimic gcc's quiet success
            pass
        else:
            print("Done!")
        
        return 0
        
    except Exception as e:
        print(f"shdlc: error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
