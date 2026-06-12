; mul.s — multiply by repeated addition (SR16 has no MUL).
; Result: R3 = 12 * 11 = 132 (0x0084).

        LI   r1, 12         ; multiplicand
        LI   r2, 11         ; loop counter
        LI   r3, 0          ; product
loop:   ADD  r3, r3, r1
        ADDI r2, r2, -1     ; sets Z when the counter hits 0
        BNE  loop
        HALT
