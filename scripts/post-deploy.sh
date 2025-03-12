#!/bin/bash

set -e  # Exit immediately if a command exits with non-zero status

# Define paths
LUMINO_ROOT="$HOME/lumino"
ROOT_VERSIONS_FILE="$LUMINO_ROOT/VERSIONS"
CONTRACTS_DIR="$LUMINO_ROOT/contracts"
CONTRACTS_VERSION_FILE="$CONTRACTS_DIR/VERSION"
CONTRACTS_CLIENT_DIR="$LUMINO_ROOT/contracts-client"
ARTIFACTS_DIR="$CONTRACTS_CLIENT_DIR/node_artifacts"
ADDRESSES_JSON="$CONTRACTS_DIR/addresses.json"
GCS_BUCKET="gs://lum-node-artifacts-f0ad091132a3b660e807c360d7410fca2bfb"
TEST_GCS_BUCKET="gs://lum-node-artifacts-f0ad091132a3b660e807c360d7410fca2bfb/test"  # For testing

# Create the artifacts directory if it doesn't exist
mkdir -p "$ARTIFACTS_DIR"

# Check if addresses.json exists
if [ ! -f "$ADDRESSES_JSON" ]; then
    echo "Error: $ADDRESSES_JSON does not exist. Run the deployment script first."
    exit 1
fi

# Read existing VERSIONS file content
if [ -f "$ROOT_VERSIONS_FILE" ]; then
    # Extract versions
    PIPELINE_ZEN_VERSION=$(grep "pipeline-zen==" "$ROOT_VERSIONS_FILE" | cut -d'=' -f3)
    CONTRACTS_CLIENT_VERSION=$(grep "lumino-contracts-client==" "$ROOT_VERSIONS_FILE" | cut -d'=' -f3)
    ROOT_CONTRACTS_VERSION=$(grep "contracts==" "$ROOT_VERSIONS_FILE" | cut -d'=' -f3)
    INSTALL_SCRIPT_VERSION=$(grep "install-script==" "$ROOT_VERSIONS_FILE" | cut -d'=' -f3)
    CONTRACTS_ADDRESSES_VERSION=$(grep "contracts-addresses==" "$ROOT_VERSIONS_FILE" | cut -d'=' -f3)
else
    echo "Warning: VERSIONS file not found. Creating default versions."
    PIPELINE_ZEN_VERSION="0-0-0"
    CONTRACTS_CLIENT_VERSION="0.0.0"
    ROOT_CONTRACTS_VERSION="0-0-0"
    INSTALL_SCRIPT_VERSION="0-0-0"
    CONTRACTS_ADDRESSES_VERSION="0-0-0"
fi

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
ADDR_MAJOR=${addresses_ver_parts[0]:-0}
ADDR_MINOR=${addresses_ver_parts[1]:-0}
ADDR_PATCH=${addresses_ver_parts[2]:-0}

# Increment contracts-addresses version
NEW_ADDR_PATCH=$((ADDR_PATCH + 1))
NEW_ADDR_VERSION="$ADDR_MAJOR-$ADDR_MINOR-$NEW_ADDR_PATCH"

# Use the contracts version from the contracts folder
CONTRACTS_VERSION="$CONTRACTS_FOLDER_VERSION"

