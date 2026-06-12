; popcount.s — count the set bits of a 16-bit constant.
; 0xB7C5 = 1011 0111 1100 0101 -> ten 1-bits. Result: R2 = 10.

        LI   r1, 0xB7C5     ; value under test
        LI   r2, 0          ; popcount
        LI   r3, 1          ; LSB mask
        LI   r5, 16         ; bit counter
loop:   AND  r4, r1, r3     ; Z=1 iff the low bit is clear
        BEQ  skip
        ADDI r2, r2, 1
skip:   SHR  r1, r1         ; next bit into position 0
        ADDI r5, r5, -1
        BNE  loop
        HALT
