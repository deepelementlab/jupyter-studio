# Developer Documentation

## Build dependencies

- [conda](https://docs.conda.io)

  You can install `conda` as part of a [Miniforge](https://github.com/conda-forge/miniforge) installer.

- [conda pack](https://github.com/conda/conda-pack) and [conda lock](https://github.com/conda/conda-lock) to bundle the Open Jupyter server environment into the standalone application and to create lock files. You can install them using:

  ```bash
  conda install -c conda-forge conda-pack conda-lock
  ```

- nodejs

  You can install from https://nodejs.org/en/download/ or run:

  ```bash
  conda install -c conda-forge nodejs
  ```

- yarn

  Install using

  ```bash
  npm install --global yarn
  ```

## Local development

Open Jupyter bundles JupyterLab front-end and a conda environment as its backend into an Electron application.

`<platform>`: osx-64, osx-arm64, linux or win

- Get the project source code

  ```bash
  git clone https://github.com/open-jupyter/open-jupyter.git
  ```

- Install dependencies and build Open Jupyter

  ```bash
  yarn
  yarn build
  ```

- Create the bundled Python environment installer using

  ```bash
  yarn create_env_installer:<platform>
  ```

  Installer will be created in `env_installer/jlab_server.tar.gz` and will be available for use in `env_installer/jlab_server`.

- Now you can launch Open Jupyter locally using:

  ```bash
  yarn start
  ```

  If Open Jupyter does not find a compatible Python environment configured, it will prompt for installation using the bundled environment installer or let you choose a custom environment on your computer at first launch.

## Building for distribution

- Build the application

  ```bash
  yarn run clean && yarn build
  ```

- Create bundled Python environment installer

  ```bash
  yarn create_env_installer:<platform>
  ```

- Create Open Jupyter application installer (bundles the server environment tarball).

  ```bash
  yarn dist:<platform>
  ```

  Application installers are written to `dist/` (for example `open-jupyter-x64.dmg` on macOS, `open-jupyter.deb` on Debian/Ubuntu, `open-jupyter.rpm` on Fedora, `open-jupyter-Setup.exe` on Windows) depending on the platform and `electron-builder` configuration.

## Release Instructions

For instructions on updating bundled JupyterLab packages and cutting a new release, please follow [Release.md](Release.md) document.
