#!/bin/bash

# Exit on any error
set -e

# Default values
ACTION="install"
URL=${URL:-""}
CURRENT_INSTALL_VERSION="0-1-0"  # Update this in each release
LUMINO_DIR="$HOME/lumino"
VERSION_FILE="$LUMINO_DIR/.lumino_versions"
SCRIPT_PATH="$LUMINO_DIR/$(basename "$0")"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --check)
            ACTION="check"
            shift
            ;;
        --update)
            ACTION="update"
            shift
            ;;
        --url)
            URL="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [--check | --update | --url URL]"
            echo "  --check: Check if lumino-node is running and restart if needed"
            echo "  --update: Check for and install updates"
            echo "  --url: Specify URL for downloads (or set URL env var)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check if URL is set
if [ -z "$URL" ]; then
    echo "Error: URL must be set via --url or URL environment variable"
    exit 1
fi

# Ensure lumino directory exists
mkdir -p "$LUMINO_DIR"
cd "$LUMINO_DIR"

# Function to get versions from remote
get_versions() {
    VERSIONS=$(curl -s "$URL/VERSIONS")
    PIPELINE_VERSION=$(echo "$VERSIONS" | sed -n '1p')
    CONTRACTS_VERSION=$(echo "$VERSIONS" | sed -n '2p')
    ENV_VERSION=$(echo "$VERSIONS" | sed -n '3p')
    INSTALL_VERSION=$(echo "$VERSIONS" | sed -n '4p')
}

# Function to load previous versions
load_previous_versions() {
    if [ -f "$VERSION_FILE" ]; then
        LAST_PIPELINE=$(sed -n '1p' "$VERSION_FILE")
        LAST_CONTRACTS=$(sed -n '2p' "$VERSION_FILE")
        LAST_ENV=$(sed -n '3p' "$VERSION_FILE")
        LAST_INSTALL=$(sed -n '4p' "$VERSION_FILE")
    else
        LAST_PIPELINE="0-0-0"
        LAST_CONTRACTS="0-0-0"
        LAST_ENV="0-0-0"
        LAST_INSTALL="0-0-0"
    fi
}

# Function to save versions
save_versions() {
    echo "$PIPELINE_VERSION" > "$VERSION_FILE"
    echo "$CONTRACTS_VERSION" >> "$VERSION_FILE"
    echo "$ENV_VERSION" >> "$VERSION_FILE"
    echo "$CURRENT_INSTALL_VERSION" >> "$VERSION_FILE"
}

# Function to compare versions (returns 1 if v1 < v2)
version_lt() {
    [ "$1" = "$2" ] && return 0
    IFS='-' read -r -a v1 <<< "$1"
    IFS='-' read -r -a v2 <<< "$2"
    for i in {0..2}; do
        if [ "${v1[$i]}" -lt "${v2[$i]}" ]; then
            return 1
        elif [ "${v1[$i]}" -gt "${v2[$i]}" ]; then
            return 0
        fi
    done
    return 0
}

# Self-update function
self_update() {
    get_versions
    if version_lt "$CURRENT_INSTALL_VERSION" "$INSTALL_VERSION"; then
        echo "Updating install script from $CURRENT_INSTALL_VERSION to $INSTALL_VERSION..."
        curl -fsSL "$URL/install.sh" -o "$LUMINO_DIR/install.sh.new"
        chmod +x "$LUMINO_DIR/install.sh.new"
        mv "$LUMINO_DIR/install.sh.new" "$LUMINO_DIR/install.sh"
        echo "Install script updated. Re-running with original arguments..."
        exec "$LUMINO_DIR/install.sh" "$@"
    fi
}

# Function to update cron jobs
update_cron() {
    # Get current crontab, remove any lines containing SCRIPT_PATH, and store in temp file
    crontab -l 2>/dev/null | grep -v "$SCRIPT_PATH" > "$LUMINO_DIR/crontab.tmp" || true

    # Add new cron jobs to temp file
    echo "* * * * * $SCRIPT_PATH --check --url $URL" >> "$LUMINO_DIR/crontab.tmp"
    echo "0 * * * * $SCRIPT_PATH --update --url $URL" >> "$LUMINO_DIR/crontab.tmp"

    # Install updated crontab and clean up
    crontab "$LUMINO_DIR/crontab.tmp"
    rm "$LUMINO_DIR/crontab.tmp"
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
    }

    # Check for NVIDIA GPU
    if ! command -v nvidia-smi &> /dev/null || ! nvidia-smi &> /dev/null; then
        echo "Error: NVIDIA GPU and drivers required"
        exit 1
    }

    # Download and unzip pipeline-zen
    curl -L "$URL/pipeline-zen-$PIPELINE_VERSION.zip" -o "pipeline-zen-$PIPELINE_VERSION.zip"
    unzip -o "pipeline-zen-$PIPELINE_VERSION.zip" -d pipeline-zen
    rm "pipeline-zen-$PIPELINE_VERSION.zip"

    # Install lumino-contracts-client
    pip3 install "lumino-contracts-client==$CONTRACTS_VERSION"

    # Download and copy .env file
    curl -L "$URL/.env-$ENV_VERSION" -o ".env-$ENV_VERSION"
    cp ".env-$ENV_VERSION" ".env"

    # Save versions after successful install
    save_versions

    # Run lumino-node in background
    nohup lumino-node > lumino-node.log 2>&1 &

    # Update cron jobs (removing old ones first)
    update_cron

    echo "Installation complete. lumino-node is running."
}

# Check function
check() {
    if ! pgrep -f lumino-node > /dev/null; then
        echo "lumino-node not running, restarting..."
        pkill -f lumino-node 2>/dev/null || true
        nohup lumino-node > lumino-node.log 2>&1 &
        echo "lumino-node restarted"
    fi
}

# Update function
update() {
    get_versions
    load_previous_versions

    if [ "$PIPELINE_VERSION" != "$LAST_PIPELINE" ] || [ "$CONTRACTS_VERSION" != "$LAST_CONTRACTS" ] || [ "$ENV_VERSION" != "$LAST_ENV" ]; then
        echo "Updating versions: pipeline-zen $LAST_PIPELINE -> $PIPELINE_VERSION, contracts $LAST_CONTRACTS -> $CONTRACTS_VERSION, env $LAST_ENV -> $ENV_VERSION"
        pkill -f lumino-node 2>/dev/null || true
        install
    else
        echo "No updates available"
    fi
}

# Main execution
self_update "$@"

case $ACTION in
    "install")
        install
        ;;
    "check")
        check
        ;;
    "update")
        update
        ;;
    *)
        echo "Invalid action"
        exit 1
        ;;
esac