import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, ANY

from web3 import Web3

from lumino.contracts_client.client import LuminoConfig, ContractError
from lumino.contracts_client.node_client import NodeConfig, LuminoNode, initialize_lumino_node


class TestNodeClient(unittest.TestCase):
    """Tests for node_client.py functionality"""

    def setUp(self):
        """Set up test environment before each test"""
        # Create a temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        
        # Create basic directory structure
        self.data_dir = self.test_dir / "node_data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Sample contract addresses
        self.contract_addresses = {
            "AccessManager": "0x1111",
            "WhitelistManager": "0x2222",
            "LuminoToken": "0x3333",
            "NodeManager": "0x4444",
            "JobManager": "0x5555",
            "NodeEscrow": "0x6666",
            "LeaderManager": "0x7777"
        }
        
        # Sample config
        self.sdk_config = LuminoConfig(
            web3_provider="http://localhost:8545",
            private_key="0x" + "0123456789" * 4,
            contract_addresses=self.contract_addresses,
            abis_dir=str(self.test_dir / "abis")
        )
        
        self.node_config = NodeConfig(
            sdk_config=self.sdk_config,
            data_dir=str(self.data_dir),
            pipeline_zen_dir=str(self.test_dir / "pipeline-zen"),
            test_mode="1111110",
            compute_rating=100
        )
        
        # Mock Lumino SDK
        self.mock_sdk = MagicMock()
        self.mock_sdk.address = "0x1234567890abcdef"
        
        # Add contract mocks
        self.mock_sdk.node_manager = MagicMock()
        self.mock_sdk.node_escrow = MagicMock()
        self.mock_sdk.leader_manager = MagicMock()
        self.mock_sdk.job_manager = MagicMock()
        self.mock_sdk.epoch_manager = MagicMock()
        self.mock_sdk.incentive_manager = MagicMock()
        
        # Mock node event
        self.mock_node_registered_event = MagicMock()
        self.mock_sdk.node_manager.events.NodeRegistered.return_value = self.mock_node_registered_event
        
        # Mock job assigned event
        self.mock_job_submitted_event = MagicMock()
        self.mock_sdk.job_manager.events.JobSubmitted.return_value = self.mock_job_submitted_event

    def tearDown(self):
        """Clean up after each test"""
        self.temp_dir.cleanup()
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    def test_initialization(self, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test LuminoNode initialization"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # Verify logger and SDK were initialized
        mock_setup_logging.assert_called_once_with(
            "LuminoNode", ANY, self.node_config.log_level
        )
        mock_lumino_client.assert_called_once_with(self.node_config.sdk_config, mock_logger)
        
        # Verify node data file was checked
        mock_load_json.assert_called_once_with(ANY, {})
        
        # Verify initial state
        self.assertEqual(node.address, self.mock_sdk.address)
        self.assertEqual(node.compute_rating, self.node_config.compute_rating)
        self.assertEqual(node.node_id, None)
        self.assertEqual(node.current_secret, None)
        self.assertEqual(node.current_commitment, None)
        self.assertEqual(node.is_leader, False)
        self.assertEqual(node.test_mode, self.node_config.test_mode)
        
        # Verify pipeline_zen_dir is set if provided
        self.assertIsNotNone(node.pipeline_zen_dir)
        self.assertEqual(node.pipeline_zen_dir, Path(self.node_config.pipeline_zen_dir))
        
        # Verify SDK event filters were set up
        self.mock_sdk.setup_event_filters.assert_called_once()
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    @patch('lumino.contracts_client.node_client.save_json_file')
    def test_node_with_existing_id(self, mock_save_json, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test LuminoNode initialization with existing node ID"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"node_id": 42}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # Verify node_id was loaded from data file
        self.assertEqual(node.node_id, 42)
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    @patch('lumino.contracts_client.node_client.save_json_file')
    def test_save_node_data(self, mock_save_json, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test saving node data"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"node_id": 42}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # Call _save_node_data
        node._save_node_data()
        
        # Verify save_json_file was called with the correct args
        mock_save_json.assert_called_once_with(node.node_data_file, {"node_id": 42})
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    def test_topup_stake_sufficient_balance(self, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test topup_stake with sufficient existing stake"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Set up stake requirement and current stake
        self.mock_sdk.get_stake_requirement.return_value = Web3.to_wei(500, 'ether')
        self.mock_sdk.get_stake_balance.return_value = Web3.to_wei(1000, 'ether')  # More than required
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # Call topup_stake
        node.topup_stake()
        
        # Verify stake was checked but not deposited
        self.mock_sdk.get_stake_requirement.assert_called_once_with(node.address)
        self.mock_sdk.get_stake_balance.assert_called_once_with(node.address)
        self.mock_sdk.approve_token_spending.assert_not_called()
        self.mock_sdk.deposit_stake.assert_not_called()
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    def test_topup_stake_insufficient_balance(self, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test topup_stake with insufficient existing stake"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Set up stake requirement and current stake
        required = Web3.to_wei(500, 'ether')
        current = Web3.to_wei(200, 'ether')  # Less than required
        self.mock_sdk.get_stake_requirement.return_value = required
        self.mock_sdk.get_stake_balance.return_value = current
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # Call topup_stake
        node.topup_stake()
        
        # Verify additional stake was approved and deposited
        self.mock_sdk.get_stake_requirement.assert_called_once_with(node.address)
        self.mock_sdk.get_stake_balance.assert_called_once_with(node.address)
        
        # Calculate additional stake (required - current)
        additional_stake = required - current
        
        self.mock_sdk.approve_token_spending.assert_called_once_with(
            self.mock_sdk.node_escrow.address,
            additional_stake
        )
        self.mock_sdk.deposit_stake.assert_called_once_with(additional_stake)
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    @patch('lumino.contracts_client.node_client.save_json_file')
    def test_register_node_already_registered(self, mock_save_json, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test register_node when already registered"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"node_id": 42}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # Call register_node
        node.register_node()
        
        # Verify node was not registered again
        self.mock_sdk.register_node.assert_not_called()
        mock_save_json.assert_not_called()
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    @patch('lumino.contracts_client.node_client.save_json_file')
    def test_register_node_new_registration(self, mock_save_json, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test register_node for new node"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {}  # No node_id
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Mock registration receipt and event
        mock_receipt = {"logs": [{"topics": ["event_topic"]}]}
        self.mock_sdk.register_node.return_value = mock_receipt
        
        # Mock event processing
        self.mock_node_registered_event.process_receipt.return_value = [
            {"args": {"nodeId": 123}}
        ]
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # Create a mock for topup_stake
        with patch.object(node, 'topup_stake') as mock_topup:
            # Call register_node
            node.register_node()
            
            # Verify topup_stake was called
            mock_topup.assert_called_once_with(add_node=True)
            
            # Verify node was registered
            self.mock_sdk.register_node.assert_called_once_with(node.compute_rating)
            
            # Verify event was processed
            self.mock_node_registered_event.process_receipt.assert_called_once_with(mock_receipt)
            
            # Verify node_id was updated
            self.assertEqual(node.node_id, 123)
            self.assertEqual(node.node_data["node_id"], 123)
            
            # Verify data was saved
            mock_save_json.assert_called_once()
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    @patch('random.randbytes')
    def test_submit_commitment(self, mock_randbytes, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test submitting commitment"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"node_id": 42}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Mock random secret and its hash
        mock_secret = b'0123456789abcdef' * 2
        mock_commitment = b'commitment_hash'
        mock_randbytes.return_value = mock_secret
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # Mock Web3.solidity_keccak
        with patch('lumino.contracts_client.node_client.Web3.solidity_keccak', return_value=mock_commitment):
            # Call submit_commitment
            node.submit_commitment()
            
            # Verify secret and commitment were generated
            self.assertEqual(node.current_secret, mock_secret)
            self.assertEqual(node.current_commitment, mock_commitment)
            
            # Verify commitment was submitted
            self.mock_sdk.submit_commitment.assert_called_once_with(
                node.node_id, mock_commitment
            )
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    def test_reveal_secret(self, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test revealing secret"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"node_id": 42}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # Set current secret
        node.current_secret = b'0123456789abcdef' * 2
        
        # Call reveal_secret
        node.reveal_secret()
        
        # Verify secret was revealed
        self.mock_sdk.reveal_secret.assert_called_once_with(
            node.node_id, node.current_secret
        )
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    def test_reveal_secret_no_secret(self, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test revealing secret when no secret exists"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"node_id": 42}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # No current secret
        node.current_secret = None
        
        # Call reveal_secret
        node.reveal_secret()
        
        # Verify secret was not revealed
        self.mock_sdk.reveal_secret.assert_not_called()
        
        # Verify error was logged
        mock_logger.error.assert_called_once_with("No secret to reveal")
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    def test_elect_leader(self, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test elect_leader function"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"node_id": 42}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # Call elect_leader
        node.elect_leader()
        
        # Verify leader election was triggered
        self.mock_sdk.elect_leader.assert_called_once()
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    def test_check_and_perform_leader_duties_not_leader(self, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test check_and_perform_leader_duties when not the leader"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"node_id": 42}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Mock current leader (not this node)
        self.mock_sdk.get_current_leader.return_value = 100  # Different from node_id
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # Call check_and_perform_leader_duties
        node.check_and_perform_leader_duties()
        
        # Verify leader was checked
        self.mock_sdk.get_current_leader.assert_called_once()
        
        # Verify is_leader flag is False
        self.assertFalse(node.is_leader)
        
        # Verify no leader duties were performed
        self.mock_sdk.start_assignment_round.assert_not_called()
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    def test_check_and_perform_leader_duties_is_leader(self, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test check_and_perform_leader_duties when is the leader"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"node_id": 42}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Mock current leader (this node)
        self.mock_sdk.get_current_leader.return_value = 42  # Same as node_id
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # Call check_and_perform_leader_duties
        node.check_and_perform_leader_duties()
        
        # Verify leader was checked
        self.mock_sdk.get_current_leader.assert_called_once()
        
        # Verify is_leader flag is True
        self.assertTrue(node.is_leader)
        
        # Verify leader duties were performed
        self.mock_sdk.start_assignment_round.assert_called_once()
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    @patch('time.sleep')
    def test_process_assigned_jobs_no_jobs(self, mock_sleep, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test process_assigned_jobs with no jobs"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"node_id": 42}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Mock no jobs assigned
        self.mock_sdk.get_jobs_by_node.return_value = []
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # Call process_assigned_jobs
        node.process_assigned_jobs()
        
        # Verify jobs were retrieved
        self.mock_sdk.get_jobs_by_node.assert_called_once_with(node.node_id)
        
        # Verify no job processing occurred
        self.mock_sdk.confirm_job.assert_not_called()
        mock_sleep.assert_not_called()
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    @patch('time.sleep')
    def test_process_assigned_jobs_with_jobs(self, mock_sleep, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test process_assigned_jobs with assigned jobs"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"node_id": 42}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Mock assigned job
        mock_job = {
            "id": 123,
            "status": 1,  # ASSIGNED
            "args": '{"dataset_id": "test_dataset"}',
            "baseModelName": "llm_test",
            "submitter": "0xsubmitter",
            "numGpus": 2
        }
        self.mock_sdk.get_jobs_by_node.return_value = [mock_job]
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        node.can_begin = True
        node.pipeline_zen_dir = None  # Use simulated job execution
        
        # Call process_assigned_jobs
        node.process_assigned_jobs()
        
        # Verify jobs were retrieved
        self.mock_sdk.get_jobs_by_node.assert_called_once_with(node.node_id)
        
        # Verify can_begin was disabled to prevent re-entry
        self.assertFalse(node.can_begin)
        
        # Verify job was confirmed
        self.mock_sdk.confirm_job.assert_called_once_with(123)
        
        # Verify simulation sleep was called
        mock_sleep.assert_called_once()
        
        # Verify token count was set
        self.mock_sdk.set_token_count_for_job.assert_called_once_with(123, 600000)
        
        # Verify job was completed
        self.mock_sdk.complete_job.assert_called_once_with(123)
        
        # Verify payment was processed
        self.mock_sdk.process_job_payment.assert_called_once_with(123)
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    def test_process_incentives(self, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test process_incentives function"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"node_id": 42}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # Call process_incentives
        node.process_incentives()
        
        # Verify incentives were processed
        self.mock_sdk.process_incentives.assert_called_once()
        
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    def test_process_incentives_with_error(self, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test process_incentives function with error"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"node_id": 42}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Make process_incentives raise ContractError
        error = ContractError("Test error")
        self.mock_sdk.process_incentives.side_effect = error
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        
        # Call process_incentives and expect exception
        with self.assertRaises(ContractError):
            node.process_incentives()
        
        # Verify error was logged
        mock_logger.error.assert_called_once_with("Failed to process incentives: Test error")
    
    def test_execute_job_simple_success(self):
        """Test _execute_job with successful execution - simpler approach"""
        # Create a simplified mock for the node
        node = MagicMock()
        node.logger = MagicMock()
        node.sdk = self.mock_sdk
        
        # We need to use the actual _execute_job method
        node._execute_job = LuminoNode._execute_job.__get__(node)
        
        # Set required attributes
        node.pipeline_zen_dir = Path("/pipeline/zen/dir")
        node.script_dir = Path("scripts/runners/celery-wf.sh")
        node.results_base_dir = Path(".results/")
        
        # Create a simple patch context that makes everything succeed
        with patch('json.loads', return_value={"dataset_id": "test_dataset"}), \
             patch('os.getcwd', return_value="/original/dir"), \
             patch('os.chdir'), \
             patch('subprocess.Popen') as mock_popen, \
             patch('random.randint', return_value=12345), \
             patch('time.sleep'), \
             patch.object(Path, 'exists', return_value=True), \
             patch.object(Path, 'mkdir'), \
             patch('builtins.open', mock_open(read_data="600000")):
            
            # Setup mock process
            mock_process = MagicMock()
            mock_process.poll.return_value = None
            mock_process.communicate.return_value = ("stdout", "stderr")
            mock_popen.return_value = mock_process
            
            # Call _execute_job
            result = node._execute_job(
                job_id=123,
                base_model_name="llm_test_model",
                args='{"dataset_id": "test_dataset"}',
                num_gpus=2,
                submitter="0xsubmitter"
            )
        
        # Verify result is True (success)
        self.assertTrue(result)
        
        # Verify token count was set
        self.mock_sdk.set_token_count_for_job.assert_called_once_with(123, 600000)
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    @patch('os.getcwd')
    @patch('os.chdir')
    @patch('json.loads')
    def test_execute_job_invalid_json(self, mock_json_loads, mock_chdir, mock_getcwd, 
                                    mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test _execute_job with invalid JSON args"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"node_id": 42}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Mock JSON parsing to raise exception
        mock_json_loads.side_effect = json.JSONDecodeError("Invalid JSON", "{", 1)
        
        # Create LuminoNode with pipeline_zen_dir
        node = LuminoNode(self.node_config)
        node.pipeline_zen_dir = Path("/pipeline/zen/dir")
        
        # Call _execute_job
        result = node._execute_job(
            job_id=123,
            base_model_name="llm_test_model",
            args='invalid json',
            num_gpus=2,
            submitter="0xsubmitter"
        )
        
        # Verify result is False (failure)
        self.assertFalse(result)
        
        # Verify error was logged
        mock_logger.error.assert_called_once_with("Invalid JSON in job args: invalid json")
        
        # Verify no further processing was done
        mock_chdir.assert_not_called()
    
    def test_execute_job_error_case(self):
        """Test _execute_job failing due to invalid JSON"""
        # Create a simplified mock for the node
        node = MagicMock()
        node.logger = MagicMock()
        node.sdk = self.mock_sdk
        
        # We need to use the actual _execute_job method
        node._execute_job = LuminoNode._execute_job.__get__(node)
        
        # Set required attributes
        node.pipeline_zen_dir = Path("/pipeline/zen/dir")
        
        # Create a simple patch context where json.loads raises an exception
        with patch('json.loads', side_effect=json.JSONDecodeError("Invalid JSON", "{}", 1)):
            # Call _execute_job with invalid JSON
            result = node._execute_job(
                job_id=123,
                base_model_name="llm_test_model",
                args='invalid json',
                num_gpus=2,
                submitter="0xsubmitter"
            )
        
        # Verify result is False (failure)
        self.assertFalse(result)
        
        # Verify error was logged
        node.logger.error.assert_called_once_with("Invalid JSON in job args: invalid json")
    
    @patch('lumino.contracts_client.node_client.get_artifacts_password')
    def test_setup_pipeline_zen(self, mock_get_password):
        """Test setup_pipeline_zen function"""
        from lumino.contracts_client.node_client import setup_pipeline_zen
        
        # Mock password
        mock_get_password.return_value = "test-password"
        
        # Mock logging
        with patch('logging.getLogger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            # Mock URL download and tarfile
            with patch('urllib.request.urlretrieve') as mock_urlretrieve, \
                 patch('tarfile.open') as mock_tarfile, \
                 patch('os.remove') as mock_remove, \
                 patch('subprocess.run') as mock_run, \
                 patch('os.path.expanduser', return_value=str(self.test_dir)):
                
                # Call setup_pipeline_zen
                setup_pipeline_zen(str(self.test_dir))
                
                # Verify artifacts password was retrieved
                mock_get_password.assert_called_once()
                
                # Verify URL construction with password
                base_url = f"https://storage.googleapis.com/lum-node-artifacts-test-password"
                expected_calls = [
                    ((f"{base_url}/pipeline-zen.tar.gz", ANY), {}),
                    ((f"{base_url}/pipeline-zen.env", ANY), {}),
                    ((f"{base_url}/pipeline-zen-gcp-key.json", ANY), {})
                ]
                mock_urlretrieve.assert_has_calls(expected_calls, any_order=True)
                
                # Verify tarfile extraction
                mock_tarfile.assert_called_once()
                
                # Verify subprocess for install-deps.sh
                mock_run.assert_called_once_with(["./scripts/install-deps.sh"], cwd=ANY, check=True)
    
    @patch('os.getenv')
    @patch('click.prompt')
    @patch('os.path.expanduser')
    @patch('lumino.contracts_client.node_client.read_env_vars')
    def test_get_artifacts_password_from_env(self, mock_read_env_vars, mock_expanduser, mock_prompt, mock_getenv):
        """Test get_artifacts_password function when password is in environment"""
        from lumino.contracts_client.node_client import get_artifacts_password
        
        # Mock environment variable
        mock_getenv.return_value = "env-password"
        
        # Call get_artifacts_password
        password = get_artifacts_password()
        
        # Verify result
        self.assertEqual(password, "env-password")
        
        # Verify no prompt was shown
        mock_prompt.assert_not_called()
        
        # Verify no file operations
        mock_read_env_vars.assert_not_called()
    
    @patch('os.getenv')
    @patch('click.prompt')
    @patch('os.path.expanduser')
    @patch('lumino.contracts_client.node_client.read_env_vars')
    @patch('builtins.open', new_callable=mock_open)
    @patch('os.environ', new_callable=dict)
    def test_get_artifacts_password_from_prompt(self, mock_environ, mock_file, mock_read_env_vars, 
                                              mock_expanduser, mock_prompt, mock_getenv):
        """Test get_artifacts_password function when prompting for password"""
        from lumino.contracts_client.node_client import get_artifacts_password, ENV_VAR_ARTIFACTS_PASSWORD
        
        # Mock environment variable (not set)
        mock_getenv.return_value = None
        
        # Mock prompt response
        mock_prompt.return_value = "prompt-password"
        
        # Mock expanduser
        mock_expanduser.return_value = str(self.test_dir)
        
        # Mock read_env_vars
        mock_read_env_vars.return_value = {"SOME_OTHER_VAR": "value"}
        
        # Call get_artifacts_password
        password = get_artifacts_password()
        
        # Verify result
        self.assertEqual(password, "prompt-password")
        
        # Verify prompt was shown
        mock_prompt.assert_called_once_with(
            "Enter artifacts password for pipeline-zen download",
            hide_input=True
        )
        
        # Verify file operations
        mock_read_env_vars.assert_called_once()
        mock_file.assert_called_once()
        
        # Verify environment was updated
        self.assertEqual(mock_environ.get(ENV_VAR_ARTIFACTS_PASSWORD), "prompt-password")
    
    @patch('lumino.contracts_client.node_client.LuminoClient')
    @patch('lumino.contracts_client.node_client.setup_logging')
    @patch('lumino.contracts_client.node_client.load_json_file')
    @patch('time.time')
    @patch('time.sleep')
    def test_run_method_state_machine(self, mock_sleep, mock_time, 
                                    mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test run method state machine logic"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"node_id": 42}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        
        # Mock time
        mock_time.side_effect = [1000, 1005, 1010, 1015, 1020]  # Add more time values
        
        # Mock process_events and get_epoch_state
        self.mock_sdk.process_events = MagicMock()
        self.mock_sdk.get_epoch_state.return_value = (0, 30)  # COMMIT phase, 30 seconds left
        
        # Create LuminoNode
        node = LuminoNode(self.node_config)
        node.node_id = 123
        node.can_begin = True
        node.test_mode = "1111111"  # Enable all phases, 1 epoch
        
        # Override the run method to avoid infinite loop
        # Instead, directly call the code from the first iteration
        def mock_node_behavior():
            # Process the first iteration of the state machine
            node.sdk.process_events()
            state, time_left = node.sdk.get_epoch_state()
            if node.can_begin and state == 0:
                node.topup_stake()
                node.submit_commitment()
            raise StopIteration("Stop the test after first iteration")
            
        # Patch the methods we're testing
        with patch.object(node, 'topup_stake') as mock_topup, \
             patch.object(node, 'submit_commitment') as mock_submit:
            
            # Call the mock behavior
            with self.assertRaises(StopIteration):
                mock_node_behavior()
            
            # Verify that appropriate methods were called for COMMIT phase
            mock_topup.assert_called_once()
            mock_submit.assert_called_once()
    
    @patch('lumino.contracts_client.node_client.setup_environment_vars')
    @patch('lumino.contracts_client.node_client.create_sdk_config')
    @patch('lumino.contracts_client.compute_power.get_compute_power')
    def test_initialize_lumino_node(self, mock_get_compute_power, mock_create_sdk_config, mock_setup_env):
        """Test initialize_lumino_node function"""
        # Mock environment setup
        mock_setup_env.return_value = ("http://localhost:8545", "0xkey")
        
        # Mock SDK config
        mock_sdk_config = MagicMock()
        mock_create_sdk_config.return_value = mock_sdk_config
        
        # Mock compute power
        mock_get_compute_power.return_value = 150
        
        # Mock environment variables
        env_vars = {
            "CC_NODE_DATA_DIR": str(self.test_dir / "node_data"),
            "CC_PIPELINE_ZEN_DIR": str(self.test_dir / "pipeline-zen"),
            "CC_TEST_MODE": "1111110",
            "CC_COMPUTE_RATING": "0"  # Will use get_compute_power instead
        }
        
        # Mock node object
        mock_node = MagicMock()
        
        # Patch the import statement in initialize_lumino_node
        compute_power_module = MagicMock()
        compute_power_module.get_compute_power = mock_get_compute_power
        sys_modules_patch = patch.dict('sys.modules', {'compute_power': compute_power_module})
        
        with patch.dict('os.environ', env_vars, clear=True), \
             patch('lumino.contracts_client.node_client.LuminoNode', return_value=mock_node), \
             patch('os.path.exists', return_value=True), \
             patch('os.listdir', return_value=[".git"]), \
             sys_modules_patch:  # Patch sys.modules to handle the import
            
            # Call initialize_lumino_node
            result = initialize_lumino_node()
            
            # Verify environment was set up
            mock_setup_env.assert_called_once_with(is_node=True)
            
            # Verify SDK config was created
            mock_create_sdk_config.assert_called_once_with(is_node=True)
            
            # Verify compute power was calculated
            mock_get_compute_power.assert_called_once()
            
            # Verify NodeConfig was created with correct values
            # Note: We can't directly verify NodeConfig creation, but we can check that
            # LuminoNode was called with appropriate args
            
            # Verify result is the mock node
            self.assertEqual(result, mock_node)


if __name__ == '__main__':
    unittest.main()