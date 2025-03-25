import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from lumino.contracts_client.utils import (
    setup_logging,
    load_json_file,
    save_json_file,
    check_and_create_dir,
    read_env_vars
)


class TestUtils(unittest.TestCase):
    """Tests for utils.py utility functions"""

    def setUp(self):
        """Set up test environment before each test"""
        # Create temporary directory for test files
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up after each test"""
        self.temp_dir.cleanup()

    def test_setup_logging(self):
        """Test the setup_logging function"""
        log_file_path = self.test_dir / "test.log"
        
        # Mock logger to avoid actual logging
        with patch('logging.getLogger') as mock_get_logger:
            mock_logger = MagicMock()
            mock_get_logger.return_value = mock_logger
            
            # Call setup_logging
            result = setup_logging("TestLogger", str(log_file_path))
            
            # Verify getLogger was called with correct name
            mock_get_logger.assert_called_once_with("TestLogger")
            
            # Verify log level was set
            mock_logger.setLevel.assert_called_once()
            
            # Verify handlers were cleared and added
            mock_logger.handlers.clear.assert_called_once()
            self.assertEqual(mock_logger.addHandler.call_count, 2)  # Console and file handlers
            
            # Verify result is the logger
            self.assertEqual(result, mock_logger)
            
        # Verify log directory was created
        self.assertTrue(log_file_path.parent.exists())

    def test_load_json_file_existing(self):
        """Test loading an existing JSON file"""
        # Create a test JSON file
        test_data = {"key1": "value1", "key2": 123}
        test_file = self.test_dir / "test.json"
        
        with open(test_file, 'w') as f:
            json.dump(test_data, f)
        
        # Call load_json_file
        result = load_json_file(str(test_file))
        
        # Verify result matches test data
        self.assertEqual(result, test_data)

    def test_load_json_file_nonexistent(self):
        """Test loading a nonexistent JSON file returns default"""
        # Nonexistent file path
        nonexistent_file = self.test_dir / "nonexistent.json"
        
        # Call load_json_file with default
        default_value = {"default": True}
        result = load_json_file(str(nonexistent_file), default_value)
        
        # Verify result is the default value
        self.assertEqual(result, default_value)

    def test_load_json_file_invalid_json(self):
        """Test loading an invalid JSON file returns default"""
        # Create an invalid JSON file
        invalid_file = self.test_dir / "invalid.json"
        
        with open(invalid_file, 'w') as f:
            f.write("This is not valid JSON")
        
        # Call load_json_file with default
        default_value = {"default": True}
        result = load_json_file(str(invalid_file), default_value)
        
        # Verify result is the default value
        self.assertEqual(result, default_value)

    def test_save_json_file(self):
        """Test saving data to a JSON file"""
        # Test data to save
        test_data = {"key1": "value1", "key2": [1, 2, 3], "key3": {"nested": True}}
        test_file = self.test_dir / "save_test.json"
        
        # Call save_json_file
        save_json_file(str(test_file), test_data)
        
        # Verify file exists
        self.assertTrue(test_file.exists())
        
        # Read back the file and verify content
        with open(test_file, 'r') as f:
            saved_data = json.load(f)
        
        self.assertEqual(saved_data, test_data)

    def test_check_and_create_dir(self):
        """Test checking and creating directories"""
        # Test with nonexistent directory
        test_dir = self.test_dir / "new_dir" / "nested_dir"
        
        # Call check_and_create_dir
        with patch('os.path.expanduser', return_value=str(test_dir)):
            result = check_and_create_dir(str(test_dir))
        
        # Verify directory was created
        self.assertTrue(test_dir.exists())
        
        # Verify result is a Path object
        self.assertIsInstance(result, Path)
        self.assertEqual(result, test_dir)
        
        # Test with existing directory
        with patch('os.path.expanduser', return_value=str(test_dir)):
            result2 = check_and_create_dir(str(test_dir))
        
        # Verify result is the same Path
        self.assertEqual(result2, test_dir)

    def test_read_env_vars_existing_file(self):
        """Test reading environment variables from an existing file"""
        # Create a test env file
        env_file = self.test_dir / ".env"
        
        with open(env_file, 'w') as f:
            f.write("KEY1=value1\n")
            f.write("KEY2=value2\n")
            f.write("# This is a comment\n")
            f.write("EMPTY_LINE=\n")
            f.write("INVALID_LINE\n")  # No equals sign
        
        # Call read_env_vars
        required_vars = {"KEY1": "Description 1", "KEY3": "Description 3"}
        
        # Need to patch os.environ for environment variables
        with patch.dict('os.environ', {"KEY3": "value3_from_env"}):
            result = read_env_vars(str(env_file), required_vars)
        
        # Verify all variables were returned
        self.assertEqual(result["KEY1"], "value1")
        self.assertEqual(result["KEY2"], "value2")
        self.assertEqual(result["KEY3"], "value3_from_env")  # From environment
        self.assertEqual(result["EMPTY_LINE"], "")
        
        # Verify missing required vars are included with empty strings
        # KEY3 was in required_vars but not in file, so it's in result from environment

    def test_read_env_vars_nonexistent_file(self):
        """Test reading environment variables from a nonexistent file"""
        # Nonexistent file path
        nonexistent_file = self.test_dir / "nonexistent.env"
        
        # Call read_env_vars
        required_vars = {"KEY1": "Description 1", "KEY2": "Description 2"}
        
        # Need to patch os.environ for environment variables
        with patch.dict('os.environ', {"KEY1": "value1_from_env"}):
            result = read_env_vars(str(nonexistent_file), required_vars)
        
        # Verify required variables are included
        self.assertEqual(result["KEY1"], "value1_from_env")  # From environment
        self.assertEqual(result["KEY2"], "")  # Empty string for missing var


if __name__ == '__main__':
    unittest.main()