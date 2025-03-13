#!/bin/bash

# Default values
ACTION="install"
URL="https://storage.googleapis.com/lum-node-artifacts-f0ad091132a3b660e807c360d7410fca2bfb"
CURRENT_INSTALL_SCRIPT_VERSION="0-1-0"  # Update this in each release
LUMINO_DIR="$HOME/lumino"
VERSION_FILE="$LUMINO_DIR/.lumino_versions"
INSTALL_SCRIPT_PATH="$LUMINO_DIR/$(basename "$0")"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --check) ACTION="check"; shift;;
        --update) ACTION="update"; shift;;
        -h|--help)
            echo "Usage: $0 [--check | --update]"
            echo "  --check: Check if lumino-node is running and restart if needed"
            echo "  --update: Check for and install updates"
            exit 0;;
        *) echo "Unknown option: $1"; exit 1;;
    esac
done

# Ensure lumino directory exists
mkdir -p "$LUMINO_DIR"

# If script is not in lumino directory, copy it there
if [ "$(pwd)" != "$LUMINO_DIR" ]; then
  cp ./node-install.sh "$LUMINO_DIR" || true
fi

# Change to lumino directory
cd "$LUMINO_DIR"

# Function to get versions from remote
get_versions() {
    VERSIONS=$(curl -s "$URL/VERSIONS")
    PIPELINE_ZEN_VERSION=$(echo "$VERSIONS" | grep "pipeline-zen==" | cut -d'=' -f3)
    CONTRACTS_CLIENT_VERSION=$(echo "$VERSIONS" | grep "lumino-contracts-client==" | cut -d'=' -f3)
    CONTRACTS_VERSION=$(echo "$VERSIONS" | grep "contracts==" | cut -d'=' -f3)
    INSTALL_SCRIPT_VERSION=$(echo "$VERSIONS" | grep "install-script==" | cut -d'=' -f3)
}

# Function to load previous versions
load_previous_versions() {
    if [ -f "$VERSION_FILE" ]; then
        LAST_PIPELINE_ZEN=$(sed -n '1p' "$VERSION_FILE")
        LAST_CONTRACTS_CLIENT=$(sed -n '2p' "$VERSION_FILE")
        LAST_CONTRACTS=$(sed -n '3p' "$VERSION_FILE")
        LAST_INSTALL_SCRIPT=$(sed -n '4p' "$VERSION_FILE")
    else
        LAST_PIPELINE_ZEN="0-0-0"
        LAST_CONTRACTS_CLIENT="0-0-0"
        LAST_CONTRACTS="0-0-0"
        LAST_INSTALL_SCRIPT=$CURRENT_INSTALL_SCRIPT_VERSION
    fi
}

# Function to save versions
save_versions() {
    echo "$PIPELINE_ZEN_VERSION" > "$VERSION_FILE"
    echo "$CONTRACTS_CLIENT_VERSION" >> "$VERSION_FILE"
    echo "$CONTRACTS_VERSION" >> "$VERSION_FILE"
    echo "$CURRENT_INSTALL_SCRIPT_VERSION" >> "$VERSION_FILE"
}

# Function to compare versions (returns 1 if v1 < v2)
version_lt() {
    local ver1="$1"  # First version
    local ver2="$2"  # Second version

    # Convert dots to hyphens if needed
    ver1=$(echo "$ver1" | tr '.' '-')
    ver2=$(echo "$ver2" | tr '.' '-')

    # Check if inputs match the expected format
    if ! echo "$ver1" | grep -qE '^[0-9]+-[0-9]+-[0-9]+$' || ! echo "$ver2" | grep -qE '^[0-9]+-[0-9]+-[0-9]+$'; then
        echo "Error: Version numbers must be in format X-Y-Z where X, Y, Z are numbers" >&2
        return 2
    fi

    # Extract parts using cut instead of arrays
    v1_major=$(echo "$ver1" | cut -d'-' -f1)
    v1_minor=$(echo "$ver1" | cut -d'-' -f2)
    v1_patch=$(echo "$ver1" | cut -d'-' -f3)

    v2_major=$(echo "$ver2" | cut -d'-' -f1)
    v2_minor=$(echo "$ver2" | cut -d'-' -f2)
    v2_patch=$(echo "$ver2" | cut -d'-' -f3)

    # Compare major version
    if [ "$v1_major" -lt "$v2_major" ]; then
        return 1
    elif [ "$v1_major" -gt "$v2_major" ]; then
        return 0
    fi

    # If major versions equal, compare minor version
    if [ "$v1_minor" -lt "$v2_minor" ]; then
        return 1
    elif [ "$v1_minor" -gt "$v2_minor" ]; then
        return 0
    fi

    # If minor versions equal, compare patch version
    if [ "$v1_patch" -lt "$v2_patch" ]; then
        return 1
    else
        return 0
    fi
}

