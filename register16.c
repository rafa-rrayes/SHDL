#include <stdint.h>
#include <stdio.h>

// Auto-generated bit-packed registered simulator for Register16
// Each gate family packs up to 64 instances into a 64-bit lane vector.
// Next state is computed from previous state and current inputs (2-phase update).

typedef struct {
    uint64_t AND_O_0;  // chunk 0 of AND outputs
    uint64_t NOT_O_0;  // chunk 0 of NOT outputs
    uint64_t NOR_O_0;  // chunk 0 of NOR outputs
} State;

static inline State tick(State s, uint64_t In, uint64_t clk) {
    State n = s;

    uint64_t AND_0_A = 0ull;
    AND_0_A |= ((uint64_t)-( ((In >> 9) & 1u) )) & 0x0000000000040000ull;
    AND_0_A |= ((uint64_t)-( ((In >> 10) & 1u) )) & 0x0000000000100000ull;
    AND_0_A |= ((uint64_t)-( ((In >> 11) & 1u) )) & 0x0000000000400000ull;
    AND_0_A |= ((uint64_t)-( ((In >> 12) & 1u) )) & 0x0000000001000000ull;
    AND_0_A |= ((uint64_t)-( ((In >> 13) & 1u) )) & 0x0000000004000000ull;
    AND_0_A |= ((uint64_t)-( ((In >> 14) & 1u) )) & 0x0000000010000000ull;
    AND_0_A |= ((uint64_t)-( ((In >> 15) & 1u) )) & 0x0000000040000000ull;
    AND_0_A |= ((uint64_t)-( ((In >> 0) & 1u) )) & 0x0000000000000001ull;
    AND_0_A |= ((uint64_t)-( ((In >> 1) & 1u) )) & 0x0000000000000004ull;
    AND_0_A |= ((uint64_t)-( ((In >> 2) & 1u) )) & 0x0000000000000010ull;
    AND_0_A |= ((uint64_t)-( ((In >> 3) & 1u) )) & 0x0000000000000040ull;
    AND_0_A |= ((uint64_t)-( ((In >> 4) & 1u) )) & 0x0000000000000100ull;
    AND_0_A |= ((uint64_t)-( ((In >> 5) & 1u) )) & 0x0000000000000400ull;
    AND_0_A |= ((uint64_t)-( ((In >> 6) & 1u) )) & 0x0000000000001000ull;
    AND_0_A |= ((uint64_t)-( ((In >> 7) & 1u) )) & 0x0000000000004000ull;
    AND_0_A |= ((uint64_t)-( ((In >> 8) & 1u) )) & 0x0000000000010000ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 0) & 1u) )) & 0x0000000000000002ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 9) & 1u) )) & 0x0000000000080000ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 10) & 1u) )) & 0x0000000000200000ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 11) & 1u) )) & 0x0000000000800000ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 12) & 1u) )) & 0x0000000002000000ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 13) & 1u) )) & 0x0000000008000000ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 14) & 1u) )) & 0x0000000020000000ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 15) & 1u) )) & 0x0000000080000000ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 1) & 1u) )) & 0x0000000000000008ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 2) & 1u) )) & 0x0000000000000020ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 3) & 1u) )) & 0x0000000000000080ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 4) & 1u) )) & 0x0000000000000200ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 5) & 1u) )) & 0x0000000000000800ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 6) & 1u) )) & 0x0000000000002000ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 7) & 1u) )) & 0x0000000000008000ull;
    AND_0_A |= ((uint64_t)-( ((s.NOT_O_0 >> 8) & 1u) )) & 0x0000000000020000ull;
    uint64_t AND_0_B = 0ull;
    AND_0_B |= ((uint64_t)-( (clk & 1u) )) & 0x00000000ffffffffull;
    n.AND_O_0 = (AND_0_A & AND_0_B) & 0x00000000ffffffffull;

    uint64_t NOT_0_A = 0ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 9) & 1u) )) & 0x0000000000000200ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 10) & 1u) )) & 0x0000000000000400ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 11) & 1u) )) & 0x0000000000000800ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 12) & 1u) )) & 0x0000000000001000ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 13) & 1u) )) & 0x0000000000002000ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 14) & 1u) )) & 0x0000000000004000ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 15) & 1u) )) & 0x0000000000008000ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 0) & 1u) )) & 0x0000000000000001ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 1) & 1u) )) & 0x0000000000000002ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 2) & 1u) )) & 0x0000000000000004ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 3) & 1u) )) & 0x0000000000000008ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 4) & 1u) )) & 0x0000000000000010ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 5) & 1u) )) & 0x0000000000000020ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 6) & 1u) )) & 0x0000000000000040ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 7) & 1u) )) & 0x0000000000000080ull;
    NOT_0_A |= ((uint64_t)-( ((In >> 8) & 1u) )) & 0x0000000000000100ull;
    n.NOT_O_0 = ~(NOT_0_A) & 0x000000000000ffffull;

    uint64_t NOR_0_A = 0ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 0) & 1u) )) & 0x0000000000000001ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 18) & 1u) )) & 0x0000000000040000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 20) & 1u) )) & 0x0000000000100000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 22) & 1u) )) & 0x0000000000400000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 24) & 1u) )) & 0x0000000001000000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 26) & 1u) )) & 0x0000000004000000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 28) & 1u) )) & 0x0000000010000000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 30) & 1u) )) & 0x0000000040000000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 2) & 1u) )) & 0x0000000000000004ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 4) & 1u) )) & 0x0000000000000010ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 6) & 1u) )) & 0x0000000000000040ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 8) & 1u) )) & 0x0000000000000100ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 10) & 1u) )) & 0x0000000000000400ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 12) & 1u) )) & 0x0000000000001000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 14) & 1u) )) & 0x0000000000004000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 16) & 1u) )) & 0x0000000000010000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 1) & 1u) )) & 0x0000000000000002ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 19) & 1u) )) & 0x0000000000080000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 21) & 1u) )) & 0x0000000000200000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 23) & 1u) )) & 0x0000000000800000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 25) & 1u) )) & 0x0000000002000000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 27) & 1u) )) & 0x0000000008000000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 29) & 1u) )) & 0x0000000020000000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 31) & 1u) )) & 0x0000000080000000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 3) & 1u) )) & 0x0000000000000008ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 5) & 1u) )) & 0x0000000000000020ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 7) & 1u) )) & 0x0000000000000080ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 9) & 1u) )) & 0x0000000000000200ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 11) & 1u) )) & 0x0000000000000800ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 13) & 1u) )) & 0x0000000000002000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 15) & 1u) )) & 0x0000000000008000ull;
    NOR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 17) & 1u) )) & 0x0000000000020000ull;
    uint64_t NOR_0_B = 0ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 0) & 1u) )) & 0x0000000000000002ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 18) & 1u) )) & 0x0000000000080000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 20) & 1u) )) & 0x0000000000200000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 22) & 1u) )) & 0x0000000000800000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 24) & 1u) )) & 0x0000000002000000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 26) & 1u) )) & 0x0000000008000000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 28) & 1u) )) & 0x0000000020000000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 30) & 1u) )) & 0x0000000080000000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 2) & 1u) )) & 0x0000000000000008ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 4) & 1u) )) & 0x0000000000000020ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 6) & 1u) )) & 0x0000000000000080ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 8) & 1u) )) & 0x0000000000000200ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 10) & 1u) )) & 0x0000000000000800ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 12) & 1u) )) & 0x0000000000002000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 14) & 1u) )) & 0x0000000000008000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 16) & 1u) )) & 0x0000000000020000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 1) & 1u) )) & 0x0000000000000001ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 19) & 1u) )) & 0x0000000000040000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 21) & 1u) )) & 0x0000000000100000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 23) & 1u) )) & 0x0000000000400000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 25) & 1u) )) & 0x0000000001000000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 27) & 1u) )) & 0x0000000004000000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 29) & 1u) )) & 0x0000000010000000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 31) & 1u) )) & 0x0000000040000000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 3) & 1u) )) & 0x0000000000000004ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 5) & 1u) )) & 0x0000000000000010ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 7) & 1u) )) & 0x0000000000000040ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 9) & 1u) )) & 0x0000000000000100ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 11) & 1u) )) & 0x0000000000000400ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 13) & 1u) )) & 0x0000000000001000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 15) & 1u) )) & 0x0000000000004000ull;
    NOR_0_B |= ((uint64_t)-( ((s.NOR_O_0 >> 17) & 1u) )) & 0x0000000000010000ull;
    n.NOR_O_0 = ~(NOR_0_A | NOR_0_B) & 0x00000000ffffffffull;

    return n;
}

