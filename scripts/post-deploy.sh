#!/bin/bash

set -e  # Exit immediately if a command exits with non-zero status

# Define paths
LUMINO_ROOT="$HOME/lumino"
ROOT_VERSIONS_FILE="$LUMINO_ROOT/VERSIONS"
CONTRACTS_DIR="$LUMINO_ROOT/contracts"
CONTRACTS_VERSION_FILE="$CONTRACTS_DIR/VERSION"
CONTRACTS_CLIENT_DIR="$LUMINO_ROOT/contracts-client"
ADDRESSES_JSON="$CONTRACTS_DIR/addresses.json"
GCS_BUCKET="gs://lum-node-artifacts-f0ad091132a3b660e807c360d7410fca2bfb"

# Check if addresses.json exists
if [ ! -f "$ADDRESSES_JSON" ]; then
    echo "Error: $ADDRESSES_JSON does not exist. Run the deployment script first."
    exit 1
fi

# Parse current versions from root VERSIONS file
PIPELINE_ZEN_VERSION=$(grep "pipeline-zen==" "$ROOT_VERSIONS_FILE" | cut -d'=' -f3)
CONTRACTS_CLIENT_VERSION=$(grep "lumino-contracts-client==" "$ROOT_VERSIONS_FILE" | cut -d'=' -f3)
ROOT_CONTRACTS_VERSION=$(grep "contracts==" "$ROOT_VERSIONS_FILE" | cut -d'=' -f3)
INSTALL_SCRIPT_VERSION=$(grep "install-script==" "$ROOT_VERSIONS_FILE" | cut -d'=' -f3)
CONTRACTS_ADDRESSES_VERSION=$(grep "contracts-addresses==" "$ROOT_VERSIONS_FILE" | cut -d'=' -f3)

# Get contracts version from contracts folder
if [ -f "$CONTRACTS_VERSION_FILE" ]; then
    CONTRACTS_FOLDER_VERSION=$(cat "$CONTRACTS_VERSION_FILE")
    # Replace dots with hyphens if needed
    CONTRACTS_FOLDER_VERSION=$(echo "$CONTRACTS_FOLDER_VERSION" | tr '.' '-')
else
    echo "Warning: Contracts VERSION file not found. Using version from root VERSIONS file."
    CONTRACTS_FOLDER_VERSION="$ROOT_CONTRACTS_VERSION"
fi

echo "Current versions:"
echo "  Pipeline-zen: $PIPELINE_ZEN_VERSION"
echo "  Contracts-client: $CONTRACTS_CLIENT_VERSION"
echo "  Contracts (root): $ROOT_CONTRACTS_VERSION"
echo "  Contracts (folder): $CONTRACTS_FOLDER_VERSION"
echo "  Install-script: $INSTALL_SCRIPT_VERSION"
echo "  Contracts-addresses: $CONTRACTS_ADDRESSES_VERSION"

# Get contracts addresses version components
IFS='-' read -r -a addresses_ver_parts <<< "$CONTRACTS_ADDRESSES_VERSION"
ADDR_MAJOR=${addresses_ver_parts[0]}
ADDR_MINOR=${addresses_ver_parts[1]}
ADDR_PATCH=${addresses_ver_parts[2]}

# Increment contracts-addresses version
NEW_ADDR_PATCH=$((ADDR_PATCH + 1))
NEW_ADDR_VERSION="$ADDR_MAJOR-$ADDR_MINOR-$NEW_ADDR_PATCH"

# Use the contracts version from the contracts folder
CONTRACTS_VERSION="$CONTRACTS_FOLDER_VERSION"

# Determine if we need to update the .env file
ENV_FILE="$CONTRACTS_CLIENT_DIR/$CONTRACTS_VERSION.env"

# Check if the env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo "Creating new env file: $ENV_FILE"
    touch "$ENV_FILE"
fi

# Update env file with new addresses
cat "$ADDRESSES_JSON" | jq -r 'to_entries[] | "\(.key)=\(.value)"' | while read -r line; do
    KEY=$(echo "$line" | cut -d'=' -f1)
    VALUE=$(echo "$line" | cut -d'=' -f2)
    
    # Convert contract name to env var format
    if [ "$KEY" = "LuminoToken" ]; then
        ENV_KEY="LUMINO_TOKEN_ADDRESS"
    elif [ "$KEY" = "AccessManager" ]; then
        ENV_KEY="ACCESS_MANAGER_ADDRESS"
    elif [ "$KEY" = "WhitelistManager" ]; then
        ENV_KEY="WHITELIST_MANAGER_ADDRESS"
    elif [ "$KEY" = "NodeEscrow" ]; then
        ENV_KEY="NODE_ESCROW_ADDRESS"
    elif [ "$KEY" = "JobEscrow" ]; then
        ENV_KEY="JOB_ESCROW_ADDRESS"
    elif [ "$KEY" = "NodeManager" ]; then
        ENV_KEY="NODE_MANAGER_ADDRESS"
    elif [ "$KEY" = "JobManager" ]; then
        ENV_KEY="JOB_MANAGER_ADDRESS"
    elif [ "$KEY" = "LeaderManager" ]; then
        ENV_KEY="LEADER_MANAGER_ADDRESS"
    elif [ "$KEY" = "IncentiveManager" ]; then
        ENV_KEY="INCENTIVE_MANAGER_ADDRESS"
    elif [ "$KEY" = "EpochManager" ]; then
        ENV_KEY="EPOCH_MANAGER_ADDRESS"
    else
        continue
    fi
    
    # Update env file with new address
    if grep -q "^$ENV_KEY=" "$ENV_FILE"; then
        sed -i "s|^$ENV_KEY=.*|$ENV_KEY=$VALUE|" "$ENV_FILE"
    else
        echo "$ENV_KEY=$VALUE" >> "$ENV_FILE"
    fi
done

# Update VERSIONS file with new contracts-addresses version and contracts version (if changed)
echo "pipeline-zen==$PIPELINE_ZEN_VERSION" > "$ROOT_VERSIONS_FILE"
echo "lumino-contracts-client==$CONTRACTS_CLIENT_VERSION" >> "$ROOT_VERSIONS_FILE"
echo "contracts==$CONTRACTS_VERSION" >> "$ROOT_VERSIONS_FILE"
echo "install-script==$INSTALL_SCRIPT_VERSION" >> "$ROOT_VERSIONS_FILE"
echo "contracts-addresses==$NEW_ADDR_VERSION" >> "$ROOT_VERSIONS_FILE"

# Upload VERSIONS file to GCS bucket
echo "Uploading VERSIONS file to GCS bucket..."
gsutil cp "$ROOT_VERSIONS_FILE" "$GCS_BUCKET/test/VERSIONS"

# Upload env file to GCS bucket
echo "Uploading .env file to GCS bucket..."
gsutil cp "$ENV_FILE" "$GCS_BUCKET/test/$CONTRACTS_VERSION.env"

# Upload contract ABIs
echo "Creating and uploading ABIs archive..."
ABIS_ARCHIVE="$CONTRACTS_VERSION-abis.tar.gz"
tar -czvf "$ABIS_ARCHIVE" -C "$CONTRACTS_DIR" out

# Upload ABIs
gsutil cp "$ABIS_ARCHIVE" "$GCS_BUCKET/test/$ABIS_ARCHIVE"
rm -f "$ABIS_ARCHIVE"

echo "Updates complete!"
echo "Using contracts version: $CONTRACTS_VERSION"
echo "New contracts-addresses version: $NEW_ADDR_VERSION"