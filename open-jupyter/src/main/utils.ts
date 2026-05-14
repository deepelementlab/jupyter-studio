// Copyright (c) Jupyter Development Team.
// Distributed under the terms of the Modified BSD License.

import * as path from 'path';
import * as fs from 'fs';
import * as semver from 'semver';
import * as tar from 'tar';
import * as os from 'os';
import log from 'electron-log';
import { AddressInfo, createServer, Socket } from 'net';
import { app, nativeTheme } from 'electron';
import { IPythonEnvironment } from './tokens';
import {
  exec,
  execFile,
  ExecFileOptions,
  execFileSync,
  execSync
} from 'child_process';

export const DarkThemeBGColor = '#212121';
export const LightThemeBGColor = '#ffffff';

export interface ISaveOptions {
  id: string;
  raw: string;
}

export function isDevMode(): boolean {
  return require.main.filename.indexOf('app.asar') === -1;
}

export function getAppDir(): string {
  let appDir = app.getAppPath();
  if (!isDevMode()) {
    appDir = path.dirname(appDir);
  }

  return appDir;
}

export function getUserHomeDir(): string {
  return app.getPath('home');
}

/**
 * PNG for taskbar/window branding. Placed at `src/assets/jupyter-studio.png` and
 * copied to `build/app-assets` by the `copyassets` script.
 */
export function getDesktopWindowIconPath(): string | undefined {
  const png = path.join(__dirname, '../../app-assets/jupyter-studio.png');
  return fs.existsSync(png) ? png : undefined;
}

export function getUserDataDir(): string {
  const userDataDir = app.getPath('userData');

  if (!fs.existsSync(userDataDir)) {
    try {
      fs.mkdirSync(userDataDir, { recursive: true });
    } catch (error) {
      log.error(error);
    }
  }

  return userDataDir;
}

/**
 * GitHub `owner/repo` for releases and auto-update, parsed from package.json `repository`.
 */
export function getGithubRepoSlug(): string | undefined {
  try {
    const pkgPath = path.join(app.getAppPath(), 'package.json');
    if (!fs.existsSync(pkgPath)) {
      return undefined;
    }
    const pkg = JSON.parse(fs.readFileSync(pkgPath, 'utf8'));
    const repo = pkg.repository;
    let url: string | undefined;
    if (typeof repo === 'string') {
      url = repo;
    } else if (repo && typeof repo.url === 'string') {
      url = repo.url;
    }
    if (!url) {
      return undefined;
    }
    const normalized = url
      .replace(/^git\+/, '')
      .replace(/\.git\s*$/, '')
      .replace(/^ssh:\/\/git@github\.com[:/]/i, 'https://github.com/')
      .replace(/^git@github\.com:/i, 'https://github.com/');
    const m = normalized.match(/github\.com\/([^/]+)\/([^/]+)\/?$/i);
    return m ? `${m[1]}/${m[2]}` : undefined;
  } catch {
    return undefined;
  }
}

export function getGithubReleasesPageUrl(): string {
  const slug = getGithubRepoSlug();
  if (slug) {
    return `https://github.com/${slug}/releases`;
  }
  return 'https://github.com/open-jupyter/open-jupyter/releases';
}

export function getGithubLatestYmlUrl(): string {
  const slug = getGithubRepoSlug();
  if (slug) {
    return `https://github.com/${slug}/releases/latest/download/latest.yml`;
  }
  return 'https://github.com/open-jupyter/open-jupyter/releases/latest/download/latest.yml';
}

export function getSchemasDir(): string {
  return path.normalize(path.join(getAppDir(), './build/schemas'));
}

export function getRelativePathToUserHome(absolutePath: string): string {
  const home = getUserHomeDir();
  if (absolutePath.startsWith(home)) {
    return `~${path.sep}${path.relative(home, absolutePath)}`;
  }
}

export function getEnvironmentPath(environment: IPythonEnvironment): string {
  return envPathForPythonPath(environment.path);
}

