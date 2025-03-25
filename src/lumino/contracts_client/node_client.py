import json
import logging
import os
import random
import subprocess
import tarfile
import time
import urllib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import click
from lumino.contracts_client.client import LuminoClient, LuminoConfig, ContractError
from lumino.contracts_client.config import load_environment, setup_environment_vars, create_sdk_config
from lumino.contracts_client.constants import (
    ENV_VAR_NODE_DATA_DIR,
    ENV_VAR_PIPELINE_ZEN_DIR,
    ENV_VAR_TEST_MODE,
    ENV_VAR_COMPUTE_RATING,
    ENV_VAR_ARTIFACTS_PASSWORD,
    DEFAULT_DATA_DIR,
    DEFAULT_PIPELINE_ZEN_DIR,
    DEFAULT_TEST_MODE,
    EPOCH_STATE, DEFAULT_LUMINO_DIR
)
from lumino.contracts_client.utils import setup_logging, load_json_file, save_json_file, check_and_create_dir, \
    read_env_vars
from web3 import Web3

# Load environment variables
load_environment()

# Escrow min deposit
MIN_DEPOSIT = Web3.to_wei(20, 'ether')


@dataclass
class NodeConfig:
    """Configuration for Lumino Node"""
    sdk_config: LuminoConfig
    data_dir: str
    pipeline_zen_dir: Optional[str] = None
    test_mode: Optional[str] = None
    log_level: int = logging.INFO
    compute_rating: int = 0


