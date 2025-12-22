#!/usr/bin/env python3
"""
Kualitee Defect Management Module
"""

import json
import csv
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.exceptions import RequestException
from rich.console import Console
from rich.table import Table
from rich.prompt import IntPrompt, Prompt
from rich.panel import Panel

# Configuration
BASE_URL = "https://apiss3.kualitee.com/api/v2"

# RCA Options
RCA_OPTIONS = [
    "Application Issues:",
    "Code: Bug",
    "Code: Deployment Issue",
    "Code: Misalignment b/w Prod & Test Lab",
    "Code: Missed during deployment",
    "Configuration: Bug",
    "Configuration: Change",
    "Configuration: Missed",
    "Database issue",
    "Design Issue: Code Change",
    "Design Issue: Design Change",
    "Environment Issues",
    "Infra Issues",
    "Intermittent Connectivity Issues",
    "Production BAU",
    "Req. - NA / OOS",
    "Requirements: Missed",
    "Requirements: New/Change",
    "Retrofit Issue",
    "Service Request (Not Defect)",
    "Test Data: Incorrect test data provided to test team",
    "Test: Duplicate Defect",
    "Test: Incorrect test data used for test",
    "Test: Missed by E2E team",
    "Test: Test Case Error",
    "Test: Test Data issue",
    "Test: Test Device Issue",
    "Test: Test User Error",
]

console = Console()


def setup_logging() -> logging.Logger:
    """Setup logging with file handler only - console output via Rich."""
    logger = logging.getLogger('kualitee_defect')
    logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Create logs directory if it doesn't exist
    Path('logs').mkdir(exist_ok=True)
    
    # File handler - always detailed
    file_handler = RotatingFileHandler(
        'logs/defect.log',
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5
    )
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger


def load_config() -> Dict:
    """Load configuration from config.json."""
    config_path = Path('config.json')
    
    if not config_path.exists():
        console.print("[red]Error: config.json not found![/red]")
        console.print("Create config.json with your token and project_id.")
        sys.exit(1)
    
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        if 'token' not in config or 'project_id' not in config:
            console.print("[red]Error: config.json must contain 'token' and 'project_id'[/red]")
            sys.exit(1)
        
        return config
    except json.JSONDecodeError as e:
        console.print(f"[red]Error: Invalid JSON in config.json: {e}[/red]")
        sys.exit(1)


def mask_token(token: str) -> str:
    """Mask token for logging - show only first and last 4 chars."""
    if len(token) <= 8:
        return '****'
    return f"{token[:4]}...{token[-4:]}"