export function getBundledEnvInstallerPath(): string {
  const appDir = getAppDir();
  return path.join(appDir, 'env_installer', 'jlab_server.tar.gz');
}

export function getBundledPythonInstallDir(): string {
  // this directory path cannot have any spaces since
  // conda environments cannot be installed to such paths
  const installDir =
    process.platform === 'darwin'
      ? path.normalize(path.join(app.getPath('home'), 'Library', app.getName()))
      : app.getPath('userData');

  if (!fs.existsSync(installDir)) {
    try {
      fs.mkdirSync(installDir, { recursive: true });
    } catch (error) {
      log.error(error);
    }
  }

  return installDir;
}

export function getBundledPythonEnvPath(): string {
  const userDataDir = getBundledPythonInstallDir();

  return path.join(userDataDir, 'jlab_server');
}

export function getBundledPythonPath(): string {
  return pythonPathForEnvPath(getBundledPythonEnvPath(), true);
}

export function isDarkTheme(themeType: string) {
  if (themeType === 'light') {
    return false;
  } else if (themeType === 'dark') {
    return true;
  } else {
    return nativeTheme.shouldUseDarkColors;
  }
}

export function clearSession(session: Electron.Session): Promise<void> {
  return new Promise((resolve, reject) => {
    try {
      Promise.all([
        session.clearCache(),
        session.clearAuthCache(),
        session.clearStorageData(),
        session.flushStorageData()
      ]).then(() => {
        resolve();
      });
    } catch (error) {
      reject();
    }
  });
}

export function isPortInUse(port: number): Promise<boolean> {
  return new Promise<boolean>((resolve, reject) => {
    let inUse = false;
    const socket = new Socket();
    socket.setTimeout(200);
    socket.once('error', err => {
      inUse = false;
      socket.destroy();
    });
    socket.on('timeout', () => {
      inUse = false;
      socket.destroy();
    });
    socket.on('connect', () => {
      inUse = true;
      socket.destroy();
    });
    socket.on('close', exception => {
      resolve(inUse);
    });
    socket.connect({ port: port, host: '127.0.0.1' });
  });
}

export function getFreePort(): Promise<number> {
  return new Promise<number>(resolve => {
    const getPort = () => {
      const server = createServer(socket => {
        socket.write('Echo server\r\n');
        socket.pipe(socket);
      });

      server.on('error', function (e) {
        getPort();
      });
      server.on('listening', function (e: any) {
        const port = (server.address() as AddressInfo).port;
        server.close();

        resolve(port);
      });

      server.listen(0, '127.0.0.1');
    };

    getPort();
  });
}

export async function waitForDuration(duration: number): Promise<boolean> {
  return new Promise(resolve => {
    setTimeout(() => {
      resolve(false);
    }, duration);
  });
}

/**
 * Wait for a function to finish for max. timeout milliseconds (copied from galata)
 *
 * @param fn Function
 * @param timeout Timeout
 */
export async function waitForFunction(
  fn: () => boolean,
  timeout?: number
): Promise<void> {
  return new Promise((resolve, reject) => {
    let checkTimer: NodeJS.Timeout = null;
    let timeoutTimer: NodeJS.Timeout = null;
    const check = async () => {
      checkTimer = null;
      if (await Promise.resolve(fn())) {
        if (timeoutTimer) {
          clearTimeout(timeoutTimer);
        }
        resolve();
      } else {
        checkTimer = setTimeout(check, 200);
      }
    };

    void check();

    if (timeout) {
      timeoutTimer = setTimeout(() => {
        timeoutTimer = null;
        if (checkTimer) {
          clearTimeout(checkTimer);
        }
        reject(new Error('Timed out waiting for condition to be fulfilled.'));
      }, timeout);
    }
  });
}

// remove alpha / beta suffixes
export function versionWithoutSuffix(version: string) {
  return `${semver.major(version, { loose: true })}.${semver.minor(version, {
    loose: true
  })}.${semver.patch(version, { loose: true })}`;
}