class LuminoNode:
    """Lumino node client implementation"""

    def __init__(self, config: NodeConfig):
        """Initialize the Lumino node client"""
        # Set up data directory
        self.data_dir = check_and_create_dir(config.data_dir)
        self.node_data_file = self.data_dir / "node_data.json"

        # Set test mode
        self.test_mode = config.test_mode

        # Set up logging
        self.logger = setup_logging("LuminoNode", self.data_dir / "lumino_node.log", config.log_level)
        self.logger.info("Initializing Lumino Node...")

        # Initialize SDK
        self.sdk = LuminoClient(config.sdk_config, self.logger)
        self.address = self.sdk.address

        # Setup event monitoring
        self.sdk.setup_event_filters()

        # Load node data
        self.node_data = load_json_file(self.node_data_file, {})
        self.node_id = self.node_data.get("node_id")

        # Node state
        self.current_secret: Optional[bytes] = None
        self.current_commitment: Optional[bytes] = None
        self.is_leader = False
        self.epochs_processed = 0

        # Compute rating
        self.compute_rating = config.compute_rating

        # Node can begin participating after first DISPUTE phase
        # to avoid entering mid-epoch
        self.can_begin = False

        # Job paths
        self.pipeline_zen_dir = None
        if config.pipeline_zen_dir:
            self.pipeline_zen_dir = Path(os.path.expanduser(config.pipeline_zen_dir))
            self.script_dir = Path("scripts/runners/celery-wf.sh")
            self.results_base_dir = Path(".results/")

        self.logger.info("Lumino Node initialization complete")

    def _save_node_data(self) -> None:
        """Save node data to disk"""
        save_json_file(self.node_data_file, self.node_data)

    def topup_stake(self, add_node: bool = False) -> None:
        addl_stake = 0
        if add_node:
            # Calculate required stake (10 token per compute rating unit)
            addl_stake = Web3.to_wei(self.compute_rating * 10, 'ether')

        # Get existing stake requirement and add additional stake if we are adding a node
        required_stake = self.sdk.get_stake_requirement(self.address) + addl_stake

        # Check current stake
        current_stake = self.sdk.get_stake_balance(self.address)
        if current_stake < required_stake:
            self.logger.info("Insufficient stake. Depositing required amount...")
            additional_stake_needed = max(required_stake - current_stake, MIN_DEPOSIT)

            # Approve and deposit tokens
            self.sdk.approve_token_spending(
                self.sdk.node_escrow.address,
                additional_stake_needed
            )
            self.sdk.deposit_stake(additional_stake_needed)

    def register_node(self) -> None:
        """Register node with the protocol"""
        if self.node_id is not None:
            self.logger.info(f"Node already registered with ID: {self.node_id}")
            return

        try:
            # Top up stake if needed
            self.topup_stake(add_node=True)

            # Register node
            receipt = self.sdk.register_node(self.compute_rating)

            # Get node ID from event
            node_registered_event = self.sdk.node_manager.events.NodeRegistered()
            logs = node_registered_event.process_receipt(receipt)
            self.node_id = logs[0]['args']['nodeId']

            # Save node ID
            self.node_data["node_id"] = self.node_id
            self._save_node_data()

            self.logger.info(f"Node registered with ID: {self.node_id}")

        except ContractError as e:
            self.logger.error(f"Failed to register node: {e}")
            raise

    def submit_commitment(self) -> None:
        """Submit commitment for current epoch"""
        # Generate random secret
        self.current_secret = random.randbytes(32)
        # Create commitment (hash of secret)
        self.current_commitment = Web3.solidity_keccak(['bytes32'], [self.current_secret])

        try:
            self.sdk.submit_commitment(self.node_id, self.current_commitment)
            self.logger.info("Commitment submitted")
        except ContractError as e:
            self.logger.error(f"Failed to submit commitment: {e}")
            raise

    def reveal_secret(self) -> None:
        """Reveal secret for current epoch"""
        if not self.current_secret:
            self.logger.error("No secret to reveal")
            return

        try:
            self.sdk.reveal_secret(self.node_id, self.current_secret)
            self.logger.info("Secret revealed")
        except ContractError as e:
            self.logger.error(f"Failed to reveal secret: {e}")
            raise

    def elect_leader(self) -> None:
        """Trigger leader election for current epoch"""
        try:
            self.sdk.elect_leader()
            self.logger.info("Leader election triggered")
        except ContractError as e:
            self.logger.error(f"Failed to elect leader: {e}")
            raise

    def check_and_perform_leader_duties(self) -> None:
        """Check if node is leader and perform leader duties"""
        try:
            current_leader = self.sdk.get_current_leader()
            self.is_leader = (current_leader == self.node_id)

            if self.is_leader:
                self.logger.info("This node is the current leader")
                self.sdk.start_assignment_round()
                self.logger.info("Assignment round started")
            else:
                self.logger.info("This node is not the current leader")
        except ContractError as e:
            self.logger.error(f"Error performing leader duties: {e}")
            raise

    def process_assigned_jobs(self) -> None:
        """Process any jobs assigned to this node"""
        try:
            jobs = self.sdk.get_jobs_by_node(self.node_id)
            for job in jobs:
                job_id = job["id"]
                job_base_model_name = job["baseModelName"]
                num_gpus = job["numGpus"]
                job_args = job["args"]
                status = job["status"]
                try:
                    if status == 1:  # ASSIGNED
                        # Disable can_begin to prevent re-entry halfway through epoch
                        self.can_begin = False

                        self.sdk.confirm_job(job_id)
                        self.logger.info(f"Confirmed job {job_id}")

                        # Execute job and monitor results
                        if self.pipeline_zen_dir:
                            success = self._execute_job(
                                job_id=job_id,
                                base_model_name=job_base_model_name,
                                args=job_args,
                                num_gpus=num_gpus,
                                submitter=job["submitter"]
                            )
                        else:
                            # Simulate job execution, success, and token count
                            time.sleep(5)
                            success = True
                            # This is the ML dataset token count after it's tokenized
                            self.sdk.set_token_count_for_job(job_id, 600000)

                        if success:
                            self.sdk.complete_job(job_id)
                            self.logger.info(f"Completed job {job_id}")
                            self.sdk.process_job_payment(job_id)
                        else:
                            self.sdk.fail_job(job_id, "Job execution failed")
                            self.logger.error(f"Job {job_id} failed execution")
                except Exception as e:
                    self.logger.error(f"Error processing job {job_id}: {e}")
                    self.sdk.fail_job(job_id, f"Processing error: {str(e)}")
                    continue
        except ContractError as e:
            self.logger.error(f"Error getting assigned jobs: {e}")
            raise

    def _execute_job(self, job_id: int, base_model_name: str, args: str, num_gpus: int, submitter: str) -> bool:
        """Execute a job using celery-wf-docker.sh and monitor results"""
        self.logger.info(f"Executing job {job_id}")

        try:
            # Parse job arguments
            try:
                args_dict = json.loads(args)
            except json.JSONDecodeError:
                self.logger.error(f"Invalid JSON in job args: {args}")
                return False

            # CD to pipeline directory
            current_dir = os.getcwd()
            os.chdir(self.pipeline_zen_dir)

            # Generate random seed
            if "seed" not in args_dict:
                args_dict["seed"] = random.randint(0, 2 ** 32)

            # Construct command
            command = [
                str(self.script_dir),
                "torchtunewrapper",
                "--job_config_name", base_model_name,
                "--job_id", f"{job_id}",
                "--user_id", submitter,
                "--dataset_id", args_dict.get("dataset_id", ""),
                "--batch_size", str(args_dict.get("batch_size", 2)),
                "--shuffle", str(args_dict.get("shuffle", "true")).lower(),
                "--num_epochs", str(args_dict.get("num_epochs", 1)),
                "--use_lora", str(args_dict.get("use_lora", "true")).lower(),
                "--use_qlora", str(args_dict.get("use_qlora", "false")).lower(),
                "--lr", str(args_dict.get("lr", "3e-4")),
                "--seed", str(args_dict.get("seed")),
                "--num_gpus", str(num_gpus)
            ]

            # Create results directory
            result_dir = self.results_base_dir / submitter / str(job_id)
            result_dir.mkdir(parents=True, exist_ok=True)

            # Start the process
            self.logger.info(f"Starting job execution: {' '.join(command)}")
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "PZ_ENV": 'cpnode'}
            )

            # Monitor token count file
            token_count_file = result_dir / ".token-count"
            finish_file = result_dir / ".finished"

            while process.poll() is None:
                # Check for token count
                if token_count_file.exists():
                    try:
                        with open(token_count_file, 'r') as f:
                            token_count = int(f.read().strip())
                        self.sdk.set_token_count_for_job(job_id, token_count)
                        self.logger.info(f"Reported token count {token_count} for job {job_id}")
                    except (ValueError, IOError) as e:
                        self.logger.warning(f"Failed to read token count: {e}")
                    break

                time.sleep(1)  # Poll every second

            # Wait for process to finish
            process.communicate()

            # Check if process finished successfully
            time.sleep(1)
            finish_file_exists = finish_file.exists()

            # Return to original directory
            os.chdir(current_dir)

            if not finish_file_exists:
                self.logger.error(f"Job {job_id} finished but no .finished file found")
                return False

            self.logger.info(f"Job {job_id} execution completed successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error executing job {job_id}: {e}")
            return False

    def process_incentives(self) -> None:
        """Process incentives for the current epoch"""
        try:
            self.sdk.process_incentives()
            self.logger.info("Incentive processing complete")
        except ContractError as e:
            self.logger.error(f"Failed to process incentives: {e}")
            raise

    def run(self) -> None:
        """Main node loop"""
        self.logger.info("Starting main node loop...")
        self.logger.info(f"Node ID: {self.node_id}")
        self.logger.info(f"Node address: {self.address}")

        # Track phase timing
        last_phase = None
        phase_start_time = time.time()

        # Use epoch state names from constants
        state_names = EPOCH_STATE

        while True:
            try:
                current_time = time.time()

                # Process any new events
                self.sdk.process_events()

                # Get current epoch state
                status_check_time = time.time()
                state, time_left = self.sdk.get_epoch_state()
                current_phase = state_names[state]

                # Log state transitions
                state_changed = last_phase != current_phase
                if state_changed:
                    if last_phase:
                        state_duration = current_time - phase_start_time
                        self.logger.info(f"Completed {last_phase} phase (duration: {state_duration:.2f}s)")
                    self.logger.info(f"Entering {current_phase} phase (time left: {time_left}s)")
                    last_phase = current_phase
                    phase_start_time = current_time

                # State machine for epoch phases
                if self.can_begin and state_changed:
                    try:
                        if state == 0 and self.test_mode and int(self.test_mode[0]) != 0:  # COMMIT
                            # If we are penalized, make sure we are topped up
                            self.topup_stake()
                            # Submit commitment
                            self.submit_commitment()

                        elif state == 1 and self.test_mode and int(self.test_mode[1]) != 0:  # REVEAL
                            if self.current_secret:
                                self.reveal_secret()
                            else:
                                self.logger.warning("No secret available to reveal")

                        elif state == 2 and self.test_mode and int(self.test_mode[2]) != 0:  # ELECT
                            self.elect_leader()

                        elif state == 3 and self.test_mode and int(self.test_mode[3]) != 0:  # EXECUTE
                            was_leader = self.is_leader
                            self.check_and_perform_leader_duties()
                            if self.is_leader != was_leader:
                                self.logger.info(
                                    f"Node leadership status changed to: {'Leader' if self.is_leader else 'Not leader'}")

                        elif state == 4 and self.test_mode and int(self.test_mode[4]) != 0:  # CONFIRM
                            self.process_assigned_jobs()

                        elif state == 5:  # DISPUTE
                            if self.test_mode and int(self.test_mode[5]) != 0:
                                self.process_incentives()
                            # Increment epoch counter
                            self.epochs_processed += 1

                    except Exception as phase_error:
                        self.logger.error(f"Error in {current_phase} phase: {phase_error}")
                        continue

                # Exit after X cycle for testing
                if self.test_mode and int(self.test_mode[6:]) != 0 and self.epochs_processed == int(self.test_mode[6:]):
                    # Wait, then print remaining events
                    time.sleep(5)
                    self.sdk.process_events()
                    self.logger.info("Test cycle complete")
                    break

                # Node can begin/resume after the DISPUTE phase
                if state == 5:
                    self.can_begin = True

                # Sleep then check epoch state again
                sleep_time = max(0, int(time_left) - int(time.time() - status_check_time)) + 2  # 2sec buffer
                time.sleep(sleep_time)

            except Exception as e:
                state, _ = self.sdk.get_epoch_state()
                self.logger.error(f"Critical error in main loop: {e}")
                self.logger.error("=== Node State at Error ===")
                self.logger.error(f"Current phase: {state_names.get(state, 'Unknown')}")
                self.logger.error(f"Is leader: {self.is_leader}")
                self.logger.error(f"Has secret: {bool(self.current_secret)}")
                self.logger.error(f"Has commitment: {bool(self.current_commitment)}")
                self.logger.error("=========================")


