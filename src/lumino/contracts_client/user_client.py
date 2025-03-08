import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Dict, List, Tuple

import click
from dotenv import load_dotenv
from web3 import Web3

from client import LuminoClient, LuminoConfig


@dataclass
class UserConfig:
    """Configuration for Lumino User Client"""
    sdk_config: LuminoConfig
    data_dir: str = "./user_data"
    log_level: int = logging.INFO
    polling_interval: int = 5  # Seconds between status checks


class LuminoUserClient:
    """User client for interacting with Lumino contracts"""

    JOB_STATUS = {
        0: "NEW",
        1: "ASSIGNED",
        2: "CONFIRMED",
        3: "COMPLETE",
        4: "FAILED"
    }
    MIN_ESCROW_BALANCE = 20  # Minimum escrow balance in LUM

    def __init__(self, config: UserConfig):
        """Initialize the Lumino User Client"""
        self.data_dir = Path(config.data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.user_data_file = self.data_dir / "user_data.json"

        self._setup_logging(config.log_level)
        self.logger.info("Initializing Lumino User Client...")

        self.sdk = LuminoClient(config.sdk_config, self.logger)
        self.address = self.sdk.address
        self.polling_interval = config.polling_interval

        self.sdk.setup_event_filters()
        self.user_data = self._load_user_data()
        self.job_ids = self.user_data.get("job_ids", [])
        # Load auto-topup settings
        self.auto_topup = self.user_data.get("auto_topup", {
            "enabled": False,
            "amount": self.MIN_ESCROW_BALANCE,
            "auto_yes_min": False,
            "auto_yes_additional": 0
        })

        self.logger.info("Lumino User Client initialization complete")

    def _setup_logging(self, log_level: int) -> None:
        """Set up logging with file and console handlers"""
        self.logger = logging.getLogger("LuminoUserClient")
        self.logger.setLevel(log_level)
        self.logger.handlers.clear()

        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        file_handler = logging.FileHandler(self.data_dir / "user_client.log")
        file_handler.setFormatter(formatter)
        self.logger.addHandler(file_handler)

    def _load_user_data(self) -> dict:
        if self.user_data_file.exists():
            with open(self.user_data_file) as f:
                return json.load(f)
        return {"job_ids": []}

    def _save_user_data(self) -> None:
        with open(self.user_data_file, 'w') as f:
            json.dump(self.user_data, f, indent=2)

    def add_funds_to_escrow(self, amount: float) -> None:
        amount_wei = Web3.to_wei(amount, 'ether')
        self.sdk.approve_token_spending(self.sdk.job_escrow.address, amount_wei)
        self.sdk.deposit_job_funds(amount_wei)
        self.logger.info(f"Deposited {amount} LUM to JobEscrow")

    def check_balances(self) -> Dict[str, float]:
        token_balance = float(Web3.from_wei(self.sdk.get_token_balance(self.address), 'ether'))
        escrow_balance = float(Web3.from_wei(self.sdk.get_job_escrow_balance(self.address), 'ether'))
        balances = {"token_balance": token_balance, "escrow_balance": escrow_balance}
        self.logger.info(f"Token Balance: {token_balance} LUM, Escrow Balance: {escrow_balance} LUM")
        return balances

    def submit_job(self, job_args: str, model_name: str, required_pool: int) -> int:
        # Check and handle auto-topup before submitting job
        if self.auto_topup["enabled"]:
            balances = self.check_balances()
            escrow_balance = balances["escrow_balance"]
            if escrow_balance < self.MIN_ESCROW_BALANCE:
                topup_amount = float(self.auto_topup["amount"])
                if self.auto_topup["auto_yes_additional"] > 0:
                    topup_amount += float(self.auto_topup["auto_yes_additional"])
                elif not self.auto_topup["auto_yes_min"]:
                    self.logger.warning("Auto-topup enabled but no automatic amount set. Skipping.")
                    click.echo("Auto-topup enabled but no automatic amount set. Please run 'topup' command.")
                else:
                    self.add_funds_to_escrow(topup_amount)
                    click.echo(f"Automatically topped up escrow with {topup_amount} LUM")

        receipt = self.sdk.submit_job(job_args, model_name, required_pool)
        job_submitted_event = self.sdk.job_manager.events.JobSubmitted()
        logs = job_submitted_event.process_receipt(receipt)
        job_id = logs[0]['args']['jobId']
        self.job_ids.append(job_id)
        self.user_data["job_ids"] = self.job_ids
        self._save_user_data()
        self.logger.info(f"Submitted job with ID: {job_id}")
        return job_id

    def monitor_job_progress(self, job_id: int) -> Tuple[str, Optional[int]]:
        status_int = self.sdk.get_job_status(job_id)
        status = self.JOB_STATUS[status_int]
        assigned_node = self.sdk.get_assigned_node(job_id)
        self.logger.info(f"Job {job_id} status: {status}, Assigned Node: {assigned_node or 'None'}")
        return status, assigned_node

    def list_jobs(self, only_active: bool = False) -> List[Dict[str, any]]:
        job_ids = self.sdk.get_jobs_by_submitter(self.address)
        self.job_ids = job_ids
        self.user_data["job_ids"] = self.job_ids
        self._save_user_data()

        jobs = []
        for job_id in job_ids:
            job = self.sdk.get_job_details(job_id)
            job_dict = {
                "job_id": job[0],
                "status": self.JOB_STATUS[job[3]],
                "assigned_node": job[2],
                "args": job[5],
                "model_name": job[6],
                "created_at": job[8]
            }
            if not only_active or job[3] < 3:  # If not COMPLETE
                jobs.append(job_dict)
        self.logger.info(f"Retrieved {len(jobs)} jobs")
        return jobs


def initialize_lumino_user_client() -> LuminoUserClient:
    load_dotenv()
    sdk_config = LuminoConfig(
        web3_provider=os.getenv('RPC_URL', 'http://localhost:8545'),
        private_key=os.getenv('USER_PRIVATE_KEY', os.getenv('NODE_PRIVATE_KEY')),
        contract_addresses={
            'LuminoToken': os.getenv('LUMINO_TOKEN_ADDRESS'),
            'AccessManager': os.getenv('ACCESS_MANAGER_ADDRESS'),
            'WhitelistManager': os.getenv('WHITELIST_MANAGER_ADDRESS'),
            'NodeManager': os.getenv('NODE_MANAGER_ADDRESS'),
            'IncentiveManager': os.getenv('INCENTIVE_MANAGER_ADDRESS'),
            'NodeEscrow': os.getenv('NODE_ESCROW_ADDRESS'),
            'LeaderManager': os.getenv('LEADER_MANAGER_ADDRESS'),
            'JobManager': os.getenv('JOB_MANAGER_ADDRESS'),
            'EpochManager': os.getenv('EPOCH_MANAGER_ADDRESS'),
            'JobEscrow': os.getenv('JOB_ESCROW_ADDRESS')
        },
        abis_dir=os.getenv('ABIS_DIR', '../contracts/out')
    )
    config = UserConfig(sdk_config=sdk_config,
                        data_dir=os.getenv('USER_DATA_DIR', 'cache/user_client'))
    return LuminoUserClient(config)


@click.group()
@click.pass_context
def cli(ctx):
    """Lumino User Client CLI"""
    ctx.obj = initialize_lumino_user_client()


@cli.command()
@click.option('--args', required=True, help='Job arguments in JSON format')
@click.option('--model', default='llm_llama3_1_8b', help='Model name')
@click.option('--pool', default=30, type=int, help='Required compute pool')
@click.option('--monitor', is_flag=True, help='Monitor job progress after submission')
@click.pass_obj
def create_job(client: LuminoUserClient, args, model, pool, monitor):
    """Create a new job"""
    try:
        job_id = client.submit_job(args, model, pool)
        click.echo(f"Job created successfully with ID: {job_id}")

        if monitor:
            click.echo("Monitoring job progress (Ctrl+C to stop)...")
            while True:
                status, node = client.monitor_job_progress(job_id)
                click.echo(f"Job {job_id} - Status: {status}, Node: {node or 'None'}")
                if status == "COMPLETE":
                    click.echo("Job completed!")
                    break
                time.sleep(client.polling_interval)
    except Exception as e:
        client.logger.error(f"Error creating job: {e}")
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.option('--job-id', required=True, type=int, help='Job ID to monitor')
@click.pass_obj
def monitor_job(client: LuminoUserClient, job_id):
    """Monitor an existing job"""
    try:
        click.echo(f"Monitoring job {job_id} (Ctrl+C to stop)...")
        while True:
            status, node = client.monitor_job_progress(job_id)
            click.echo(f"Job {job_id} - Status: {status}, Node: {node or 'None'}")
            if status in ("COMPLETE", "FAILED"):
                click.echo(f"Job {job_id} {status}!")
                break
            time.sleep(client.polling_interval)
    except Exception as e:
        client.logger.error(f"Error monitoring job: {e}")
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.option('--only-active', is_flag=True, help='Show only active jobs')
@click.option('--exit-on-complete', is_flag=True, help='Exit when all jobs are complete')
@click.pass_obj
def monitor_all(client: LuminoUserClient, only_active: bool, exit_on_complete: bool):
    """Monitor all non-completed jobs"""
    try:
        click.echo("Monitoring all non-completed jobs (Ctrl+C to stop)...")
        while True:
            jobs = client.list_jobs(only_active=only_active)
            if not jobs:
                click.echo("No active jobs found.")
                break

            for job in jobs:
                click.echo(f"Job {job['job_id']} - Status: {job['status']}, "
                           f"Node: {job['assigned_node'] or 'None'}")

            all_complete = all(job['status'] == "COMPLETE" for job in jobs)
            if all_complete and exit_on_complete:
                click.echo("All jobs completed!")
                break
            time.sleep(client.polling_interval)
    except Exception as e:
        client.logger.error(f"Error monitoring jobs: {e}")
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.pass_obj
def topup(client: LuminoUserClient):
    """Interactively manage escrow balance and auto-topup settings"""
    try:
        balances = client.check_balances()
        escrow_balance = balances["escrow_balance"]
        token_balance = balances["token_balance"]

        click.echo(f"Current Escrow Balance: {escrow_balance} LUM")
        click.echo(f"Minimum Required Balance: {client.MIN_ESCROW_BALANCE} LUM")
        click.echo(f"Available Token Balance: {token_balance} LUM")

        if escrow_balance < client.MIN_ESCROW_BALANCE:
            deficit = float(client.MIN_ESCROW_BALANCE - escrow_balance)
            click.echo(f"WARNING: Balance is {deficit} LUM below minimum!")

            if click.confirm("Would you like to top up to minimum balance?"):
                additional = float(click.prompt(
                    "Enter additional amount to deposit (0 for none)",
                    type=float,
                    default=0.0
                ))
                total_topup = deficit + additional
                if total_topup > token_balance:
                    click.echo(f"Error: Insufficient tokens ({token_balance} LUM available)")
                    return
                client.add_funds_to_escrow(total_topup)
                click.echo(f"Successfully deposited {total_topup} LUM")

        # Auto-topup configuration
        click.echo("\nCurrent auto-topup settings:")
        click.echo(f"Enabled: {client.auto_topup['enabled']}")
        click.echo(f"Minimum topup amount: {client.auto_topup['amount']} LUM")
        click.echo(f"Auto-yes to minimum: {client.auto_topup['auto_yes_min']}")
        click.echo(f"Auto-yes additional amount: {client.auto_topup['auto_yes_additional']} LUM")

        if click.confirm("\nWould you like to configure auto-topup?"):
            enable = click.confirm("Enable auto-topup when below minimum?")
            if enable:
                auto_yes_min = click.confirm("Automatically top up to minimum without asking?")
                additional = 0.0
                if auto_yes_min:
                    additional = float(click.prompt(
                        "Enter additional auto-topup amount (0 for none)",
                        type=float,
                        default=0.0
                    ))
                client.auto_topup = {
                    "enabled": True,
                    "amount": float(client.MIN_ESCROW_BALANCE),
                    "auto_yes_min": auto_yes_min,
                    "auto_yes_additional": additional
                }
            else:
                client.auto_topup = {
                    "enabled": False,
                    "amount": float(client.MIN_ESCROW_BALANCE),
                    "auto_yes_min": False,
                    "auto_yes_additional": 0.0
                }
            client.user_data["auto_topup"] = client.auto_topup
            client._save_user_data()
            click.echo("Auto-topup settings updated successfully")

        # Show final balance
        balances = client.check_balances()
        click.echo(f"\nFinal balances - Token: {balances['token_balance']} LUM, "
                   f"Escrow: {balances['escrow_balance']} LUM")

    except Exception as e:
        client.logger.error(f"Error managing topup: {e}")
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.pass_obj
def list(client: LuminoUserClient):
    """List all jobs"""
    try:
        jobs = client.list_jobs()
        if not jobs:
            click.echo("No jobs found.")
            return

        for job in jobs:
            click.echo(f"Job {job['job_id']} - Status: {job['status']}, "
                       f"Node: {job['assigned_node'] or 'None'}, "
                       f"Model: {job['model_name']}, "
                       f"Created: {time.ctime(job['created_at'])}")
    except Exception as e:
        client.logger.error(f"Error listing jobs: {e}")
        click.echo(f"Error: {e}", err=True)


if __name__ == "__main__":
    cli()