export enum EnvironmentInstallStatus {
  Started = 'STARTED',
  Running = 'RUNNING',
  Failure = 'FAILURE',
  Cancelled = 'CANCELLED',
  Success = 'SUCCESS',
  RemovingExistingInstallation = 'REMOVING_EXISTING_INSTALLATION'
}

export enum EnvironmentDeleteStatus {
  Started = 'STARTED',
  Running = 'RUNNING',
  Failure = 'FAILURE',
  Cancelled = 'CANCELLED',
  Success = 'SUCCESS'
}

export interface ICondaPackEnvironmentInstallListener {
  onInstallStatus: (status: EnvironmentInstallStatus, message?: string) => void;
  forceOverwrite?: boolean;
  confirmOverwrite?: () => Promise<boolean>;
}

export function bundledEnvironmentIsInstalled(): boolean {
  const bundledPythonEnvPath = getBundledPythonEnvPath();

  return (
    fs.existsSync(bundledPythonEnvPath) &&
    fs.statSync(bundledPythonEnvPath).isDirectory()
  );
}

export async function installBundledEnvironment(
  installPath: string,
  listener?: ICondaPackEnvironmentInstallListener
): Promise<boolean> {
  const condaPackPath = getBundledEnvInstallerPath();

  return installCondaPackEnvironment(condaPackPath, installPath, listener);
}

export async function installCondaPackEnvironment(
  condaPackPath: string,
  installPath: string,
  listener?: ICondaPackEnvironmentInstallListener
): Promise<boolean> {
  const isBundledInstaller = condaPackPath === getBundledEnvInstallerPath();
  // eslint-disable-next-line no-async-promise-executor
  return new Promise<boolean>(async (resolve, reject) => {
    const platform = process.platform;
    const isWin = platform === 'win32';
    installPath = installPath || getBundledPythonEnvPath();

    if (fs.existsSync(installPath)) {
      if (listener) {
        const confirmed =
          listener.forceOverwrite ||
          (listener.confirmOverwrite !== undefined &&
            (await listener.confirmOverwrite()));
        if (confirmed) {
          listener?.onInstallStatus(
            EnvironmentInstallStatus.RemovingExistingInstallation
          );
          fs.rmSync(installPath, { recursive: true });
        } else {
          listener?.onInstallStatus(EnvironmentInstallStatus.Cancelled);
          reject();
          return;
        }
      } else {
        reject();
        return;
      }
    }

    listener?.onInstallStatus(EnvironmentInstallStatus.Started);

    try {
      fs.mkdirSync(installPath, { recursive: true });
      await tar.x({ C: installPath, file: condaPackPath });
    } catch (error) {
      listener?.onInstallStatus(
        EnvironmentInstallStatus.Failure,
        'Failed to install the environment'
      );
      log.error(new Error(`Installer Exit: ${error}`));
      reject();
      return;
    }

    markEnvironmentAsJupyterInstalled(installPath, {
      type: 'conda',
      source: 'bundled-installer',
      appVersion: app.getVersion()
    });

    let unpackCommand = isWin
      ? `${installPath}\\Scripts\\activate.bat && conda-unpack`
      : `source "${installPath}/bin/activate" && conda-unpack`;

    // only unsign when installing from bundled installer
    if (platform === 'darwin' && isBundledInstaller) {
      unpackCommand = `${createUnsignScriptInEnv(
        installPath
      )}\n${unpackCommand}`;
    }

    const installerProc = exec(unpackCommand, {
      shell: isWin ? 'cmd.exe' : '/bin/bash'
    });

    installerProc.on('exit', (exitCode: number) => {
      if (exitCode === 0) {
        listener?.onInstallStatus(EnvironmentInstallStatus.Success);
        resolve(true);
      } else {
        const message = `Installer Exit: ${exitCode}`;
        listener?.onInstallStatus(EnvironmentInstallStatus.Failure, message);
        log.error(new Error(message));
        reject();
        return;
      }
    });

    installerProc.on('error', (err: Error) => {
      listener?.onInstallStatus(EnvironmentInstallStatus.Failure, err.message);
      log.error(err);
      reject();
      return;
    });
  });
}