class KualiteeDefectAPI:
    """Kualitee API client for defect management."""
    
    def __init__(self, token: str, project_id: int, logger: logging.Logger):
        self.token = token
        self.project_id = project_id
        self.logger = logger
        self.session = requests.Session()
        self.session.verify = False  # Disable SSL verification
        
        # Suppress SSL warnings
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        """Make API request with logging."""
        url = f"{BASE_URL}{endpoint}"
        
        # Log request
        self.logger.info(f"[API] {method} {endpoint}")
        if 'json' in kwargs:
            log_data = kwargs['json'].copy()
            if 'token' in log_data:
                log_data['token'] = mask_token(log_data['token'])
            self.logger.debug(f"Request: {json.dumps(log_data, indent=2)}")
        
        # Make request
        import time
        start = time.time()
        response = self.session.request(method, url, **kwargs)
        duration = time.time() - start
        
        # Log response
        self.logger.info(f"Response: {response.status_code} ({duration:.2f}s)")
        
        if response.status_code != 200:
            self.logger.error(f"API Error: {response.text}")
            response.raise_for_status()
        
        result = response.json()
        self.logger.debug(f"Response body: {json.dumps(result, indent=2)[:1000]}")
        
        return result
    
    def list_defects(self, length: int = 2000) -> List[Dict]:
        """
        List all defects in the project.
        
        Args:
            length: Number of defects to retrieve (default 2000)
            
        Returns:
            List of defect dictionaries
        """
        try:
            response = self._request(
                'POST',
                '/defects/list',
                json={
                    'token': self.token,
                    'project_id': self.project_id,
                    'length': length
                }
            )
            
            # Extract data array from response
            defects = response.get('data', [])
            self.logger.info(f"Retrieved {len(defects)} defects")
            return defects
            
        except RequestException as e:
            self.logger.error(f"Failed to list defects: {e}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error listing defects: {e}")
            return []
    
    def get_defect_details(self, defect_id: str) -> Optional[Dict]:
        """
        Get detailed information about a specific defect.
        
        Args:
            defect_id: The defect ID to fetch details for
            
        Returns:
            Defect details dictionary or None if not found
        """
        try:
            response = self._request(
                'GET',
                f'/defects/details?project_id={self.project_id}&defect_id={defect_id}&token={self.token}'
            )
            
            self.logger.info(f"Retrieved details for defect {defect_id}")
            return response
            
        except RequestException as e:
            self.logger.error(f"Failed to get defect details: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error getting defect details: {e}")
            return None
    
    def update_defect(self, defect_id: str, status: str, rca: str, defect_data: Dict) -> bool:
        """
        Update a defect's status and RCA, keeping all other fields unchanged.
        
        Args:
            defect_id: The defect ID to update
            status: New status (should be 'close')
            rca: RCA (Root Cause Analysis) value
            defect_data: Full defect data from get_defect_details
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Start with all existing fields from defect_data
            form_data = {}
            
            # Copy all fields from defect data
            for key, value in defect_data.items():
                if value is None:
                    form_data[key] = ''
                elif isinstance(value, list):
                    # Convert lists to comma-separated strings
                    form_data[key] = ','.join(str(v) for v in value) if value else ''
                elif isinstance(value, dict):
                    # Skip complex objects
                    continue
                else:
                    form_data[key] = str(value)
            
            # Override with new values
            form_data['status'] = status
            form_data['custom_field_11665'] = rca
            
            # Add required fields
            form_data['token'] = self.token
            form_data['project_id'] = str(self.project_id)
            form_data['id'] = defect_id
            form_data['defect_id'] = defect_id
            
            response = self._request(
                'POST',
                '/defects/update',
                data=form_data
            )
            
            self.logger.info(f"Updated defect {defect_id} to status: {status}, RCA: {rca}")
            return True
            
        except RequestException as e:
            self.logger.error(f"Failed to update defect: {e}")
            return False
        except Exception as e:
            self.logger.error(f"Unexpected error updating defect: {e}")
            return False
    
    def get_multiple_defects(self, defect_ids: List[str], max_workers: int = 10) -> Dict[str, Optional[Dict]]:
        """
        Get details for multiple defects using threading.
        
        Args:
            defect_ids: List of defect IDs to fetch
            max_workers: Maximum number of concurrent threads
            
        Returns:
            Dictionary mapping defect_id to defect details
        """
        results = {}
        
        def fetch_defect(defect_id):
            return defect_id, self.get_defect_details(defect_id)
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_defect, did): did for did in defect_ids}
            
            for future in as_completed(futures):
                try:
                    defect_id, details = future.result()
                    results[defect_id] = details
                except Exception as e:
                    defect_id = futures[future]
                    self.logger.error(f"Error fetching defect {defect_id}: {e}")
                    results[defect_id] = None
        
        return results


def search_defect_by_id(api, logger):
    """Search for a specific defect by ID."""
    try:
        defect_id = Prompt.ask("\n[cyan]Enter defect ID to search (blank to cancel)[/cyan]")
        if not defect_id:
            return
        
        console.print(f"\n[blue]Fetching defect details...[/blue]")
        defect = api.get_defect_details(defect_id)
        
        if not defect:
            console.print(f"[yellow]No defect found with ID: {defect_id}[/yellow]")
            input("\nPress Enter to continue...")
            return
        
        # Display defect details
        console.clear()
        console.print(Panel.fit(
            "[bold cyan]Kualitee Defect Management Tool[/bold cyan]\n"
            "      - By Nischay :)\n",
            border_style="cyan"
        ))
        
        console.print(f"\n[bold cyan]Defect #{defect.get('id', 'N/A')}[/bold cyan]\n")
        
        # Basic Information
        console.print("[bold yellow]Basic Information:[/bold yellow]")
        console.print(f"  [bold]Title:[/bold] {defect.get('description', 'N/A')[:100]}")
        console.print(f"  [bold]Status:[/bold] {defect.get('uc_status', 'N/A')}")
        console.print(f"  [bold]Severity:[/bold] {defect.get('uc_severity', 'N/A')}")
        console.print(f"  [bold]Priority:[/bold] {defect.get('uc_priority', 'N/A')}")
        console.print(f"  [bold]Type:[/bold] {defect.get('uc_defect_type', 'N/A')}")
        console.print(f"  [bold]OS:[/bold] {defect.get('uc_os_type', 'N/A')}")
        console.print(f"  [bold]Devices:[/bold] {defect.get('uc_devices', 'N/A')}")
        console.print(f"  [bold]Created:[/bold] {defect.get('created_on', 'N/A')}")
        console.print(f"  [bold]Aging:[/bold] {defect.get('defect_aging', 'N/A')}")
        
        # Build & Module
        console.print(f"\n[bold yellow]Build & Module:[/bold yellow]")
        console.print(f"  [bold]Build:[/bold] {defect.get('build_name', 'N/A')}")
        console.print(f"  [bold]Module:[/bold] {defect.get('module_name', 'N/A')}")
        console.print(f"  [bold]Cycle:[/bold] {defect.get('cycle_name', 'N/A')}")
        
        # Custom Fields
        if defect.get('custom_fields'):
            console.print(f"\n[bold yellow]Custom Fields:[/bold yellow]")
            for field in defect['custom_fields']:
                label = field.get('custom_field_label', 'Unknown')
                value = field.get('custom_field_value', 'N/A')
                if value and value != "":
                    console.print(f"  [bold]{label}:[/bold] {value}")
        
        # Comments History
        if defect.get('bug_comments'):
            console.print(f"\n[bold yellow]Comments History:[/bold yellow]")
            for comment in defect['bug_comments']:
                console.print(f"  [{comment.get('date', 'N/A')}] {comment.get('commented_by', 'Unknown')} → {comment.get('status', 'N/A')}")
                if comment.get('comment'):
                    console.print(f"    {comment['comment']}")
        
        input("\n\nPress Enter to continue...")
        
    except KeyboardInterrupt:
        console.print("\n[cyan]Going back...[/cyan]")
        return
    except Exception as e:
        console.print(f"[red]Error searching defect: {e}[/red]")
        logger.error(f"Error searching defect: {e}", exc_info=True)
        input("\nPress Enter to continue...")


def update_single_defect(api, logger):
    """Update a single defect."""
    try:
        defect_id = Prompt.ask("\n[cyan]Enter defect ID to update (blank to cancel)[/cyan]")
        if not defect_id:
            return
        
        console.print(f"\n[blue]Fetching defect details...[/blue]")
        defect = api.get_defect_details(defect_id)
        
        if not defect:
            console.print(f"[yellow]No defect found with ID: {defect_id}[/yellow]")
            input("\nPress Enter to continue...")
            return
        
        # Show current status
        current_status = defect.get('status', '').lower()
        console.print(f"\n[bold]Current Status:[/bold] {defect.get('uc_status', 'N/A')}")
        console.print(f"[bold]Current RCA:[/bold] {defect.get('custom_field_11665', 'N/A')}")
        console.print(f"[bold]Description:[/bold] {defect.get('description', 'N/A')}")
        
        # Check if already closed
        if current_status == 'close':
            console.print("\n[yellow]⚠ This defect is already closed. No update needed.[/yellow]")
            input("\nPress Enter to continue...")
            return
        
        # Status is always 'close'
        status = 'close'
        
        # Display RCA options
        console.print("\n[bold cyan]Select Root Cause Analysis (RCA):[/bold cyan]")
        rca_table = Table(show_header=True, header_style="bold magenta")
        rca_table.add_column("#", style="cyan", width=4)
        rca_table.add_column("RCA Option", style="yellow")
        
        for idx, option in enumerate(RCA_OPTIONS, 1):
            rca_table.add_row(str(idx), option)
        
        console.print(rca_table)
        
        # Get RCA selection
        while True:
            try:
                selection = IntPrompt.ask(
                    f"\n[cyan]Select RCA option (1-{len(RCA_OPTIONS)})[/cyan]"
                )
                if 1 <= selection <= len(RCA_OPTIONS):
                    rca = RCA_OPTIONS[selection - 1]
                    break
                else:
                    console.print(f"[red]Please enter a number between 1 and {len(RCA_OPTIONS)}[/red]")
            except Exception:
                console.print("[red]Invalid input. Please enter a number.[/red]")
        
        console.print(f"\n[green]Selected RCA: {rca}[/green]")
        
        # Confirm
        console.print(f"\n[yellow]About to close defect {defect_id} with RCA: {rca}[/yellow]")
        
        confirm = Prompt.ask("\n[cyan]Proceed? (y/n)[/cyan]", default="n")
        if confirm.lower() != "y":
            console.print("[yellow]Update cancelled[/yellow]")
            input("\nPress Enter to continue...")
            return
        
        # Update
        console.print(f"\n[blue]Updating defect...[/blue]")
        success = api.update_defect(defect_id, status, rca, defect)
        
        if success:
            console.print(f"[green]✓ Defect {defect_id} updated successfully![/green]")
        else:
            console.print(f"[red]✗ Failed to update defect {defect_id}[/red]")
        
        input("\nPress Enter to continue...")
        
    except KeyboardInterrupt:
        console.print("\n[cyan]Going back...[/cyan]")
        return
    except Exception as e:
        console.print(f"[red]Error updating defect: {e}[/red]")
        logger.error(f"Error updating defect: {e}", exc_info=True)
        input("\nPress Enter to continue...")


def update_bulk_defects(api, logger):
    """Update multiple defects from CSV file."""
    try:
        console.print("\n[bold cyan]Required CSV Format:[/bold cyan]")
        
        # Show example CSV in table format
        example_table = Table(show_header=True, header_style="bold cyan", show_lines=True)
        example_table.add_column("defect_id", style="green")
        example_table.add_column("status", style="yellow")
        example_table.add_column("RCA", style="white")
        
        example_table.add_row("265744", "close", "Configuration: Bug")
        example_table.add_row("265745", "close", "Code: Bug")
        example_table.add_row("265746", "close", "Design Issue: Code Change")
        
        console.print(example_table)
        console.print("[dim]Note: Status must be 'close' (case-insensitive). CSV header row must be: defect_id,status,RCA[/dim]")
        
        csv_file = Prompt.ask("\n[cyan]Enter CSV file path (blank to cancel)[/cyan]")
        if not csv_file:
            return
        
        # Clean up path
        csv_file = csv_file.strip()
        if csv_file.startswith('& '):
            csv_file = csv_file[2:]
        csv_file = csv_file.strip('"').strip("'")
        
        # Read CSV
        csv_path = Path(csv_file)
        if not csv_path.exists():
            console.print(f"[red]File not found: {csv_file}[/red]")
            input("\nPress Enter to continue...")
            return
        
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            csv_rows = list(reader)
        
        if not csv_rows:
            console.print("[red]CSV file is empty[/red]")
            input("\nPress Enter to continue...")
            return
        
        # Validate CSV columns
        required_cols = {'defect_id', 'status', 'RCA'}
        if not required_cols.issubset(set(csv_rows[0].keys())):
            console.print(f"[red]CSV must have columns: {required_cols}[/red]")
            input("\nPress Enter to continue...")
            return
        
        # Extract defect IDs
        defect_ids = [row['defect_id'] for row in csv_rows]
        
        # Fetch all defect details using threading
        console.print(f"\n[blue]Fetching details for {len(defect_ids)} defects using threading...[/blue]")
        defects_data = api.get_multiple_defects(defect_ids)
        
        # Validate and prepare
        valid = []
        skipped = []
        
        for row in csv_rows:
            defect_id = row['defect_id']
            status = row['status']
            rca = row['RCA']
            
            # Check status
            if status.lower() != 'close':
                skipped.append((defect_id, f'Invalid status: {status} (must be "close")'))
                continue
            
            # Check if defect exists
            defect = defects_data.get(defect_id)
            if not defect:
                skipped.append((defect_id, 'Defect not found'))
                continue
            
            # Check if already closed
            current_status = defect.get('status', '').lower()
            if current_status == 'close':
                skipped.append((defect_id, 'Already closed'))
                continue
            
            valid.append((defect_id, status, rca, defect))
        
        # Show preview
        console.print("\n[bold]Preview:[/bold]")
        
        preview_table = Table(show_header=True, header_style="bold magenta", show_lines=True)
        preview_table.add_column("Defect ID", style="cyan")
        preview_table.add_column("Current Status", style="yellow")
        preview_table.add_column("New Status", style="green")
        preview_table.add_column("RCA", style="white")
        preview_table.add_column("Result", style="white")
        
        for defect_id, status, rca, defect in valid:
            preview_table.add_row(
                defect_id,
                defect.get('uc_status', 'N/A'),
                status,
                rca[:40],
                "[green]Will Update[/green]"
            )
        
        for defect_id, reason in skipped:
            preview_table.add_row(
                defect_id,
                "-",
                "-",
                "-",
                f"[red]Skip: {reason}[/red]"
            )
        
        console.print(preview_table)
        console.print(f"\n[green]{len(valid)} to update[/green], [red]{len(skipped)} to skip[/red]")
        
        # Confirm
        if not valid:
            console.print("[yellow]No valid defects to update[/yellow]")
            input("\nPress Enter to continue...")
            return
        
        confirm = Prompt.ask("\n[cyan]Proceed with bulk update? (yes/no)[/cyan]", default="no")
        if confirm.lower() != "yes":
            console.print("[yellow]Update cancelled[/yellow]")
            input("\nPress Enter to continue...")
            return
        
        # Execute updates
        console.print("\n[blue]Updating defects...[/blue]")
        success_count = 0
        fail_count = 0
        
        for defect_id, status, rca, defect in valid:
            console.print(f"  Updating {defect_id}...", end=" ")
            
            if api.update_defect(defect_id, status, rca, defect):
                console.print("[green]✓[/green]")
                success_count += 1
            else:
                console.print("[red]✗[/red]")
                fail_count += 1
        
        # Summary
        console.print("\n[bold]Summary:[/bold]")
        console.print(f"[green]✓ Success: {success_count}[/green]")
        console.print(f"[red]✗ Failed: {fail_count}[/red]")
        console.print(f"[yellow]- Skipped: {len(skipped)}[/yellow]")
        input("\nPress Enter to continue...")
        
    except KeyboardInterrupt:
        console.print("\n[cyan]Going back...[/cyan]")
        return
    except Exception as e:
        console.print(f"[red]Error in bulk update: {e}[/red]")
        logger.error(f"Error in bulk update: {e}", exc_info=True)
        input("\nPress Enter to continue...")


def show_defect_menu(api, logger):
    """Show interactive defect management menu."""
    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold cyan]Kualitee Defect Management Tool[/bold cyan]\n"
            "      - By Nischay :)\n",
            border_style="cyan"
        ))
        
        console.print("\n[bold]Defect Management Menu[/bold]\n")
        console.print("1. Search Defect by ID")
        console.print("2. Update Single Defect")
        console.print("3. Update Bulk Defects (CSV)")
        console.print("0. Back to Main Menu")
        
        try:
            choice = IntPrompt.ask("\n[cyan]Enter your choice[/cyan]", choices=["0", "1", "2", "3"])
            
            if choice == 1:
                search_defect_by_id(api, logger)
            elif choice == 2:
                update_single_defect(api, logger)
            elif choice == 3:
                update_bulk_defects(api, logger)
            elif choice == 0:
                return  # Return to main menu
        except KeyboardInterrupt:
            console.print("\n[cyan]Going back...[/cyan]")
            return
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            input("\nPress Enter to continue...")


def run_defect_management():
    """Entry point for defect management module."""
    # Setup
    logger = setup_logging()
    config = load_config()
    
    api = KualiteeDefectAPI(
        token=config['token'],
        project_id=config['project_id'],
        logger=logger
    )
    
    # Show defect management menu
    show_defect_menu(api, logger)


if __name__ == '__main__':
    try:
        run_defect_management()
    except KeyboardInterrupt:
        console.print("\n[yellow]Goodbye![/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
