#!/usr/bin/env bash
# Linux / macOS one-click installer mirroring install.ps1.
# Usage:
#   ./install.sh                    # full install
#   ./install.sh --start            # ... and launch the Electron shell
#   ./install.sh --skip-shell       # backend only
#   ./install.sh --recreate         # nuke .venv first
#
# All flags:
#   --python-exe <path>     Python interpreter to seed the venv from (default: python3)
#   --venv-path <path>      venv directory (default: $REPO/.venv)
#   --recreate              Delete & recreate the venv before installing
#   --skip-python           Skip the editable pip installs
#   --skip-jlpm             Skip jlpm install + build:dev
#   --skip-shell            Skip the Electron desktop shell build
#   --skip-settings-write   Don't pre-write open-jupyter settings.json
#   --start                 Run `npm start` in open-jupyter at the end
#   --use-yarn              Prefer yarn over npm for the Electron shell

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAWCODE_DIR="$REPO/clawcode"
JUPYTER_STUDIO_AI_DIR="$REPO/jupyter_studio_ai"
OPEN_JUPYTER_DIR="$REPO/open-jupyter"
JUPYTERLAB_MAIN_DIR="$OPEN_JUPYTER_DIR/jupyterlab-main"

PYTHON_EXE="python3"
VENV_PATH="$REPO/.venv"
RECREATE=0
SKIP_PYTHON=0
SKIP_JLPM=0
SKIP_SHELL=0
SKIP_SETTINGS_WRITE=0
START=0
USE_YARN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python-exe)         PYTHON_EXE="$2"; shift 2 ;;
    --venv-path)          VENV_PATH="$2"; shift 2 ;;
    --recreate)           RECREATE=1; shift ;;
    --skip-python)        SKIP_PYTHON=1; shift ;;
    --skip-jlpm)          SKIP_JLPM=1; shift ;;
    --skip-shell)         SKIP_SHELL=1; shift ;;
    --skip-settings-write) SKIP_SETTINGS_WRITE=1; shift ;;
    --start)              START=1; shift ;;
    --use-yarn)           USE_YARN=1; shift ;;
    -h|--help)
      sed -n '1,40p' "$0" ; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2 ; exit 2 ;;
  esac
done

banner() {
  echo
  printf '%s\n' "========================================================================"
  printf '>> %s\n' "$1"
  printf '%s\n' "========================================================================"
}
step() { echo ; echo "[step] $1" ; }
info() { echo "       $1" ; }
have() { command -v "$1" >/dev/null 2>&1 ; }

# JupyterLab's editable install transitively invokes
# `node buildutils/lib/ensure-repo.js`, which runs `git ls-tree HEAD --name-only`.
# Source checkouts that were not cloned via git (zip / tarball download) need
# a tiny local-only git repo for that to succeed. The repository's own
# .gitignore excludes node_modules / lib / build / dev_mode artifacts, so this
# stays cheap.
# Patch JupyterLab's buildutils so `ensureBuildUtils` doesn't fail with EPERM
# when symlink privileges are missing (mostly a Windows issue, but harmless to
# apply on POSIX). Idempotent: a sentinel marker prevents re-patching.
patch_ensure_repo_symlink_fallback() {
  local jupyterlab_main="$1"
  local files=(
    "$jupyterlab_main/buildutils/lib/ensure-repo.js"
    "$jupyterlab_main/buildutils/src/ensure-repo.ts"
  )
  for f in "${files[@]}" ; do
    [[ -f "$f" ]] || continue
    if grep -q "OPEN_JUPYTER_INSTALLER_PATCH" "$f" ; then
      info "Already patched: $f"
      continue
    fi
    "$VENV_PYTHON" - "$f" <<'PY'
import io, os, sys, pathlib
p = pathlib.Path(sys.argv[1])
text = p.read_text(encoding="utf-8")
if "OPEN_JUPYTER_INSTALLER_PATCH" in text:
    sys.exit(0)
needles = []
if p.name.endswith(".js"):
    needles.append((
        "        fs.symlinkSync(src, dest, 'file');\n        fs.chmodSync(dest, 0o777);\n",
        (
            "        // OPEN_JUPYTER_INSTALLER_PATCH: Windows non-admin accounts cannot\n"
            "        // create file symlinks (EPERM). Fall back to a regular file copy.\n"
            "        try {\n"
            "            fs.symlinkSync(src, dest, 'file');\n"
            "            fs.chmodSync(dest, 0o777);\n"
            "        }\n"
            "        catch (_b) {\n"
            "            fs.copyFileSync(src, dest);\n"
            "            try {\n"
            "                fs.chmodSync(dest, 0o777);\n"
            "            }\n"
            "            catch (_c) {\n"
            "                // best effort\n"
            "            }\n"
            "        }\n"
        ),
    ))
else:
    needles.append((
        "    fs.symlinkSync(src, dest, 'file');\n    fs.chmodSync(dest, 0o777);\n",
        (
            "    // OPEN_JUPYTER_INSTALLER_PATCH: Windows non-admin accounts cannot create\n"
            "    // file symlinks (EPERM). Fall back to a regular file copy, which is\n"
            "    // functionally equivalent for these tiny wrapper JS scripts under\n"
            "    // buildutils/lib (they are invoked via ``node ...``, not exec).\n"
            "    try {\n"
            "      fs.symlinkSync(src, dest, 'file');\n"
            "      fs.chmodSync(dest, 0o777);\n"
            "    } catch (err) {\n"
            "      fs.copyFileSync(src, dest);\n"
            "      try {\n"
            "        fs.chmodSync(dest, 0o777);\n"
            "      } catch {\n"
            "        // best effort\n"
            "      }\n"
            "    }\n"
        ),
    ))
patched = text
for find, repl in needles:
    if find in patched:
        patched = patched.replace(find, repl, 1)
if patched == text:
    print(f"  patch anchor not found in {p}; skipping")
    sys.exit(0)
p.write_text(patched, encoding="utf-8")
print(f"  patched: {p}")
PY
  done
}