export function markEnvironmentAsJupyterInstalled(
  envPath: string,
  extraData?: { [key: string]: any }
) {
  const envInstallInfoPath = jupyterEnvInstallInfoPathForEnvPath(envPath);

  const data = {
    installer: 'open-jupyter',
    ...(extraData || {})
  };

  try {
    const dirPath = path.dirname(envInstallInfoPath);
    if (!fs.existsSync(dirPath)) {
      fs.mkdirSync(dirPath, { recursive: true });
    }

    fs.writeFileSync(envInstallInfoPath, JSON.stringify(data, null, 2));
  } catch (error) {
    console.error('Failed to create file', envInstallInfoPath, error);
  }
}

export interface IEnvironmentDeleteListener {
  onDeleteStatus: (status: EnvironmentDeleteStatus, message?: string) => void;
}

export async function deletePythonEnvironment(
  envPath: string,
  listener?: IEnvironmentDeleteListener
): Promise<boolean> {
  return new Promise<boolean>((resolve, reject) => {
    if (!isEnvInstalledByDesktopApp(envPath)) {
      listener?.onDeleteStatus(
        EnvironmentDeleteStatus.Failure,
        'Environment cannot be deleted since it was not installed by Open Jupyter.'
      );
      reject();
    }

    try {
      listener?.onDeleteStatus(
        EnvironmentDeleteStatus.Running,
        'Deleting environment files...'
      );
      fs.rmSync(envPath, { recursive: true, force: true });
      listener?.onDeleteStatus(EnvironmentDeleteStatus.Success);
      resolve(true);
    } catch (error) {
      listener?.onDeleteStatus(EnvironmentDeleteStatus.Failure, error.message);
      reject();
    }
  });
}

export function createTempFile(
  fileName = 'temp',
  data = '',
  encoding: BufferEncoding = 'utf8'
) {
  const tempDirPath = path.join(os.tmpdir(), 'open_jupyter');
  const tmpDir = fs.mkdtempSync(tempDirPath);
  const tmpFilePath = path.join(tmpDir, fileName);

  fs.writeFileSync(tmpFilePath, data, { encoding });

  return tmpFilePath;
}

export function pythonPathForEnvPath(envPath: string, isConda?: boolean) {
  if (process.platform === 'win32') {
    if (isConda === undefined) {
      isConda = isCondaEnv(envPath);
    }
    return isConda
      ? path.join(envPath, 'python.exe')
      : path.join(envPath, 'Scripts', 'python.exe');
  } else {
    return path.join(envPath, 'bin', 'python');
  }
}

export function envPathForPythonPath(pythonPath: string): string {
  const isWin = process.platform === 'win32';
  let envPath = path.dirname(pythonPath);
  if (!isWin || path.basename(envPath) === 'Scripts') {
    envPath = path.normalize(path.join(envPath, '../'));
  }

  return envPath;
}

export function activatePathForEnvPath(envPath: string) {
  return process.platform === 'win32'
    ? path.join(envPath, 'Scripts', 'activate.bat')
    : path.join(envPath, 'bin', 'activate');
}

export function condaSourcePathForEnvPath(envPath: string) {
  if (process.platform !== 'win32') {
    return path.join(envPath, 'etc', 'profile.d', 'conda.sh');
  }
}

export function jupyterEnvInstallInfoPathForEnvPath(envPath: string) {
  return path.join(envPath, '.jupyter', 'env.json');
}

export function isEnvInstalledByDesktopApp(envPath: string) {
  return fs.existsSync(jupyterEnvInstallInfoPathForEnvPath(envPath));
}

export function isCondaEnv(envPath: string): boolean {
  return fs.existsSync(path.join(envPath, 'conda-meta'));
}

