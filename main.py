#!/usr/bin/env python3
"""
Kualitee Management Tool - Main Entry Point
"""

import sys
from rich.console import Console
from rich.prompt import IntPrompt
from rich.panel import Panel

console = Console()


def show_main_menu():
    """Display main menu and route to selected module."""
    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold cyan]Kualitee Management Tool[/bold cyan]\n"
            "      - By Nischay :)\n",
            border_style="cyan"
        ))
        
        console.print("\n[bold]Select Module[/bold]\n")
        console.print("1. Test Cycle Management")
        console.print("2. Defect Management")
        console.print("0. Exit")
        
        try:
            choice = IntPrompt.ask("\n[cyan]Enter your choice[/cyan]", choices=["0", "1", "2"])
            
            if choice == 1:
                # Import and run test cycle management
                from modules import test_cycle
                test_cycle.run_test_cycle_management()
            elif choice == 2:
                # Import and run defect management
                from modules import defect
                defect.run_defect_management()
            elif choice == 0:
                console.print("\n[yellow]Goodbye![/yellow]")
                sys.exit(0)
        except KeyboardInterrupt:
            console.print("\n\n[yellow]Goodbye![/yellow]")
            sys.exit(0)
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            input("\nPress Enter to continue...")


def main():
    """Main entry point."""
    try:
        show_main_menu()
    except KeyboardInterrupt:
        console.print("\n[yellow]Goodbye![/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Critical Error: {e}[/red]")
        sys.exit(1)


if __name__ == '__main__':
    main()
