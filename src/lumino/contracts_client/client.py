import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from eth_account import Account
from eth_account.signers.local import LocalAccount
from eth_account.types import PrivateKeyType
from eth_typing import ChecksumAddress
from web3 import Web3
from web3.contract import Contract
from web3.exceptions import ContractLogicError

from lumino.contracts_client.error_handler import ErrorHandler
from lumino.contracts_client.event_handler import EventHandler


@dataclass
class LuminoConfig:
    """Configuration for Lumino SDK"""
    web3_provider: str
    private_key: PrivateKeyType
    contract_addresses: Dict[str, ChecksumAddress]
    abis_dir: str


class LuminoError(Exception):
    """Base exception for Lumino SDK"""
    pass


class ContractError(LuminoError):
    """Exception for contract-related errors"""
    pass


class LuminoClient:
    """SDK for interacting with Lumino contracts"""

    def __init__(self, config: LuminoConfig, logger: Optional[logging.Logger] = None):
        """Initialize the Lumino SDK"""
        self.logger = logger or logging.getLogger("LuminoSDK")

        # Initialize handlers
        self.error_handler = ErrorHandler()
        self.event_handler = EventHandler(self.logger)

        # Initialize Web3 and account
        self.w3 = Web3(Web3.HTTPProvider(config.web3_provider))
        if not self.w3.is_connected():
            raise ConnectionError(f"Failed to connect to {config.web3_provider}")

        self.account: LocalAccount = Account.from_key(config.private_key)
        self.address = self.account.address

        # Load ABIs and initialize contracts
        self.abis = self._load_abis(config.abis_dir)
        self._init_contracts(config.contract_addresses)

    def _load_abis(self, abis_dir: str) -> Dict[str, dict]:
        """Load contract ABIs from Foundry output directory"""
        abis = {}
        out_dir = Path(abis_dir)

        if not out_dir.exists():
            raise FileNotFoundError(
                f"Foundry output directory not found at {out_dir}. "
                "Please run 'forge build' first."
            )

        for file_path in out_dir.rglob('*.json'):
            contract_name = file_path.parent.stem.replace('.sol', '')
            if contract_name.endswith('.t'):
                continue

            try:
                contract_data = json.loads(file_path.read_text())
                if 'abi' in contract_data:
                    abis[contract_name] = contract_data['abi']
                    self.logger.debug(f"Loaded ABI for {contract_name}")
            except Exception as e:
                self.logger.warning(f"Failed to load ABI from {file_path}: {e}")

        if not abis:
            raise ValueError(
                "No ABIs found in Foundry output directory. "
                "Please ensure contracts are compiled with 'forge build'."
            )

        return abis

    def _init_contracts(self, contract_addresses: Dict[str, ChecksumAddress]) -> None:
        """Initialize all contract interfaces"""
        try:
            self.access_manager = self._init_contract('AccessManager', contract_addresses)
            self.whitelist_manager = self._init_contract('WhitelistManager', contract_addresses)
            self.token = self._init_contract('LuminoToken', contract_addresses)
            self.incentive_manager = self._init_contract('IncentiveManager', contract_addresses)
            self.node_manager = self._init_contract('NodeManager', contract_addresses)
            self.node_escrow = self._init_contract('NodeEscrow', contract_addresses)
            self.leader_manager = self._init_contract('LeaderManager', contract_addresses)
            self.job_manager = self._init_contract('JobManager', contract_addresses)
            self.job_escrow = self._init_contract('JobEscrow', contract_addresses)
            self.epoch_manager = self._init_contract('EpochManager', contract_addresses)
        except Exception as e:
            raise ContractError(f"Failed to initialize contracts: {e}")

    def _init_contract(self, name: str, addresses: Dict[str, ChecksumAddress]) -> Contract:
        """Initialize a single contract"""
        address = addresses[name]
        abi = self.abis[name]
        return self.w3.eth.contract(address=address, abi=abi)

    def _send_transaction(self, contract_function) -> dict:
        """Helper to send a transaction and wait for receipt"""
        try:
            tx = contract_function.build_transaction({
                'from': self.address,
                'nonce': self.w3.eth.get_transaction_count(self.address),
            })
            signed_tx = self.w3.eth.account.sign_transaction(tx, self.account.key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.raw_transaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            return receipt
        except ContractLogicError as e:
            error_message = self.error_handler.decode_contract_error(e)
            raise ContractError(f"Contract error: {error_message}")
        except Exception as e:
            raise ContractError(f"Transaction failed: {e}")

    # Token functions
    def approve_token_spending(self, spender: ChecksumAddress, amount: int) -> dict:
        """Approve token spending"""
        return self._send_transaction(
            self.token.functions.approve(spender, amount)
        )

    def get_token_balance(self, address: ChecksumAddress) -> int:
        """Get token balance for address"""
        return self.token.functions.balanceOf(address).call()

    # Node Escrow functions
    def deposit_stake(self, amount: int) -> dict:
        """Deposit stake into NodeEscrow"""
        return self._send_transaction(
            self.node_escrow.functions.deposit(amount)
        )

    def get_stake_balance(self, address: ChecksumAddress) -> int:
        """Get stake balance for address"""
        return self.node_escrow.functions.getBalance(address).call()

    def request_withdraw(self, amount: int) -> dict:
        """Request withdrawal from NodeEscrow"""
        return self._send_transaction(
            self.node_escrow.functions.requestWithdraw(amount)
        )

    def cancel_withdraw(self) -> dict:
        """Cancel pending withdrawal request"""
        return self._send_transaction(
            self.node_escrow.functions.cancelWithdraw()
        )

    def withdraw(self) -> dict:
        """Execute withdrawal after lock period"""
        return self._send_transaction(
            self.node_escrow.functions.withdraw()
        )

    # Node Manager functions
    def register_node(self, compute_rating: int) -> dict:
        """Register node with given compute rating"""
        return self._send_transaction(
            self.node_manager.functions.registerNode(compute_rating)
        )

    def unregister_node(self, node_id: int) -> dict:
        """Unregister an existing node"""
        return self._send_transaction(
            self.node_manager.functions.unregisterNode(node_id)
        )

    def get_node_info(self, node_id: int) -> tuple:
        """Get node information"""
        return self.node_manager.functions.getNodeInfo(node_id).call()

    def get_nodes_in_pool(self, pool_id: int) -> List[int]:
        """Get list of nodes in a specific pool"""
        return self.node_manager.functions.getNodesInPool(pool_id).call()

    def get_node_owner(self, node_id: int) -> str:
        """Get the owner address of a node"""
        return self.node_manager.functions.getNodeOwner(node_id).call()

    def get_stake_requirement(self, address: ChecksumAddress) -> int:
        """Get stake requirement for an address"""
        return self.node_manager.functions.getStakeRequirement(address).call()

    # Epoch Manager functions
    def get_current_epoch(self) -> int:
        """Get current epoch number"""
        return self.epoch_manager.functions.getCurrentEpoch().call()

    def get_epoch_state(self) -> Tuple[int, int]:
        """Get current epoch state and time remaining"""
        if self.epoch_manager.functions.testCounter.call() is not None:
            self._send_transaction(self.epoch_manager.functions.upTestCounter())
        return self.epoch_manager.functions.getEpochState().call()

    # Leader Manager functions
    def submit_commitment(self, node_id: int, commitment: bytes) -> dict:
        """Submit commitment for current epoch"""
        return self._send_transaction(
            self.leader_manager.functions.submitCommitment(node_id, commitment)
        )

    def reveal_secret(self, node_id: int, secret: bytes) -> dict:
        """Reveal secret for current epoch"""
        return self._send_transaction(
            self.leader_manager.functions.revealSecret(node_id, secret)
        )

    def elect_leader(self) -> dict:
        """Trigger leader election"""
        return self._send_transaction(
            self.leader_manager.functions.electLeader()
        )

    def get_current_leader(self) -> int:
        """Get current leader node ID"""
        return self.leader_manager.functions.getCurrentLeader().call()

    def get_final_random_value(self, epoch: int) -> bytes:
        """Get final random value for an epoch"""
        return self.leader_manager.functions.getFinalRandomValue(epoch).call()

    def get_nodes_who_revealed(self, epoch: int) -> List[int]:
        """Get list of nodes that revealed for an epoch"""
        return self.leader_manager.functions.getNodesWhoRevealed(epoch).call()

    # Job Manager functions
    def submit_job(self, args: str, model_name: str, required_pool: int) -> dict:
        """Submit a new job"""
        return self._send_transaction(
            self.job_manager.functions.submitJob(args, model_name, required_pool)
        )

    def start_assignment_round(self) -> dict:
        """Start job assignment round"""
        return self._send_transaction(
            self.job_manager.functions.startAssignmentRound()
        )

    def set_token_count_for_job(self, job_id: int, token_count: int) -> dict:
        """Set token count for a job"""
        return self._send_transaction(
            self.job_manager.functions.setTokenCountForJob(job_id, token_count)
        )

    def confirm_job(self, job_id: int) -> dict:
        """Confirm assigned job"""
        return self._send_transaction(
            self.job_manager.functions.confirmJob(job_id)
        )

    def complete_job(self, job_id: int) -> dict:
        """Mark job as complete"""
        return self._send_transaction(
            self.job_manager.functions.completeJob(job_id)
        )

    def fail_job(self, job_id: int, reason: str) -> dict:
        """Fail an assigned job"""
        return self._send_transaction(
            self.job_manager.functions.failJob(job_id, reason)
        )

    def process_job_payment(self, job_id: int) -> dict:
        """Process payment for completed job"""
        return self._send_transaction(
            self.job_manager.functions.processPayment(job_id)
        )

    def get_jobs_by_node(self, node_id: int) -> List[dict]:
        """Get detailed job information for a node"""
        jobs = self.job_manager.functions.getJobsDetailsByNode(node_id).call()
        return [{"id": j[0], "submitter": j[1], "assignedNode": j[2], "status": j[3],
                 "requiredPool": j[4], "args": j[5], "base_model_name": j[6],
                 "tokenCount": j[7], "createdAt": j[8]} for j in jobs]

    def get_assigned_node(self, job_id: int) -> int:
        """Get node assigned to a job"""
        return self.job_manager.functions.getAssignedNode(job_id).call()

    def get_job_status(self, job_id: int) -> int:
        """Get the status of a job"""
        return self.job_manager.functions.getJobStatus(job_id).call()

    def get_job_details(self, job_id: int) -> tuple:
        """Get detailed information about a job"""
        return self.job_manager.functions.getJobDetails(job_id).call()

    def get_jobs_by_submitter(self, submitter: str) -> List[int]:
        """Get all job IDs submitted by an address"""
        return self.job_manager.functions.getJobsBySubmitter(submitter).call()

    # Job Escrow functions
    def deposit_job_funds(self, amount: int) -> dict:
        """Deposit funds into JobEscrow"""
        return self._send_transaction(
            self.job_escrow.functions.deposit(amount)
        )

    def get_job_escrow_balance(self, address: ChecksumAddress) -> int:
        """Get JobEscrow balance for address"""
        return self.job_escrow.functions.getBalance(address).call()

    # Whitelist Manager functions
    def add_cp(self, cp_address: ChecksumAddress) -> dict:
        """Add a computing provider to whitelist"""
        return self._send_transaction(
            self.whitelist_manager.functions.addCP(cp_address)
        )

    def remove_cp(self, cp_address: ChecksumAddress) -> dict:
        """Remove a computing provider from whitelist"""
        return self._send_transaction(
            self.whitelist_manager.functions.removeCP(cp_address)
        )

    def is_whitelisted(self, cp_address: ChecksumAddress) -> bool:
        """Check if address is whitelisted"""
        try:
            self.whitelist_manager.functions.requireWhitelisted(cp_address).call()
            return True
        except:
            return False

    # Incentive Manager functions
    def process_incentives(self) -> dict:
        """Process incentives for current epoch"""
        return self._send_transaction(
            self.incentive_manager.functions.processAll()
        )

    # Event monitoring methods
    def setup_event_filters(self) -> None:
        """Set up filters for all relevant contract events"""
        contracts = {
            'AccessManager': self.access_manager,
            'WhitelistManager': self.whitelist_manager,
            'LuminoToken': self.token,
            'IncentiveManager': self.incentive_manager,
            'NodeManager': self.node_manager,
            'NodeEscrow': self.node_escrow,
            'LeaderManager': self.leader_manager,
            'JobManager': self.job_manager,
            'JobEscrow': self.job_escrow
        }
        from_block = self.w3.eth.block_number
        self.event_handler.setup_event_filters(contracts, from_block)

    def process_events(self) -> None:
        """Process any new events from all filters"""
        self.event_handler.process_events()
