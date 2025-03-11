import json
import os
import re
import subprocess
import time
from typing import Dict

import pytest
from dotenv import load_dotenv
from web3 import Web3

from lumino.contracts_client.client import LuminoClient, LuminoConfig
from lumino.contracts_client.node_client import LuminoNode, NodeConfig
from utils import ThreadHelper

# Constants
CONTRACTS_DIR = '../contracts'
ABIS_DIR = f'{CONTRACTS_DIR}/out'
RPC_URL = 'http://localhost:8545'
COMPUTE_RATING = 30
STAKE_AMOUNT = Web3.to_wei(30 * 10, 'ether')
JOB_ARGS = json.dumps({"prompt": "Test job"})
MODEL_NAME = "llm_llama3_1_8b"
TEST_MODE = "1111111"  # Run all phases, 1 epoch
MIN_TOKEN_BALANCE = Web3.to_wei(500, 'ether')
TOKENS_500 = Web3.to_wei(500, 'ether')

# Reward and Penalty Constants
LEADER_REWARD = Web3.to_wei(5, 'ether')
JOB_AVAILABILITY_REWARD = Web3.to_wei(1, 'ether')
DISPUTER_REWARD = Web3.to_wei(0.5, 'ether')
LEADER_NOT_EXECUTED_PENALTY = Web3.to_wei(15, 'ether')
JOB_NOT_CONFIRMED_PENALTY = Web3.to_wei(10, 'ether')
MAX_PENALTIES_BEFORE_SLASH = 10


def deploy_contracts() -> Dict[str, str]:
    """Run forge deploy and parse proxy contract addresses from output."""
    try:
        deploy_command = ["forge", "script", "script/Deploy.s.sol:DeploymentScript", "--rpc-url", RPC_URL,
                          "--broadcast", "--private-key", os.getenv('DEPLOYER_PRIVATE_KEY')]
        result = subprocess.run(
            deploy_command,
            cwd=CONTRACTS_DIR,
            capture_output=True,
            text=True,
            check=True
        )

        # Parse output for proxy contract addresses
        output = result.stdout
        contract_pattern = re.compile(r"(?:(\w+) \(Proxy\): (0x[a-fA-F0-9]{40})|EpochManager: (0x[a-fA-F0-9]{40}))")

        # Process matches to handle both proxy and non-proxy cases
        matches = contract_pattern.findall(output)
        contract_addresses = {}
        for match in matches:
            # match[0] is proxy name (if present), match[1] is proxy address, match[2] is EpochManager address
            if match[0]:  # Proxy case
                contract_addresses[match[0]] = match[1]
            elif match[2]:  # EpochManager case
                contract_addresses['EpochManager'] = match[2]

        if not contract_addresses:
            raise ValueError("No proxy contract addresses or EpochManager found in forge deploy output")

        return contract_addresses

    except subprocess.CalledProcessError as e:
        pytest.fail(f"Forge deploy failed: {e.stderr}")
    except Exception as e:
        pytest.fail(f"Error during contract deployment: {str(e)}")


@pytest.fixture(scope="function")
def anvil_config(tmp_path_factory) -> Dict:
    """Fixture to set up test environment with Anvil and fresh contract deployment."""
    load_dotenv()

    # Deploy contracts and get addresses
    deployed_addresses = deploy_contracts()

    # Use temporary directory for node data, unique per test run
    temp_base_dir = tmp_path_factory.mktemp("node_test")
    unique_node_dir = temp_base_dir / f"node_data_{int(time.time() * 1000)}"
    unique_node_dir.mkdir()

    # Update contract addresses with deployed ones
    contract_addresses = {
        'LuminoToken': deployed_addresses.get('LuminoToken'),
        'AccessManager': deployed_addresses.get('AccessManager'),
        'WhitelistManager': deployed_addresses.get('WhitelistManager'),
        'NodeManager': deployed_addresses.get('NodeManager'),
        'IncentiveManager': deployed_addresses.get('IncentiveManager'),
        'NodeEscrow': deployed_addresses.get('NodeEscrow'),
        'LeaderManager': deployed_addresses.get('LeaderManager'),
        'JobManager': deployed_addresses.get('JobManager'),
        'EpochManager': deployed_addresses.get('EpochManager'),
        'JobEscrow': deployed_addresses.get('JobEscrow')
    }

    # Validate all required addresses are present
    missing = [k for k, v in contract_addresses.items() if v is None]
    if missing:
        pytest.fail(f"Missing contract addresses after deployment: {missing}")

    return {
        'node_sdk_config': LuminoConfig(
            web3_provider=os.getenv('RPC_URL', RPC_URL),
            private_key=os.getenv('NODE_PRIVATE_KEY'),
            contract_addresses=contract_addresses,
            abis_dir=os.getenv('ABIS_DIR', ABIS_DIR)
        ),
        'user_sdk_config': LuminoConfig(
            web3_provider=os.getenv('RPC_URL', RPC_URL),
            private_key=os.getenv('USER_PRIVATE_KEY'),
            contract_addresses=contract_addresses,
            abis_dir=os.getenv('ABIS_DIR', ABIS_DIR)
        ),
        'data_dir': str(unique_node_dir),
        'log_level': 10,  # DEBUG,
        'pipeline_zen_dir': None,  # Set to empty to emulate job with time.sleep()
        'test_mode': TEST_MODE
    }


