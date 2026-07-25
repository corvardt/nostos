#!/usr/bin/env sh
# Install Nostos.
#
#   curl -fsSL https://raw.githubusercontent.com/corvardt/nostos/main/scripts/install.sh | sh
#
# Everything lands in two places, and nowhere else:
#
#   ~/.local/share/uv/tools/nostos-app    the program and its own Python
#   ~/.local/share/nostos                 database, cookies, ffmpeg, logs
#
# No system Python is touched, nothing is installed globally, and uninstalling
# is `uv tool uninstall nostos-app` plus deleting the second directory.
#
# POSIX sh on purpose: this has to run before we have installed anything.
set -eu

REPO="${NOSTOS_REPO:-corvardt/nostos}"

# Set NOSTOS_PACKAGE to install something else - a local wheel while testing,
# or a specific release. Empty means "whatever the latest release ships".
PACKAGE="${NOSTOS_PACKAGE:-}"

say()  { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

fetch() {
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$1"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- "$1"
  else
    die "Neither curl nor wget is available."
  fi
}

# The wheel is a GitHub release asset rather than a package on an index, so the
# URL has to be looked up: its filename carries the version. Unauthenticated
# API calls are rate-limited per address, which is fine for one install.
latest_wheel() {
  fetch "https://api.github.com/repos/$REPO/releases/latest" \
    | grep -o "https://[^\"]*\.whl" \
    | head -n 1
}

# ---------------------------------------------------------------------- uv
#
# uv is a single static binary that also installs Python, so this is the only
# prerequisite, and it removes the need for the user to have a Python at all.

if command -v uv >/dev/null 2>&1; then
  say "uv is already installed."
else
  say "Installing uv (a single binary; it brings its own Python)…"
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://astral.sh/uv/install.sh | sh
  else
    die "Neither curl nor wget is available. Install one, or install uv yourself."
  fi

  # uv's installer puts it here but only updates the PATH of *future* shells.
  for dir in "$HOME/.local/bin" "$HOME/.cargo/bin"; do
    [ -x "$dir/uv" ] && PATH="$dir:$PATH"
  done
  export PATH
  command -v uv >/dev/null 2>&1 || die "uv was installed but is not on PATH. Open a new terminal and run this again."
fi

# ------------------------------------------------------------------- nostos

if [ -z "$PACKAGE" ]; then
  say "Looking up the latest release…"
  PACKAGE="$(latest_wheel || true)"
  [ -n "$PACKAGE" ] || die "No release wheel found for $REPO. Has a release been published?"
fi

say "Installing ${PACKAGE##*/}…"
uv tool install --force "$PACKAGE"

# `uv tool install` puts the command in uv's tool bin directory, which is on the
# PATH of future shells only - the same gap uv's own installer leaves. Without
# this, a first install on a machine where that directory is not yet on PATH
# stopped here: the ffmpeg step never ran and the one line in the readme left a
# half-finished install behind. Prepend it for the rest of this script, and say
# so at the end rather than in place of the remaining work.
TOOL_BIN="$(uv tool dir --bin 2>/dev/null || true)"
if [ -z "$TOOL_BIN" ]; then
  # Older uv has no `--bin`. These are the same defaults it would have printed.
  TOOL_BIN="${UV_TOOL_BIN_DIR:-${XDG_BIN_HOME:-$HOME/.local/bin}}"
fi

SHELL_NEEDS_UPDATING=""
case ":$PATH:" in
  *":$TOOL_BIN:"*) ;;
  *)
    PATH="$TOOL_BIN:$PATH"
    export PATH
    SHELL_NEEDS_UPDATING=1
    ;;
esac

if ! command -v nostos >/dev/null 2>&1; then
  warn ""
  warn "nostos was installed but is not in $TOOL_BIN."
  warn "Run:  uv tool update-shell"
  warn "then open a new terminal."
  warn ""
  exit 0
fi

# ------------------------------------------------------------------- ffmpeg
#
# The one dependency pip cannot supply. A system build is better than ours, so
# only fetch one when there is nothing already there.

if command -v ffmpeg >/dev/null 2>&1 && command -v ffprobe >/dev/null 2>&1; then
  say "ffmpeg is already installed."
else
  say "Fetching ffmpeg (about 40 MB, once, into ~/.local/share/nostos)…"
  nostos ffmpeg || warn "ffmpeg could not be fetched. Install it with your package manager, then run: nostos doctor"
fi

say ""
say "Done. Start it with:"
say ""
say "    nostos"
say ""
if [ -n "$SHELL_NEEDS_UPDATING" ]; then
  say "In a new terminal that needs one more step, because $TOOL_BIN is not on"
  say "your PATH yet:"
  say ""
  say "    uv tool update-shell"
  say ""
fi
say "That opens the interface in your browser. 'nostos doctor' says what is"
say "installed and where things live; 'nostos stop' shuts it down."