init_jupyterlab_git_repo() {
  local path="$1"
  if [[ -d "$path/.git" ]]; then
    info "JupyterLab source is already a git repo, skipping init."
    return 0
  fi
  if ! have git; then
    echo "ERROR: JupyterLab's editable install requires git on PATH." >&2
    echo "       Install git first, then rerun the installer." >&2
    exit 1
  fi
  info "Seeding local git history in $path (one-time)"
  (
    cd "$path"
    git init -q
    git -c user.email=installer@open-jupyter.local \
        -c user.name="open-jupyter installer" add -A
    git -c user.email=installer@open-jupyter.local \
        -c user.name="open-jupyter installer" \
        commit -q -m "init (open-jupyter installer)" --allow-empty
  )
  info "Done. (jupyterlab-main is now a local-only git repo; not pushed anywhere.)"
}

# ---------------------------------------------------------------------------
# 0. Pre-flight
# ---------------------------------------------------------------------------

banner "jupyter-studio one-click installer"
info "Repo: $REPO"
info "Venv: $VENV_PATH"

step "Checking host tools"
have "$PYTHON_EXE" || { echo "Python not found: $PYTHON_EXE"; exit 1; }
info "Python : $($PYTHON_EXE --version 2>&1)"
have node || { echo "Node.js not found; install Node 20+."; exit 1; }
info "Node   : $(node --version)"

if have yarn ; then info "Yarn   : $(yarn --version)"; fi
if have npm  ; then info "npm    : $(npm --version)"; fi

# ---------------------------------------------------------------------------
# 1. Venv
# ---------------------------------------------------------------------------

step "Preparing virtual environment"
if [[ $RECREATE -eq 1 && -d "$VENV_PATH" ]] ; then
  info "Removing existing venv: $VENV_PATH"
  rm -rf "$VENV_PATH"
fi
if [[ ! -d "$VENV_PATH" ]] ; then
  info "Creating venv at $VENV_PATH"
  "$PYTHON_EXE" -m venv "$VENV_PATH"
else
  info "Reusing venv at $VENV_PATH"
fi

VENV_PYTHON="$VENV_PATH/bin/python"
VENV_BIN="$VENV_PATH/bin"
[[ -x "$VENV_PYTHON" ]] || { echo "venv python missing: $VENV_PYTHON"; exit 1; }

info "Upgrading pip / setuptools / wheel"
"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel

# ---------------------------------------------------------------------------
# 2. Python packages (editable installs)
# ---------------------------------------------------------------------------

if [[ $SKIP_PYTHON -eq 0 ]] ; then
  step "Installing clawcode (editable)"
  "$VENV_PYTHON" -m pip install -e "$CLAWCODE_DIR"

  step "Installing jupyter_studio_ai (editable)"
  "$VENV_PYTHON" -m pip install -e "$JUPYTER_STUDIO_AI_DIR"

  step "Preparing JupyterLab source tree for editable install"
  init_jupyterlab_git_repo "$JUPYTERLAB_MAIN_DIR"
  patch_ensure_repo_symlink_fallback "$JUPYTERLAB_MAIN_DIR"

  step "Installing JupyterLab from local source (editable + dev extras)"
  "$VENV_PYTHON" -m pip install -e "${JUPYTERLAB_MAIN_DIR}[dev]"

  step "Verifying imports"
  "$VENV_PYTHON" -c "import clawcode, jupyter_studio_ai, jupyterlab; print('clawcode', getattr(clawcode,'__version__','ok')); print('jupyterlab', jupyterlab.__version__); print('jupyter_studio_ai', jupyter_studio_ai.__version__)"

  if [[ -x "$VENV_BIN/jupyter" ]] ; then
    info "Listing server extensions"
    "$VENV_BIN/jupyter" server extension list || info "(extension list failed; continuing)"
  fi
