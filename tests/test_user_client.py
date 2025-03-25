import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open, ANY

from web3 import Web3

from lumino.contracts_client.client import LuminoConfig
from lumino.contracts_client.user_client import UserConfig, LuminoUser, initialize_lumino_user


class TestUserClient(unittest.TestCase):
    """Tests for user_client.py functionality"""

    def setUp(self):
        """Set up test environment before each test"""
        # Create a temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)
        
        # Create basic directory structure
        self.data_dir = self.test_dir / "user_data"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Sample contract addresses
        self.contract_addresses = {
            "AccessManager": "0x1111",
            "WhitelistManager": "0x2222",
            "LuminoToken": "0x3333",
            "NodeManager": "0x4444",
            "JobManager": "0x5555",
            "NodeEscrow": "0x6666",
            "JobEscrow": "0x7777"
        }
        
        # Sample config
        self.sdk_config = LuminoConfig(
            web3_provider="http://localhost:8545",
            private_key="0x" + "0123456789" * 4,
            contract_addresses=self.contract_addresses,
            abis_dir=str(self.test_dir / "abis")
        )
        
        self.user_config = UserConfig(
            sdk_config=self.sdk_config,
            data_dir=str(self.data_dir),
            log_level=20,  # INFO
            polling_interval=5
        )
        
        # Mock Lumino SDK
        self.mock_sdk = MagicMock()
        self.mock_sdk.address = "0x1234567890abcdef"
        
        # Add contract mocks
        self.mock_sdk.job_manager = MagicMock()
        self.mock_sdk.job_escrow = MagicMock()
        self.mock_sdk.token = MagicMock()
        
        # Mock job submission event
        self.mock_job_submitted_event = MagicMock()
        self.mock_sdk.job_manager.events.JobSubmitted.return_value = self.mock_job_submitted_event

    def tearDown(self):
        """Clean up after each test"""
        self.temp_dir.cleanup()
    
    @patch('lumino.contracts_client.user_client.LuminoClient')
    @patch('lumino.contracts_client.user_client.setup_logging')
    @patch('lumino.contracts_client.user_client.load_json_file')
    @patch('lumino.contracts_client.user_client.check_and_create_dir')
    def test_initialization(self, mock_check_dir, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test LuminoUser initialization"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"job_ids": [1, 2, 3]}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        mock_check_dir.return_value = self.data_dir
        
        # Create LuminoUser
        user = LuminoUser(self.user_config)
        
        # Verify directory was checked
        mock_check_dir.assert_called_once_with(self.user_config.data_dir)
        
        # Verify logger was initialized
        mock_setup_logging.assert_called_once_with(
            "LuminoUserClient", ANY, self.user_config.log_level
        )
        
        # Verify SDK was initialized
        mock_lumino_client.assert_called_once_with(self.user_config.sdk_config, mock_logger)
        
        # Verify user data was loaded
        mock_load_json.assert_called_once_with(ANY, {"job_ids": []})
        
        # Verify initial state
        self.assertEqual(user.address, self.mock_sdk.address)
        self.assertEqual(user.job_ids, [1, 2, 3])
        self.assertEqual(user.polling_interval, self.user_config.polling_interval)
        
        # Verify SDK event filters were set up
        self.mock_sdk.setup_event_filters.assert_called_once()
    
    @patch('lumino.contracts_client.user_client.LuminoClient')
    @patch('lumino.contracts_client.user_client.setup_logging')
    @patch('lumino.contracts_client.user_client.load_json_file')
    @patch('lumino.contracts_client.user_client.save_json_file')
    @patch('lumino.contracts_client.user_client.check_and_create_dir')
    def test_save_user_data(self, mock_check_dir, mock_save_json, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test save_user_data method"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"job_ids": [1, 2, 3]}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        mock_check_dir.return_value = self.data_dir
        
        # Create LuminoUser
        user = LuminoUser(self.user_config)
        
        # Call save_user_data
        user.save_user_data()
        
        # Verify data was saved
        mock_save_json.assert_called_once_with(user.user_data_file, {"job_ids": [1, 2, 3]})
    
    @patch('lumino.contracts_client.user_client.LuminoClient')
    @patch('lumino.contracts_client.user_client.setup_logging')
    @patch('lumino.contracts_client.user_client.load_json_file')
    @patch('lumino.contracts_client.user_client.check_and_create_dir')
    def test_add_funds_to_escrow(self, mock_check_dir, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test adding funds to escrow"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"job_ids": []}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        mock_check_dir.return_value = self.data_dir
        
        # Create LuminoUser
        user = LuminoUser(self.user_config)
        
        # Call add_funds_to_escrow
        amount = 10.5
        user.add_funds_to_escrow(amount)
        
        # Verify token spending was approved
        amount_wei = Web3.to_wei(amount, 'ether')
        self.mock_sdk.approve_token_spending.assert_called_once_with(
            self.mock_sdk.job_escrow.address,
            amount_wei
        )
        
        # Verify funds were deposited
        self.mock_sdk.deposit_job_funds.assert_called_once_with(amount_wei)
    
    @patch('lumino.contracts_client.user_client.LuminoClient')
    @patch('lumino.contracts_client.user_client.setup_logging')
    @patch('lumino.contracts_client.user_client.load_json_file')
    @patch('lumino.contracts_client.user_client.check_and_create_dir')
    def test_check_balances(self, mock_check_dir, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test checking balances"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"job_ids": []}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        mock_check_dir.return_value = self.data_dir
        
        # Mock token and escrow balances
        token_balance_wei = Web3.to_wei(50, 'ether')
        escrow_balance_wei = Web3.to_wei(20, 'ether')
        self.mock_sdk.get_token_balance.return_value = token_balance_wei
        self.mock_sdk.get_job_escrow_balance.return_value = escrow_balance_wei
        
        # Create LuminoUser
        user = LuminoUser(self.user_config)
        
        # Call check_balances
        balances = user.check_balances()
        
        # Verify balances were retrieved
        self.mock_sdk.get_token_balance.assert_called_once_with(user.address)
        self.mock_sdk.get_job_escrow_balance.assert_called_once_with(user.address)
        
        # Verify returned balances
        self.assertEqual(balances["token_balance"], 50.0)
        self.assertEqual(balances["escrow_balance"], 20.0)
    
    @patch('lumino.contracts_client.user_client.LuminoClient')
    @patch('lumino.contracts_client.user_client.setup_logging')
    @patch('lumino.contracts_client.user_client.load_json_file')
    @patch('lumino.contracts_client.user_client.save_json_file')
    @patch('lumino.contracts_client.user_client.check_and_create_dir')
    def test_submit_job(self, mock_check_dir, mock_save_json, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test submitting a job"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"job_ids": []}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        mock_check_dir.return_value = self.data_dir
        
        # Mock job submission receipt and event
        mock_receipt = {"logs": [{"topics": ["event_topic"]}]}
        self.mock_sdk.submit_job.return_value = mock_receipt
        
        # Mock event processing
        self.mock_job_submitted_event.process_receipt.return_value = [
            {"args": {"jobId": 42}}
        ]
        
        # Create LuminoUser
        user = LuminoUser(self.user_config)
        
        # Call submit_job
        job_args = '{"dataset_id": "test_dataset"}'
        model_name = "llm_model"
        ft_type = "LORA"
        
        job_id = user.submit_job(job_args, model_name, ft_type)
        
        # Verify job was submitted
        self.mock_sdk.submit_job.assert_called_once_with(job_args, model_name, ft_type)
        
        # Verify event was processed
        self.mock_job_submitted_event.process_receipt.assert_called_once_with(mock_receipt)
        
        # Verify job_id was returned and saved
        self.assertEqual(job_id, 42)
        self.assertEqual(user.job_ids, [42])
        self.assertEqual(user.user_data["job_ids"], [42])
        
        # Verify data was saved
        mock_save_json.assert_called_once()
    
    @patch('lumino.contracts_client.user_client.LuminoClient')
    @patch('lumino.contracts_client.user_client.setup_logging')
    @patch('lumino.contracts_client.user_client.load_json_file')
    @patch('lumino.contracts_client.user_client.check_and_create_dir')
    def test_monitor_job_progress(self, mock_check_dir, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test monitoring job progress"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"job_ids": [42]}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        mock_check_dir.return_value = self.data_dir
        
        # Mock job status and assigned node
        self.mock_sdk.get_job_status.return_value = 2  # CONFIRMED
        self.mock_sdk.get_assigned_node.return_value = 99
        
        # Create LuminoUser
        user = LuminoUser(self.user_config)
        
        # Call monitor_job_progress
        status, node = user.monitor_job_progress(42)
        
        # Verify status and node were retrieved
        self.mock_sdk.get_job_status.assert_called_once_with(42)
        self.mock_sdk.get_assigned_node.assert_called_once_with(42)
        
        # Verify returned values
        self.assertEqual(status, "CONFIRMED")
        self.assertEqual(node, 99)
    
    @patch('lumino.contracts_client.user_client.LuminoClient')
    @patch('lumino.contracts_client.user_client.setup_logging')
    @patch('lumino.contracts_client.user_client.load_json_file')
    @patch('lumino.contracts_client.user_client.save_json_file')
    @patch('lumino.contracts_client.user_client.check_and_create_dir')
    def test_list_jobs(self, mock_check_dir, mock_save_json, mock_load_json, mock_setup_logging, mock_lumino_client):
        """Test listing jobs"""
        # Set up mocks
        mock_lumino_client.return_value = self.mock_sdk
        mock_load_json.return_value = {"job_ids": [1, 2]}
        mock_logger = MagicMock()
        mock_setup_logging.return_value = mock_logger
        mock_check_dir.return_value = self.data_dir
        
        # Mock jobs by submitter
        self.mock_sdk.get_jobs_by_submitter.return_value = [1, 2, 3]
        
        # Mock job details
        job1 = (1, "0xsubmitter", 99, 1, 2, '{"test": 1}', "llm_model1", "LORA", 1234567890)  # ASSIGNED
        job2 = (2, "0xsubmitter", 88, 2, 2, '{"test": 2}', "llm_model2", "QLORA", 1234567891)  # CONFIRMED
        job3 = (3, "0xsubmitter", 77, 3, 2, '{"test": 3}', "llm_model3", "LORA", 1234567892)  # COMPLETE
        
        self.mock_sdk.get_job_details.side_effect = [job1, job2, job3]
        
        # Create LuminoUser
        user = LuminoUser(self.user_config)
        
        # Call list_jobs (all jobs)
        jobs = user.list_jobs()
        
        # Verify jobs were retrieved
        self.mock_sdk.get_jobs_by_submitter.assert_called_once_with(user.address)
        self.assertEqual(self.mock_sdk.get_job_details.call_count, 3)
        
        # Verify job_ids were updated and saved
        self.assertEqual(user.job_ids, [1, 2, 3])
        self.assertEqual(user.user_data["job_ids"], [1, 2, 3])
        mock_save_json.assert_called_once()
        
        # Verify returned jobs list
        self.assertEqual(len(jobs), 3)
        self.assertEqual(jobs[0]["job_id"], 1)
        self.assertEqual(jobs[0]["status"], "ASSIGNED")
        self.assertEqual(jobs[0]["assigned_node"], 99)
        self.assertEqual(jobs[0]["model_name"], "llm_model1")
        
        self.assertEqual(jobs[2]["job_id"], 3)
        self.assertEqual(jobs[2]["status"], "COMPLETE")
        
        # Reset mocks
        mock_save_json.reset_mock()
        self.mock_sdk.get_job_details.reset_mock()
        self.mock_sdk.get_job_details.side_effect = [job1, job2, job3]
        
        # Call list_jobs (only active jobs)
        jobs = user.list_jobs(only_active=True)
        
        # Verify only active jobs were returned
        self.assertEqual(len(jobs), 2)  # Only jobs 1 and 2 are active (not COMPLETE)
        job_ids = [job["job_id"] for job in jobs]
        self.assertIn(1, job_ids)
        self.assertIn(2, job_ids)
        self.assertNotIn(3, job_ids)
    
    @patch('lumino.contracts_client.user_client.setup_environment_vars')
    @patch('lumino.contracts_client.user_client.create_sdk_config')
    def test_initialize_lumino_user(self, mock_create_sdk_config, mock_setup_env):
        """Test initialize_lumino_user function"""
        # Mock environment setup
        mock_setup_env.return_value = ("http://localhost:8545", "0xkey")
        
        # Mock SDK config
        mock_sdk_config = MagicMock()
        mock_create_sdk_config.return_value = mock_sdk_config
        
        # Mock environment variables
        env_vars = {
            "CC_USER_DATA_DIR": str(self.test_dir / "user_data")
        }
        
        # Mock user object
        mock_user = MagicMock()
        
        with patch.dict('os.environ', env_vars, clear=True), \
             patch('lumino.contracts_client.user_client.LuminoUser', return_value=mock_user):
            
            # Call initialize_lumino_user
            result = initialize_lumino_user()
            
            # Verify environment was set up
            mock_setup_env.assert_called_once_with(is_node=False)
            
            # Verify SDK config was created
            mock_create_sdk_config.assert_called_once_with(is_node=False)
            
            # Verify LuminoUser was created with correct config
            
            # Verify result is the mock user
            self.assertEqual(result, mock_user)


if __name__ == '__main__':
    unittest.main()