int main(void) {
    State s = {0};
    unsigned long long In = 0ull;
    unsigned long long clk = 0ull;
    while (1) {
        printf("Enter inputs: In clk\n");
        if (scanf("%llu %llu", &In, &clk) != 2) break;
        s = tick(s, In, clk);

        unsigned long long Out_val = (( (s.NOR_O_0 >> 1) & 1ull) << 0) | (( (s.NOR_O_0 >> 3) & 1ull) << 1) | (( (s.NOR_O_0 >> 5) & 1ull) << 2) | (( (s.NOR_O_0 >> 7) & 1ull) << 3) | (( (s.NOR_O_0 >> 9) & 1ull) << 4) | (( (s.NOR_O_0 >> 11) & 1ull) << 5) | (( (s.NOR_O_0 >> 13) & 1ull) << 6) | (( (s.NOR_O_0 >> 15) & 1ull) << 7) | (( (s.NOR_O_0 >> 17) & 1ull) << 8) | (( (s.NOR_O_0 >> 19) & 1ull) << 9) | (( (s.NOR_O_0 >> 21) & 1ull) << 10) | (( (s.NOR_O_0 >> 23) & 1ull) << 11) | (( (s.NOR_O_0 >> 25) & 1ull) << 12) | (( (s.NOR_O_0 >> 27) & 1ull) << 13) | (( (s.NOR_O_0 >> 29) & 1ull) << 14) | (( (s.NOR_O_0 >> 31) & 1ull) << 15);
        printf("Out=%llu\n", Out_val);
    }
    return 0;
}