else
  info "Skipping Python installs (--skip-python)"
fi

# ---------------------------------------------------------------------------
# 3. JupyterLab front-end (jlpm install + build:dev)
# ---------------------------------------------------------------------------

if [[ $SKIP_JLPM -eq 0 ]] ; then
  step "Building JupyterLab dev_mode (jlpm install + build:dev)"
  JLPM="$VENV_BIN/jlpm"
  [[ -x "$JLPM" ]] || { echo "jlpm not found at $JLPM; did the JupyterLab install succeed?"; exit 1; }
  ( cd "$JUPYTERLAB_MAIN_DIR" && "$JLPM" install )
  ( cd "$JUPYTERLAB_MAIN_DIR" && "$JLPM" run build:packages )
  ( cd "$JUPYTERLAB_MAIN_DIR" && "$JLPM" run build:dev )
  info "OK: dev_mode/static/index.html should now exist."
else
  info "Skipping JupyterLab dev_mode build (--skip-jlpm)"
fi

# ---------------------------------------------------------------------------
# 4. Electron shell (open-jupyter)
# ---------------------------------------------------------------------------

if [[ $SKIP_SHELL -eq 0 ]] ; then
  step "Installing open-jupyter shell dependencies"
  if [[ $USE_YARN -eq 1 ]] && have yarn ; then
    ( cd "$OPEN_JUPYTER_DIR" && yarn install )
    ( cd "$OPEN_JUPYTER_DIR" && yarn build )
  else
    have npm || { echo "npm is required; install Node.js."; exit 1; }
    ( cd "$OPEN_JUPYTER_DIR" && npm install --legacy-peer-deps )
    ( cd "$OPEN_JUPYTER_DIR" && npm run build )
  fi
else
  info "Skipping Electron shell build (--skip-shell)"
fi

# ---------------------------------------------------------------------------
# 5. Pre-write open-jupyter settings.json
# ---------------------------------------------------------------------------

if [[ $SKIP_SETTINGS_WRITE -eq 0 ]] ; then
  step "Writing open-jupyter settings.json (local-dev defaults)"
  case "$(uname -s)" in
    Darwin*) USERDATA="$HOME/Library/Application Support/open-jupyter" ;;
    *)       USERDATA="${XDG_CONFIG_HOME:-$HOME/.config}/open-jupyter" ;;
  esac
  mkdir -p "$USERDATA"
  SETTINGS="$USERDATA/settings.json"

  TMP=$(mktemp)
  if [[ -f "$SETTINGS" ]] ; then
    cp "$SETTINGS" "$TMP" || true
  else
    echo '{}' > "$TMP"
  fi
  "$VENV_PYTHON" - <<PY > "$SETTINGS"
import json, sys, pathlib
src = pathlib.Path(r"""$TMP""")
try:
    data = json.loads(src.read_text() or '{}')
except Exception:
    data = {}
data.update({
    "useLocalDevJupyterLab": True,
    "localJupyterLabPath":   r"""$JUPYTERLAB_MAIN_DIR""",
    "localJupyterLabPython": r"""$VENV_PYTHON""",
    "localJupyterLabDevMode": True,
})
print(json.dumps(data, indent=2))
PY
  rm -f "$TMP"
  info "Wrote $SETTINGS"
else
  info "Skipping settings.json write (--skip-settings-write)"
fi

# ---------------------------------------------------------------------------
# 6. Done
# ---------------------------------------------------------------------------

banner "Installation complete"
cat <<EOM

Next steps:

  * Configure your LLM API keys (env vars):
      export ANTHROPIC_API_KEY=...   # or OPENAI_API_KEY / GOOGLE_API_KEY

  * Activate the venv in new shells:
      source "$VENV_PATH/bin/activate"

  * Standalone Lab:
      jupyter lab --dev-mode --notebook-dir="$REPO"

  * Desktop shell:
      ( cd "$OPEN_JUPYTER_DIR" && npm start )

EOM

if [[ $START -eq 1 ]] ; then
  banner "Launching open-jupyter"
  cd "$OPEN_JUPYTER_DIR"
  if [[ $USE_YARN -eq 1 ]] && have yarn ; then
    yarn start
  else
    npm start
  fi
fi
