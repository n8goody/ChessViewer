#!/bin/bash

# Grab the first word you type after the script name
VERSION=$1

# Stop the script if you forgot to type a version
if [ -z "$VERSION" ]; then
  echo "Error: Please provide a version tag."
  echo "Usage: ./deploy.sh v2.0.0"
  exit 1
fi

echo "Building and pushing version: $VERSION..."

# Build with both tags
docker build -t your-username/chess-renderer:$VERSION -t your-username/chess-renderer:latest .

# Push both tags
docker push your-username/chess-renderer:$VERSION
docker push your-username/chess-renderer:latest

echo "Deployment Complete for $VERSION!"