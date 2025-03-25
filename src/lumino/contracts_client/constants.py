# Environment variable names
ENV_VAR_RPC_URL = 'RPC_URL'
ENV_VAR_USER_PRIVATE_KEY = 'CC_USER_PRIVATE_KEY'
ENV_VAR_NODE_PRIVATE_KEY = 'CC_NODE_PRIVATE_KEY'
ENV_VAR_USER_DATA_DIR = 'CC_USER_DATA_DIR'
ENV_VAR_NODE_DATA_DIR = 'CC_NODE_DATA_DIR'
ENV_VAR_ABIS_DIR = 'CC_ABIS_DIR'
ENV_VAR_PIPELINE_ZEN_DIR = 'CC_PIPELINE_ZEN_DIR'
ENV_VAR_TEST_MODE = 'CC_TEST_MODE'
ENV_VAR_COMPUTE_RATING = 'CC_COMPUTE_RATING'
ENV_VAR_ARTIFACTS_PASSWORD = 'CC_ARTIFACTS_PASSWORD'

# Default paths
DEFAULT_LUMINO_DIR = '~/.lumino'
DEFAULT_STORAGE_DIR = f'{DEFAULT_LUMINO_DIR}/storage'
DEFAULT_DATA_DIR = {
    'user': f'{DEFAULT_STORAGE_DIR}/user_client',
    'node': f'{DEFAULT_STORAGE_DIR}/node_client',
}
DEFAULT_ABIS_DIR = f'{DEFAULT_LUMINO_DIR}/abis'
DEFAULT_PIPELINE_ZEN_DIR = f'{DEFAULT_LUMINO_DIR}/pipeline-zen'
DEFAULT_RPC_URL = 'https://'

# Token constants
MIN_ESCROW_BALANCE = 20  # Minimum escrow balance in LUM

# Epoch state enums
EPOCH_STATE = {
    0: "COMMIT",
    1: "REVEAL",
    2: "ELECT",
    3: "EXECUTE",
    4: "CONFIRM",
    5: "DISPUTE",
    6: "PAUSED"
}

# Epoch phase durations (in seconds)
EPOCH_DURATION = 180  # Total epoch duration (6 phases * 30s)
COMMIT_DURATION = 30  # COMMIT phase duration
REVEAL_DURATION = 30  # REVEAL phase duration
ELECT_DURATION = 30  # ELECT phase duration
EXECUTE_DURATION = 30  # EXECUTE phase duration
CONFIRM_DURATION = 30  # CONFIRM phase duration
DISPUTE_DURATION = 30  # DISPUTE phase duration

# Job status enums
JOB_STATUS = {
    0: "NEW",
    1: "ASSIGNED",
    2: "CONFIRMED",
    3: "COMPLETE",
    4: "FAILED"
}

# Default test mode (1=on, 0=off for each phase, plus num epochs to run before exit)
DEFAULT_TEST_MODE = '1111110'
