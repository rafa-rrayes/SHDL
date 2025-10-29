# QUICK START GUIDE

## 5-Minute Setup

### Step 1: Generate the Library
```python
from pathlib import Path
from shdl_compiler import SHDLParser, generate_c_bitpacked

# Parse and compile your SHDL design
parser = SHDLParser([Path(".")])
component = parser.parse_file(Path("your_design.shdl"))
component = parser.flatten_all_levels(component)

# Generate the library
c_code = generate_c_bitpacked(component)
with open("your_design.c", "w") as f:
    f.write(c_code)
```

### Step 2: Compile as Shared Library
```bash
gcc -shared -fPIC -O3 your_design.c -o your_design.so
```

### Step 3: Use from Python
```python
import ctypes

# Load library
lib = ctypes.CDLL("./your_design.so")

# Setup function signatures
lib.reset.restype = None
lib.poke.argtypes = [ctypes.c_char_p, ctypes.c_uint64]
lib.peek.restype = ctypes.c_uint64
lib.peek.argtypes = [ctypes.c_char_p]
lib.eval.restype = None

# Use it!
lib.reset()
lib.poke(b"InputName", 42)
lib.step(4)
result = lib.peek(b"OutputName")
print(f"Result: {result}")
```