// TODO: sync with condaExePathForEnvPath
export function isBaseCondaEnv(envPath: string): boolean {
  const isWin = process.platform === 'win32';
  const condaBinPath = path.join(
    envPath,
    'condabin',
    isWin ? 'conda.bat' : 'conda'
  );
  return fs.existsSync(condaBinPath) && fs.lstatSync(condaBinPath).isFile();
}

export function createCommandScriptInEnv(
  envPath: string,
  baseCondaEnvPath: string,
  options?: {
    command?: string;
    quoteChar?: string;
    joinStr?: string;
  }
): string {
  try {
    const stat = fs.lstatSync(envPath);
    if (!stat.isDirectory()) {
      return '';
    }
  } catch (error) {
    //
  }

  const quoteChar = options?.quoteChar || '"';
  const joinStr = options?.joinStr || '\n';
  let command = options?.command;
  const isWin = process.platform === 'win32';

  let activatePath = activatePathForEnvPath(envPath);
  let condaSourcePath;

  let hasActivate = fs.existsSync(activatePath);
  const isConda = isCondaEnv(envPath);
  // conda commands don't work properly when called from the sub environment.
  // instead call using conda from the base environment with -p parameter
  const isCondaCommand = isConda && command?.startsWith('conda ');
  if (isCondaCommand && !isBaseCondaEnv(envPath)) {
    command = `${command} -p ${envPath}`;
  }

  // conda activate is only available in base conda environments or
  // conda-packed environments
  let isBaseCondaActivate = false;
  if (!hasActivate && isConda) {
    if (fs.existsSync(baseCondaEnvPath)) {
      activatePath = activatePathForEnvPath(baseCondaEnvPath);
      condaSourcePath = condaSourcePathForEnvPath(baseCondaEnvPath);
      hasActivate = fs.existsSync(activatePath);
      isBaseCondaActivate = true;
    }
  }

  if (!hasActivate) {
    return '';
  }

  const scriptLines: string[] = [];

  if (isWin) {
    scriptLines.push(`CALL ${activatePath}`);
    if (isConda && isBaseCondaActivate) {
      scriptLines.push(`CALL conda activate ${envPath}`);
    }
    if (command) {
      scriptLines.push(`CALL ${command}`);
    }
  } else {
    scriptLines.push(`source ${quoteChar}${activatePath}${quoteChar}`);
    if (isConda && isBaseCondaActivate) {
      scriptLines.push(`source ${quoteChar}${condaSourcePath}${quoteChar}`);
      if (!isCondaCommand) {
        scriptLines.push(`conda activate ${quoteChar}${envPath}${quoteChar}`);
      }
    }
    if (command) {
      scriptLines.push(command);
    }
  }

  return scriptLines.join(joinStr);
}

/*
  signed tarball contents need to be unsigned except for python binary,
  otherwise server runs into issues at runtime. python binary comes originally
  ad-hoc signed. after installation it needs be converted from hardened runtime,
  back to ad-hoc signed.
*/
export function createUnsignScriptInEnv(envPath: string): string {
  const appDir = getAppDir();
  const signListFile = path.join(
    appDir,
    'env_installer',
    `sign-osx-${process.arch === 'arm64' ? 'arm64' : '64'}.txt`
  );
  const fileContents = fs.readFileSync(signListFile, 'utf-8');
  const signList: string[] = [];

  fileContents.split(/\r?\n/).forEach(line => {
    if (line) {
      signList.push(`"${line}"`);
    }
  });

  // sign all binaries with ad-hoc signature
  return `cd ${envPath} && codesign -s - -o 0x2 -f ${signList.join(
    ' '
  )} && cd -`;
}

export function getLogFilePath(processType: 'main' | 'renderer' = 'main') {
  switch (process.platform) {
    case 'win32':
      return path.join(getUserDataDir(), `\\logs\\${processType}.log`);
    case 'darwin':
      return path.join(
        getUserHomeDir(),
        'Library',
        'Logs',
        app.getName(),
        `${processType}.log`
      );
    default:
      return path.join(
        getUserHomeDir(),
        '.config',
        app.getName(),
        'logs',
        `${processType}.log`
      );
  }
}

