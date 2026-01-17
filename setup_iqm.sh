#!/bin/bash
# Quick setup script for IQM hardware validation
# Edit this file with your credentials, then run: bash setup_iqm.sh

# ============================================================================
# IQM API Key Setup
# ============================================================================

# If you have an API Key (from IQM account):
export IQM_API_KEY="your-api-key-here"
export IQM_API_URL="https://api.resonance.meetiqm.com"

# Alternative: If you have OAuth credentials:
# export IQM_CLIENT_ID="your-client-id"
# export IQM_CLIENT_SECRET="your-client-secret"

# ============================================================================
# Verify Setup
# ============================================================================

echo "Checking IQM credentials..."

if [ -n "$IQM_API_KEY" ]; then
    echo "✓ API Key: ${IQM_API_KEY:0:10}..."
    echo "✓ API URL: $IQM_API_URL"
fi

if [ -n "$IQM_CLIENT_ID" ]; then
    echo "✓ OAuth Client ID: ${IQM_CLIENT_ID:0:10}..."
    echo "✓ OAuth Client Secret: ${IQM_CLIENT_SECRET:0:10}..."
fi

if [ -z "$IQM_API_KEY" ] && [ -z "$IQM_CLIENT_ID" ]; then
    echo "✗ No IQM credentials found!"
    echo "Please set IQM_API_KEY or IQM_CLIENT_ID + IQM_CLIENT_SECRET"
    exit 1
fi

echo ""
echo "Setup complete! You can now run:"
echo "  python experiments/hardware_validate.py --num-circuits 5"
