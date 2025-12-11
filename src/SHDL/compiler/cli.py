#!/usr/bin/env python3
"""
shdlc - SHDL Compiler

Command-line interface for compiling SHDL to optimized C simulation code.

Usage:
    shdlc input.shdl                  # Output C to stdout
    shdlc input.shdl -o output.c      # Write C to file
    shdlc input.shdl -c -o libout.dylib  # Compile to shared library
    shdlc input.shdl --flatten        # Flatten Expanded SHDL first
    
Debug builds:
    shdlc input.shdl -g -c -o libout.dylib    # Debug build with introspection
    shdlc input.shdl -g2 -c -o libout.dylib   # Debug level 2 (default)
    shdlc input.shdl -g3 -c -o libout.dylib   # Maximum debug info
"""

import argparse
import sys
from pathlib import Path

from .compiler import SHDLCompiler, compile_shdl_file
from .parser import parse, parse_file


def main():
    """Main entry point for shdlc."""
    parser = argparse.ArgumentParser(
        prog="shdlc",
        description="Compile SHDL to optimized C simulation code",
        epilog="Example: shdlc adder.shdl -o libadder.c"
    )
    
    parser.add_argument(
        "input",
        help="Input SHDL file"
    )
    
    parser.add_argument(
        "-o", "--output",
        help="Output file (default: stdout for C, required for library)"
    )
    
    parser.add_argument(
        "-c", "--compile",
        action="store_true",
        help="Compile to shared library (requires -o)"
    )
    
    parser.add_argument(
        "--flatten",
        action="store_true",
        help="Flatten Expanded SHDL to Base SHDL first"
    )
    
    parser.add_argument(
        "-I", "--include",
        action="append",
        default=[],
        help="Add include directory for imports"
    )
    
    parser.add_argument(
        "--component",
        help="Component name to compile (default: last component)"
    )
    
    parser.add_argument(
        "-O", "--optimize",
        type=int,
        choices=[0, 1, 2, 3],
        default=3,
        help="Optimization level for C compilation (default: 3)"
    )
    
    parser.add_argument(
        "--cc",
        default="gcc",
        help="C compiler to use (default: gcc)"
    )
    
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Verbose output"
    )
    
    parser.add_argument(
        "--emit-base-shdl",
        action="store_true",
        help="Emit flattened Base SHDL instead of C code"
    )
    
    # Debug build options
    debug_group = parser.add_argument_group('debug options')
    
    debug_group.add_argument(
        "-g",
        action="store_true",
        help="Enable debug build (equivalent to -g2)"
    )
    
    debug_group.add_argument(
        "-g1",
        action="store_true",
        help="Debug level 1: basic symbols, no gate table"
    )
    
    debug_group.add_argument(
        "-g2",
        action="store_true",
        help="Debug level 2: symbols + gate table (default with -g)"
    )
    
    debug_group.add_argument(
        "-g3",
        action="store_true",
        help="Debug level 3: full debug info including source mapping"
    )
    
    debug_group.add_argument(
        "--no-shdb",
        action="store_true",
        help="Don't generate .shdb debug info file (only with -g)"
    )
    
    args = parser.parse_args()
    
    input_path = Path(args.input)
    
    if not input_path.exists():
        print(f"Error: File not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    # Validate arguments
    if args.compile and not args.output:
        print("Error: -c/--compile requires -o/--output", file=sys.stderr)
        sys.exit(1)
    
    # Determine debug level
    debug_level = 0
    if args.g3:
        debug_level = 3
    elif args.g2:
        debug_level = 2
    elif args.g1:
        debug_level = 1
    elif args.g:
        debug_level = 2  # -g defaults to level 2
    
    is_debug_build = debug_level > 0
    
    # Process
    try:
        if args.flatten or args.emit_base_shdl:
            # Use the main SHDL flattener
            from SHDL import Flattener
            
            flattener = Flattener(search_paths=args.include)
            
            # Add the file's directory to search paths
            file_dir = str(input_path.parent)
            if file_dir not in flattener._library.search_paths:
                flattener._library.search_paths.insert(0, Path(file_dir))
            
            flattener.load_file(str(input_path))
            
            # Get component name
            if args.component:
                comp_name = args.component
            else:
                # Use the last component
                module = flattener._library.components
                if not module:
                    print("Error: No components found", file=sys.stderr)
                    sys.exit(1)
                comp_name = list(module.keys())[-1]
            
            base_shdl = flattener.flatten_to_base_shdl(comp_name)
            
            if args.emit_base_shdl:
                if args.output:
                    with open(args.output, 'w') as f:
                        f.write(base_shdl)
                else:
                    print(base_shdl)
                sys.exit(0)
            
            source = base_shdl
        else:
            # Read Base SHDL directly
            with open(input_path, 'r') as f:
                source = f.read()
        
        # Compile
        compiler = SHDLCompiler(include_paths=args.include)
        source_path = str(input_path.absolute())
        
        if args.compile:
            if is_debug_build:
                # Debug build - compile to library with introspection
                # For debug builds, use -O1 instead of user-specified optimization
                cflags = [f"-O{min(args.optimize, 1)}"]
                
                # Determine what debug features to enable based on level
                emit_gate_table = debug_level >= 2
                emit_peek_gate = debug_level >= 2
                emit_cycle_counter = True
                
                result = compiler.compile_to_library_debug(
                    source,
                    args.output,
                    component_name=args.component,
                    source_path=source_path,
                    cc=args.cc,
                    cflags=cflags,
                    debug_level=debug_level,
                    emit_gate_table=emit_gate_table,
                    emit_peek_gate=emit_peek_gate,
                    emit_cycle_counter=emit_cycle_counter,
                    generate_shdb=not args.no_shdb
                )
                
                if result.success and result.debug_info_path and args.verbose:
                    print(f"Generated debug info: {result.debug_info_path}", file=sys.stderr)
            else:
                # Normal release build
                cflags = [f"-O{args.optimize}"]
                result = compiler.compile_to_library(
                    source,
                    args.output,
                    args.component,
                    cc=args.cc,
                    cflags=cflags
                )
        else:
            # Generate C code
            if is_debug_build:
                result = compiler.compile_source_debug(
                    source,
                    component_name=args.component,
                    source_path=source_path,
                    debug_level=debug_level
                )
            else:
                result = compiler.compile_source(source, args.component)
        
        # Handle result
        if args.verbose:
            for warning in result.warnings:
                print(f"Warning: {warning}", file=sys.stderr)
        
        if not result.success:
            for error in result.errors:
                print(f"Error: {error}", file=sys.stderr)
            sys.exit(1)
        
        if args.compile:
            if args.verbose:
                print(f"Successfully compiled to {result.library_path}", file=sys.stderr)
        else:
            if args.output:
                with open(args.output, 'w') as f:
                    f.write(result.c_code)
                if args.verbose:
                    print(f"Successfully wrote {args.output}", file=sys.stderr)
            else:
                print(result.c_code)
    
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