export async function runCommand(
  executablePath: string,
  commands: string[],
  options?: ExecFileOptions
): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(executablePath, commands, options, (error, stdout, stderr) => {
      if (error) {
        reject(error);
      }
      if (stdout) {
        resolve(stdout);
      } else if (stderr) {
        resolve(stderr);
      } else {
        reject(
          new Error(
            `"${executablePath} ${commands.join(
              ' '
            )}" produced no output to stdout or stderr!`
          )
        );
      }
    });
  });
}

export function runCommandSync(
  executablePath: string,
  commands: string[],
  options?: ExecFileOptions
): string {
  return execFileSync(executablePath, commands, options).toString();
}

export function openDirectoryInExplorer(dirPath: string): boolean {
  if (!(fs.existsSync(dirPath) && fs.statSync(dirPath).isDirectory())) {
    return false;
  }

  const { platform } = process;
  const openCommand =
    platform === 'darwin'
      ? 'open'
      : platform === 'win32'
      ? 'explorer'
      : 'xdg-open';

  exec(`${openCommand} "${dirPath}"`);

  return true;
}

export function launchTerminalInDirectory(options: {
  dirPath: string;
  interactive: boolean;
  commands?: string;
}): boolean {
  const { dirPath, interactive } = options;
  if (!(fs.existsSync(dirPath) && fs.statSync(dirPath).isDirectory())) {
    return false;
  }

  const { platform } = process;
  let commands = options.commands;

  if (platform === 'darwin') {
    let callCommands = '';
    if (commands) {
      // replace " with '
      commands = commands.split('"').join("'");
      callCommands = `&& ${commands}`;
    }

    exec(
      `osascript -e 'tell application "Terminal" to do script "cd '${dirPath}' ${callCommands}"' -e 'tell application "Terminal" to activate'`
    );
    ``;
  } else if (platform === 'win32') {
    if (commands) {
      const activateFilePath = createTempFile(
        `activate.bat`,
        `cd /D "${dirPath}"\n${commands}`
      );

      exec(`start cmd.exe /K ${activateFilePath}`);

      setTimeout(() => {
        try {
          fs.unlinkSync(activateFilePath);
        } catch (error) {
          console.error('Failed to delete the temp file');
        }
      }, 2000);
    } else {
      exec(`start cmd.exe /K cd /D "${dirPath}"`);
    }
  } else {
    let callCommands = '';
    if (commands) {
      // note that calling "exec bash" at the end will cause .bashrc to be reloaded,
      // which could possibly override python path (e.g. base conda initialization)
      callCommands = ` -- bash -c "${commands}${
        interactive ? '; exec bash' : ''
      }"`;
    }
    exec(`gnome-terminal --working-directory="${dirPath}"${callCommands}`);
  }
}

export function getJlabCLICommandSymlinkPath(): string {
  if (process.platform === 'darwin') {
    return '/usr/local/bin/jlab';
  }
}

export function getJlabCLICommandTargetPath(): string {
  if (process.platform === 'darwin') {
    return `${getAppDir()}/app/jlab`;
  }
}

export function jlabCLICommandIsSetup(): boolean {
  if (process.platform !== 'darwin') {
    return true;
  }

  const symlinkPath = getJlabCLICommandSymlinkPath();
  const targetPath = getJlabCLICommandTargetPath();

  if (!fs.existsSync(symlinkPath)) {
    return false;
  }

  const stats = fs.lstatSync(symlinkPath);
  if (!stats.isSymbolicLink()) {
    return false;
  }

  try {
    fs.accessSync(targetPath, fs.constants.X_OK);
  } catch (error) {
    log.error('App CLI is not executable', error);
    return false;
  }

  return fs.readlinkSync(symlinkPath) === targetPath;
}

export async function setupJlabCLICommandWithElevatedRights(): Promise<
  boolean