# Find the latest existing env file to use as a template
EXISTING_ENV_FILES=("$CONTRACTS_CLIENT_DIR"/*.env)
if [ ${#EXISTING_ENV_FILES[@]} -gt 0 ]; then
    TEMPLATE_ENV_FILE="${EXISTING_ENV_FILES[0]}"
    echo "Using template env file: $TEMPLATE_ENV_FILE"
else
    echo "Error: No template env file found. Exiting."
    exit 1
fi

# Determine the output env file
ENV_FILE="$ARTIFACTS_DIR/$CONTRACTS_VERSION.env"

# Get contract addresses from JSON
LUMINO_TOKEN=$(jq -r '.LuminoToken' "$ADDRESSES_JSON")
ACCESS_MANAGER=$(jq -r '.AccessManager' "$ADDRESSES_JSON")
WHITELIST_MANAGER=$(jq -r '.WhitelistManager' "$ADDRESSES_JSON")
NODE_ESCROW=$(jq -r '.NodeEscrow' "$ADDRESSES_JSON")
JOB_ESCROW=$(jq -r '.JobEscrow' "$ADDRESSES_JSON")
NODE_MANAGER=$(jq -r '.NodeManager' "$ADDRESSES_JSON")
JOB_MANAGER=$(jq -r '.JobManager' "$ADDRESSES_JSON")
LEADER_MANAGER=$(jq -r '.LeaderManager' "$ADDRESSES_JSON")
INCENTIVE_MANAGER=$(jq -r '.IncentiveManager' "$ADDRESSES_JSON")
EPOCH_MANAGER=$(jq -r '.EpochManager' "$ADDRESSES_JSON")

# Create new env file with updated addresses
echo "Creating new env file with updated addresses..."

# Process the template file line by line
while IFS= read -r line; do
    VAR_NAME=$(echo "$line" | cut -d'=' -f1)
    
    case "$VAR_NAME" in
        "LUMINO_TOKEN_ADDRESS")
            echo "LUMINO_TOKEN_ADDRESS=$LUMINO_TOKEN" >> "$ENV_FILE"
            ;;
        "ACCESS_MANAGER_ADDRESS")
            echo "ACCESS_MANAGER_ADDRESS=$ACCESS_MANAGER" >> "$ENV_FILE"
            ;;
        "WHITELIST_MANAGER_ADDRESS")
            echo "WHITELIST_MANAGER_ADDRESS=$WHITELIST_MANAGER" >> "$ENV_FILE"
            ;;
        "NODE_ESCROW_ADDRESS")
            echo "NODE_ESCROW_ADDRESS=$NODE_ESCROW" >> "$ENV_FILE"
            ;;
        "JOB_ESCROW_ADDRESS")
            echo "JOB_ESCROW_ADDRESS=$JOB_ESCROW" >> "$ENV_FILE"
            ;;
        "NODE_MANAGER_ADDRESS")
            echo "NODE_MANAGER_ADDRESS=$NODE_MANAGER" >> "$ENV_FILE"
            ;;
        "JOB_MANAGER_ADDRESS")
            echo "JOB_MANAGER_ADDRESS=$JOB_MANAGER" >> "$ENV_FILE"
            ;;
        "LEADER_MANAGER_ADDRESS")
            echo "LEADER_MANAGER_ADDRESS=$LEADER_MANAGER" >> "$ENV_FILE"
            ;;
        "INCENTIVE_MANAGER_ADDRESS")
            echo "INCENTIVE_MANAGER_ADDRESS=$INCENTIVE_MANAGER" >> "$ENV_FILE"
            ;;
        "EPOCH_MANAGER_ADDRESS")
            echo "EPOCH_MANAGER_ADDRESS=$EPOCH_MANAGER" >> "$ENV_FILE"
            ;;
        *)
            echo "$line" >> "$ENV_FILE"
            ;;
    esac
done < "$TEMPLATE_ENV_FILE"

# Create VERSIONS file in artifacts directory
VERSIONS_ARTIFACT="$ARTIFACTS_DIR/VERSIONS"
echo "pipeline-zen==$PIPELINE_ZEN_VERSION" > "$VERSIONS_ARTIFACT"
echo "lumino-contracts-client==$CONTRACTS_CLIENT_VERSION" >> "$VERSIONS_ARTIFACT"
echo "contracts==$CONTRACTS_VERSION" >> "$VERSIONS_ARTIFACT"
echo "install-script==$INSTALL_SCRIPT_VERSION" >> "$VERSIONS_ARTIFACT"
echo "contracts-addresses==$NEW_ADDR_VERSION" >> "$VERSIONS_ARTIFACT"

# Also update the root VERSIONS file
cp "$VERSIONS_ARTIFACT" "$ROOT_VERSIONS_FILE"

# Create ABIs archive - properly organized in 'abis' folder
echo "Creating ABIs archive..."
mkdir -p "$ARTIFACTS_DIR/abis"
cp -r "$CONTRACTS_DIR/out"/* "$ARTIFACTS_DIR/abis/"
ABIS_ARCHIVE="$ARTIFACTS_DIR/$CONTRACTS_VERSION-abis.tar.gz"
(cd "$ARTIFACTS_DIR" && tar -czvf "$CONTRACTS_VERSION-abis.tar.gz" abis)
rm -rf "$ARTIFACTS_DIR/abis"  # Clean up

# Copy node-install.sh script for completeness
if [ -f "$CONTRACTS_CLIENT_DIR/node-install.sh" ]; then
    cp "$CONTRACTS_CLIENT_DIR/node-install.sh" "$ARTIFACTS_DIR/node-install.sh"
else
    echo "Warning: node-install.sh not found in contracts-client directory."
fi

# Show what's being uploaded
echo "Files staged for upload:"
ls -la "$ARTIFACTS_DIR"

# Ask for confirmation before uploading
read -p "Upload these files to GCS bucket? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Upload to GCS
    echo "Uploading files to GCS bucket..."
    gsutil cp "$VERSIONS_ARTIFACT" "$GCS_BUCKET/VERSIONS"
    gsutil cp "$ENV_FILE" "$GCS_BUCKET/$CONTRACTS_VERSION.env"
    gsutil cp "$ABIS_ARCHIVE" "$GCS_BUCKET/$CONTRACTS_VERSION-abis.tar.gz"
    
    # Optional: Upload to test bucket as well
    read -p "Upload to test bucket as well? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        gsutil cp "$VERSIONS_ARTIFACT" "$TEST_GCS_BUCKET/VERSIONS"
        cat $ENV_FILE
        gsutil cp "$ENV_FILE" "$TEST_GCS_BUCKET/$CONTRACTS_VERSION.env"
        gsutil cp "$ABIS_ARCHIVE" "$TEST_GCS_BUCKET/$CONTRACTS_VERSION-abis.tar.gz"
        echo "Files uploaded to test bucket."
    fi
    
    echo "Files uploaded to GCS bucket."
else
    echo "Upload cancelled. Files are staged in $ARTIFACTS_DIR"
fi

echo "Updates complete!"
echo "Using contracts version: $CONTRACTS_VERSION"
echo "New contracts-addresses version: $NEW_ADDR_VERSION"