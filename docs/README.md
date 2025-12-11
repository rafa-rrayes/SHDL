# Website

This website is built using [Docusaurus](https://docusaurus.io/), a modern static website generator.

Go to [docs/](https://github.com/rafa-rrayes/SHDL/tree/docs/docs) to see the documentation markdown files.

## Installation

```bash
yarn
```

## Local Development

```bash
yarn start
```

This command starts a local development server and opens up a browser window. Most changes are reflected live without having to restart the server.

## Build

```bash
yarn build
```

This command generates static content into the `build` directory and can be served using any static contents hosting service.

## Deployment

This site is automatically deployed to GitHub Pages when changes are pushed to the `main` branch.

The deployment is handled by a GitHub Actions workflow that:
1. Builds the static site using `yarn build`
2. Uploads the build artifacts
3. Deploys to GitHub Pages

To trigger a manual deployment, go to the Actions tab in GitHub and run the "Deploy Docusaurus to GitHub Pages" workflow.

### Manual Deployment (Alternative)

If needed, you can also deploy manually using SSH:

```bash
USE_SSH=true yarn deploy
```

Or without SSH:

```bash
GIT_USER=<Your GitHub username> yarn deploy
```
