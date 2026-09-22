import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const repo = 'https://github.com/rafa-rrayes/SHDL';

// Pages of the retired SHDB debugger section. The debugger is planned, not
// shipped; old links land on the roadmap instead of a 404.
const debuggerPages = [
  'overview', 'getting-started', 'debug-build', 'commands', 'breakpoints',
  'inspection', 'hierarchy', 'waveforms', 'scripting', 'python-api',
  'common-problems',
];

const config: Config = {
  title: 'SHDL',
  tagline: 'A gate-level hardware description language that simulates every gate, every cycle.',
  favicon: 'img/favicon.svg',

  future: {
    v4: true,
  },

  url: 'https://rafa-rrayes.github.io',
  baseUrl: '/SHDL/',
  organizationName: 'rafa-rrayes',
  projectName: 'SHDL',
  trailingSlash: false,

  onBrokenLinks: 'throw',
  onBrokenAnchors: 'throw',

  markdown: {
    // .md is CommonMark, .mdx is MDX: the in-repo specs (rendered under
    // /specs) are plain GitHub Markdown full of `<`, `{` and `}`.
    format: 'detect',
    hooks: {
      onBrokenMarkdownLinks: 'throw',
    },
  },

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          editUrl: `${repo}/tree/master/website/`,
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  plugins: [
    [
      '@docusaurus/plugin-content-docs',
      {
        id: 'specs',
        path: '../docs',
        routeBasePath: 'specs',
        sidebarPath: './sidebarsSpecs.ts',
        editUrl: `${repo}/tree/master/docs/`,
      },
    ],
    [
      '@docusaurus/plugin-client-redirects',
      {
        redirects: [
          {from: '/docs/examples/bit-adder', to: '/docs/examples/8-bit-adder'},
          {from: '/docs/category/language-reference', to: '/docs/language-reference/overview'},
          {from: '/docs/category/shdb-debugger', to: '/docs/roadmap'},
          {from: '/docs/debugger', to: '/docs/roadmap'},
          ...debuggerPages.map((page) => ({
            from: `/docs/debugger/${page}`,
            to: '/docs/roadmap',
          })),
        ],
      },
    ],
  ],

  themeConfig: {
    colorMode: {
      respectPrefersColorScheme: true,
    },
    navbar: {
      title: 'SHDL',
      logo: {
        alt: 'SHDL',
        src: 'img/logo.svg',
      },
      items: [
        {type: 'docSidebar', sidebarId: 'guide', position: 'left', label: 'Docs'},
        {to: '/docs/language-reference/overview', label: 'Language', position: 'left'},
        {to: '/docs/tools/python-api', label: 'Python API', position: 'left'},
        {to: '/docs/tools/shdl-cli', label: 'CLI', position: 'left'},
        {
          type: 'docSidebar',
          sidebarId: 'specs',
          docsPluginId: 'specs',
          position: 'left',
          label: 'Specs',
        },
        {href: 'https://rafa-rrayes.github.io/CCircus', label: 'Circuit Circus', position: 'right'},
        {href: repo, label: 'GitHub', position: 'right'},
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Learn',
          items: [
            {label: 'Introduction', to: '/docs/intro'},
            {label: 'Your first circuit', to: '/docs/getting-started/first-circuit'},
            {label: 'Simulation model', to: '/docs/concepts/simulation-model'},
            {label: 'Language reference', to: '/docs/language-reference/overview'},
          ],
        },
        {
          title: 'Tools',
          items: [
            {label: 'Python API', to: '/docs/tools/python-api'},
            {label: 'shdl CLI', to: '/docs/tools/shdl-cli'},
            {label: 'C ABI', to: '/docs/tools/c-abi'},
            {label: 'Specifications', to: '/specs/shdl'},
          ],
        },
        {
          title: 'Project',
          items: [
            {label: 'GitHub', href: repo},
            {label: 'Issues', href: `${repo}/issues`},
            {label: 'PyPI (PySHDL)', href: 'https://pypi.org/project/PySHDL/'},
            {label: 'Circuit Circus', href: 'https://rafa-rrayes.github.io/CCircus'},
          ],
        },
      ],
      copyright: `SHDL is free software under the GPL-3.0-or-later. Built with Docusaurus.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'toml', 'c', 'python', 'json'],
    },
    tableOfContents: {
      minHeadingLevel: 2,
      maxHeadingLevel: 4,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
