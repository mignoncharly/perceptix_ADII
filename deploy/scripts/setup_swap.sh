#!/bin/bash
# ============================================================================
# Swap Setup Script
# ============================================================================
# This script sets up a 4GB swap file to prevent OOM kills during deployment.
# ============================================================================

set -e

SWAP_FILE="/swapfile"
SWAP_SIZE="4G"

# Check if script is run as root
if [ "$(id -u)" -ne 0 ]; then
    echo "Error: This script must be run as root."
    echo "Usage: sudo $0"
    exit 1
fi

echo "Checking for existing swap..."
if swapon --show | grep -q "$SWAP_FILE"; then
    echo "Swap file $SWAP_FILE already exists and is active."
    free -h
    exit 0
fi

if [ -f "$SWAP_FILE" ]; then
    echo "Swap file $SWAP_FILE exists but is not active."
else
    echo "Creating $SWAP_SIZE swap file at $SWAP_FILE..."
    fallocate -l $SWAP_SIZE $SWAP_FILE
    chmod 600 $SWAP_FILE
    mkswap $SWAP_FILE
fi

echo "Enabling swap..."
swapon $SWAP_FILE

echo "Persisting swap in /etc/fstab..."
if ! grep -q "$SWAP_FILE" /etc/fstab; then
    echo "$SWAP_FILE none swap sw 0 0" >> /etc/fstab
    echo "Added to /etc/fstab."
else
    echo "Already in /etc/fstab."
fi

echo "Swap setup complete!"
echo "Current memory usage:"
free -h
