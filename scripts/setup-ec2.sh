#!/bin/bash
# One-time setup for the EC2 benchmark client.
# Run this once on a fresh Amazon Linux 2023 instance before benchmark-aws.sh.
#
# Installs: wrk2, jq, git, gcc, make, openssl-devel
# Tested on: Amazon Linux 2023 (AL2023), Amazon Linux 2 (AL2)
set -euo pipefail

echo "════════════════════════════════════════"
echo " EC2 Benchmark Client — Setup"
echo "════════════════════════════════════════"

# ── Detect package manager ─────────────────────────────────────────────────────
if command -v dnf &>/dev/null; then
    PKG="dnf"
elif command -v yum &>/dev/null; then
    PKG="yum"
elif command -v apt-get &>/dev/null; then
    PKG="apt-get"
else
    echo "Unsupported OS — install wrk2 manually."
    exit 1
fi
echo "Package manager: $PKG"

# ── Install dependencies ───────────────────────────────────────────────────────
if [ "$PKG" = "apt-get" ]; then
    sudo apt-get update -y
    sudo apt-get install -y git make gcc libssl-dev jq python3 python3-pip
else
    sudo "$PKG" install -y git make gcc openssl-devel jq python3 python3-pip
fi

# ── Python packages for benchmark.py ──────────────────────────────────────────
pip3 install --user pandas matplotlib

# ── Build wrk2 from source ─────────────────────────────────────────────────────
# wrk2 is the constant-rate variant of wrk — mandatory for accurate HDR histograms.
if command -v wrk2 &>/dev/null; then
    echo "wrk2 already installed: $(wrk2 --version 2>&1 | head -1)"
else
    echo "Building wrk2 from source..."
    TMPDIR=$(mktemp -d)
    git clone --depth 1 https://github.com/giltene/wrk2.git "$TMPDIR/wrk2"
    make -C "$TMPDIR/wrk2" -j"$(nproc)"
    sudo cp "$TMPDIR/wrk2/wrk" /usr/local/bin/wrk2
    rm -rf "$TMPDIR"
    echo "wrk2 installed: $(wrk2 --version 2>&1 | head -1)"
fi

# ── Install AWS CLI v2 (if missing) ───────────────────────────────────────────
if ! command -v aws &>/dev/null; then
    echo "Installing AWS CLI v2..."
    curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o /tmp/awscliv2.zip
    unzip -q /tmp/awscliv2.zip -d /tmp
    sudo /tmp/aws/install
    rm -rf /tmp/aws /tmp/awscliv2.zip
fi
echo "AWS CLI: $(aws --version)"

echo ""
echo "✓ Setup complete. Next steps:"
echo "  1. Upload repo:  scp -r algo-test/ ec2-user@<ip>:~/"
echo "  2. Run smoke tests:  bash scripts/test-aws.sh"
echo "  3. Run benchmark:    python3 scripts/benchmark.py"
