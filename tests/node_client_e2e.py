from node_client import LuminoNode, LuminoConfig

# Test job is completed

# Submit a job
# ...

config = {"test_mode": "11111", }
config = LuminoConfig(**config)
n = LuminoNode(config)
n.run()

# Assert something
# call contract to confirm that job is completed