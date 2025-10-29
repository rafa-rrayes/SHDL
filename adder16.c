#include <stdint.h>
#include <stdio.h>
#include <string.h>

// Auto-generated bit-packed registered simulator for FullAdder16
// Each gate family packs up to 64 instances into a 64-bit lane vector.
// Next state is computed from previous state and current inputs (2-phase update).
//
// Library API:
//   void reset(void);
//   void poke(const char *signal_name, uint64_t value);
//   uint64_t peek(const char *signal_name);
//   void eval(void);
//   void step(int cycles);
//   void dump_vcd(const char *filename);

typedef struct {
    uint64_t XOR_O_0;  // chunk 0 of XOR outputs
    uint64_t AND_O_0;  // chunk 0 of AND outputs
    uint64_t OR_O_0;  // chunk 0 of OR outputs
} State;

static inline State tick(State s, uint64_t A, uint64_t B, uint64_t Cin) {
    State n = s;

    uint64_t XOR_0_A = 0ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 9) & 1u) )) & 0x0000000000040000ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 10) & 1u) )) & 0x0000000000100000ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 11) & 1u) )) & 0x0000000000400000ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 12) & 1u) )) & 0x0000000001000000ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 13) & 1u) )) & 0x0000000004000000ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 14) & 1u) )) & 0x0000000010000000ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 15) & 1u) )) & 0x0000000040000000ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 0) & 1u) )) & 0x0000000000000001ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 1) & 1u) )) & 0x0000000000000004ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 2) & 1u) )) & 0x0000000000000010ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 3) & 1u) )) & 0x0000000000000040ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 4) & 1u) )) & 0x0000000000000100ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 5) & 1u) )) & 0x0000000000000400ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 6) & 1u) )) & 0x0000000000001000ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 7) & 1u) )) & 0x0000000000004000ull;
    XOR_0_A |= ((uint64_t)-( ((A >> 8) & 1u) )) & 0x0000000000010000ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 18) & 1u) )) & 0x0000000000080000ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 20) & 1u) )) & 0x0000000000200000ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 22) & 1u) )) & 0x0000000000800000ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 24) & 1u) )) & 0x0000000002000000ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 26) & 1u) )) & 0x0000000008000000ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 28) & 1u) )) & 0x0000000020000000ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 30) & 1u) )) & 0x0000000080000000ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 0) & 1u) )) & 0x0000000000000002ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 2) & 1u) )) & 0x0000000000000008ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 4) & 1u) )) & 0x0000000000000020ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 6) & 1u) )) & 0x0000000000000080ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 8) & 1u) )) & 0x0000000000000200ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 10) & 1u) )) & 0x0000000000000800ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 12) & 1u) )) & 0x0000000000002000ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 14) & 1u) )) & 0x0000000000008000ull;
    XOR_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 16) & 1u) )) & 0x0000000000020000ull;
    uint64_t XOR_0_B = 0ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 9) & 1u) )) & 0x0000000000040000ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 10) & 1u) )) & 0x0000000000100000ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 11) & 1u) )) & 0x0000000000400000ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 12) & 1u) )) & 0x0000000001000000ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 13) & 1u) )) & 0x0000000004000000ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 14) & 1u) )) & 0x0000000010000000ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 15) & 1u) )) & 0x0000000040000000ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 0) & 1u) )) & 0x0000000000000001ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 1) & 1u) )) & 0x0000000000000004ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 2) & 1u) )) & 0x0000000000000010ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 3) & 1u) )) & 0x0000000000000040ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 4) & 1u) )) & 0x0000000000000100ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 5) & 1u) )) & 0x0000000000000400ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 6) & 1u) )) & 0x0000000000001000ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 7) & 1u) )) & 0x0000000000004000ull;
    XOR_0_B |= ((uint64_t)-( ((B >> 8) & 1u) )) & 0x0000000000010000ull;
    XOR_0_B |= ((uint64_t)-( (Cin & 1u) )) & 0x0000000000000002ull;
    XOR_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 9) & 1u) )) & 0x0000000000200000ull;
    XOR_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 10) & 1u) )) & 0x0000000000800000ull;
    XOR_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 11) & 1u) )) & 0x0000000002000000ull;
    XOR_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 12) & 1u) )) & 0x0000000008000000ull;
    XOR_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 13) & 1u) )) & 0x0000000020000000ull;
    XOR_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 14) & 1u) )) & 0x0000000080000000ull;
    XOR_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 0) & 1u) )) & 0x0000000000000008ull;
    XOR_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 1) & 1u) )) & 0x0000000000000020ull;
    XOR_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 2) & 1u) )) & 0x0000000000000080ull;
    XOR_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 3) & 1u) )) & 0x0000000000000200ull;
    XOR_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 4) & 1u) )) & 0x0000000000000800ull;
    XOR_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 5) & 1u) )) & 0x0000000000002000ull;
    XOR_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 6) & 1u) )) & 0x0000000000008000ull;
    XOR_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 7) & 1u) )) & 0x0000000000020000ull;
    XOR_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 8) & 1u) )) & 0x0000000000080000ull;
    n.XOR_O_0 = (XOR_0_A ^ XOR_0_B) & 0x00000000ffffffffull;

    uint64_t AND_0_A = 0ull;
    AND_0_A |= ((uint64_t)-( ((A >> 9) & 1u) )) & 0x0000000000040000ull;
    AND_0_A |= ((uint64_t)-( ((A >> 10) & 1u) )) & 0x0000000000100000ull;
    AND_0_A |= ((uint64_t)-( ((A >> 11) & 1u) )) & 0x0000000000400000ull;
    AND_0_A |= ((uint64_t)-( ((A >> 12) & 1u) )) & 0x0000000001000000ull;
    AND_0_A |= ((uint64_t)-( ((A >> 13) & 1u) )) & 0x0000000004000000ull;
    AND_0_A |= ((uint64_t)-( ((A >> 14) & 1u) )) & 0x0000000010000000ull;
    AND_0_A |= ((uint64_t)-( ((A >> 15) & 1u) )) & 0x0000000040000000ull;
    AND_0_A |= ((uint64_t)-( ((A >> 0) & 1u) )) & 0x0000000000000001ull;
    AND_0_A |= ((uint64_t)-( ((A >> 1) & 1u) )) & 0x0000000000000004ull;
    AND_0_A |= ((uint64_t)-( ((A >> 2) & 1u) )) & 0x0000000000000010ull;
    AND_0_A |= ((uint64_t)-( ((A >> 3) & 1u) )) & 0x0000000000000040ull;
    AND_0_A |= ((uint64_t)-( ((A >> 4) & 1u) )) & 0x0000000000000100ull;
    AND_0_A |= ((uint64_t)-( ((A >> 5) & 1u) )) & 0x0000000000000400ull;
    AND_0_A |= ((uint64_t)-( ((A >> 6) & 1u) )) & 0x0000000000001000ull;
    AND_0_A |= ((uint64_t)-( ((A >> 7) & 1u) )) & 0x0000000000004000ull;
    AND_0_A |= ((uint64_t)-( ((A >> 8) & 1u) )) & 0x0000000000010000ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 18) & 1u) )) & 0x0000000000080000ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 20) & 1u) )) & 0x0000000000200000ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 22) & 1u) )) & 0x0000000000800000ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 24) & 1u) )) & 0x0000000002000000ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 26) & 1u) )) & 0x0000000008000000ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 28) & 1u) )) & 0x0000000020000000ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 30) & 1u) )) & 0x0000000080000000ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 0) & 1u) )) & 0x0000000000000002ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 2) & 1u) )) & 0x0000000000000008ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 4) & 1u) )) & 0x0000000000000020ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 6) & 1u) )) & 0x0000000000000080ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 8) & 1u) )) & 0x0000000000000200ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 10) & 1u) )) & 0x0000000000000800ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 12) & 1u) )) & 0x0000000000002000ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 14) & 1u) )) & 0x0000000000008000ull;
    AND_0_A |= ((uint64_t)-( ((s.XOR_O_0 >> 16) & 1u) )) & 0x0000000000020000ull;
    uint64_t AND_0_B = 0ull;
    AND_0_B |= ((uint64_t)-( ((B >> 9) & 1u) )) & 0x0000000000040000ull;
    AND_0_B |= ((uint64_t)-( ((B >> 10) & 1u) )) & 0x0000000000100000ull;
    AND_0_B |= ((uint64_t)-( ((B >> 11) & 1u) )) & 0x0000000000400000ull;
    AND_0_B |= ((uint64_t)-( ((B >> 12) & 1u) )) & 0x0000000001000000ull;
    AND_0_B |= ((uint64_t)-( ((B >> 13) & 1u) )) & 0x0000000004000000ull;
    AND_0_B |= ((uint64_t)-( ((B >> 14) & 1u) )) & 0x0000000010000000ull;
    AND_0_B |= ((uint64_t)-( ((B >> 15) & 1u) )) & 0x0000000040000000ull;
    AND_0_B |= ((uint64_t)-( ((B >> 0) & 1u) )) & 0x0000000000000001ull;
    AND_0_B |= ((uint64_t)-( ((B >> 1) & 1u) )) & 0x0000000000000004ull;
    AND_0_B |= ((uint64_t)-( ((B >> 2) & 1u) )) & 0x0000000000000010ull;
    AND_0_B |= ((uint64_t)-( ((B >> 3) & 1u) )) & 0x0000000000000040ull;
    AND_0_B |= ((uint64_t)-( ((B >> 4) & 1u) )) & 0x0000000000000100ull;
    AND_0_B |= ((uint64_t)-( ((B >> 5) & 1u) )) & 0x0000000000000400ull;
    AND_0_B |= ((uint64_t)-( ((B >> 6) & 1u) )) & 0x0000000000001000ull;
    AND_0_B |= ((uint64_t)-( ((B >> 7) & 1u) )) & 0x0000000000004000ull;
    AND_0_B |= ((uint64_t)-( ((B >> 8) & 1u) )) & 0x0000000000010000ull;
    AND_0_B |= ((uint64_t)-( (Cin & 1u) )) & 0x0000000000000002ull;
    AND_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 9) & 1u) )) & 0x0000000000200000ull;
    AND_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 10) & 1u) )) & 0x0000000000800000ull;
    AND_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 11) & 1u) )) & 0x0000000002000000ull;
    AND_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 12) & 1u) )) & 0x0000000008000000ull;
    AND_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 13) & 1u) )) & 0x0000000020000000ull;
    AND_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 14) & 1u) )) & 0x0000000080000000ull;
    AND_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 0) & 1u) )) & 0x0000000000000008ull;
    AND_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 1) & 1u) )) & 0x0000000000000020ull;
    AND_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 2) & 1u) )) & 0x0000000000000080ull;
    AND_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 3) & 1u) )) & 0x0000000000000200ull;
    AND_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 4) & 1u) )) & 0x0000000000000800ull;
    AND_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 5) & 1u) )) & 0x0000000000002000ull;
    AND_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 6) & 1u) )) & 0x0000000000008000ull;
    AND_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 7) & 1u) )) & 0x0000000000020000ull;
    AND_0_B |= ((uint64_t)-( ((s.OR_O_0 >> 8) & 1u) )) & 0x0000000000080000ull;
    n.AND_O_0 = (AND_0_A & AND_0_B) & 0x00000000ffffffffull;

    uint64_t OR_0_A = 0ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 18) & 1u) )) & 0x0000000000000200ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 20) & 1u) )) & 0x0000000000000400ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 22) & 1u) )) & 0x0000000000000800ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 24) & 1u) )) & 0x0000000000001000ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 26) & 1u) )) & 0x0000000000002000ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 28) & 1u) )) & 0x0000000000004000ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 30) & 1u) )) & 0x0000000000008000ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 0) & 1u) )) & 0x0000000000000001ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 2) & 1u) )) & 0x0000000000000002ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 4) & 1u) )) & 0x0000000000000004ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 6) & 1u) )) & 0x0000000000000008ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 8) & 1u) )) & 0x0000000000000010ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 10) & 1u) )) & 0x0000000000000020ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 12) & 1u) )) & 0x0000000000000040ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 14) & 1u) )) & 0x0000000000000080ull;
    OR_0_A |= ((uint64_t)-( ((s.AND_O_0 >> 16) & 1u) )) & 0x0000000000000100ull;
    uint64_t OR_0_B = 0ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 19) & 1u) )) & 0x0000000000000200ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 21) & 1u) )) & 0x0000000000000400ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 23) & 1u) )) & 0x0000000000000800ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 25) & 1u) )) & 0x0000000000001000ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 27) & 1u) )) & 0x0000000000002000ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 29) & 1u) )) & 0x0000000000004000ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 31) & 1u) )) & 0x0000000000008000ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 1) & 1u) )) & 0x0000000000000001ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 3) & 1u) )) & 0x0000000000000002ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 5) & 1u) )) & 0x0000000000000004ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 7) & 1u) )) & 0x0000000000000008ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 9) & 1u) )) & 0x0000000000000010ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 11) & 1u) )) & 0x0000000000000020ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 13) & 1u) )) & 0x0000000000000040ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 15) & 1u) )) & 0x0000000000000080ull;
    OR_0_B |= ((uint64_t)-( ((s.AND_O_0 >> 17) & 1u) )) & 0x0000000000000100ull;
    n.OR_O_0 = (OR_0_A | OR_0_B) & 0x000000000000ffffull;

    return n;
}

