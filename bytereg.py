import ctypes

# Load library
lib = ctypes.CDLL("SHDL_components/bytereg.so")

# Setup function signatures
lib.reset.restype = None
lib.poke.argtypes = [ctypes.c_char_p, ctypes.c_uint64]
lib.peek.restype = ctypes.c_uint64
lib.peek.argtypes = [ctypes.c_char_p]

# Use it!
lib.reset()
lib.poke(b"In", 44)
lib.poke(b"clk", 1)
lib.step(2)
lib.poke(b"clk", 0)
lib.poke(b"In", 67)
lib.step(2)
result = lib.peek(b"Out")
print(f"Result: {result}")