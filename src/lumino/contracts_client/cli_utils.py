"""CLI utility functions for Lumino contracts client"""
from typing import Dict, Optional, Any, Callable

import click
from lumino.contracts_client.constants import MIN_ESCROW_BALANCE


class CLIUtils:
    """Utility functions for command-line interfaces"""

    @staticmethod
    def interactive_topup(
            check_balances_fn: Callable[[], Dict[str, float]],
            add_funds_fn: Callable[[float], None],
            min_balance: float = MIN_ESCROW_BALANCE,
            auto_topup_config: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Interactive escrow balance management and auto-topup configuration
        
        Args:
            check_balances_fn: Function that returns current balances dict
            add_funds_fn: Function to add funds to escrow
            min_balance: Minimum required balance
            auto_topup_config: Current auto-topup configuration
            
        Returns:
            Updated auto-topup configuration
        """
        if auto_topup_config is None:
            auto_topup_config = {
                "enabled": False,
                "amount": float(min_balance),
                "auto_yes_min": False,
                "auto_yes_additional": 0.0
            }

        # Check current balances
        balances = check_balances_fn()
        escrow_balance = balances["escrow_balance"]
        token_balance = balances["token_balance"]

        click.echo(f"Current Escrow Balance: {escrow_balance} LUM")
        click.echo(f"Minimum Required Balance: {min_balance} LUM")
        click.echo(f"Available Token Balance: {token_balance} LUM")

        # Check if balance is below minimum
        if escrow_balance < min_balance:
            deficit = float(min_balance - escrow_balance)
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
                    return auto_topup_config
                add_funds_fn(total_topup)
                click.echo(f"Successfully deposited {total_topup} LUM")

        # Auto-topup configuration
        click.echo("\nCurrent auto-topup settings:")
        click.echo(f"Enabled: {auto_topup_config['enabled']}")
        click.echo(f"Minimum topup amount: {auto_topup_config['amount']} LUM")
        click.echo(f"Auto-yes to minimum: {auto_topup_config['auto_yes_min']}")
        click.echo(f"Auto-yes additional amount: {auto_topup_config['auto_yes_additional']} LUM")

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
                auto_topup_config = {
                    "enabled": True,
                    "amount": float(min_balance),
                    "auto_yes_min": auto_yes_min,
                    "auto_yes_additional": additional
                }
            else:
                auto_topup_config = {
                    "enabled": False,
                    "amount": float(min_balance),
                    "auto_yes_min": False,
                    "auto_yes_additional": 0.0
                }
            click.echo("Auto-topup settings updated successfully")

        # Show final balance
        balances = check_balances_fn()
        click.echo(f"\nFinal balances - Token: {balances['token_balance']} LUM, "
                   f"Escrow: {balances['escrow_balance']} LUM")

        return auto_topup_config