static inline uint64_t extract_sum(const State *s) {
    return (((s->XOR_O_0 >> 1) & 1ull) << 0) | (((s->XOR_O_0 >> 3) & 1ull) << 1) | (((s->XOR_O_0 >> 5) & 1ull) << 2) | (((s->XOR_O_0 >> 7) & 1ull) << 3) | (((s->XOR_O_0 >> 9) & 1ull) << 4) | (((s->XOR_O_0 >> 11) & 1ull) << 5) | (((s->XOR_O_0 >> 13) & 1ull) << 6) | (((s->XOR_O_0 >> 15) & 1ull) << 7) | (((s->XOR_O_0 >> 17) & 1ull) << 8) | (((s->XOR_O_0 >> 19) & 1ull) << 9) | (((s->XOR_O_0 >> 21) & 1ull) << 10) | (((s->XOR_O_0 >> 23) & 1ull) << 11) | (((s->XOR_O_0 >> 25) & 1ull) << 12) | (((s->XOR_O_0 >> 27) & 1ull) << 13) | (((s->XOR_O_0 >> 29) & 1ull) << 14) | (((s->XOR_O_0 >> 31) & 1ull) << 15) | (((s->OR_O_0 >> 15) & 1ull) << 16);
}

typedef struct {
    State current;
    State pending;
    uint64_t input_A;
    uint64_t input_B;
    uint64_t input_Cin;
    uint64_t sum;
    int pending_valid;
    int outputs_valid;
} DutContext;

