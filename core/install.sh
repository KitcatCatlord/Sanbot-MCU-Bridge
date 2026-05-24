#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CXX="${CXX:-g++}"
AUTO_INSTALL=1

for arg in "$@"; do
  case "$arg" in
    --no-install)
      AUTO_INSTALL=0
      ;;
    -h|--help)
      printf 'Usage: %s [--no-install]\n' "$0"
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$arg" >&2
      exit 2
      ;;
  esac
done

have_command() {
  command -v "$1" >/dev/null 2>&1
}

have_pkg_config_module() {
  have_command pkg-config && pkg-config --exists "$1"
}

configure_brew_paths() {
  if ! have_command brew; then
    return
  fi

  local prefixes=()
  local prefix
  for formula in sqlite libusb; do
    if prefix="$(brew --prefix "$formula" 2>/dev/null)"; then
      prefixes+=("$prefix")
    fi
  done

  for prefix in "${prefixes[@]}"; do
    if [[ -d "$prefix/lib/pkgconfig" ]]; then
      export PKG_CONFIG_PATH="$prefix/lib/pkgconfig:${PKG_CONFIG_PATH:-}"
    fi
    if [[ -d "$prefix" ]]; then
      export CMAKE_PREFIX_PATH="$prefix:${CMAKE_PREFIX_PATH:-}"
    fi
  done
}

missing_dependencies() {
  local missing=()

  have_command pkg-config || missing+=("pkg-config")
  have_pkg_config_module sqlite3 || missing+=("sqlite3")
  have_pkg_config_module libusb-1.0 || missing+=("libusb-1.0")
  printf '%s\n' "${missing[@]}"
}

install_with_package_manager() {
  if [[ "$AUTO_INSTALL" -eq 0 ]]; then
    return 1
  fi

  if have_command brew; then
    brew install pkg-config sqlite libusb
    configure_brew_paths
    return 0
  fi

  if have_command apt-get; then
    sudo apt-get update
    sudo apt-get install -y build-essential pkg-config libsqlite3-dev libusb-1.0-0-dev
    return 0
  fi

  if have_command dnf; then
    sudo dnf install -y gcc-c++ pkgconf-pkg-config sqlite-devel libusb1-devel
    return 0
  fi

  if have_command pacman; then
    sudo pacman -S --needed --noconfirm base-devel pkgconf sqlite libusb
    return 0
  fi

  if have_command zypper; then
    sudo zypper install -y gcc-c++ pkg-config sqlite3-devel libusb-1_0-devel
    return 0
  fi

  return 1
}

ensure_dependencies() {
  configure_brew_paths

  local missing
  missing="$(missing_dependencies)"
  if [[ -z "$missing" ]]; then
    return
  fi

  printf 'Missing build libraries:\n%s\n' "$missing" >&2
  if ! install_with_package_manager; then
    cat >&2 <<'EOF'
Could not automatically install the missing libraries.
Install pkg-config, SQLite3 development headers, and libusb-1.0 development headers.
On macOS with Homebrew:
  brew install pkg-config sqlite libusb
EOF
    exit 1
  fi

  missing="$(missing_dependencies)"
  if [[ -n "$missing" ]]; then
    printf 'Still missing after install:\n%s\n' "$missing" >&2
    exit 1
  fi
}

build() {
  cd "$ROOT_DIR"

  "$CXX" -std=c++20 \
    src/main.cpp src/control-catalogue.cpp src/command-database.cpp src/packet-assembler.cpp src/usb-send.cpp \
    -o sanbot-mcu-bridge \
    $(pkg-config --cflags --libs sqlite3 libusb-1.0)

  "$CXX" -std=c++20 \
    src/command-database-smoke.cpp src/control-catalogue.cpp src/command-database.cpp src/packet-assembler.cpp \
    -o sanbot-command-db-smoke \
    $(pkg-config --cflags --libs sqlite3)

}

ensure_dependencies
build
