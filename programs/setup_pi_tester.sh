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

if [[ -d .git ]]; then
    info "Updating git repository (git pull --ff-only)..."
    git pull --ff-only
else
    info "No .git directory detected; skipping git pull."
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

info "Reinstalling project tester dependencies..."
pip uninstall -y sanbot-mcu-bridge >/dev/null 2>&1 || true
pip install --upgrade --force-reinstall '.[tester]'

if groups "$USER" | grep -qw plugdev && groups "$USER" | grep -qw audio; then
    info "User already in plugdev and audio groups; skipping group update."
else
    info "Adding $USER to plugdev and audio groups (sudo)..."
    sudo usermod -aG plugdev,audio "$USER"
    echo "*** Log out and back in (or reboot) for group membership to take effect."
fi

info "Installing udev rule for Sanbot USB permissions and auto-detach..."
sudo tee /etc/udev/rules.d/99-sanbot.rules >/dev/null <<'EOF'
SUBSYSTEM=="usb", ATTR{idVendor}=="0483", ATTR{idProduct}=="5740", MODE="0666", GROUP="plugdev", \
  RUN+="/bin/sh -c 'echo -n $env{DEVPATH}:1.0 > /sys/bus/usb/drivers/cdc_acm/unbind 2>/dev/null || true'"
SUBSYSTEM=="usb", ATTR{idVendor}=="0483", ATTR{idProduct}=="5741", MODE="0666", GROUP="plugdev", \
  RUN+="/bin/sh -c 'echo -n $env{DEVPATH}:1.0 > /sys/bus/usb/drivers/cdc_acm/unbind 2>/dev/null || true'"
EOF
sudo udevadm control --reload-rules
sudo udevadm trigger
echo "*** Unplug/replug the Sanbot USB cable after this script completes to apply new rules."

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
