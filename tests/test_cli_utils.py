import unittest
from unittest.mock import patch, MagicMock

from click.testing import CliRunner

from lumino.contracts_client.cli_utils import CLIUtils


class TestCLIUtils(unittest.TestCase):
    """Tests for cli_utils.py CLI utility functions"""

    def setUp(self):
        """Set up test environment before each test"""
        self.runner = CliRunner()
        
        # Mock functions for interactive_topup
        self.mock_check_balances = MagicMock(return_value={
            "token_balance": 100.0,
            "escrow_balance": 15.0
        })
        
        self.mock_add_funds = MagicMock()
        
        # Default min balance
        self.min_balance = 20.0
        
        # Default auto-topup config
        self.default_auto_topup = {
            "enabled": False,
            "amount": self.min_balance,
            "auto_yes_min": False,
            "auto_yes_additional": 0.0
        }

    def test_interactive_topup_default_config(self):
        """Test interactive_topup creates default config when None is provided"""
        # Call with None auto_topup_config
        with patch('click.echo'), patch('click.confirm', return_value=False):
            result = CLIUtils.interactive_topup(
                self.mock_check_balances,
                self.mock_add_funds,
                self.min_balance,
                None
            )
        
        # Verify default config was created
        self.assertEqual(result["enabled"], False)
        self.assertEqual(result["amount"], self.min_balance)
        self.assertEqual(result["auto_yes_min"], False)
        self.assertEqual(result["auto_yes_additional"], 0.0)

    def test_interactive_topup_no_deficit(self):
        """Test interactive_topup when balance is sufficient"""
        # Change mock to return sufficient balance
        self.mock_check_balances.return_value = {
            "token_balance": 100.0,
            "escrow_balance": 25.0  # Above min_balance
        }
        
        # Call interactive_topup with all prompts declined
        with patch('click.echo'), patch('click.confirm', return_value=False):
            result = CLIUtils.interactive_topup(
                self.mock_check_balances,
                self.mock_add_funds,
                self.min_balance,
                self.default_auto_topup
            )
        
        # Verify add_funds was not called
        self.mock_add_funds.assert_not_called()
        
        # Verify config is unchanged
        self.assertEqual(result, self.default_auto_topup)

    def test_interactive_topup_with_deficit(self):
        """Test interactive_topup when balance is below minimum"""
        # Using default mock with deficit of 5.0
        
        # User confirms topup but declines additional amount
        with patch('click.echo'), \
             patch('click.confirm', side_effect=[True, False]), \
             patch('click.prompt', return_value=0.0):
            
            result = CLIUtils.interactive_topup(
                self.mock_check_balances,
                self.mock_add_funds,
                self.min_balance,
                self.default_auto_topup
            )
        
        # Verify add_funds was called with correct amount (just the deficit)
        deficit = self.min_balance - 15.0  # 5.0
        self.mock_add_funds.assert_called_once_with(deficit)
        
        # Verify config is unchanged
        self.assertEqual(result, self.default_auto_topup)

    def test_interactive_topup_with_deficit_and_additional(self):
        """Test interactive_topup when balance is below minimum and user adds additional funds"""
        # Using default mock with deficit of 5.0
        
        # User confirms topup and adds 10.0 additional
        additional = 10.0
        with patch('click.echo'), \
             patch('click.confirm', side_effect=[True, False]), \
             patch('click.prompt', return_value=additional):
            
            result = CLIUtils.interactive_topup(
                self.mock_check_balances,
                self.mock_add_funds,
                self.min_balance,
                self.default_auto_topup
            )
        
        # Verify add_funds was called with correct amount (deficit + additional)
        deficit = self.min_balance - 15.0  # 5.0
        self.mock_add_funds.assert_called_once_with(deficit + additional)
        
        # Verify config is unchanged
        self.assertEqual(result, self.default_auto_topup)

    def test_interactive_topup_insufficient_tokens(self):
        """Test interactive_topup when user has insufficient tokens for requested topup"""
        # Modify the mock to have minimal token balance
        self.mock_check_balances.return_value = {
            "token_balance": 3.0,  # Only 3.0 tokens available
            "escrow_balance": 15.0  # Deficit of 5.0
        }
        
        # User confirms topup and adds 10.0 additional (which is too much)
        additional = 10.0
        with patch('click.echo'), \
             patch('click.confirm', side_effect=[True, False]), \
             patch('click.prompt', return_value=additional):
            
            result = CLIUtils.interactive_topup(
                self.mock_check_balances,
                self.mock_add_funds,
                self.min_balance,
                self.default_auto_topup
            )
        
        # Verify add_funds was not called due to insufficient tokens
        self.mock_add_funds.assert_not_called()
        
        # Verify config is unchanged
        self.assertEqual(result, self.default_auto_topup)

    def test_interactive_topup_enable_auto_topup(self):
        """Test interactive_topup when user enables auto-topup"""
        # Using default mock with deficit of 5.0
        
        # User declines immediate topup but enables auto-topup with auto-yes
        # and 15.0 additional amount
        additional = 15.0
        
        # We need three True/False values for click.confirm: 
        # 1. Would you like to top up? (No)
        # 2. Would you like to configure auto-topup? (Yes)
        # 3. Enable auto-topup? (Yes)
        # 4. Automatically top up without asking? (Yes)
        with patch('click.echo'), \
             patch('click.confirm', side_effect=[False, True, True, True]), \
             patch('click.prompt', return_value=additional):
            
            result = CLIUtils.interactive_topup(
                self.mock_check_balances,
                self.mock_add_funds,
                self.min_balance,
                self.default_auto_topup
            )
        
        # Verify add_funds was not called
        self.mock_add_funds.assert_not_called()
        
        # Verify config is updated
        self.assertEqual(result["enabled"], True)
        self.assertEqual(result["amount"], self.min_balance)
        self.assertEqual(result["auto_yes_min"], True)
        self.assertEqual(result["auto_yes_additional"], additional)

    def test_interactive_topup_disable_auto_topup(self):
        """Test interactive_topup when user disables auto-topup"""
        # Start with enabled auto-topup
        enabled_auto_topup = {
            "enabled": True,
            "amount": self.min_balance,
            "auto_yes_min": True,
            "auto_yes_additional": 10.0
        }
        
        # User declines immediate topup, configures auto-topup, and disables it
        # 1. Would you like to top up? (No)
        # 2. Would you like to configure auto-topup? (Yes)
        # 3. Enable auto-topup? (No)
        with patch('click.echo'), \
             patch('click.confirm', side_effect=[False, True, False]):
            
            result = CLIUtils.interactive_topup(
                self.mock_check_balances,
                self.mock_add_funds,
                self.min_balance,
                enabled_auto_topup
            )
        
        # Verify config is updated to disabled
        self.assertEqual(result["enabled"], False)
        self.assertEqual(result["amount"], self.min_balance)
        self.assertEqual(result["auto_yes_min"], False)
        self.assertEqual(result["auto_yes_additional"], 0.0)


if __name__ == '__main__':
    unittest.main()