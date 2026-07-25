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

# The distribution is nostos-app; the command it installs is `nostos`.
PACKAGE="${NOSTOS_PACKAGE:-nostos-app}"

say()  { printf '%s\n' "$*"; }
warn() { printf '%s\n' "$*" >&2; }
die()  { printf 'error: %s\n' "$*" >&2; exit 1; }

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

say "Installing $PACKAGE…"
uv tool install --force "$PACKAGE"

if ! command -v nostos >/dev/null 2>&1; then
  warn ""
  warn "nostos is installed but not yet on your PATH."
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
say "That opens the interface in your browser. 'nostos doctor' says what is"
say "installed and where things live; 'nostos stop' shuts it down."
