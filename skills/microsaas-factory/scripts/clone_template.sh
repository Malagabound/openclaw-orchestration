#!/bin/bash
# Clone the micro-saas-template to a new product directory
# Usage: bash clone_template.sh <slug>
# Example: bash clone_template.sh markdown-magic

set -e

SLUG="$1"
SOURCE="/home/milad/micro-saas-template"
TARGET="/home/milad/$SLUG"

if [ -z "$SLUG" ]; then
    echo "ERROR: No slug provided"
    echo "Usage: bash clone_template.sh <slug>"
    exit 1
fi

if [ -d "$TARGET" ]; then
    echo "ERROR: Directory $TARGET already exists"
    echo "Remove it first or choose a different slug"
    exit 1
fi

if [ ! -d "$SOURCE" ]; then
    echo "ERROR: Source template not found at $SOURCE"
    exit 1
fi

echo "Cloning template to $TARGET..."
cp -r "$SOURCE" "$TARGET"

# Clean up build artifacts and git history
rm -rf "$TARGET/.git"
rm -rf "$TARGET/.next"
rm -rf "$TARGET/.vercel"
rm -rf "$TARGET/node_modules"
rm -f "$TARGET/.env.local"

echo "CLONE_SUCCESS"
echo "Directory: $TARGET"
