import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from lumino.contracts_client.config import setup_environment_vars
from lumino.contracts_client.utils import read_env_vars
from lumino.contracts_client.constants import ENV_VAR_RPC_URL, ENV_VAR_NODE_PRIVATE_KEY, ENV_VAR_USER_PRIVATE_KEY


class TestConfig(unittest.TestCase):
    """Test config and environment variable handling"""

    def setUp(self):
        # Create a temporary .env file for testing
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_file = os.path.join(self.temp_dir.name, '.env')

    def tearDown(self):
        # Clean up temp directory
        self.temp_dir.cleanup()

    @patch.dict('os.environ', {}, clear=True)
    def test_read_env_vars_preserves_all_variables(self):
        """Test that read_env_vars preserves all variables from the env file"""
        # Create a test env file with multiple variables
        with open(self.env_file, 'w') as f:
            f.write(f"{ENV_VAR_RPC_URL}=https://test-rpc.com\n")
            f.write(f"{ENV_VAR_NODE_PRIVATE_KEY}=0xnode1234\n")
            f.write(f"{ENV_VAR_USER_PRIVATE_KEY}=0xuser5678\n")
            f.write("EXTRA_VAR=extravalue\n")

        # Test reading only RPC_URL (with patched empty os.environ)
        result = read_env_vars(self.env_file, {ENV_VAR_RPC_URL: 'RPC URL'})

        # Verify all variables are returned, not just the requested ones
        self.assertEqual(result[ENV_VAR_RPC_URL], 'https://test-rpc.com')
        self.assertEqual(result[ENV_VAR_NODE_PRIVATE_KEY], '0xnode1234')
        self.assertEqual(result[ENV_VAR_USER_PRIVATE_KEY], '0xuser5678')
        self.assertEqual(result['EXTRA_VAR'], 'extravalue')

    @patch('lumino.contracts_client.config.click.prompt')
    def test_setup_environment_vars_doesnt_overwrite_other_keys(self, mock_prompt):
        """Test that setup_environment_vars doesn't overwrite non-requested variables"""
        # Set up return values for mock prompts
        mock_prompt.side_effect = ['https://new-rpc.com', '0xnewnode9876']

        # Create a test env file with multiple variables
        with open(self.env_file, 'w') as f:
            f.write(f"{ENV_VAR_USER_PRIVATE_KEY}=0xuser5678\n")
            f.write("EXTRA_VAR=extravalue\n")

        # Mock environment and call setup_environment_vars for node client
        with patch('lumino.contracts_client.config.os') as mock_os:
            # Set up os.path.* calls
            mock_os.path.expanduser.return_value = self.temp_dir.name
            mock_os.path.join.return_value = self.env_file
            mock_os.path.exists.return_value = True
            
            # Set up os.environ and os.getenv
            mock_env = {}
            mock_os.environ = mock_env
            mock_os.getenv.side_effect = lambda key, default=None: mock_env.get(key, default)
            mock_os.makedirs.return_value = None
            
            # Call the function for node client
            with patch('lumino.contracts_client.config.load_dotenv'):
                setup_environment_vars(is_node=True)

        # Read the updated env file directly
        with open(self.env_file, 'r') as f:
            content = f.read()

        # Verify all variables are preserved
        self.assertIn(f"{ENV_VAR_RPC_URL}=https://new-rpc.com", content)
        self.assertIn(f"{ENV_VAR_NODE_PRIVATE_KEY}=0xnewnode9876", content)
        self.assertIn(f"{ENV_VAR_USER_PRIVATE_KEY}=0xuser5678", content)
        self.assertIn("EXTRA_VAR=extravalue", content)


if __name__ == '__main__':
    unittest.main()
