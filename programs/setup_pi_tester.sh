#!/usr/bin/env bash
# Convenience installer for the Sanbot USB bridge tester on Raspberry Pi.

set -euo pipefail

# shellcheck disable=SC2155
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -f "pyproject.toml" ]]; then
    echo "[!] Run this script from the repository root (pyproject.toml not found)." >&2
    exit 1
fi

APT_PACKAGES=(
    python3-venv
    libusb-1.0-0-dev
    libportaudio2
    portaudio19-dev
    libatlas-base-dev
    libxcb-xinerama0
    libxcb-randr0
    libxcb-render-util0
    libxcb-image0
    libxcb-keysyms1
    libgl1
    python3-opencv
    unzip
)

info() { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

info "Updating APT package index (sudo)..."
sudo apt-get update

info "Installing required APT packages (sudo)..."
sudo apt-get install -y "${APT_PACKAGES[@]}"

if [[ ! -d .venv ]]; then
    info "Creating Python virtual environment (.venv)..."
    python3 -m venv .venv
fi

info "Activating virtual environment..."
# shellcheck disable=SC1091
source .venv/bin/activate

info "Upgrading pip and wheel..."
pip install --upgrade pip wheel

info "Installing project tester dependencies..."
pip install .[tester]

if groups "$USER" | grep -qw plugdev && groups "$USER" | grep -qw audio; then
    info "User already in plugdev and audio groups; skipping group update."
else
    info "Adding $USER to plugdev and audio groups (sudo)..."
    sudo usermod -aG plugdev,audio "$USER"
    echo "*** Log out and back in (or reboot) for group membership to take effect."
fi

cat <<'DONE'

Setup complete.

Next steps:
  1. Ensure the Sanbot MCU is connected via USB and camera/mic are enabled.
  2. Activate the virtual environment when needed:
       source .venv/bin/activate
  3. Launch the tester GUI from an X session:
       DISPLAY=:0 QT_QPA_PLATFORM=xcb python programs/usb_bridge_tester.py

For full usage, see usage-docs/USB_BRIDGE_TESTER.md.
DONE