def get_artifacts_password() -> str:
    """
    Get artifacts password from environment variables or prompt user for it.
    
    Returns:
        The artifacts password string
    """
    # Check if password exists in environment
    artifacts_password = os.getenv(ENV_VAR_ARTIFACTS_PASSWORD)

    if not artifacts_password:
        # Password not in environment, prompt user
        artifacts_password = click.prompt(
            "Enter artifacts password for pipeline-zen download",
            hide_input=True
        )

        # Save to environment file
        lumino_dir = os.path.expanduser(DEFAULT_LUMINO_DIR)
        env_file = os.path.join(lumino_dir, '.env')

        # Use existing utility function to read env vars
        env_vars = read_env_vars(env_file, {ENV_VAR_ARTIFACTS_PASSWORD: 'Artifacts Password'})

        # Update password and write back
        env_vars[ENV_VAR_ARTIFACTS_PASSWORD] = artifacts_password

        with open(env_file, 'w') as f:
            for key, value in env_vars.items():
                f.write(f"{key}={value}\n")

        # Set in current environment
        os.environ[ENV_VAR_ARTIFACTS_PASSWORD] = artifacts_password

    return artifacts_password


def setup_pipeline_zen(data_dir: str) -> None:
    """
    Set up pipeline-zen for the node.
    
    Downloads and extracts pipeline-zen tarball, env file, and GCP key.
    
    Args:
        data_dir: The data directory path
    """
    logger = logging.getLogger("PipelineZenSetup")

    # Get artifacts password
    artifacts_password = get_artifacts_password()

    # Artifacts base URL
    artifacts_base = f"https://storage.googleapis.com/lum-node-artifacts-{artifacts_password}"

    # Pipeline-zen directory path
    pipeline_zen_dir = Path(os.path.expanduser(data_dir))

    # Create directory structure
    pipeline_zen_dir.mkdir(parents=True, exist_ok=True)
    secrets_dir = pipeline_zen_dir / ".secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)

    # Artifacts to download
    artifacts = {
        "pipeline-zen.tar.gz": {
            "url": f"{artifacts_base}/pipeline-zen.tar.gz",
            "path": pipeline_zen_dir / "pipeline-zen.tar.gz",
            "extract": True
        },
        "pipeline-zen.env": {
            "url": f"{artifacts_base}/pipeline-zen.env",
            "path": pipeline_zen_dir / ".env",
            "extract": False
        },
        "pipeline-zen-gcp-key.json": {
            "url": f"{artifacts_base}/pipeline-zen-gcp-key.json",
            "path": secrets_dir / "gcp_key.json",
            "extract": False
        }
    }

    try:
        # Download and process each artifact
        for name, artifact in artifacts.items():
            logger.info(f"Downloading {name}...")

            # Download the file
            try:
                urllib.request.urlretrieve(artifact["url"], artifact["path"])
            except Exception as e:
                logger.error(f"Failed to download {name}: {e}")
                continue

            # Extract if needed
            if artifact["extract"]:
                logger.info(f"Extracting {name}...")
                try:
                    with tarfile.open(artifact["path"]) as tar:
                        tar.extractall(path=pipeline_zen_dir / "..")

                    # Remove the tarball after extraction
                    os.remove(artifact["path"])
                except Exception as e:
                    logger.error(f"Failed to extract {name}: {e}")
                    continue

        logger.info("Running install-deps.sh script...")
        try:
            subprocess.run(["./scripts/install-deps.sh"], cwd=pipeline_zen_dir, check=True)
            logger.info("install-deps.sh completed successfully")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to run install-deps.sh: {e}")
        except Exception as e:
            logger.error(f"Error running install-deps.sh: {e}")

        logger.info("Pipeline-zen setup complete")

    except Exception as e:
        logger.error(f"Error setting up pipeline-zen: {e}")
        raise


