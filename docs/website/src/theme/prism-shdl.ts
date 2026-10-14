/**
 * Prism grammar for SHDL and Base SHDL (the lexer in flattener/lexer.py is
 * the source of truth). Comments come in three forms: `# line`,
 * `"single-line string"` and `"""triple-quoted"""`; all are ignored by the
 * flattener. Base SHDL reuses the grammar; its trailing `meta { ... }` block is
 * JSON (whose strings would otherwise read as SHDL string comments).
 */
import type * as PrismNamespace from 'prismjs';

export default function registerShdl(Prism: typeof PrismNamespace): void {
  const shdl = {
    comment: [
      {pattern: /"""[\s\S]*?"""/, greedy: true},
      {pattern: /"[^"\n]*"/, greedy: true},
      {pattern: /#.*/, greedy: true},
    ],
    keyword: /\b(?:component|use|connect|init|when|else|top)\b/,
    builtin: /\b(?:AND|OR|NOT|XOR|__VCC__|__GND__)\b/,
    'class-name': /\b[A-Z][A-Za-z0-9_]*(?=\s*(?:<|\())/,
    number: /\b(?:0[xX][0-9a-fA-F]+|0[bB][01]+|\d+)\b/,
    operator: /->|::|==|!=|<=|>=|&&|\|\||[=<>+\-*/:]/,
    punctuation: /[{}[\];(),.]/,
  };
  Prism.languages.shdl = shdl;
  Prism.languages['base-shdl'] = {
    meta: {
      pattern: /^meta\s*\{[\s\S]*/m,
      greedy: true,
      inside: {
        keyword: /^meta\b/,
        rest: Prism.languages.json,
      },
    },
    ...shdl,
  };
}
