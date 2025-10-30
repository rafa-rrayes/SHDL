from SHDL import Circuit

def test_register16():
    circuit = Circuit("examples/SHDL_components/reg16.shdl")


    circuit.poke("In", 13)
    circuit.poke("clk", 0)
    circuit.step(10)
    circuit.poke("In", 6213)
    circuit.poke("clk", 1)
    circuit.step(10)
    circuit.poke("clk", 0)
    circuit.step(10)
    circuit.poke("In", 432)
    circuit.step(10)

    result = circuit.peek("Out")
    print(f"Register16 output: {result}")

if __name__ == "__main__":
    print("SHDL Driver - Example Usage")
    print("=" * 50)

    circuit = Circuit("examples/SHDL_components/addSub16.shdl")
    

    A = 103
    B = 3482
    Cin = 0
    circuit.poke("A", A)
    circuit.poke("B", B)
    circuit.poke("sub", Cin)
    
    circuit.step(500)

    result = circuit.peek("Sum")

    print(f"{A} + {B} + {Cin} = {result}, expected {A + B + Cin}")
    test_register16()