@pytest.fixture(scope="function")
def deployer_sdk(anvil_config) -> LuminoClient:
    """Fixture to initialize deployer SDK for token management and whitelisting."""
    load_dotenv()
    deployer_config = LuminoConfig(
        web3_provider=anvil_config['node_sdk_config'].web3_provider,
        private_key=os.getenv('DEPLOYER_PRIVATE_KEY'),
        contract_addresses=anvil_config['node_sdk_config'].contract_addresses,
        abis_dir=anvil_config['node_sdk_config'].abis_dir
    )
    sdk = LuminoClient(deployer_config)
    return sdk


@pytest.fixture(scope="function")
def node(anvil_config, deployer_sdk) -> LuminoNode:
    """Fixture to initialize Lumino node with token and whitelist management."""
    config = NodeConfig(
        sdk_config=anvil_config['node_sdk_config'],
        data_dir=anvil_config['data_dir'],
        pipeline_zen_dir=os.getenv('PIPELINE_ZEN_DIR'),
        log_level=anvil_config['log_level'],
        test_mode=anvil_config['test_mode'],
        compute_rating=COMPUTE_RATING
    )
    node = LuminoNode(config)

    # Ensure node has minimum token balance
    node_balance = deployer_sdk.get_token_balance(node.address)
    if node_balance < MIN_TOKEN_BALANCE:
        deployer_sdk.token.functions.transfer(node.address, TOKENS_500).transact({
            'from': deployer_sdk.address,
            'nonce': deployer_sdk.w3.eth.get_transaction_count(deployer_sdk.address)
        })
        node.logger.info(f"Transferred {Web3.from_wei(TOKENS_500, 'ether')} LUM to node {node.address}")

    # Ensure node is whitelisted
    if not deployer_sdk.is_whitelisted(node.address):
        deployer_sdk.add_cp(node.address)
        node.logger.info(f"Whitelisted node address {node.address}")

    return node


@pytest.fixture(scope="function")
def node_sdk(anvil_config, deployer_sdk) -> LuminoClient:
    """Fixture to initialize node SDK."""
    sdk = LuminoClient(anvil_config['node_sdk_config'])
    return sdk


@pytest.fixture(scope="function")
def user_sdk(anvil_config, deployer_sdk) -> LuminoClient:
    """Fixture to initialize user SDK with separate address."""
    sdk = LuminoClient(anvil_config['user_sdk_config'])

    # Ensure user has minimum token balance
    user_balance = deployer_sdk.get_token_balance(sdk.address)
    if user_balance < MIN_TOKEN_BALANCE:
        deployer_sdk.token.functions.transfer(sdk.address, TOKENS_500).transact({
            'from': deployer_sdk.address,
            'nonce': deployer_sdk.w3.eth.get_transaction_count(deployer_sdk.address)
        })
        sdk.logger.info(f"Transferred {Web3.from_wei(TOKENS_500, 'ether')} LUM to user {sdk.address}")

    return sdk


