import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

// The normative specifications, rendered straight from the repository's
// docs/ directory (the same files GitHub shows).
const sidebars: SidebarsConfig = {
  specs: [
    'shdl',
    'base_shdl',
    'shdlc_goals',
    'pyshdl',
    'shdl_cli',
    'SHDL_Project',
    'golden_tests',
  ],
};

export default sidebars;
