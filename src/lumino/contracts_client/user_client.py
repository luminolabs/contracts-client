import logging
import os
import time
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple

import click
from lumino.contracts_client.client import LuminoClient, LuminoConfig
from lumino.contracts_client.config import load_environment, setup_environment_vars, create_sdk_config
from lumino.contracts_client.constants import (
    ENV_VAR_USER_DATA_DIR,
    DEFAULT_DATA_DIR,
    JOB_STATUS,
    MIN_ESCROW_BALANCE
)
from lumino.contracts_client.utils import setup_logging, load_json_file, save_json_file, check_and_create_dir
from web3 import Web3

# Load environment variables
load_environment()


@dataclass
class UserConfig:
    """Configuration for Lumino User Client"""
    sdk_config: LuminoConfig
    data_dir: str
    log_level: int = logging.INFO
    polling_interval: int = 5


class LuminoUser:
    """User client for interacting with Lumino contracts"""

    def __init__(self, config: UserConfig):
        """Initialize the Lumino User Client"""
        self.data_dir = check_and_create_dir(config.data_dir)
        self.user_data_file = self.data_dir / "user_data.json"

        self.logger = setup_logging("LuminoUserClient", self.data_dir / "user_client.log", config.log_level)
        self.logger.info("Initializing Lumino User Client...")

        self.sdk = LuminoClient(config.sdk_config, self.logger)
        self.address = self.sdk.address
        self.polling_interval = config.polling_interval

        self.sdk.setup_event_filters()
        self.user_data = load_json_file(self.user_data_file, {"job_ids": []})
        self.job_ids = self.user_data.get("job_ids", [])

        # Load auto-topup settings
        self.auto_topup = self.user_data.get("auto_topup", {
            "enabled": False,
            "amount": MIN_ESCROW_BALANCE,
            "auto_yes_min": False,
            "auto_yes_additional": 0
        })

        self.logger.info("Lumino User Client initialization complete")

    def save_user_data(self) -> None:
        """Save user data to JSON file"""
        save_json_file(self.user_data_file, self.user_data)

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

    def submit_job(self, job_args: str, model_name: str, ft_type: str) -> int:
        # Check and handle auto-topup before submitting job
        if self.auto_topup["enabled"]:
            balances = self.check_balances()
            escrow_balance = balances["escrow_balance"]
            if escrow_balance < MIN_ESCROW_BALANCE:
                topup_amount = float(self.auto_topup["amount"])
                if self.auto_topup["auto_yes_additional"] > 0:
                    topup_amount += float(self.auto_topup["auto_yes_additional"])
                elif not self.auto_topup["auto_yes_min"]:
                    self.logger.warning("Auto-topup enabled but no automatic amount set. Skipping.")
                    click.echo("Auto-topup enabled but no automatic amount set. Please run 'topup' command.")
                else:
                    self.add_funds_to_escrow(topup_amount)
                    click.echo(f"Automatically topped up escrow with {topup_amount} LUM")

        receipt = self.sdk.submit_job(job_args, model_name, ft_type)
        job_submitted_event = self.sdk.job_manager.events.JobSubmitted()
        logs = job_submitted_event.process_receipt(receipt)
        job_id = logs[0]['args']['jobId']
        self.job_ids.append(job_id)
        self.user_data["job_ids"] = self.job_ids
        self.save_user_data()
        self.logger.info(f"Submitted job with ID: {job_id}")
        return job_id

    def monitor_job_progress(self, job_id: int) -> Tuple[str, Optional[int]]:
        status_int = self.sdk.get_job_status(job_id)
        status = JOB_STATUS[status_int]
        assigned_node = self.sdk.get_assigned_node(job_id)
        self.logger.info(f"Job {job_id} status: {status}, Assigned Node: {assigned_node or 'None'}")
        return status, assigned_node

    def list_jobs(self, only_active: bool = False) -> List[Dict[str, any]]:
        job_ids = self.sdk.get_jobs_by_submitter(self.address)
        self.job_ids = job_ids
        self.user_data["job_ids"] = self.job_ids
        self.save_user_data()

        jobs = []
        for job_id in job_ids:
            job = self.sdk.get_job_details(job_id)
            job_dict = {
                "job_id": job[0],
                "status": JOB_STATUS[job[3]],
                "assigned_node": job[2],
                "args": job[5],
                "model_name": job[6],
                "created_at": job[8]
            }
            if not only_active or job[3] < 3:  # If not COMPLETE
                jobs.append(job_dict)
        self.logger.info(f"Retrieved {len(jobs)} jobs")
        return jobs


def initialize_lumino_user() -> LuminoUser:
    """Initialize and return a LuminoUser instance with proper config"""
    # Setup environment variables, prompting for missing values
    setup_environment_vars(is_node=False)

    # Create SDK config
    sdk_config = create_sdk_config(is_node=False)

    # Create user config
    config = UserConfig(
        sdk_config=sdk_config,
        data_dir=os.getenv(ENV_VAR_USER_DATA_DIR, DEFAULT_DATA_DIR['user'])
    )

    return LuminoUser(config)


@click.group()
@click.pass_context
def cli(ctx):
    """Lumino User Client CLI"""
    ctx.obj = initialize_lumino_user()


@cli.command()
@click.option('--args', required=True, help='Job arguments in JSON format')
@click.option('--model', default='llm_llama3_1_8b', help='Model name')
@click.option('--ft_type', default='LORA', type=str, help='Fine-tuning type (QLORA, LORA, FULL)')
@click.option('--monitor', is_flag=True, help='Monitor job progress after submission')
@click.pass_obj
def create_job(client: LuminoUser, args, model, ft_type, monitor):
    """Create a new job"""
    try:
        job_id = client.submit_job(args, model, ft_type)
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
def monitor_job(client: LuminoUser, job_id):
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
def monitor_all(client: LuminoUser, only_active: bool, exit_on_complete: bool):
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
def topup(client: LuminoUser):
    """Interactively manage escrow balance and auto-topup settings"""
    try:
        from lumino.contracts_client.cli_utils import CLIUtils
        from lumino.contracts_client.constants import MIN_ESCROW_BALANCE

        # Use the interactive topup utility
        client.auto_topup = CLIUtils.interactive_topup(
            check_balances_fn=client.check_balances,
            add_funds_fn=client.add_funds_to_escrow,
            min_balance=MIN_ESCROW_BALANCE,
            auto_topup_config=client.auto_topup
        )

        # Update and save user data
        client.user_data["auto_topup"] = client.auto_topup
        client.save_user_data()

    except Exception as e:
        client.logger.error(f"Error managing topup: {e}")
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.pass_obj
def list(client: LuminoUser):
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
