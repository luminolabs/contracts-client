import json
import logging
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from web3 import Web3

from lumino_sdk import LuminoSDK, LuminoConfig, ContractError


@dataclass
class NodeConfig:
    """Configuration for Lumino Node"""
    sdk_config: LuminoConfig
    data_dir: str = "../node_data"
    log_level: int = logging.INFO
    test_mode: Optional[str] = None

    @classmethod
    def from_file(cls, config_path: str) -> 'NodeConfig':
        """Create config from JSON file"""
        with open(config_path) as f:
            config_data = json.load(f)
        sdk_config_data = {
            'web3_provider': config_data['web3_provider'],
            'private_key': config_data['private_key'],
            'contract_addresses': config_data['contract_addresses'],
            'contracts_dir': config_data['contracts_dir']
        }
        sdk_config = LuminoConfig(**sdk_config_data)
        return cls(
            sdk_config=sdk_config,
            data_dir=config_data.get('data_dir', "../node_data"),
            log_level=config_data.get('log_level', logging.INFO),
            test_mode=config_data.get('test_mode')
        )


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
        self.sdk = LuminoSDK(config.sdk_config, self.logger)
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

    def register_node(self, compute_rating: int) -> None:
        """Register node with the protocol"""
        if self.node_id is not None:
            self.logger.info(f"Node already registered with ID: {self.node_id}")
            return

        try:
            # Calculate required stake (1 token per compute rating unit)
            required_stake = Web3.to_wei(compute_rating, 'ether')

            # Check current stake
            current_stake = self.sdk.get_stake_balance(self.address)
            if current_stake < required_stake:
                self.logger.info("Insufficient stake. Depositing required amount...")
                additional_stake_needed = required_stake - current_stake

                # Approve and deposit tokens
                self.sdk.approve_token_spending(
                    self.sdk.node_escrow.address,
                    additional_stake_needed
                )
                self.sdk.deposit_stake(additional_stake_needed)

            # Register node
            receipt = self.sdk.register_node(compute_rating)

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
                job_args = job["args"]
                status = job["status"]
                try:
                    if status == 1:  # ASSIGNED
                        self.sdk.confirm_job(job_id)
                        self.logger.info(f"Confirmed job {job_id}")
                        self._execute_job(job_id, job_args)
                        self.sdk.complete_job(job_id)
                        self.logger.info(f"Completed job {job_id}")
                        self.sdk.process_job_payment(job_id)
                    elif status == 2:  # CONFIRMED
                        self._execute_job(job_id, job_args)
                        self.sdk.complete_job(job_id)
                        self.logger.info(f"Completed job {job_id}")
                        self.sdk.process_job_payment(job_id)
                except Exception as e:
                    self.logger.error(f"Error processing job {job_id}: {e}")
                    continue
        except ContractError as e:
            self.logger.error(f"Error getting assigned jobs: {e}")
            raise

    def _execute_job(self, job_id: int, job_args: str) -> None:
        """Execute a job (simulated for testing)"""
        self.logger.info(f"Executing job {job_id}")
        try:
            # Simulated work
            time.sleep(2)
            self.sdk.set_token_count_for_job(job_id, 1000000)
            time.sleep(5)
            self.logger.info(f"Job [{job_id} : {job_args}] execution completed")
        except Exception as e:
            self.logger.error(f"Error executing job {job_id}: {e}")
            raise

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

        # Node can begin after first DISPUTE phase
        can_begin = False
        epochs_processed = 0

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
                if can_begin and state_changed:
                    try:
                        if state == 0:  # COMMIT
                            self.submit_commitment()

                        elif state == 1:  # REVEAL
                            if self.current_secret:
                                self.reveal_secret()
                            else:
                                self.logger.warning("No secret available to reveal")

                        elif state == 2:  # ELECT
                            self.elect_leader()

                        elif state == 3:  # EXECUTE
                            was_leader = self.is_leader
                            self.check_and_perform_leader_duties()
                            if self.is_leader != was_leader:
                                self.logger.info(
                                    f"Node leadership status changed to: {'Leader' if self.is_leader else 'Not leader'}")

                        elif state == 4:  # CONFIRM
                            self.process_assigned_jobs()

                        elif state == 5:  # DISPUTE
                            self.process_incentives()
                            epochs_processed += 1

                    except Exception as phase_error:
                        self.logger.error(f"Error in {current_phase} phase: {phase_error}")
                        if self.test_mode:
                            # Wait 3 seconds, then print remaining events
                            time.sleep(3)
                            self.sdk.process_events()
                            raise
                        continue

                # Exit after first cycle for testing
                if self.test_mode and int(self.test_mode[5]) != 0 and epochs_processed >= int(self.test_mode[5]):
                    # Wait 3 seconds, then print remaining events
                    time.sleep(3)
                    self.sdk.process_events()
                    self.logger.info("Test cycle complete")
                    break

                # Node can begin after first DISPUTE phase
                if state == 5:
                    can_begin = True

                # Sleep until next phase
                sleep_time = min(time_left, 2)  # Check state every 2 seconds
                time.sleep(sleep_time)

            except Exception as e:
                self.logger.error(f"Critical error in main loop: {e}")
                self.logger.error("=== Node State at Error ===")
                self.logger.error(f"Current phase: {state_names.get(state, 'Unknown')}")
                self.logger.error(f"Is leader: {self.is_leader}")
                self.logger.error(f"Has secret: {bool(self.current_secret)}")
                self.logger.error(f"Has commitment: {bool(self.current_commitment)}")
                self.logger.error("=========================")

                if self.test_mode:
                    raise
                time.sleep(5)  # Brief pause before retrying


def initialize_lumino_node(config_path: str = None) -> LuminoNode:
    """Initialize a Lumino node from a config file"""

    if config_path:
        config = NodeConfig.from_file(config_path)
    else:
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
            contracts_dir= os.getenv('CONTRACTS_DIR', '../contracts/src')
        )
        config = NodeConfig(
            sdk_config=sdk_config,
            data_dir=os.getenv('NODE_DATA_DIR', 'cache/node_client'),
            test_mode=os.getenv('TEST_MODE')
        )

    # Initialize node
    return LuminoNode(config)


if __name__ == "__main__":
    # Load environment variables
    load_dotenv()

    # Initialize node
    node = initialize_lumino_node()

    # Register with compute rating from environment
    compute_rating = int(os.getenv('COMPUTE_RATING', '10'))
    node.register_node(compute_rating)

    # Run main loop
    node.run()