# Function to update cron jobs
update_cron() {
    echo "Updating cron jobs..."
    crontab -l 2>/dev/null | grep -v "$INSTALL_SCRIPT_PATH" > "$LUMINO_DIR/crontab.tmp" || true
    echo "* * * * * $INSTALL_SCRIPT_PATH --check" >> "$LUMINO_DIR/crontab.tmp"
    echo "0 * * * * $INSTALL_SCRIPT_PATH --update" >> "$LUMINO_DIR/crontab.tmp"
    crontab "$LUMINO_DIR/crontab.tmp"
    rm "$LUMINO_DIR/crontab.tmp"
}

# Function to update .env with user input for NODE_PRIVATE_KEY and NODE_ADDRESS
update_env_keys() {
    local env_file=".env"

    NODE_PRIVATE_KEY=$1
    NODE_ADDRESS=$2

    # Only prompt if the values are empty
    if [ -z "$NODE_PRIVATE_KEY" ]; then
        read -p "Enter NODE_PRIVATE_KEY: " NODE_PRIVATE_KEY
    fi
    if [ -z "$NODE_ADDRESS" ]; then
        read -p "Enter NODE_ADDRESS: " NODE_ADDRESS
    fi

    # Update the .env file with the values (existing or newly entered)
    if [ -n "$NODE_PRIVATE_KEY" ]; then
        if grep -q "^NODE_PRIVATE_KEY=" "$env_file"; then
            sed -i "s|^NODE_PRIVATE_KEY=.*|NODE_PRIVATE_KEY=$NODE_PRIVATE_KEY|" "$env_file"
        else
            echo "NODE_PRIVATE_KEY=$NODE_PRIVATE_KEY" >> "$env_file"
        fi
    fi
    if [ -n "$NODE_ADDRESS" ]; then
        if grep -q "^NODE_ADDRESS=" "$env_file"; then
            sed -i "s|^NODE_ADDRESS=.*|NODE_ADDRESS=$NODE_ADDRESS|" "$env_file"
        else
            echo "NODE_ADDRESS=$NODE_ADDRESS" >> "$env_file"
        fi
    fi
}

