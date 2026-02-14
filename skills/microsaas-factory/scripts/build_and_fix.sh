#!/bin/bash
# Build a micro-SaaS product with retry logic
# Usage: bash build_and_fix.sh <slug>
# Example: bash build_and_fix.sh markdown-magic

set -e

SLUG="$1"
PROJECT_DIR="/home/milad/$SLUG"
MAX_RETRIES=3

if [ -z "$SLUG" ]; then
    echo "ERROR: No slug provided"
    exit 1
fi

if [ ! -d "$PROJECT_DIR" ]; then
    echo "ERROR: Project directory $PROJECT_DIR not found"
    exit 1
fi

# Source nvm
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

cd "$PROJECT_DIR"

# Install dependencies
echo "Installing dependencies..."
npm install 2>&1
INSTALL_EXIT=$?

if [ $INSTALL_EXIT -ne 0 ]; then
    echo "INSTALL_FAILED"
    exit 1
fi

echo "Dependencies installed."

# Build with retry
ATTEMPT=1
while [ $ATTEMPT -le $MAX_RETRIES ]; do
    echo "Build attempt $ATTEMPT/$MAX_RETRIES..."
    BUILD_OUTPUT=$(npm run build 2>&1)
    BUILD_EXIT=$?

    if [ $BUILD_EXIT -eq 0 ]; then
        echo "BUILD_SUCCESS"
        echo "Product $SLUG built successfully on attempt $ATTEMPT"
        exit 0
    fi

    echo "Build attempt $ATTEMPT failed."
    echo "BUILD_OUTPUT_START"
    echo "$BUILD_OUTPUT"
    echo "BUILD_OUTPUT_END"

    ATTEMPT=$((ATTEMPT + 1))

    if [ $ATTEMPT -le $MAX_RETRIES ]; then
        echo "Waiting 2s before retry..."
        sleep 2
    fi
done

echo "BUILD_FAILED"
echo "All $MAX_RETRIES build attempts failed for $SLUG"
exit 1
