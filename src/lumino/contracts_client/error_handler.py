from eth_abi import decode
from web3 import Web3
from web3.exceptions import ContractLogicError


class ErrorHandler:
    """Handles decoding and formatting of Lumino contract custom errors"""

    # Enum mappings
    JOB_STATUS = {
        0: "NEW",
        1: "ASSIGNED",
        2: "CONFIRMED",
        3: "COMPLETE"
    }

    EPOCH_STATE = {
        0: "COMMIT",
        1: "REVEAL",
        2: "ELECT",
        3: "EXECUTE",
        4: "CONFIRM",
        5: "DISPUTE",
        6: "PAUSED"
    }

    def __init__(self):
        # Error definitions with their parameter types and formatters
        self.error_defs = {
            # AccessManager errors
            "RoleManagerUnauthorized": {
                "params": ["address"],
                "format": lambda args: f"Account {args[0]} is not authorized for this role"
            },
            "InvalidRole": {
                "params": ["bytes32"],
                "format": lambda args: f"Invalid role: {args[0].hex()}"
            },
            "CannotRevokeAdmin": {
                "params": [],
                "format": lambda args: "Cannot revoke the last admin role"
            },
            "MustConfirmRenounce": {
                "params": ["address"],
                "format": lambda args: f"Account {args[0]} must confirm renounce"
            },

            # EpochManager errors
            "InvalidState": {
                "params": ["uint8"],
                "format": lambda args: f"Invalid epoch state: {self.EPOCH_STATE.get(args[0], 'Unknown')}"
            },

            # Escrow (AEscrow) errors
            "BelowMinimumDeposit": {
                "params": ["uint256", "uint256"],
                "format": lambda
                    args: f"Deposit amount {Web3.from_wei(args[0], 'ether')} is below minimum required {Web3.from_wei(args[1], 'ether')}"
            },
            "InsufficientBalance": {
                "params": ["address", "uint256", "uint256"],
                "format": lambda
                    args: f"Insufficient balance for {args[0]}: requested {Web3.from_wei(args[1], 'ether')}, available {Web3.from_wei(args[2], 'ether')}"
            },
            "ExistingWithdrawRequest": {
                "params": ["address"],
                "format": lambda args: f"Active withdrawal request already exists for {args[0]}"
            },
            "NoWithdrawRequest": {
                "params": ["address"],
                "format": lambda args: f"No active withdrawal request found for {args[0]}"
            },
            "LockPeriodActive": {
                "params": ["address", "uint256"],
                "format": lambda args: f"Lock period still active for {args[0]}, {args[1]} seconds remaining"
            },
            "TransferFailed": {
                "params": [],
                "format": lambda args: "Token transfer failed"
            },
            "InsufficientContractBalance": {
                "params": ["uint256", "uint256"],
                "format": lambda
                    args: f"Contract balance insufficient: requested {Web3.from_wei(args[0], 'ether')}, available {Web3.from_wei(args[1], 'ether')}"
            },

            # JobManager errors
            "InvalidStatusTransition": {
                "params": ["uint8", "uint8"],
                "format": lambda
                    args: f"Invalid job status transition from {self.JOB_STATUS.get(args[0], 'Unknown')} to {self.JOB_STATUS.get(args[1], 'Unknown')}"
            },
            "JobAlreadyProcessed": {
                "params": ["uint256"],
                "format": lambda args: f"Job {args[0]} has already been processed"
            },
            "JobNotComplete": {
                "params": ["uint256"],
                "format": lambda args: f"Job {args[0]} is not in completed state"
            },
            "InvalidModelName": {
                "params": ["string"],
                "format": lambda args: f"Invalid model name: {args[0]}"
            },

            # LeaderManager errors
            "NoCommitmentFound": {
                "params": ["uint256", "uint256"],
                "format": lambda args: f"No commitment found for epoch {args[0]}, node {args[1]}"
            },
            "InvalidSecret": {
                "params": ["uint256"],
                "format": lambda args: f"Invalid secret revealed for node {args[0]}"
            },
            "NoRevealsSubmitted": {
                "params": ["uint256"],
                "format": lambda args: f"No secrets revealed for epoch {args[0]}"
            },
            "MissingReveal": {
                "params": ["uint256"],
                "format": lambda args: f"Missing secret reveal from node {args[0]}"
            },
            "NotCurrentLeader": {
                "params": ["address", "address"],
                "format": lambda args: f"Account {args[0]} is not the current leader (leader is {args[1]})"
            },
            "NoRandomValueForEpoch": {
                "params": ["uint256"],
                "format": lambda args: f"No random value available for epoch {args[0]}"
            },
            "LeaderAlreadyElected": {
                "params": ["uint256"],
                "format": lambda args: f"Leader already elected for epoch {args[0]}"
            },

            # NodeEscrow errors
            "SlashedCP": {
                "params": ["address"],
                "format": lambda args: f"Address is slashed: {args[0]}"
            },

            # NodeManager errors
            "NodeNotFound": {
                "params": ["uint256"],
                "format": lambda args: f"Node {args[0]} not found"
            },
            "NodeNotActive": {
                "params": ["uint256"],
                "format": lambda args: f"Node {args[0]} is not active"
            },
            "InsufficientStake": {
                "params": ["address", "uint256"],
                "format": lambda args: f"Insufficient stake for {args[0]} with compute rating {args[1]}"
            },
            "InvalidNodeOwner": {
                "params": ["uint256", "address"],
                "format": lambda args: f"Invalid node owner: {args[1]} does not own node {args[0]}"
            },

            # WhitelistManager errors
            "AlreadyWhitelisted": {
                "params": ["address"],
                "format": lambda args: f"Computing provider {args[0]} is already whitelisted"
            },
            "CooldownActive": {
                "params": ["address", "uint256"],
                "format": lambda args: f"Cooldown period active for {args[0]}, {args[1]} seconds remaining"
            },
            "NotWhitelisted": {
                "params": ["address"],
                "format": lambda args: f"Computing provider {args[0]} is not whitelisted"
            },

            # IncentiveManager errors
            "EpochAlreadyProcessed": {
                "params": ["uint256"],
                "format": lambda args: f"Epoch incentives has already been processed, got epoch {args[0]}"
            }
        }

        # Generate error selectors using web3
        self.error_selectors = {}
        w3 = Web3()
        for error_name, error_def in self.error_defs.items():
            # Create the error signature
            params_str = ",".join(error_def["params"])
            signature = f"{error_name}({params_str})"

            # Generate the selector
            selector = w3.keccak(text=signature)[:4].hex()
            self.error_selectors[selector] = (error_name, error_def)

    def decode_error(self, error_data: str) -> str:
        """
        Decodes a contract custom error into a human-readable message

        Args:
            error_data: The hex string of the error selector and data

        Returns:
            A human-readable error message
        """
        try:
            # Clean up error data if needed
            if isinstance(error_data, tuple):
                error_data = error_data[0]
            if error_data.startswith("execution reverted: "):
                error_data = error_data.split("execution reverted: ")[1]

            # Extract the selector (first 4 bytes)
            if error_data.startswith("0x"):
                selector = error_data[2:10]
            else:
                selector = error_data[:8]

            # Look up the error information
            if selector in self.error_selectors:
                error_name, error_def = self.error_selectors[selector]

                # If no parameters, return the basic message
                if not error_def["params"]:
                    return error_def["format"]([])

                # Extract the parameter data
                param_data = error_data[10:] if error_data.startswith("0x") else error_data[8:]

                # Decode the parameters using eth_abi
                decoded_params = decode(error_def["params"], bytes.fromhex(param_data))

                # Format the error message
                return error_def["format"](decoded_params)

            return f"Unknown error selector: 0x{selector}"

        except Exception as e:
            return f"Error decoding custom error: {error_data} (Decoder error: {str(e)})"

    def decode_contract_error(self, error: ContractLogicError) -> str:
        """
        Decodes a ContractLogicError into a human-readable message

        Args:
            error: The ContractLogicError from web3.py

        Returns:
            A human-readable error message
        """
        try:
            # Extract the error data from the error message
            return self.decode_error(error.data)
        except Exception as e:
            return f"Failed to decode contract error: {str(error)} (Decoder error: {str(e)})"