static DutContext dut = {0};

static void mark_dirty(void) {
    dut.outputs_valid = 0;
    dut.pending_valid = 0;
}

static void compute_pending(void) {
    dut.pending = tick(dut.current, dut.input_A, dut.input_B, dut.input_Cin);
    dut.sum = extract_sum(&dut.pending);
    dut.pending_valid = 1;
    dut.outputs_valid = 1;
}

static void ensure_outputs(void) {
    if (!dut.outputs_valid) {
        compute_pending();
    }
}

void reset(void) {
    memset(&dut, 0, sizeof(dut));
}

void poke(const char *signal_name, uint64_t value) {
    if (strcmp(signal_name, "A") == 0) {
        dut.input_A = value & 0xffffull;
    }else if (strcmp(signal_name, "B") == 0) {
        dut.input_B = value & 0xffffull;
    }else if (strcmp(signal_name, "Cin") == 0) {
        dut.input_Cin = value & 0x1ull;
    }else {
        fprintf(stderr, "Unknown signal '%s'\n", signal_name);
        return;
    }
    mark_dirty();
}

uint64_t peek(const char *signal_name) {
    if (strcmp(signal_name, "A") == 0) {
        return dut.input_A;
    }
    if (strcmp(signal_name, "B") == 0) {
        return dut.input_B;
    }
    if (strcmp(signal_name, "Cin") == 0) {
        return dut.input_Cin;
    }

    ensure_outputs();

    const State *visible_state = dut.pending_valid ? &dut.pending : &dut.current;

    if (strcmp(signal_name, "Sum") == 0) {
        return dut.sum;
    }
    if (strcmp(signal_name, "XOR_O_0") == 0) {
        return visible_state->XOR_O_0;
    }
    if (strcmp(signal_name, "AND_O_0") == 0) {
        return visible_state->AND_O_0;
    }
    if (strcmp(signal_name, "OR_O_0") == 0) {
        return visible_state->OR_O_0;
    }

    fprintf(stderr, "Unknown signal '%s'\n", signal_name);
    return 0ull;
}

void eval(void) {
    compute_pending();
}

void step(int cycles) {
    if (cycles <= 0) {
        ensure_outputs();
        return;
    }

    for (int i = 0; i < cycles; ++i) {
        dut.current = tick(dut.current, dut.input_A, dut.input_B, dut.input_Cin);
    }

    dut.pending_valid = 0;
    dut.sum = extract_sum(&dut.current);
    dut.outputs_valid = 1;
}

void dump_vcd(const char *filename) {
    (void)filename;
    fprintf(stderr, "dump_vcd not implemented for this model\n");
}