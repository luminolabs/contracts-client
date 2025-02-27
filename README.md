### Local setup

1. Clone the repository
2. Update .env file with correct values (use addresses/private keys from the anvil output, and contract addresses from the forge output)
3. In the terminal, export the environment variables from the .env file
4. Transfer funds to the user/node addresses
5. Whitelist the node address to participate in the network
6. Install python dependencies
7. Start the node client
8. Top up the user account with tokens
9. Create a job using the user client

#### Transfer funds to node and user addresses (update .env file with correct values first)
```bash
export $(grep -v '^#' .env | xargs) && \
cast send $LUMINO_TOKEN_ADDRESS "transfer(address,uint256)" $USER_ADDRESS $TOKENS_500 --private-key $DEPLOYER_PRIVATE_KEY --rpc-url $RPC_URL && \
cast send $LUMINO_TOKEN_ADDRESS "transfer(address,uint256)" $NODE_ADDRESS $TOKENS_500 --private-key $DEPLOYER_PRIVATE_KEY --rpc-url $RPC_URL && \
cast send $LUMINO_TOKEN_ADDRESS "transfer(address,uint256)" $NODE2_ADDRESS $TOKENS_500 --private-key $DEPLOYER_PRIVATE_KEY --rpc-url $RPC_URL && \
cast send $LUMINO_TOKEN_ADDRESS "transfer(address,uint256)" $NODE3_ADDRESS $TOKENS_500 --private-key $DEPLOYER_PRIVATE_KEY --rpc-url $RPC_URL
```

#### Whitelist node address
```bash
export $(grep -v '^#' .env | xargs) && \
cast send $WHITELIST_MANAGER_ADDRESS "addCP(address)" $NODE_ADDRESS --private-key $DEPLOYER_PRIVATE_KEY --rpc-url $RPC_URL && \
cast send $WHITELIST_MANAGER_ADDRESS "addCP(address)" $NODE2_ADDRESS --private-key $DEPLOYER_PRIVATE_KEY --rpc-url $RPC_URL && \
cast send $WHITELIST_MANAGER_ADDRESS "addCP(address)" $NODE3_ADDRESS --private-key $DEPLOYER_PRIVATE_KEY --rpc-url $RPC_URL
```

#### Install python dependencies
```bash
pip install -r requirements.txt
```

#### Start the node client
```bash
python node_client.py
```

#### Top up the user account with tokens
```bash
python src/user_client.py topup
```

#### Create a job using the user client
```bash
python src/user_client.py create-job --args '{"task": "example"}' --model llm_dummy --pool 30 --monitor
```