import re

def clean_code(code: str) -> str:
    """
    Removes all comments and newlines from SHDL code
    """

    code_no_multiline = re.sub(r'"""(.*?)"""', '', code, flags=re.DOTALL)

    cleaned_code = "\n".join(line.rstrip() for line in code_no_multiline.splitlines() if line.strip())
    
    return cleaned_code


def compile_generators(code: str) -> str:
    """
    Replace each >>> ... <<< generator block by executing the Python inside.
    Any line whose first non-space character is '>' becomes:
        _output_lines.append(f"...")
    The joined _output_lines replace the whole block.
    """
    pattern = re.compile(r'>>>((?:.|\n)*?)<<<', re.DOTALL)

    def _run_block(match: re.Match) -> str:
        block = match.group(1)
        exec_lines = []

        start_ident_len = None
        for raw in block.strip("\n").splitlines():
            stripped = raw.lstrip()
            if start_ident_len is None:
                start_ident_len = len(raw) - len(stripped)

                print(f"Detected block indent length: {start_ident_len}")
            if stripped.startswith(">"):
                # Preserve original indentation for correct block structure
                content = stripped[1:]  # drop leading '>'
                content = " "*start_ident_len + content.lstrip()  # remove any space after '>'
                # Append as an f-string-producing line

                exec_lines.append(f'    _output_lines.append(f{repr(content)})')

            else:
                content = raw[start_ident_len:]  # drop leading '>'
                exec_lines.append(content)

        ns = {"_output_lines": []}
        print( exec_lines)
        exec("\n".join(exec_lines), ns)
        return "\n".join(ns["_output_lines"]).strip()

    return pattern.sub(_run_block, code)


def open_file(path):
    with open(path, 'r') as file:
        return file.read()
    
if __name__ == "__main__":
    code = open_file("new_SHDL.shdl")
    # print(clean_code(code))
    print(compile_generators(clean_code(code)))