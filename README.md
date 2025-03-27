# Lumino Contracts Client

A Python client for interacting with the Lumino protocol, a decentralized computing platform for machine learning jobs.

## Overview

The Lumino Contracts Client provides two main executables:

- `lumino-node`: For node operators to participate in the Lumino network
- `lumino-client`: For users to submit and monitor jobs on the network

## Installation

### Requirements

- Python 3.11
- An Ethereum wallet address
- Lumino tokens
- ETH for gas fees
- RPC endpoint for the blockchain

### Installing via pip

```bash
pip install lumino-contracts-client
export PATH=$HOME/.local/bin:$PATH  # Add Python bin to PATH
```

### Ubuntu-specific setup

If Python 3.11 is not already installed:

```bash
sudo apt upgrade -y python3
sudo update-alternatives --config python  # (select version 3.11)
python --version  # (confirm version == 3.11)
python -m pip install lumino-contracts-client && export PATH=/home/$USER/.local/bin:$PATH
```

## Configuration

Both clients create a `$HOME/.lumino` directory for storing state:

- Node artifacts and configuration
- Client state and job information
- Logs and temporary files

## Node Client (`lumino-node`)

### Features

- Interacts with smart contracts for leader election, job assignment, and incentives
- Executes machine learning jobs upon assignment
- Automatically manages node's stake on the node escrow (i.e. top-up)
- Registers node to the Lumino network

### Requirements

- A whitelisted Ethereum address
- Lumino tokens transferred to the address
- The lumino artifacts password
- Some ETH for gas costs
- Compatible GPU hardware

### Supported GPU Hardware

- 1, 2, 4, or 8x NVIDIA A100 (40GB or 80GB)
- 8x NVIDIA H100 (80GB)

### Running the Node

```bash
lumino-node
```

## User Client (`lumino-client`)

### Features

- Submits machine learning jobs to the Lumino network
- Monitors job execution and retrieves results
- Manages user's balance on the job escrow contract

### Basic Usage

Top up your balance for paying for jobs:

```bash
lumino-client topup
```

### Submitting Jobs

Example dummy job:

```bash
lumino-client create-job --args '{"shuffle": true, "use_lora": true, "use_qlora": false, "batch_size": 4, "dataset_id": "gs://lum-dev-pipeline-zen-datasets/0ca98b07-9366-4a31-8c83-569961c90294/2024-12-17_21-57-21_text2sql.jsonl", "num_epochs": 1, "job_config_name": "llm_dummy"}' --model llm_dummy --ft_type "LORA" --monitor
```

Example LLaMA 3.2 1B LoRA job:

```bash
lumino-client create-job --args '{"shuffle": true, "use_lora": true, "use_qlora": false, "batch_size": 4, "dataset_id": "gs://lum-dev-pipeline-zen-datasets/0ca98b07-9366-4a31-8c83-569961c90294/2024-12-17_21-57-21_text2sql.jsonl", "num_epochs": 1, "job_config_name": "llm_llama3_2_1b"}' --model llm_llama3_2_1b --ft_type "LORA"
```

### Monitoring Jobs

Monitor all submitted jobs:

```bash
lumino-client monitor-all
```

## Development

For development setup and contributing guidelines, see [DEVEL.md](DEVEL.md).