import logging
from typing import Dict, List, Tuple

from web3 import Web3
from web3.contract import Contract


class EventHandler:
    """Handles contract event processing and logging"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self.event_filters: Dict[Tuple[str, str], any] = {}  # (contract_address, event_name) -> filter

        # Define contract event mappings
        self.contract_events = {
            'AccessManager': [
                'RoleGranted',
                'RoleRevoked'
            ],
            'NodeManager': [
                'NodeRegistered',
                'NodeUnregistered',
                'NodeUpdated',
                'StakeValidated',
                'StakeRequirementUpdated'
            ],
            'LeaderManager': [
                'CommitSubmitted',
                'SecretRevealed',
                'LeaderElected'
            ],
            'JobManager': [
                'JobSubmitted',
                'JobStatusUpdated',
                'JobAssigned',
                'AssignmentRoundStarted',
                'JobConfirmed',
                'JobCompleted',
                'JobFailed',
                'PaymentProcessed'
            ],
            'NodeEscrow': [
                'Deposited',
                'WithdrawRequested',
                'WithdrawCancelled',
                'Withdrawn',
                'PenaltyApplied',
                'SlashApplied',
                'RewardApplied'
            ],
            'JobEscrow': [
                'Deposited',
                'WithdrawRequested',
                'WithdrawCancelled',
                'Withdrawn',
                'PaymentReleased'
            ],
            'WhitelistManager': [
                'CPAdded',
                'CPRemoved'
            ],
            'LuminoToken': [
                'Transfer',
                'Approval'
            ],
            'IncentiveManager': [
                'LeaderRewardApplied',
                'JobAvailabilityRewardApplied',
                'DisputerRewardApplied',
                'LeaderNotExecutedPenaltyApplied',
                'JobNotConfirmedPenaltyApplied'
            ]
        }

    def setup_event_filters(self, contracts: Dict[str, Contract], from_block: int) -> None:
        """Set up filters for all contract events

        Args:
            contracts: Dictionary mapping contract names to Contract objects
            from_block: Block number to start filtering from
        """
        for contract_name, contract in contracts.items():
            if contract_name in self.contract_events:
                self._create_event_filters(
                    contract,
                    self.contract_events[contract_name],
                    from_block
                )

    def create_event_filter(self, contract: Contract, event_name: str, from_block: int) -> None:
        """Create a new event filter for a specific contract event"""
        event = getattr(contract.events, event_name)
        event_filter = event.create_filter(from_block=from_block)
        self.event_filters[(contract.address, event_name)] = event_filter
        self.logger.info(f"Created filter for {event_name} events from block {from_block}")

    def _create_event_filters(self, contract: Contract, event_names: List[str], from_block: int) -> None:
        """Create filters for multiple events from a contract"""
        for event_name in event_names:
            self.create_event_filter(contract, event_name, from_block)

    def process_events(self) -> None:
        """Process all pending events from all filters"""
        for (contract_address, event_name), event_filter in self.event_filters.items():
            try:
                for event in event_filter.get_new_entries():
                    self._log_event(event_name, event)
            except Exception as e:
                self.logger.error(f"Error processing {event_name} events: {e}")

    def _log_event(self, event_name: str, event: dict) -> None:
        """Format and log a contract event"""
        # Extract event arguments
        args = event['args']
        formatted_args = []
        for key, value in args.items():
            # Format value based on type
            if isinstance(value, bytes):
                formatted_value = value.hex()
            elif isinstance(value, int):
                # Check if it might be wei
                if key.lower().endswith(('amount', 'balance', 'stake')):
                    formatted_value = f"{Web3.from_wei(value, 'ether')} ETH"
                else:
                    formatted_value = str(value)
            else:
                formatted_value = str(value)
            formatted_args.append(f"{key}: {formatted_value}")

        # Build event message
        event_msg = f"Event {event_name} emitted:"
        for arg in formatted_args:
            event_msg += f"\n    {arg}"

        self.logger.info(event_msg)
