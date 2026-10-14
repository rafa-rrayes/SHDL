import type {ReactNode} from 'react';
import clsx from 'clsx';
import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import Heading from '@theme/Heading';
import CodeBlock from '@theme/CodeBlock';

import styles from './index.module.css';

const heroSource = `component HalfAdder(A, B) -> (Sum, Carry) {
    x1: XOR;  a1: AND;

    connect {
        A -> x1.A;  B -> x1.B;  x1.O -> Sum;
        A -> a1.A;  B -> a1.B;  a1.O -> Carry;
    }
}`;

const pythonSource = `from SHDL import Circuit

with Circuit("examples/adder8.shdl") as c:
    c["A"] = 100
    c["B"] = 55
    c.settle()          # advance max_depth (17) gate levels
    print(c["Sum"])     # 155`;

const pipeline = `  .shdl source ──► shdl-flatten ──► Base SHDL ──► shdlc ──► C ──► cc ──► shared library
                  (flattener)     netlist of                           reset / poke / peek /
                                  AND OR NOT XOR                       step / step_settle /
                                  + JSON metadata                      run_batch
                                                                             │
                              PySHDL  (from SHDL import Circuit) ◄──────────┘ ctypes`;

type Feature = {title: string; to: string; body: ReactNode};

const features: Feature[] = [
  {
    title: 'Every gate, every cycle',
    to: '/docs/concepts/simulation-model',
    body: (
      <>
        A unit-delay model: each gate takes one cycle, so signals visibly ripple
        through your design. No tool in the chain collapses or optimizes the
        structure you wrote.
      </>
    ),
  },
  {
    title: 'A small, readable language',
    to: '/docs/language-reference/overview',
    body: (
      <>
        Components, multi-bit ports, slices, concatenation, compile-time
        parameters, generators, <code>when</code> conditionals, named
        constants, initial state and imports. Four primitive gates underneath.
      </>
    ),
  },
  {
    title: 'Compiled, not interpreted',
    to: '/docs/tools/shdlc',
    body: (
      <>
        <code>shdlc</code> turns the flat netlist into C and builds a shared
        library with a six-function ABI you can call from Python, C or anything
        with an FFI.
      </>
    ),
  },
  {
    title: 'One Python class',
    to: '/docs/tools/python-api',
    body: (
      <>
        <code>Circuit</code> runs flatten, compile, build and load in-process,
        then gives you <code>poke</code>/<code>peek</code>/<code>step</code>,
        dict-style access, batch runs and full circuit metadata.
      </>
    ),
  },
  {
    title: 'Projects and packages',
    to: '/docs/tools/shdl-cli',
    body: (
      <>
        The <code>shdl</code> CLI scaffolds projects, vendors libraries from
        the Circuit Circus index with a committed lockfile, runs test vectors
        and opens a live REPL.
      </>
    ),
  },
  {
    title: 'Verified end to end',
    to: '/docs/tools/conformance',
    body: (
      <>
        A frozen conformance corpus pins byte-exact flattener output and
        cycle-by-cycle traces; two independent reference interpreters
        cross-check the compiler.
      </>
    ),
  },
];

export default function Home(): ReactNode {
  return (
    <Layout
      title="Gate-level hardware description"
      description="SHDL is an educational gate-level hardware description language and toolchain: write circuits, flatten them to a primitive netlist, compile to C and simulate every gate, every cycle.">
      <header className={styles.hero}>
        <div className={clsx('container', styles.heroGrid)}>
          <div>
            <Heading as="h1">SHDL</Heading>
            <p className={styles.tagline}>
              A gate-level hardware description language. Describe circuits out
              of AND, OR, NOT and XOR, compile them to native code, and watch
              signals ripple through them one gate delay at a time.
            </p>
            <div className={styles.buttons}>
              <Link className="button button--primary button--lg" to="/docs/getting-started/first-circuit">
                Build your first circuit
              </Link>
              <Link className="button button--secondary button--outline button--lg" to="/docs/intro">
                What is SHDL?
              </Link>
            </div>
          </div>
          <CodeBlock language="shdl" title="halfAdder.shdl" className={styles.heroCode}>
            {heroSource}
          </CodeBlock>
        </div>
      </header>
      <main>
        <section className={clsx('container', styles.features)}>
          <div className="row">
            {features.map((f) => (
              <div key={f.title} className={clsx('col col--4 margin-bottom--lg', styles.feature)}>
                <Heading as="h3">
                  <Link to={f.to}>{f.title}</Link>
                </Heading>
                <p>{f.body}</p>
              </div>
            ))}
          </div>
        </section>
        <section className={clsx('container', styles.pipeline)}>
          <div className="row">
            <div className="col col--6">
              <Heading as="h2">Drive it from Python</Heading>
              <CodeBlock language="python">{pythonSource}</CodeBlock>
            </div>
            <div className="col col--6">
              <Heading as="h2">The toolchain</Heading>
              <CodeBlock language="text">{pipeline}</CodeBlock>
              <p>
                Install with <code>pip install PySHDL</code> (Python 3.14+ and a C
                compiler). See <Link to="/docs/getting-started/installation">Installation</Link>.
              </p>
            </div>
          </div>
        </section>
      </main>
    </Layout>
  );
}
