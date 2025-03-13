import json
import logging
import os
import random
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from web3 import Web3

from lumino.contracts_client.client import LuminoClient, LuminoConfig, ContractError

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
        self.data_dir = Path(config.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.node_data_file = self.data_dir / "node_data.json"

        # Set test mode
        self.test_mode = config.test_mode

        # Set up logging
        self._setup_logging(config.log_level)
        self.logger.info("Initializing Lumino Node...")

        # Initialize SDK
        self.sdk = LuminoClient(config.sdk_config, self.logger)
        self.address = self.sdk.address

        # Setup event monitoring
        self.sdk.setup_event_filters()

        # Load node data
        self.node_data = self._load_node_data()
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
            self.pipeline_zen_dir = Path(config.pipeline_zen_dir)
            self.script_dir = Path("scripts/runners/celery-wf.sh")
            self.results_base_dir = Path(".results/")

        self.logger.info("Lumino Node initialization complete")

    def _setup_logging(self, log_level: int) -> None:
        """Set up logging with file and console handlers"""
        self.logger = logging.getLogger("LuminoNode")
        self.logger.setLevel(log_level)

        # Clear existing handlers
        self.logger.handlers.clear()

        # Create formatters and handlers
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # File handler
        file_handler = logging.FileHandler(
            self.data_dir / "lumino_node.log"
        )
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def _load_node_data(self) -> dict:
        """Load node data from disk or initialize if not exists"""
        if self.node_data_file.exists():
            with open(self.node_data_file) as f:
                return json.load(f)
        return {}

    def _save_node_data(self) -> None:
        """Save node data to disk"""
        with open(self.node_data_file, 'w') as f:
            json.dump(self.node_data, f, indent=2)

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
            stdout, stderr = process.communicate()

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
        status_update_interval = 300  # 5 minutes
        last_status_update = time.time()

        # Map numeric states to readable names
        state_names = {
            0: "COMMIT",
            1: "REVEAL",
            2: "ELECT",
            3: "EXECUTE",
            4: "CONFIRM",
            5: "DISPUTE"
        }

        while True:
            try:
                current_time = time.time()

                # Process any new events
                self.sdk.process_events()

                # Periodic status update
                if current_time - last_status_update >= status_update_interval:
                    stake_balance = self.sdk.get_stake_balance(self.address)
                    token_balance = self.sdk.get_token_balance(self.address)
                    current_epoch = self.sdk.get_current_epoch()

                    self.logger.info("=== Node Status Update ===")
                    self.logger.info(f"Current epoch: {current_epoch}")
                    self.logger.info(f"Stake balance: {Web3.from_wei(stake_balance, 'ether')} LUM")
                    self.logger.info(f"Token balance: {Web3.from_wei(token_balance, 'ether')} LUM")
                    self.logger.info(f"Leader status: {'Leader' if self.is_leader else 'Regular node'}")
                    self.logger.info("========================")

                    last_status_update = current_time

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


def initialize_lumino_node() -> LuminoNode:
    """Initialize a Lumino node from a config file"""

    # Load configuration from environment
    sdk_config = LuminoConfig(
        web3_provider=os.getenv('RPC_URL', 'http://localhost:8545'),
        private_key=os.getenv('NODE_PRIVATE_KEY'),
        contract_addresses={
            'LuminoToken': os.getenv('LUMINO_TOKEN_ADDRESS'),
            'AccessManager': os.getenv('ACCESS_MANAGER_ADDRESS'),
            'WhitelistManager': os.getenv('WHITELIST_MANAGER_ADDRESS'),
            'NodeManager': os.getenv('NODE_MANAGER_ADDRESS'),
            'IncentiveManager': os.getenv('INCENTIVE_MANAGER_ADDRESS'),
            'NodeEscrow': os.getenv('NODE_ESCROW_ADDRESS'),
            'LeaderManager': os.getenv('LEADER_MANAGER_ADDRESS'),
            'JobManager': os.getenv('JOB_MANAGER_ADDRESS'),
            'EpochManager': os.getenv('EPOCH_MANAGER_ADDRESS'),
            'JobEscrow': os.getenv('JOB_ESCROW_ADDRESS')
        },
        abis_dir=os.getenv('ABIS_DIR', '../contracts/out')
    )

    compute_rating = int(os.getenv('COMPUTE_RATING', "0"))
    if not compute_rating:
        from lumino.contracts_client.hw_spec.hardware_pool_integration import HardwarePoolIntegration
        hpi = HardwarePoolIntegration('cache/')
        compute_rating = hpi.calculate_compute_power()

    config = NodeConfig(
        sdk_config=sdk_config,
        data_dir=os.getenv('NODE_DATA_DIR', 'cache/node_client'),
        pipeline_zen_dir=os.getenv('PIPELINE_ZEN_DIR'),
        test_mode=os.getenv('TEST_MODE'),
        compute_rating=compute_rating,
    )

    # Initialize node
    return LuminoNode(config)


def main():
    # Load environment variables
    load_dotenv()

    # Initialize node
    node = initialize_lumino_node()

    # Register with compute rating from environment
    node.register_node()

    # Run main loop
    node.run()


if __name__ == "__main__":
    main()