# Installation function
install() {
    get_versions

    # Check Python version
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d'.' -f2)
    if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
        echo "Error: Python 3.10 or higher required. Found: $PYTHON_VERSION"
        exit 1
    fi

    # Check for NVIDIA GPU
    if ! command -v nvidia-smi &> /dev/null || ! nvidia-smi &> /dev/null; then
        echo "Error: NVIDIA GPU and drivers required"
        exit 1
    fi

    # Download and extract pipeline-zen
    curl -L "$URL/$PIPELINE_ZEN_VERSION-pipeline-zen.tar.gz" -o "$PIPELINE_ZEN_VERSION-pipeline-zen.tar.gz"
    # Test tar file integrity
    tar -tzvf "$PIPELINE_ZEN_VERSION-pipeline-zen.tar.gz" > /dev/null
    # Extract tar file and clean up
    rm -rf pipeline-zen || true
    tar -xzvf "$PIPELINE_ZEN_VERSION-pipeline-zen.tar.gz" -C ./
    rm "$PIPELINE_ZEN_VERSION-pipeline-zen.tar.gz"

    # Install lumino-contracts-client
    pip install --upgrade pip
    pip install -U "lumino-contracts-client==$CONTRACTS_CLIENT_VERSION" --target=$(pwd)/pydist
    export PYTHONPATH=$(pwd)/pydist:$PYTHONPATH
    export PATH=$(pwd)/pydist/bin:$PATH
    pip uninstall -y lumino-contracts-client
    pip install "lumino-contracts-client==$CONTRACTS_CLIENT_VERSION" --target=$(pwd)/pydist

    # Preserve existing NODE_PRIVATE_KEY and NODE_ADDRESS if .env exists
    EXISTING_NODE_PRIVATE_KEY=""
    EXISTING_NODE_ADDRESS=""
    if [ -f ".env" ]; then
        EXISTING_NODE_PRIVATE_KEY=$(grep "^NODE_PRIVATE_KEY=" .env | cut -d'=' -f2)
        EXISTING_NODE_ADDRESS=$(grep "^NODE_ADDRESS=" .env | cut -d'=' -f2)
    fi

    # Download and copy new .env file
    curl -L "$URL/$CONTRACTS_VERSION.env" -o ".$CONTRACTS_VERSION.env"
    cp ".$CONTRACTS_VERSION.env" ".env"
    rm ".$CONTRACTS_VERSION.env"

    # Update NODE_PRIVATE_KEY and NODE_ADDRESS in .env if needed
    update_env_keys $EXISTING_NODE_PRIVATE_KEY $EXISTING_NODE_ADDRESS

    # Download and extract contract ABIs
    curl -L "$URL/$CONTRACTS_VERSION-abis.tar.gz" -o "$CONTRACTS_VERSION-abis.tar.gz"
    # Test tar file integrity
    tar -tzvf "$CONTRACTS_VERSION-abis.tar.gz" > /dev/null
    # Extract tar file and clean up
    rm -rf abis || true
    tar -xzvf "$CONTRACTS_VERSION-abis.tar.gz" -C ./
    rm "$CONTRACTS_VERSION-abis.tar.gz"

    # Install pipeline-zen dependencies
    cd ./pipeline-zen
    ./scripts/install-deps.sh
    cd ../

    # Save versions after successful install
    save_versions

    # Run lumino-node in background
    export $(grep -v '^#' .env | xargs)
    killall lumino-node || true
    nohup lumino-node > lumino-node.log 2>&1 &

    # Update cron jobs
    update_cron

    echo "Installation complete. lumino-node is running."
}

# Node install script self-update function
self_update() {
    get_versions
    load_previous_versions

    version_lt "$LAST_INSTALL_SCRIPT" "$INSTALL_SCRIPT_VERSION"
    v=$?
    echo "su: version_lt: $v"
    if [ $v -eq "1" ]; then
        echo "Updating install script from $LAST_INSTALL_SCRIPT to $INSTALL_SCRIPT_VERSION..."
        curl -L "$URL/node-install.sh" -o "$INSTALL_SCRIPT_PATH.new"
        chmod +x "$INSTALL_SCRIPT_PATH.new"
        mv "$INSTALL_SCRIPT_PATH.new" "$INSTALL_SCRIPT_PATH"
        echo "Install script updated. Please rerun the script."
        # Save versions after successful install
        save_versions
        exit 0
    fi
}

# Check if lumino-node is running and restart if needed
check() {
    if ! pgrep -f "lumino-node" > /dev/null; then
        echo "lumino-node not running, restarting..."
        export $(grep -v '^#' .env | xargs)
        nohup lumino-node > lumino-node.log 2>&1 &
        echo "lumino-node restarted."
    else
        echo "lumino-node is running."
    fi
}

# Update components
update() {
    get_versions
    load_previous_versions

    UPDATE_REQUIRED=0
    # Check and update pipeline-zen
    version_lt "$LAST_PIPELINE_ZEN" "$PIPELINE_ZEN_VERSION"
    v=$?
    echo "pz: version_lt: $v"
    if [ $v -eq "1" ]; then
        UPDATE_REQUIRED=1
    fi
    # Check and update contracts client
    version_lt "$LAST_CONTRACTS_CLIENT" "$CONTRACTS_CLIENT_VERSION"
    v=$?
    echo "cc: version_lt: $v"
    if [ $v -eq "1" ]; then
        UPDATE_REQUIRED=1
    fi
    # Check and update env/abis
    version_lt "$LAST_CONTRACTS" "$CONTRACTS_VERSION"
    v=$?
    echo "co: version_lt: $v"
    if [ $v -eq "1" ]; then
        UPDATE_REQUIRED=1
    fi

    if [ $UPDATE_REQUIRED -eq 0 ]; then
        echo "No updates available."
        exit 0
    fi

    echo "Updating lumino-node..."
    install  # Reuse the install function to reinstall everything
}

# Main execution
self_update "$@"

case $ACTION in
    "install") install;;
    "check") check;;
    "update") update;;
    *) echo "Invalid action"; exit 1;;
esac