#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <ctype.h>


#ifndef COUNT_OF
#define COUNT_OF(a) (sizeof(a)/sizeof((a)[0]))
#endif

static void trim(char *s) {
    // trim leading
    char *p = s;
    while (*p && isspace((unsigned char)*p)) p++;
    if (p != s) memmove(s, p, strlen(p)+1);
    // trim trailing
    size_t n = strlen(s);
    while (n && isspace((unsigned char)s[n-1])) s[--n] = '\0';
}

static void tolower_inplace(char *s) {
    for (; *s; ++s) *s = (char)tolower((unsigned char)*s);
}

static int parse_uint(const char *s, unsigned *out) {
    char *end = NULL;
    unsigned long v = strtoul(s, &end, 10);
    if (end == s || *end != '\0') return 0;
    *out = (unsigned)v;
    return 1;
}

static void print_help(void) {
    puts(
        "Commands:\n"
        "  q | quit                     quit\n"
        "  s | step [n]                 step the simulation n times (default 1)\n"
        "  p | print outputs|nodes|inputs  print values\n"
        "  po | pn | pi                 legacy print shortcuts\n"
        "  set <inputName> <0|1>        set an input value\n"
        "  1 <inputName>                legacy: set input to 1\n"
        "  0 <inputName>                legacy: set input to 0\n"
        "  help                         show this message\n"
    );
}
static inline int toBool(int x) { return !!x; }

int notGate(const int *a)                 { return !toBool(*a); }
int andGate(const int *a, const int *b)   { return toBool(*a) && toBool(*b); }
int orGate (const int *a, const int *b)   { return toBool(*a) || toBool(*b); }
int xorGate(const int *a, const int *b)   { return toBool(*a) ^  toBool(*b); }
int nandGate(const int *a, const int *b)  { return !andGate(a, b); }
int norGate (const int *a, const int *b)  { return !orGate(a, b); }
int xnorGate(const int *a, const int *b)  { return !xorGate(a, b); }



typedef struct Node Node;  // forward typedef so we can use `Node*` below
typedef int (*EvalFn)(Node *self);

struct Node {
    const char *name;
    int output;
    EvalFn evaluate;
    const int **inputs;   // pointers to inputs
    int input_count;

};

typedef struct OutputNode {
    const char *name;
    const int *output;
} OutputNode;


int eval_not(Node *self) {
    if (self->input_count != 1) return 0;
    return notGate(self->inputs[0]);
}

int eval_and(Node *self) {
    if (self->input_count != 2) return 0;
    return andGate(self->inputs[0], self->inputs[1]);
}

int eval_or(Node *self) {
    if (self->input_count != 2) return 0;
    return orGate(self->inputs[0], self->inputs[1]);
}

int eval_xor(Node *self) {
    if (self->input_count != 2) return 0;
    return xorGate(self->inputs[0], self->inputs[1]);
}

int eval_nand(Node *self) {
    if (self->input_count != 2) return 0;
    return nandGate(self->inputs[0], self->inputs[1]);
}

int eval_nor(Node *self) {
    if (self->input_count != 2) return 0;
    return norGate(self->inputs[0], self->inputs[1]);
}

int eval_xnor(Node *self) {
    if (self->input_count != 2) return 0;
    return xnorGate(self->inputs[0], self->inputs[1]);
}


void _step(Node **nodes, size_t count) {
    if (!nodes || count == 0) return;
    int *new_state = malloc(sizeof(int) * count);
    if (!new_state) return;

    for (size_t i = 0; i < count; ++i) {
        new_state[i] = nodes[i]->evaluate ? nodes[i]->evaluate(nodes[i]) : nodes[i]->output;
    }
    for (size_t i = 0; i < count; ++i) {
        nodes[i]->output = new_state[i];
    }
    free(new_state);
}

int main(void) {


    // LE CODE


    char line[256];

    for (;;) {
        printf("\n> ");
        if (!fgets(line, sizeof line, stdin)) break;

        trim(line);
        if (line[0] == '\0') continue;


        char *argv[4] = {0};
        int argc = 0;
        char *tok = strtok(line, " \t");
        while (tok && argc < (int)COUNT_OF(argv)) {
            argv[argc++] = tok;
            tok = strtok(NULL, " \t");
        }
        // normalize the command token to lowercase for matching
        tolower_inplace(argv[0]);

        // ---- dispatch ----
        if (!strcmp(argv[0], "q") || !strcmp(argv[0], "quit")) {
            break;
        }
        else if (!strcmp(argv[0], "help")) {
            print_help();
        }
                else if (!strcmp(argv[0], "s") || !strcmp(argv[0], "step")) {
            unsigned n = 1;
            if (argc >= 2) {
                if (!parse_uint(argv[1], &n) || n == 0) {
                    puts("error: step count must be a positive integer");
                    continue;
                }
            }
            for (unsigned i = 0; i < n; ++i) {
                _step(nodes, COUNT_OF(nodes));
            }
        }
        else if (!strcmp(argv[0], "p") || !strcmp(argv[0], "print") ||
                 !strcmp(argv[0], "po") || !strcmp(argv[0], "pn") || !strcmp(argv[0], "pi")) {

            const char *what = NULL;
            if (!strcmp(argv[0], "po")) what = "outputs";
            else if (!strcmp(argv[0], "pn")) what = "nodes";
            else if (!strcmp(argv[0], "pi")) what = "inputs";
            else if (argc >= 2) {
                tolower_inplace(argv[1]);
                what = argv[1];
            }

            if (!what) {
                puts("usage: print outputs|nodes|inputs  (or po/pn/pi)");
                continue;
            }

            if (!strcmp(what, "outputs")) {
                for (size_t i = 0; i < COUNT_OF(output_nodes); ++i) {
                    printf("%s: %d\n", output_nodes[i]->name, *(output_nodes[i]->output));
                }
            } else if (!strcmp(what, "nodes")) {
                for (size_t i = 0; i < COUNT_OF(nodes); ++i) {
                    printf("%s: %d\n", nodes[i]->name, nodes[i]->output);
                }
            } else if (!strcmp(what, "inputs")) {
                for (size_t i = 0; i < COUNT_OF(input_nodes); ++i) {
                    printf("%s: %d\n", input_nodes[i]->name, input_nodes[i]->output);
                }
            } else {
                puts("unknown print target. use: outputs | nodes | inputs");
            }
        }
        else if (!strcmp(argv[0], "set")) {
            if (argc < 3) {
                puts("usage: set <inputName> <0|1>");
                continue;
            }
            const char *name = argv[1];
            unsigned val;
            if (!parse_uint(argv[2], &val) || (val != 0 && val != 1)) {
                puts("error: value must be 0 or 1");
                continue;
            }
            int found = 0;
            for (size_t i = 0; i < COUNT_OF(input_nodes); ++i) {
                if (strcmp(input_nodes[i]->name, name) == 0) {
                    input_nodes[i]->output = (int)val;
                    found = 1;
                    break;
                }
            }
            if (!found) {
                printf("input '%s' not found\n", name);
            }
        }
    }
    return 0;
}