> {
  if (process.platform !== 'darwin') {
    return false;
  }

  const symlinkPath = getJlabCLICommandSymlinkPath();
  const targetPath = getJlabCLICommandTargetPath();

  if (!fs.existsSync(targetPath)) {
    log.error(`Target path "${targetPath}" does not exist! `);
    return false;
  }

  const shellCommands: string[] = [];
  const symlinkParentDir = path.dirname(symlinkPath);

  // create parent directory
  if (!fs.existsSync(symlinkParentDir)) {
    shellCommands.push(`mkdir -p ${symlinkParentDir}`);
  }

  // create symlink
  shellCommands.push(`ln -f -s \\"${targetPath}\\" \\"${symlinkPath}\\"`);

  // make files executable
  shellCommands.push(`chmod 755 \\"${symlinkPath}\\"`);
  shellCommands.push(`chmod 755 \\"${targetPath}\\"`);

  const command = `do shell script "${shellCommands.join(
    ' && '
  )}" with administrator privileges`;

  return new Promise<boolean>((resolve, reject) => {
    const cliSetupProc = exec(`osascript -e '${command}'`);

    cliSetupProc.on('exit', (exitCode: number) => {
      if (exitCode === 0) {
        resolve(true);
      } else {
        log.error(`Failed to setup CLI with exit code ${exitCode}`);
        reject();
      }
    });

    cliSetupProc.on('error', (err: Error) => {
      log.error(err);
      reject();
    });
  });
}

export async function setupJlabCommandWithUserRights() {
  const symlinkPath = getJlabCLICommandSymlinkPath();
  const targetPath = getJlabCLICommandTargetPath();

  if (!fs.existsSync(targetPath)) {
    return;
  }

  try {
    if (!fs.existsSync(symlinkPath)) {
      const cmd = `ln -s ${targetPath} ${symlinkPath}`;
      execSync(cmd, { shell: '/bin/bash' });
      fs.chmodSync(symlinkPath, 0o755);
    }

    // after a DMG install, mode resets
    fs.chmodSync(targetPath, 0o755);
  } catch (error) {
    log.error(error);
  }
}

// ---------------------------------------------------------------------------
// Local-dev JupyterLab helpers
//
// Used by the registry to decide whether a Python environment is bound to a
// local JupyterLab source checkout (``pip install -e ./jupyterlab-main``).
// When that is the case we boot ``jupyter lab --dev-mode`` against it so the
// custom extensions living under ``packages/*`` are served to the WebView.
// ---------------------------------------------------------------------------

/**
 * Normalize a path for case-insensitive comparison on Windows / macOS.
 */
function _normalizeForCompare(p: string): string {
  const normalized = path.resolve(p);
  return process.platform === 'win32' || process.platform === 'darwin'
    ? normalized.toLowerCase()
    : normalized;
}

/**
 * Return the absolute install location of ``jupyterlab`` in the given Python
 * environment, preferring ``Editable project location`` (PEP 660 / pip > 21.3)
 * over the regular ``Location`` field. Returns ``undefined`` if the import
 * does not exist or the command failed.
 */
export function getJupyterlabInstallLocation(
  pythonPath: string
): string | undefined {
  if (!pythonPath || !fs.existsSync(pythonPath)) {
    return undefined;
  }
  // Default 30s. Windows cold start of a venv python + pip show easily blows
  // through 8s on slow disks / first launches, which previously caused
  // ``_tryResolveLocalDevEnvironment`` to silently fall back to the system
  // conda env (a different jupyterlab without our AI Coder extension). The
  // override env var helps users on extra slow machines.
  const timeoutMs = (() => {
    const v = parseInt(
      process.env.OPEN_JUPYTER_PIP_SHOW_TIMEOUT_MS || '',
      10
    );
    return Number.isFinite(v) && v > 0 ? v : 30000;
  })();
  try {
    const out = execFileSync(
      pythonPath,
      ['-m', 'pip', 'show', 'jupyterlab'],
      { encoding: 'utf8', timeout: timeoutMs }
    );
    const editable = out.match(/Editable project location:\s*(.+)/i);
    if (editable && editable[1]) {
      return path.resolve(editable[1].trim());
    }
    const location = out.match(/^Location:\s*(.+)$/im);
    if (location && location[1]) {
      return path.resolve(location[1].trim());
    }
  } catch (err) {
    // Promote from debug to info so the cause is visible without --debug.
    log.info(
      `[open-jupyter] pip show jupyterlab failed for ${pythonPath} (timeout=${timeoutMs}ms): ${err}. ` +
        `Increase OPEN_JUPYTER_PIP_SHOW_TIMEOUT_MS or warm the venv to fix this.`
    );
  }
  return undefined;
}

