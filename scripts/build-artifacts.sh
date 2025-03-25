#!/bin/bash

# Exit on any error
set -e

# Define directories and paths
ARTIFACTS_DIR="artifacts"
TEMP_DIR=$(mktemp -d)
CONTRACTS_DIR="../contracts"
OPEN_BUCKET_URL="gs://lum-artifacts"

# Read artifacts password from environment or prompt for it
ARTIFACTS_PASSWORD="${CC_ARTIFACTS_PASSWORD:-}"
if [ -z "$ARTIFACTS_PASSWORD" ]; then
    # Try to read from ~/.lumino/.env file
    if [ -f ~/.lumino/.env ]; then
        source ~/.lumino/.env
        ARTIFACTS_PASSWORD="${CC_ARTIFACTS_PASSWORD:-}"
    fi
    
    # If still empty, prompt user
    if [ -z "$ARTIFACTS_PASSWORD" ]; then
        echo -n "Enter artifacts password: "
        read -s ARTIFACTS_PASSWORD
        echo
        
        # Save to ~/.lumino/.env
        mkdir -p ~/.lumino
        echo "CC_ARTIFACTS_PASSWORD=$ARTIFACTS_PASSWORD" >> ~/.lumino/.env
    fi
fi

NODE_BUCKET_URL="gs://lum-node-artifacts-$ARTIFACTS_PASSWORD"

# Create artifacts directory if it doesn't exist
mkdir -p "$ARTIFACTS_DIR"

# 1. Copy addresses.json
echo "Copying addresses.json..."
cp "$CONTRACTS_DIR/addresses.json" "$ARTIFACTS_DIR/addresses.json"

# 2. Create abis.tar.gz
echo "Creating abis.tar.gz..."
# Copy out folder to temp location and rename to abis
cp -R "$CONTRACTS_DIR/out" "$TEMP_DIR/abis"
# Create tar.gz
tar -czvf "$ARTIFACTS_DIR/abis.tar.gz" -C "$TEMP_DIR" abis
# Clean up temp abis folder
rm -rf "$TEMP_DIR/abis"

# 3. Create pipeline-zen.tar.gz
echo "Creating pipeline-zen.tar.gz..."
# Clone pipeline-zen to temp location
git clone git@github.com:luminolabs/pipeline-zen.git "$TEMP_DIR/pipeline-zen"
# Remove .git directory
rm -rf "$TEMP_DIR/pipeline-zen/.git"
# Create tar.gz
tar -czvf "$ARTIFACTS_DIR/pipeline-zen.tar.gz" -C "$TEMP_DIR" pipeline-zen
# Clean up temp pipeline-zen folder
rm -rf "$TEMP_DIR/pipeline-zen"

# 4. Upload artifacts to GCS
echo "Do you want to upload artifacts to Google Cloud Storage? (y/n)"
read -r response
if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
    echo "Uploading abis.tar.gz and addresses.json to $OPEN_BUCKET_URL..."
    gsutil -m cp "$ARTIFACTS_DIR/abis.tar.gz" "$ARTIFACTS_DIR/addresses.json" "$OPEN_BUCKET_URL/"
    
    echo "Uploading pipeline-zen artifacts to $NODE_BUCKET_URL..."
    gsutil -m cp "$ARTIFACTS_DIR/pipeline-zen.env" "$ARTIFACTS_DIR/pipeline-zen.tar.gz" \
      "$ARTIFACTS_DIR/pipeline-zen-gcp-key.json" "$NODE_BUCKET_URL/"
    
    echo "Upload completed successfully!"
else
    echo "Upload skipped."
fi


# Clean up temp directory
rmdir "$TEMP_DIR"

echo "Script completed successfully!"