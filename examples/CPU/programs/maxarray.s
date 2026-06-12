; maxarray.s — unsigned maximum of a 5-word array at 0x20, stored to 0x30.
; Exercises LD/ST, CMP + BLO (unsigned compare: C=1 means no borrow).
; Result: R3 = MEM[0x30] = 0xBEEF.

        LI   r1, 0x20       ; element pointer
        LI   r2, 5          ; element count
        LD   r3, [r1]       ; max = first element
loop:   ADDI r1, r1, 1
        ADDI r2, r2, -1     ; Z=1 when all elements consumed
        BEQ  done
        LD   r4, [r1]
        CMP  r4, r3
        BLO  loop           ; r4 < max (unsigned) -> keep current max
        MOV  r3, r4         ; new max
        JMP  loop
done:   LI   r5, 0x30
        ST   [r5], r3
        HALT

        .org 0x20
        .word 0x0042
        .word 0xBEEF
        .word 0x1234
        .word 0x8001
        .word 0x7FFF
