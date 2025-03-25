import unittest
from unittest.mock import MagicMock, patch

from web3.exceptions import ContractLogicError

from lumino.contracts_client.error_handler import ErrorHandler


class TestErrorHandler(unittest.TestCase):
    """Tests for error_handler.py error decoding functionality"""

    def setUp(self):
        self.error_handler = ErrorHandler()

    def test_error_selectors_initialization(self):
        """Test that error selectors are properly initialized"""
        # Verify we have the expected number of error selectors (should match error_defs)
        self.assertEqual(len(self.error_handler.error_selectors), len(self.error_handler.error_defs))
        
        # Verify error signatures are correctly converted to selectors
        # Example: signature "NotWhitelisted(address)" becomes a specific selector 
        for selector, (error_name, error_def) in self.error_handler.error_selectors.items():
            self.assertIsInstance(selector, str)
            self.assertIsInstance(error_name, str)
            self.assertIn("params", error_def)
            self.assertIn("format", error_def)

    def test_decode_error_without_parameters(self):
        """Test decoding an error that has no parameters"""
        # Mock the error data for "TransferFailed" which has no parameters
        transfer_failed_selector = None
        for selector, (name, _) in self.error_handler.error_selectors.items():
            if name == "TransferFailed":
                transfer_failed_selector = selector
                break
        
        self.assertIsNotNone(transfer_failed_selector, "TransferFailed selector not found")
        
        # Create error data with just the selector
        error_data = f"0x{transfer_failed_selector}"
        
        # Decode the error
        result = self.error_handler.decode_error(error_data)
        
        # Verify the result
        self.assertEqual(result, "Token transfer failed")

    def test_decode_error_with_parameters(self):
        """Test decoding an error with parameters"""
        # Since we can't easily construct a valid error with parameters,
        # we'll mock the decode method to return known values
        with patch('lumino.contracts_client.error_handler.decode') as mock_decode:
            # Set up the mock to return address value
            mock_decode.return_value = ["0x1234567890123456789012345678901234567890"]
            
            # Find the NotWhitelisted error selector
            not_whitelisted_selector = None
            for selector, (name, _) in self.error_handler.error_selectors.items():
                if name == "NotWhitelisted":
                    not_whitelisted_selector = selector
                    break
            
            self.assertIsNotNone(not_whitelisted_selector, "NotWhitelisted selector not found")
            
            # Create error data with selector and some parameter data
            error_data = f"0x{not_whitelisted_selector}1234567890"
            
            # Decode the error
            result = self.error_handler.decode_error(error_data)
            
            # Verify the result format includes the address
            self.assertIn("0x1234567890123456789012345678901234567890", result)
            self.assertIn("not whitelisted", result.lower())

    def test_decode_contract_error(self):
        """Test decoding a ContractLogicError instance"""
        # Create a ContractLogicError mock
        mock_error = MagicMock(spec=ContractLogicError)
        mock_error.data = "0xabcdef"  # Some dummy data
        
        # Mock decode_error to return a known value
        with patch.object(self.error_handler, 'decode_error', return_value="Mocked error message") as mock_decode:
            result = self.error_handler.decode_contract_error(mock_error)
            mock_decode.assert_called_once_with("0xabcdef")
            self.assertEqual(result, "Mocked error message")
    
    def test_decode_error_unknown_selector(self):
        """Test handling of unknown error selectors"""
        # Use an error selector that doesn't exist
        unknown_selector = "deadbeef"
        error_data = f"0x{unknown_selector}"
        
        result = self.error_handler.decode_error(error_data)
        
        # Should return a message about unknown selector
        self.assertIn("Unknown error selector", result)
        self.assertIn(unknown_selector, result)
    
    def test_decode_error_exception_handling(self):
        """Test error handling when an exception occurs during decoding"""
        # We need to patch the selector lookup to return a valid selector
        # and then force the decode to fail
        selector = "abcdef12"
        
        # Create a mock error definition
        error_name = "TestError"
        error_def = {"params": ["address"], "format": lambda args: f"Formatted: {args[0]}"}
        
        # Patch the error_selectors dict to include our test selector
        with patch.dict(self.error_handler.error_selectors, {selector: (error_name, error_def)}):
            # Force an exception during decoding
            with patch('lumino.contracts_client.error_handler.decode', side_effect=Exception("Test exception")):
                error_data = f"0x{selector}1234"  # Use our selector
                
                # Should handle the exception and return an error message
                result = self.error_handler.decode_error(error_data)
                self.assertIn("Error decoding custom error", result)
                self.assertIn("Test exception", result)


if __name__ == '__main__':
    unittest.main()