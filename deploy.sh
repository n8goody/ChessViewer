#!/bin/bash

# Grab the first word you type after the script name
#VERSION=$1

# Stop the script if you forgot to type a version
# if [ -z "$VERSION" ]; then
#   echo "Error: Please provide a version tag."
#   echo "Usage: ./deploy.sh v2.0.0"
#   exit 1
# fi

#echo "Building and pushing version: $VERSION..."

# Build with both tags
docker build  -t n8goody/chessviewer:dev-nate . #-t n8goody/chessviewer:$VERSION

# Push both tags
#docker push n8goody/chessviewer:$VERSION
docker push n8goody/chessviewer:dev-nate

#echo "Deployment Complete for $VERSION!"