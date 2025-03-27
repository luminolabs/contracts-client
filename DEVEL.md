# Development Guide

This document provides instructions for setting up a local development environment for the Lumino Contracts Client.

## Prerequisites

Before you begin, ensure you have the following:

- Python 3.11
- pip
- Git
- [Foundry](https://book.getfoundry.sh/getting-started/installation) (for smart contract interactions)
- Access to the required repositories:
    - contracts repository
    - pipeline-zen repository
    - this contracts-client repository

## Repository Setup

Clone the required repositories in the same parent directory:

```bash
mkdir lumino-dev
cd lumino-dev
git clone <contracts-repo-url> contracts
git clone <pipeline-zen-repo-url> pipeline-zen
git clone <contracts-client-repo-url> contracts-client
```

## Local Development Environment

### Step 1: Backup Existing Configuration

If you have previously used the Lumino client, backup your existing configuration:

```bash
mv ~/.lumino ~/.lumino.bak
```

### Step 2: Set Up the Smart Contracts

1. Start a local Ethereum node with Anvil:

```bash
anvil
```

2. Configure the contracts environment:

Create and populate `../contracts/.env` from `../contracts/example.env`

3. Export the environment variables:

```bash
cd ../contracts
export $(grep -v '^#' .env | xargs)
```

4. Deploy the contracts:

```bash
./deploy.sh
```

This creates a `../contracts/addresses.json` file with the contract addresses.

### Step 3: Configure Pipeline-Zen

Ensure the pipeline-zen repository has the correct configuration:

1. Create and populate `../pipeline-zen/.env`:

```
PZ_ENV=local
PZ_DEVICE=cpu
PZ_HUGGINGFACE_TOKEN=check 1password
```

### Step 4: Set Up the Contracts Client

1. Create your local environment file:

```bash
cd ../contracts-client
cp example.env .env
```

2. Edit `.env` with your specific configuration values.

3. Install the client in editable mode:

```bash
pip install -Ue .
```

### Step 5: Configure Test Accounts

Whitelist your test node address and transfer tokens to the node and client addresses:

```bash
export NODE_ADDRESS=...
export CLIENT_ADDRESS=...
export LUMINO_TOKEN_ADDRESS=get this from ../contracts/addresses.json
export WHITELIST_MANAGER_ADDRESS=get this from ../contracts/addresses.json
export RPC_URL=http://localhost:8545
export DEPLOYER_PRIVATE_KEY=...

cast send $LUMINO_TOKEN_ADDRESS "transfer(address,uint256)" $NODE_ADDRESS $TOKENS_50000 --private-key $DEPLOYER_PRIVATE_KEY --rpc-url $RPC_URL
cast send $LUMINO_TOKEN_ADDRESS "transfer(address,uint256)" $CLIENT_ADDRESS $TOKENS_50000 --private-key $DEPLOYER_PRIVATE_KEY --rpc-url $RPC_URL
cast send $WHITELIST_MANAGER_ADDRESS "addCP(address)" $NODE_ADDRESS --private-key $DEPLOYER_PRIVATE_KEY --rpc-url $RPC_URL
```

## Running the Development Environment

### Start the Node

```bash
lumino-node
```

This will start the node client, which will:

- Register with the network
- Participate in leader election
- Accept and execute jobs when assigned

### Submit a Test Job

Test the entire pipeline with a dummy job:

```bash
lumino-client create-job --args '{"shuffle": true, "use_lora": true, "use_qlora": false, "batch_size": 4, "dataset_id": "gs://lum-dev-pipeline-zen-datasets/0ca98b07-9366-4a31-8c83-569961c90294/2024-12-17_21-57-21_text2sql.jsonl", "num_epochs": 1, "job_config_name": "llm_dummy"}' --model llm_dummy --ft_type "LORA" --monitor
```

## Running Tests

### Unit Tests

Run the unit test suite:

```bash
pip install -r requirements-test.txt
pytest
```

### End-to-End Tests

Run the end-to-end integration tests:

```bash
pytest tests_e2e
```

## Development Guidelines

### Code Structure

The client is organized into the following main components:

- `src/lumino/contracts_client/client.py` - Base client functionality
- `src/lumino/contracts_client/node_client.py` - Node-specific client logic
- `src/lumino/contracts_client/user_client.py` - User-specific client logic
- `src/lumino/contracts_client/config.py` - Configuration handling
- `src/lumino/contracts_client/utils.py` - Utility functions
- `src/lumino/contracts_client/compute_power.py` - Compute resource pool detection

### Adding New Features

1. Implement your changes in the appropriate module
2. Add tests for your changes
3. Verify that all tests pass
4. Update documentation if necessary
5. Submit a pull request