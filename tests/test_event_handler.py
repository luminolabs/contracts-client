import logging
import unittest
from unittest.mock import MagicMock, patch

from web3.contract import Contract

from lumino.contracts_client.event_handler import EventHandler


class TestEventHandler(unittest.TestCase):
    """Tests for event_handler.py event monitoring functionality"""

    def setUp(self):
        """Set up test environment before each test"""
        # Create a mock logger
        self.mock_logger = MagicMock(spec=logging.Logger)
        
        # Initialize EventHandler with mock logger
        self.event_handler = EventHandler(self.mock_logger)

    def test_event_handler_initialization(self):
        """Test that EventHandler initializes correctly"""
        # Verify event_filters is empty at initialization
        self.assertEqual(len(self.event_handler.event_filters), 0)
        
        # Verify contract_events is populated
        self.assertGreater(len(self.event_handler.contract_events), 0)
        
        # Check a few specific contracts and events
        self.assertIn('NodeManager', self.event_handler.contract_events)
        self.assertIn('JobManager', self.event_handler.contract_events)
        self.assertIn('WhitelistManager', self.event_handler.contract_events)
        
        # Check specific events
        self.assertIn('NodeRegistered', self.event_handler.contract_events['NodeManager'])
        self.assertIn('JobSubmitted', self.event_handler.contract_events['JobManager'])

    def test_create_event_filter(self):
        """Test creating a single event filter"""
        # Create a mock contract
        mock_contract = MagicMock(spec=Contract)
        mock_contract.address = "0x1234"
        
        # Create a mock event object with create_filter method
        mock_event = MagicMock()
        mock_event.create_filter.return_value = "filter_object"
        
        # Set up the contract.events.EventName attribute
        mock_contract.events.TestEvent = mock_event
        
        # Call create_event_filter
        self.event_handler.create_event_filter(mock_contract, "TestEvent", 100)
        
        # Verify create_filter was called with correct args
        mock_event.create_filter.assert_called_once_with(from_block=100)
        
        # Verify event_filters was updated correctly
        self.assertIn((mock_contract.address, "TestEvent"), self.event_handler.event_filters)
        self.assertEqual(self.event_handler.event_filters[(mock_contract.address, "TestEvent")], "filter_object")
        
        # Verify log message
        self.mock_logger.info.assert_called_once()
        log_msg = self.mock_logger.info.call_args[0][0]
        self.assertIn("TestEvent", log_msg)
        self.assertIn("100", log_msg)

    def test_create_event_filters(self):
        """Test creating multiple event filters"""
        # Create a mock contract
        mock_contract = MagicMock(spec=Contract)
        mock_contract.address = "0x5678"
        
        # Set up event attributes and return values
        event_names = ["Event1", "Event2", "Event3"]
        for event_name in event_names:
            mock_event = MagicMock()
            mock_event.create_filter.return_value = f"{event_name}_filter"
            setattr(mock_contract.events, event_name, mock_event)
        
        # Call _create_event_filters
        self.event_handler._create_event_filters(mock_contract, event_names, 200)
        
        # Verify correct filters were created
        for event_name in event_names:
            self.assertIn((mock_contract.address, event_name), self.event_handler.event_filters)
            self.assertEqual(
                self.event_handler.event_filters[(mock_contract.address, event_name)], 
                f"{event_name}_filter"
            )
        
        # Verify log messages (one for each event)
        self.assertEqual(self.mock_logger.info.call_count, 3)

    def test_setup_event_filters(self):
        """Test setting up filters for all contract events"""
        # Create mock contracts
        contract_dict = {
            'NodeManager': MagicMock(spec=Contract),
            'JobManager': MagicMock(spec=Contract),
            'InvalidContract': MagicMock(spec=Contract)  # Not in contract_events
        }
        
        # Set addresses
        for name, contract in contract_dict.items():
            contract.address = f"0x{name}"
        
        # Set up events for NodeManager
        node_events = self.event_handler.contract_events['NodeManager']
        for event_name in node_events:
            mock_event = MagicMock()
            mock_event.create_filter.return_value = f"{event_name}_filter"
            setattr(contract_dict['NodeManager'].events, event_name, mock_event)
        
        # Set up events for JobManager
        job_events = self.event_handler.contract_events['JobManager']
        for event_name in job_events:
            mock_event = MagicMock()
            mock_event.create_filter.return_value = f"{event_name}_filter"
            setattr(contract_dict['JobManager'].events, event_name, mock_event)
        
        # Call setup_event_filters
        with patch.object(self.event_handler, '_create_event_filters') as mock_create:
            self.event_handler.setup_event_filters(contract_dict, 300)
            
            # Verify _create_event_filters was called for each valid contract
            self.assertEqual(mock_create.call_count, 2)  # Only for NodeManager and JobManager
            
            # Verify it was called with correct arguments
            mock_create.assert_any_call(
                contract_dict['NodeManager'],
                self.event_handler.contract_events['NodeManager'],
                300
            )
            mock_create.assert_any_call(
                contract_dict['JobManager'],
                self.event_handler.contract_events['JobManager'],
                300
            )

    def test_process_events(self):
        """Test processing events from all filters"""
        # Create mock filters
        filter1 = MagicMock()
        filter1.get_new_entries.return_value = [
            {'args': {'key1': 'value1', 'key2': 123}}
        ]
        
        filter2 = MagicMock()
        filter2.get_new_entries.return_value = [
            {'args': {'key3': b'binary_data', 'key4': 456}}
        ]
        
        filter3 = MagicMock()
        filter3.get_new_entries.side_effect = Exception("Filter error")
        
        # Add filters to event_handler
        self.event_handler.event_filters = {
            ('0x1111', 'Event1'): filter1,
            ('0x2222', 'Event2'): filter2,
            ('0x3333', 'Event3'): filter3
        }
        
        # Call process_events
        with patch.object(self.event_handler, '_log_event') as mock_log:
            self.event_handler.process_events()
            
            # Verify _log_event was called for each event
            self.assertEqual(mock_log.call_count, 2)  # Not called for filter3 due to exception
            mock_log.assert_any_call('Event1', {'args': {'key1': 'value1', 'key2': 123}})
            mock_log.assert_any_call('Event2', {'args': {'key3': b'binary_data', 'key4': 456}})
            
            # Verify error was logged for filter3
            self.mock_logger.error.assert_called_once()
            error_msg = self.mock_logger.error.call_args[0][0]
            self.assertIn('Event3', error_msg)
            self.assertIn('Filter error', error_msg)

    def test_log_event(self):
        """Test event logging functionality"""
        # Create test event with different types of arguments
        event = {
            'args': {
                'text': 'Some text',
                'number': 42,
                'binary': b'binary_data',
                'address': '0xabcdef1234567890',
                'amount': 1000000000000000000,  # 1 ETH in wei
                'balance': 2000000000000000000,  # 2 ETH in wei
                'stake': 3000000000000000000,   # 3 ETH in wei
                'otherNumber': 987654321
            }
        }
        
        # Call _log_event
        self.event_handler._log_event('TestEvent', event)
        
        # Verify logger.info was called once
        self.mock_logger.info.assert_called_once()
        
        # Get the log message
        log_msg = self.mock_logger.info.call_args[0][0]
        
        # Verify event name is in the message
        self.assertIn('TestEvent', log_msg)
        
        # Verify all arguments are formatted correctly
        self.assertIn('text: Some text', log_msg)
        self.assertIn('number: 42', log_msg)
        self.assertIn('binary: 62696e6172795f64617461', log_msg)  # hex of binary_data
        self.assertIn('address: 0xabcdef1234567890', log_msg)
        
        # Check ETH formatting for amount, balance, stake
        self.assertIn('amount: 1 ETH', log_msg)
        self.assertIn('balance: 2 ETH', log_msg)
        self.assertIn('stake: 3 ETH', log_msg)
        
        # Other number should be formatted as string
        self.assertIn('otherNumber: 987654321', log_msg)


if __name__ == '__main__':
    unittest.main()