/**
 * True when the given ``pythonPath`` resolves an editable install of
 * JupyterLab that lives inside ``localPath`` (or matches it exactly).
 */
export function isJupyterlabEditableAt(
  pythonPath: string,
  localPath: string
): boolean {
  if (!localPath) return false;
  const loc = getJupyterlabInstallLocation(pythonPath);
  if (!loc) return false;
  const a = _normalizeForCompare(loc);
  const b = _normalizeForCompare(localPath);
  return a === b || a.startsWith(b + path.sep);
}

/**
 * True when ``localPath`` looks like a JupyterLab source checkout
 * (``packages/``, ``dev_mode/`` and ``pyproject.toml`` exist).
 */
export function looksLikeJupyterLabSourceTree(localPath: string): boolean {
  if (!localPath || !fs.existsSync(localPath)) return false;
  return (
    fs.existsSync(path.join(localPath, 'packages')) &&
    fs.existsSync(path.join(localPath, 'dev_mode')) &&
    (fs.existsSync(path.join(localPath, 'pyproject.toml')) ||
      fs.existsSync(path.join(localPath, 'setup.cfg')) ||
      fs.existsSync(path.join(localPath, 'setup.py')))
  );
}

/**
 * True when ``dev_mode/static/index.html`` exists, i.e. ``jlpm run build:dev``
 * has been executed at least once. Without it, launching jupyter lab in
 * ``--dev-mode`` would yield a blank page.
 */
export function localJupyterLabDevModeBuilt(localPath: string): boolean {
  if (!localPath) return false;
  return fs.existsSync(path.join(localPath, 'dev_mode', 'static', 'index.html'));
}

/**
 * Best-effort discovery of a Python interpreter able to load the local
 * JupyterLab source. Returns the first existing candidate among:
 *
 * 1. ``$OPEN_JUPYTER_LOCAL_DEV_PYTHON`` (escape hatch for power users / CI)
 * 2. ``<localPath>/.venv/{Scripts/python.exe|bin/python}``
 * 3. ``<localPath>/../.venv/{Scripts/python.exe|bin/python}``
 * 4. ``<localPath>/venv/{Scripts/python.exe|bin/python}``
 */
export function guessLocalDevPython(
  localPath: string
): string | undefined {
  if (!localPath) return undefined;
  const isWin = process.platform === 'win32';
  const exe = isWin ? 'python.exe' : 'python';
  const binDir = isWin ? 'Scripts' : 'bin';
  const candidates = [
    process.env.OPEN_JUPYTER_LOCAL_DEV_PYTHON,
    path.join(localPath, '.venv', binDir, exe),
    path.join(localPath, '..', '.venv', binDir, exe),
    path.join(localPath, 'venv', binDir, exe)
  ].filter(Boolean) as string[];
  return candidates.find(p => fs.existsSync(p));
}

/**
 * Default location of the JupyterLab source checkout when the user does not
 * configure it explicitly. The Electron app lives in ``open-jupyter/`` and
 * its sibling ``jupyterlab-main/`` is where the source tree is expected.
 */
export function getDefaultLocalJupyterLabPath(): string {
  return path.resolve(getAppDir(), '..', 'jupyterlab-main');
}
