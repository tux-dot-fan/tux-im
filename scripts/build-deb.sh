#!/bin/sh
# Build tux-im .deb package.
# Usage: ./scripts/build-deb.sh
set -eu

cd "$(dirname "$0")/.."

if [ "$(id -u)" -eq 0 ]; then
    SUDO=""
else
    SUDO="sudo"
fi

# Install build dependencies.
$SUDO apt-get install -y \
    debhelper \
    dh-sequence-python3 \
    pybuild-plugin-pyproject \
    python3-all \
    python3-gi \
    python3-ibus-1.0 \
    python3-tomli-w \
    python3-httpx \
    python3-sounddevice \
    build-essential \
    dpkg-dev \
    fakeroot

# Build.
dpkg-buildpackage -us -uc -b --no-sign

echo
echo "Built packages in parent directory:"
ls -1 ../tux-im_*.deb 2>/dev/null || true
