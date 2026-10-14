import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  guide: [
    'intro',
    {
      type: 'category',
      label: 'Getting Started',
      collapsed: false,
      link: {
        type: 'generated-index',
        slug: '/category/getting-started',
        description: 'Install the toolchain, build and simulate a first circuit, and set up a project.',
      },
      items: [
        'getting-started/installation',
        'getting-started/first-circuit',
        'getting-started/using-pyshdl',
        'getting-started/projects',
      ],
    },
    {
      type: 'category',
      label: 'Concepts',
      collapsed: false,
      items: ['concepts/simulation-model'],
    },
    {
      type: 'category',
      label: 'Language Reference',
      link: {type: 'doc', id: 'language-reference/overview'},
      items: [
        'language-reference/lexical-elements',
        'language-reference/components',
        'language-reference/signals',
        'language-reference/connections',
        'language-reference/parameters',
        'language-reference/generators',
        'language-reference/constants',
        'language-reference/sequential-logic',
        'language-reference/imports',
        'language-reference/standard-gates',
        'language-reference/errors',
      ],
    },
    {
      type: 'category',
      label: 'Tools',
      items: [
        'tools/python-api',
        'tools/shdl-cli',
        'tools/project-manifest',
        'tools/testing',
        'tools/packages',
        'tools/shdl-flatten',
        'tools/shdlc',
        'tools/c-abi',
        'tools/conformance',
      ],
    },
    {
      type: 'category',
      label: 'Examples',
      link: {
        type: 'generated-index',
        slug: '/category/examples',
        description: 'Complete, verified circuits: from a half adder to a 16-bit CPU and a Game of Life.',
      },
      items: [
        'examples/half-adder',
        'examples/full-adder',
        'examples/8-bit-adder',
        'examples/multiplexer',
        'examples/decoder',
        'examples/comparator',
        'examples/register',
        'examples/latches',
        'examples/alu',
        'examples/ring-oscillator',
        'examples/sr16-cpu',
        'examples/game-of-life',
      ],
    },
    {
      type: 'category',
      label: 'Architecture',
      link: {
        type: 'generated-index',
        slug: '/category/architecture',
        description: 'How the toolchain works inside: the flattener, Base SHDL, shdlc and PySHDL.',
      },
      items: [
        'architecture/overview',
        'architecture/flattening-pipeline',
        'architecture/base-shdl',
        'architecture/compiler-internals',
        'architecture/pyshdl-internals',
      ],
    },
    'roadmap',
  ],
};

export default sidebars;