def initialize_lumino_node() -> LuminoNode:
    """Initialize and return a LuminoNode instance with proper config"""
    # Setup environment variables, prompting for missing values
    setup_environment_vars(is_node=True)

    # Set up pipeline-zen directory
    pipeline_zen_path = os.getenv(ENV_VAR_PIPELINE_ZEN_DIR, DEFAULT_PIPELINE_ZEN_DIR)
    # If there's a .git in the dir, assume it's a local dev env so skip setup pipeline-zen
    pipeline_zen_path = os.path.expanduser(pipeline_zen_path)
    if not os.path.exists(pipeline_zen_path) or ".git" not in os.listdir(pipeline_zen_path):
        setup_pipeline_zen(pipeline_zen_path)

    # Create SDK config
    sdk_config = create_sdk_config(is_node=True)

    # Get or calculate compute rating
    compute_rating = int(os.getenv(ENV_VAR_COMPUTE_RATING, "0"))
    if not compute_rating:
        # Import here to ensure proper mocking in tests
        from lumino.contracts_client.compute_power import get_compute_power
        compute_rating = get_compute_power()

    # Create node config
    config = NodeConfig(
        sdk_config=sdk_config,
        data_dir=os.getenv(ENV_VAR_NODE_DATA_DIR, DEFAULT_DATA_DIR['node']),
        pipeline_zen_dir=pipeline_zen_path,
        test_mode=os.getenv(ENV_VAR_TEST_MODE, DEFAULT_TEST_MODE),
        compute_rating=compute_rating,
    )

    # Initialize node
    return LuminoNode(config)


def main():
    # Initialize node
    node = initialize_lumino_node()

    # Register with compute rating from environment
    node.register_node()

    # Run main loop
    node.run()


if __name__ == "__main__":
    main()
