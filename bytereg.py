import ctypes

# Load library
lib = ctypes.CDLL("SHDL_components/adderSubtractor16.so")

# Setup function signatures
lib.reset.restype = None
lib.poke.argtypes = [ctypes.c_char_p, ctypes.c_uint64]
lib.peek.restype = ctypes.c_uint64
lib.peek.argtypes = [ctypes.c_char_p]

# Use it!
lib.reset()
lib.poke(b"A", 1037)
lib.poke(b"B", 1038)
lib.poke(b"sub", 1)
lib.step(100)
result = lib.peek(b"Sum")
print(f"Result: {result}")