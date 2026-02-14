#!/bin/bash
# Deploy a micro-SaaS product to GitHub and Vercel
# Usage: bash deploy.sh <slug> [env_file_path]
# Example: bash deploy.sh markdown-magic /tmp/markdown-magic.env

set -e

SLUG="$1"
ENV_FILE="$2"
PROJECT_DIR="/home/milad/$SLUG"

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

# Copy env file if provided
if [ -n "$ENV_FILE" ] && [ -f "$ENV_FILE" ]; then
    cp "$ENV_FILE" .env.local
    echo "Copied env file from $ENV_FILE"
fi

# Initialize git
echo "Initializing git..."
git init
git add -A
git commit -m "Initial commit: $SLUG micro-SaaS product

Built by MicroSaaS Factory (OpenClaw)
Template: ConvertFlow boilerplate"

echo "Git initialized."

# Deploy to Vercel
echo "Deploying to Vercel..."
DEPLOY_OUTPUT=$(vercel --prod --yes 2>&1)
DEPLOY_EXIT=$?

if [ $DEPLOY_EXIT -ne 0 ]; then
    echo "DEPLOY_FAILED"
    echo "$DEPLOY_OUTPUT"
    exit 1
fi

# Extract the URL from Vercel output
VERCEL_URL=$(echo "$DEPLOY_OUTPUT" | grep -oP 'https://[a-zA-Z0-9-]+\.vercel\.app' | tail -1)

echo "DEPLOY_SUCCESS"
echo "URL: $VERCEL_URL"
echo "Slug: $SLUG"