class TestNodeClientE2E:
    """End-to-end tests_e2e for Lumino node client"""

    def test_node_registration(self, node: LuminoNode, node_sdk: LuminoClient):
        """Test node registration process"""
        # Setup: Approve and deposit stake
        node_sdk.approve_token_spending(node_sdk.node_escrow.address, STAKE_AMOUNT)
        node_sdk.deposit_stake(STAKE_AMOUNT)

        # Record initial balance
        initial_balance = node_sdk.get_stake_balance(node_sdk.address)

        # Register node
        node.register_node()

        # Verify registration
        assert node.node_id is not None, "Node ID should be set after registration"
        assert node_sdk.get_node_info(node.node_id)[0] == node_sdk.address, "Node owner should match address"
        assert node_sdk.get_stake_requirement(node_sdk.address) == STAKE_AMOUNT, "Stake requirement mismatch"

        # Verify balance (no rewards/penalties expected)
        final_balance = node_sdk.get_stake_balance(node_sdk.address)
        assert final_balance == initial_balance, \
            f"Balance should not change during registration. Expected {Web3.from_wei(initial_balance, 'ether')} LUM, " \
            f"got {Web3.from_wei(final_balance, 'ether')} LUM"

    def test_full_job_lifecycle(self, node: LuminoNode, node_sdk: LuminoClient, user_sdk: LuminoClient):
        """Test complete job lifecycle from submission to completion"""
        # Setup: Ensure node is registered
        if not node.node_id:
            node_sdk.approve_token_spending(node_sdk.node_escrow.address, STAKE_AMOUNT)
            node_sdk.deposit_stake(STAKE_AMOUNT)
            node.register_node()

        # Record initial balances
        node_initial_balance = node_sdk.get_stake_balance(node_sdk.address)
        user_initial_escrow = user_sdk.get_job_escrow_balance(user_sdk.address)

        # Setup: Submit job as user using user_sdk
        user_sdk.approve_token_spending(user_sdk.job_escrow.address, Web3.to_wei(20, 'ether'))
        user_sdk.deposit_job_funds(Web3.to_wei(20, 'ether'))
        receipt = user_sdk.submit_job(JOB_ARGS, MODEL_NAME, COMPUTE_RATING)

        # Get job ID from event
        job_submitted_event = user_sdk.job_manager.events.JobSubmitted()
        logs = job_submitted_event.process_receipt(receipt)
        job_id = logs[0]['args']['jobId']

        # Run node for one epoch plus initial wait for first DISPUTE
        node_thread = ThreadHelper(node.run).run()

        # Wait for job completion by checking epochs_processed
        while node.epochs_processed < 1:
            time.sleep(0.3)

        # Cleanup
        node_thread.stop()

        # Verify job completion
        status = user_sdk.get_job_status(job_id)
        assert status == 3, f"Job {job_id} did not complete, final status: {status}"
        assert user_sdk.get_assigned_node(job_id) == node.node_id, "Job not assigned to test node"
        assert node.epochs_processed >= 1, f"Expected at least 1 epoch processed, got {node.epochs_processed}"

        # Verify balances
        node_final_balance = node_sdk.get_stake_balance(node_sdk.address)
        user_final_escrow = user_sdk.get_job_escrow_balance(user_sdk.address)
        expected_rewards = JOB_AVAILABILITY_REWARD + DISPUTER_REWARD  # Participation rewards
        node_change = node_final_balance - node_initial_balance
        assert node_final_balance > node_initial_balance, "Node should receive payment/rewards"
        assert user_final_escrow < Web3.to_wei(20, 'ether'), "Payment not deducted from submitter escrow"
        assert node_change >= expected_rewards, \
            f"Node balance increase insufficient. Expected at least {Web3.from_wei(expected_rewards, 'ether')} LUM, " \
            f"got {Web3.from_wei(node_change, 'ether')} LUM"

    def test_leader_election_and_assignment(self, node: LuminoNode, node_sdk: LuminoClient, user_sdk: LuminoClient):
        """Test leader election and job assignment"""
        # Setup: Ensure node is registered
        if not node.node_id:
            node_sdk.approve_token_spending(node_sdk.node_escrow.address, STAKE_AMOUNT)
            node_sdk.deposit_stake(STAKE_AMOUNT)
            node.register_node()

        # Record initial balance
        initial_balance = node_sdk.get_stake_balance(node_sdk.address)

        # Submit a job using user_sdk
        user_sdk.approve_token_spending(user_sdk.job_escrow.address, Web3.to_wei(20, 'ether'))
        user_sdk.deposit_job_funds(Web3.to_wei(20, 'ether'))
        receipt = user_sdk.submit_job(JOB_ARGS, MODEL_NAME, COMPUTE_RATING)
        job_id = user_sdk.job_manager.events.JobSubmitted().process_receipt(receipt)[0]['args']['jobId']

        # Run node through one full epoch
        node_thread = ThreadHelper(node.run).run()
        while node.epochs_processed < 1:
            time.sleep(0.3)
        node_thread.stop()

        # Verify leader election
        leader_id = node_sdk.get_current_leader()
        assert leader_id > 0, "No leader elected"
        assert node.epochs_processed >= 1, f"Expected at least 1 epoch processed, got {node.epochs_processed}"

        # If this node is leader, verify assignment
        if leader_id == node.node_id:
            assigned_node = user_sdk.get_assigned_node(job_id)
            assert assigned_node > 0, "Job not assigned by leader"

        # Verify balance (leader or participant rewards)
        final_balance = node_sdk.get_stake_balance(node_sdk.address)
        expected_rewards = JOB_AVAILABILITY_REWARD + DISPUTER_REWARD
        if leader_id == node.node_id:
            expected_rewards += LEADER_REWARD
        actual_change = final_balance - initial_balance
        assert actual_change >= expected_rewards, \
            f"Balance increase insufficient. Expected at least {Web3.from_wei(expected_rewards, 'ether')} LUM, " \
            f"got {Web3.from_wei(actual_change, 'ether')} LUM"

    def test_incentive_processing(self, node: LuminoNode, node_sdk: LuminoClient):
        """Test incentive processing"""
        # Setup: Ensure node is registered
        if not node.node_id:
            node_sdk.approve_token_spending(node_sdk.node_escrow.address, STAKE_AMOUNT)
            node_sdk.deposit_stake(STAKE_AMOUNT)
            node.register_node()

        # Record initial balance
        initial_balance = node_sdk.get_stake_balance(node_sdk.address)

        # Run node for one full epoch
        node_thread = ThreadHelper(node.run).run()
        while node.epochs_processed < 1:
            time.sleep(0.3)
        node_thread.stop()

        # Verify incentives
        final_balance = node_sdk.get_stake_balance(node_sdk.address)
        expected_rewards = JOB_AVAILABILITY_REWARD + DISPUTER_REWARD
        actual_change = final_balance - initial_balance
        assert node.epochs_processed >= 1, f"Expected at least 1 epoch processed, got {node.epochs_processed}"
        assert actual_change >= expected_rewards, \
            f"Incentive rewards insufficient. Expected at least {Web3.from_wei(expected_rewards, 'ether')} LUM, " \
            f"got {Web3.from_wei(actual_change, 'ether')} LUM"

    def test_leader_fails_duties_penalty(self, node: LuminoNode, node_sdk: LuminoClient):
        """Test penalty applied when leader fails to start assignment round"""
        # Setup: Ensure node is registered
        if not node.node_id:
            node_sdk.approve_token_spending(node_sdk.node_escrow.address, STAKE_AMOUNT)
            node_sdk.deposit_stake(STAKE_AMOUNT)
            node.register_node()

        # Record initial stake balance
        initial_balance = node_sdk.get_stake_balance(node_sdk.address)

        # Run node with modified TEST_MODE to skip EXECUTE phase
        node.test_mode = "1110111"  # Skip EXECUTE, 1 epoch
        node_thread = ThreadHelper(node.run).run()
        while node.epochs_processed < 1:
            time.sleep(0.3)
        node_thread.stop()

        # Verify penalty conditions
        current_epoch = node_sdk.epoch_manager.functions.getCurrentEpoch().call()
        assert not node_sdk.job_manager.functions.wasAssignmentRoundStarted(current_epoch).call(), \
            "Assignment round should not have started"
        assert node.epochs_processed >= 1, f"Expected at least 1 epoch processed, got {node.epochs_processed}"

        # Verify balance change
        final_balance = node_sdk.get_stake_balance(node_sdk.address)
        expected_penalty = LEADER_NOT_EXECUTED_PENALTY
        expected_rewards = JOB_AVAILABILITY_REWARD + DISPUTER_REWARD
        expected_change = expected_rewards - expected_penalty
        actual_change = final_balance - initial_balance
        assert final_balance == initial_balance + expected_change, \
            f"Balance change incorrect. Expected {Web3.from_wei(expected_change, 'ether')} LUM " \
            f"(rewards {Web3.from_wei(expected_rewards, 'ether')} - penalty {Web3.from_wei(expected_penalty, 'ether')}), " \
            f"got {Web3.from_wei(actual_change, 'ether')} LUM"

    def test_node_fails_to_confirm_penalty(self, node: LuminoNode, node_sdk: LuminoClient, user_sdk: LuminoClient):
        """Test penalty applied when node fails to confirm an assigned job"""
        # Setup: Ensure node is registered
        if not node.node_id:
            node_sdk.approve_token_spending(node_sdk.node_escrow.address, STAKE_AMOUNT)
            node_sdk.deposit_stake(STAKE_AMOUNT)
            node.register_node()

        # Submit a job
        user_sdk.approve_token_spending(user_sdk.job_escrow.address, Web3.to_wei(20, 'ether'))
        user_sdk.deposit_job_funds(Web3.to_wei(20, 'ether'))
        receipt = user_sdk.submit_job(JOB_ARGS, MODEL_NAME, COMPUTE_RATING)
        job_id = user_sdk.job_manager.events.JobSubmitted().process_receipt(receipt)[0]['args']['jobId']

        # Record initial stake balance
        initial_balance = node_sdk.get_stake_balance(node_sdk.address)

        # Run node skipping CONFIRM phase
        node.test_mode = "1111011"  # Skip CONFIRM, 1 epoch
        node_thread = ThreadHelper(node.run).run()
        while node.epochs_processed < 1:
            time.sleep(0.3)
        node_thread.stop()

        # Verify job was assigned but not confirmed
        assigned_node = user_sdk.get_assigned_node(job_id)
        assert assigned_node == node.node_id, "Job should be assigned to test node"
        assert user_sdk.get_job_status(job_id) == 1, "Job should remain ASSIGNED (1), not CONFIRMED (2)"
        assert node.epochs_processed >= 1, f"Expected at least 1 epoch processed, got {node.epochs_processed}"

        # Verify balance change
        final_balance = node_sdk.get_stake_balance(node_sdk.address)
        expected_penalty = JOB_NOT_CONFIRMED_PENALTY
        expected_rewards = JOB_AVAILABILITY_REWARD + LEADER_REWARD + DISPUTER_REWARD
        expected_change = expected_rewards - expected_penalty
        actual_change = final_balance - initial_balance
        assert final_balance == initial_balance + expected_change, \
            f"Balance change incorrect. Expected {Web3.from_wei(expected_change, 'ether')} LUM " \
            f"(rewards {Web3.from_wei(expected_rewards, 'ether')} - penalty {Web3.from_wei(expected_penalty, 'ether')}), " \
            f"got {Web3.from_wei(actual_change, 'ether')} LUM"

    def test_slashing_after_multiple_penalties(self, node: LuminoNode, node_sdk: LuminoClient, user_sdk: LuminoClient):
        """Test slashing applied after exceeding maximum penalties"""
        # Setup: Ensure node is registered
        if not node.node_id:
            node_sdk.approve_token_spending(node_sdk.node_escrow.address, STAKE_AMOUNT)
            node_sdk.deposit_stake(STAKE_AMOUNT)
            node.register_node()

        # Record initial stake balance
        initial_balance = node_sdk.get_stake_balance(node_sdk.address)
        assert initial_balance >= STAKE_AMOUNT, "Initial balance should match deposited stake"

        # Simulate multiple failures to reach MAX_PENALTIES_BEFORE_SLASH (5)
        max_penalties = MAX_PENALTIES_BEFORE_SLASH  # From LShared.MAX_PENALTIES_BEFORE_SLASH
        required_epochs = max_penalties  # One penalty per epoch

        # Adjust TEST_MODE for multiple epochs, skipping CONFIRM
        node.test_mode = "111011" + str(required_epochs)  # Skip CONFIRM, run 5 epochs
        node_thread = ThreadHelper(node.run).run()
        while node.epochs_processed < required_epochs:
            time.sleep(0.3)
        node_thread.stop()

        # Verify epoch count
        assert node.epochs_processed == required_epochs, \
            f"Expected {required_epochs} epochs processed, got {node.epochs_processed}"

        # Verify balance slashed to 0
        final_balance = node_sdk.get_stake_balance(node_sdk.address)
        assert final_balance == 0, f"Balance should be slashed to 0. Expected 0 LUM, got {Web3.from_wei(final_balance, 'ether')} LUM"


if __name__ == "__main__":
    pytest.main(["-v"])
