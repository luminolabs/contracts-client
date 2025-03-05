# Client for the Lumino protocol

To install, run the following command:

```bash
pip install lumino-contracts-client
```

## Usage

Start the node client to register the node on the network and start listening for jobs:

```bash
lumino-node
```

Start the user client to create a job:

```bash
lumino-user create-job \
  --args '{"dataset_id": "gs://...", "batch_size": 2, "shuffle": "true", "num_epochs": 1, "use_lora": "true", "use_qlora": "false", "lr": "3e-4"}' \
  --model llm_llama3_2_1b \
  --pool 30 \
  --monitor
```