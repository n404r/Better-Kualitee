#!/usr/bin/env python3
"""
Kualitee Test Cycle Management Module
"""

import json
import csv
import logging
import mimetypes
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from logging.handlers import RotatingFileHandler

import requests
from requests.exceptions import RequestException
from rich.console import Console
from rich.table import Table
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.panel import Panel

# Configuration
BASE_URL = "https://apiss3.kualitee.com/api/v2"
ALLOWED_EXTENSIONS = {
    'gif', 'jpg', 'png', 'jpeg', 'pdf', 'docx', 'csv', 
    'xls', 'ppt', 'mp4', 'webm', 'msg', 'eml', 'zip', 'xml', 'pcap'
}

console = Console()

# Track last Ctrl+C time for double-press detection
last_interrupt_time = 0


# Custom exception to signal return to main menu
class MainMenuRequest(Exception):
    """Exception raised to signal a request to return to main menu."""
    pass


def handle_interrupt():
    """Handle Ctrl+C - double press within 2 seconds exits, single press goes back to previous menu."""
    global last_interrupt_time
    current_time = time.time()
    
    if current_time - last_interrupt_time < 2.0:
        # Double press detected - exit
        console.print("\n[yellow]Goodbye!   : ([/yellow]")
        sys.exit(0)
    else:
        # Single press - go back to previous menu
        last_interrupt_time = current_time
        console.print("\n[cyan]Going back... (Press Ctrl+C again to exit)[/cyan]")
        return True  # Signal to return to previous menu


def setup_logging() -> logging.Logger:
    """Setup logging with file handler only - console output via Rich."""
    logger = logging.getLogger('kualitee_test_cycle')
    logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Create logs directory if it doesn't exist
    Path('logs').mkdir(exist_ok=True)
    
    # File handler - always detailed
    file_handler = RotatingFileHandler(
        'logs/test_cycle.log',
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
        console.print("""
{
  "token": "TOKEN_HERE",
  "project_id": 27433
}

""")
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
        return "****"
    return f"{token[:4]}...{token[-4:]}"


def truncate_for_log(data: str, max_length: int = 2000) -> str:
    """Truncate long strings for logging."""
    if len(data) <= max_length:
        return data
    return data[:max_length] + f"... (truncated, {len(data)} total chars)"


class KualiteeAPI:
    """API client for Kualitee."""
    
    def __init__(self, config: Dict, logger: logging.Logger):
        self.config = config
        self.token = config['token']
        self.project_id = config['project_id']
        self.logger = logger
        self.session = requests.Session()
    
    def _log_request(self, method: str, endpoint: str, data: Dict = None):
        """Log API request details."""
        self.logger.info(f"[API] {method} {endpoint}")
        if data:
            # Mask token in logs
            log_data = data.copy()
            if 'token' in log_data:
                log_data['token'] = mask_token(log_data['token'])
            self.logger.debug(f"Request: {json.dumps(log_data, indent=2)}")
    
    def _log_response(self, response: requests.Response, start_time: float):
        """Log API response details."""
        import time
        elapsed = time.time() - start_time
        self.logger.info(f"Response: {response.status_code} ({elapsed:.2f}s)")
        
        try:
            response_data = response.json()
            self.logger.debug(f"Response body: {truncate_for_log(json.dumps(response_data, indent=2))}")
        except:
            self.logger.debug(f"Response body: {truncate_for_log(response.text)}")
    
    def _request(self, method: str, endpoint: str, json_data: Dict = None, 
                 files: Dict = None, data: Dict = None) -> Optional[Dict]:
        """Make API request with logging and error handling."""
        import time
        url = f"{BASE_URL}{endpoint}"
        
        self._log_request(method, endpoint, json_data or data)
        
        try:
            start_time = time.time()
            
            if method == 'POST':
                if files:
                    response = self.session.post(url, data=data, files=files, verify=False)
                else:
                    response = self.session.post(url, json=json_data, verify=False)
            else:
                response = self.session.get(url, verify=False)
            
            self._log_response(response, start_time)
            
            response.raise_for_status()
            return response.json()
        
        except RequestException as e:
            self.logger.error(f"API request failed: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_data = e.response.json()
                    self.logger.error(f"Error response: {error_data}")
                except:
                    self.logger.error(f"Error response: {e.response.text}")
            raise
    
    def list_cycles(self) -> List[Dict]:
        """Get list of test cycles."""
        response = self._request('POST', '/cycle/list', json_data={
            'token': self.token,
            'project_id': self.project_id
        })
        
        if not response or 'data' not in response:
            self.logger.warning("No cycles data in response")
            return []
        
        return response['data']
    
    def list_test_cases(self, cycle_id: int) -> List[Dict]:
        """Get list of test cases for a cycle."""
        response = self._request('POST', '/test_case_execution/list', json_data={
            'token': self.token,
            'project_id': self.project_id,
            'cycle_id': cycle_id,
            'length': 2000
        })
        
        if not response or 'data' not in response:
            self.logger.warning(f"No test cases data in response for cycle {cycle_id}")
            return []
        
        return response['data']
    
    def execute_test(self, tc_id: int, build_id: int, cycle_id: int, 
                    testscenario_id: int) -> Optional[str]:
        """Execute a test case. Returns execution result ID."""
        response = self._request('POST', '/test_case_execution/execute', json_data={
            'token': self.token,
            'project_id': self.project_id,
            'cycle_id': cycle_id,
            'build_id': build_id,
            'tc_id': tc_id,
            'status': 'Passed',
            'execute': 'yes',
            'testscenario_id': testscenario_id
        })
        
        if not response:
            return None
        
        if not response.get('status'):
            self.logger.error(f"Test execution failed: {response.get('message')}")
            return None
        
        if 'executed_results' not in response or not response['executed_results']:
            self.logger.error("No execution results in response")
            return None
        
        execution_id = response['executed_results'][0].get('id')
        self.logger.info(f"Test executed successfully. Execution ID: {execution_id}")
        return execution_id
    
    def upload_attachment(self, testcase_id: int, cycle_id: int, 
                         execution_id: str, file_path: Path) -> bool:
        """Upload attachment to test execution."""
        if not file_path.exists():
            self.logger.error(f"File not found: {file_path}")
            return False
        
        # Validate file extension
        ext = file_path.suffix[1:].lower()
        if ext not in ALLOWED_EXTENSIONS:
            self.logger.error(f"Invalid file type: {ext}. Allowed: {ALLOWED_EXTENSIONS}")
            return False
        
        # Get MIME type
        mime_type, _ = mimetypes.guess_type(str(file_path))
        if not mime_type:
            mime_type = 'application/octet-stream'
        
        try:
            with open(file_path, 'rb') as f:
                files = {'attachment[]': (file_path.name, f, mime_type)}
                data = {
                    'token': self.token,
                    'project_id': str(self.project_id),
                    'cycle_id': str(cycle_id),
                    'testcase_id': str(testcase_id),
                    'execution_id': str(execution_id),
                    'type': 'tc',
                    'sub_testcase_id': ''
                }
                
                response = self._request('POST', '/test_case_execution/execution_attachments',
                                       files=files, data=data)
                
                if response and response.get('status'):
                    self.logger.info(f"Attachment uploaded: {file_path.name}")
                    return True
                else:
                    self.logger.error(f"Attachment upload failed: {response}")
                    return False
        
        except Exception as e:
            self.logger.error(f"Error uploading attachment: {e}")
            return False


def show_test_cycle_menu(ctx):
    """Show interactive test cycle management menu."""
    while True:
        console.clear()
        console.print(Panel.fit(
            "[bold cyan]A Better Kualitee Tool[/bold cyan]\n"
            "      - By Nischay :)\n",
            border_style="cyan"
        ))
        
        console.print("\n[bold]Test Cycle Management Menu[/bold]\n")
        console.print("1. Select Test Cycle")
        console.print("2. Search Cycles by Name")
        console.print("0. Back to Main Menu")
        
        try:
            choice = IntPrompt.ask("\n[cyan]Enter your choice[/cyan]", choices=["0", "1", "2"])
            
            if choice == 1:
                select_cycle_interactive(ctx)
            elif choice == 2:
                search_and_select_cycle_interactive(ctx)
            elif choice == 0:
                return  # Return to main menu
        except KeyboardInterrupt:
            console.print("\n[cyan]Going back...[/cyan]")
            return
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            input("\nPress Enter to continue...")


def select_cycle_interactive(ctx):
    """Select a test cycle from numbered list."""
    api = ctx.obj['api']
    logger = ctx.obj['logger']
    
    console.print("\n[blue]Fetching cycles...[/blue]")
    
    try:
        cycles_data = api.list_cycles()
        
        if not cycles_data:
            console.print("[yellow]No cycles found[/yellow]")
            input("\nPress Enter to return to main menu...")
            return
        
        # Loop to allow going back to cycle list
        while True:
            console.clear()
            console.print(Panel.fit(
                "[bold cyan]A Better Kualitee Tool[/bold cyan]\n"
                "      - By Nischay :)\n",
                border_style="cyan"
            ))
            
            # Display in table with serial numbers
            table = Table(title="\nTest Cycles - Select by Number", show_header=True, header_style="bold magenta")
            table.add_column("#", style="cyan", no_wrap=True)
            table.add_column("Cycle ID", style="blue", no_wrap=True)
            table.add_column("Cycle Name", style="green")
            table.add_column("Status", style="yellow")
            
            for idx, cycle in enumerate(cycles_data, 1):
                table.add_row(
                    str(idx),
                    str(cycle.get('id', '')),
                    cycle.get('cycle_name', ''),
                    cycle.get('status', '')
                )
            
            console.print(table)
            console.print(f"\n[green]Total cycles: {len(cycles_data)}[/green]")
            console.print("\n9. Back to Main Menu")
            console.print("0. Main Menu")
            
            # Get user selection
            choice = IntPrompt.ask(f"\n[cyan]Select cycle (1-{len(cycles_data)})[/cyan]", default=9)
            
            if choice == 9:
                return  # Back to main menu
            
            if choice == 0:
                raise MainMenuRequest()  # Jump to main menu
            
            if choice < 1 or choice > len(cycles_data):
                console.print("[red]Invalid selection[/red]")
                input("\nPress Enter to continue...")
                continue
            
            # Show cycle detail menu
            selected_cycle = cycles_data[choice - 1]
            try:
                show_cycle_menu(ctx, selected_cycle)
            except MainMenuRequest:
                raise  # Propagate to main menu
            # If show_cycle_menu returns normally (user pressed 9), loop continues
    
    except MainMenuRequest:
        return  # Return to main menu
    except KeyboardInterrupt:
        handle_interrupt()
        return
    except Exception as e:
        console.print(f"[red]Error listing cycles: {e}[/red]")
        logger.error(f"Error listing cycles: {e}", exc_info=True)
        input("\nPress Enter to return to main menu...")


def search_and_select_cycle_interactive(ctx):
    """Search cycles by name and select one."""
    api = ctx.obj['api']
    logger = ctx.obj['logger']
    
    try:
        search_term = Prompt.ask("\n[cyan]Enter cycle name to search (blank to cancel)[/cyan]")
        if not search_term:
            return
        
        console.print(f"\n[blue]Searching for cycles containing '{search_term}'...[/blue]")
        cycles_data = api.list_cycles()
        
        if not cycles_data:
            console.print("[yellow]No cycles found[/yellow]")
            input("\nPress Enter to return to main menu...")
            return
        
        # Filter cycles
        filtered = [c for c in cycles_data if search_term.lower() in c.get('cycle_name', '').lower()]
        
        if not filtered:
            console.print(f"[yellow]No cycles found matching '{search_term}'[/yellow]")
            input("\nPress Enter to return to main menu...")
            return
        
        # Loop to allow going back to search results
        while True:
            console.clear()
            console.print(Panel.fit(
                "[bold cyan]A Better Kualitee Tool[/bold cyan]\n"
                "      - By Nischay :)\n",
                border_style="cyan"
            ))
            
            # Display results with serial numbers
            table = Table(title=f"\nSearch Results for '{search_term}' - Select by Number", show_header=True, header_style="bold magenta")
            table.add_column("#", style="cyan", no_wrap=True)
            table.add_column("Cycle ID", style="blue", no_wrap=True)
            table.add_column("Cycle Name", style="green")
            table.add_column("Status", style="yellow")
            
            for idx, cycle in enumerate(filtered, 1):
                table.add_row(
                    str(idx),
                    str(cycle.get('id', '')),
                    cycle.get('cycle_name', ''),
                    cycle.get('status', '')
                )
            
            console.print(table)
            console.print(f"\n[green]Found {len(filtered)} cycle(s)[/green]")
            console.print("\n9. Back to Main Menu")
            console.print("0. Main Menu")
            
            # Get user selection
            choice = IntPrompt.ask(f"\n[cyan]Select cycle (1-{len(filtered)})[/cyan]", default=9)
            
            if choice == 9:
                return  # Back to main menu
            
            if choice == 0:
                raise MainMenuRequest()  # Jump to main menu
            
            if choice < 1 or choice > len(filtered):
                console.print("[red]Invalid selection[/red]")
                input("\nPress Enter to continue...")
                continue
            
            # Show cycle detail menu
            selected_cycle = filtered[choice - 1]
            try:
                show_cycle_menu(ctx, selected_cycle)
            except MainMenuRequest:
                raise  # Propagate to main menu
            # If show_cycle_menu returns normally (user pressed 9), loop continues
    
    except MainMenuRequest:
        return  # Return to main menu
    except KeyboardInterrupt:
        handle_interrupt()
        return
    except Exception as e:
        console.print(f"[red]Error searching cycles: {e}[/red]")
        logger.error(f"Error searching cycles: {e}", exc_info=True)
        input("\nPress Enter to return to main menu...")


def show_cycle_menu(ctx, cycle):
    """Show menu for selected cycle with test cases and execution options."""
    api = ctx.obj['api']
    logger = ctx.obj['logger']
    cycle_id = cycle.get('id')
    cycle_name = cycle.get('cycle_name')
    
    while True:
        try:
            console.clear()
            console.print(Panel.fit(
                "[bold cyan]A Better Kualitee Tool[/bold cyan]\n"
                "      - By Nischay :)\n"
                f"\n[yellow]Cycle:[/yellow] {cycle_name}\n"
                f"[yellow]ID:[/yellow] {cycle_id}",
                border_style="cyan"
            ))
            
            # Fetch and display test cases
            console.print("\n[blue]Loading test cases...[/blue]")
            test_cases = api.list_test_cases(cycle_id)
            
            if not test_cases:
                console.print("[yellow]No test cases found in this cycle[/yellow]")
                input("\nPress Enter to return to main menu...")
                return
            
            # Display test cases with serial numbers and status
            table = Table(title="\nTest Cases", show_header=True, header_style="bold magenta", show_lines=True)
            table.add_column("#", style="cyan", no_wrap=True)
            table.add_column("Test ID", style="blue", no_wrap=True)
            table.add_column("Test Name", style="green")
            table.add_column("Status", style="yellow")
            table.add_column("Summary", style="white", max_width=30)
            table.add_column("Attachment", style="magenta", no_wrap=True)
            table.add_column("Executed By", style="bright_cyan", no_wrap=True)
            
            for idx, tc in enumerate(test_cases, 1):
                executed_by = tc.get('executed_by', '-')
                has_attachment = "Yes" if tc.get('attachments_exist', '0') == '1' else "No"
                summary = tc.get('summary', '')
                
                # Truncate summary from middle if too long
                if len(summary) > 50:
                    summary = summary[:22] + '...' + summary[-22:]
                
                table.add_row(
                    str(idx),
                    str(tc.get('testcase_id', '')),
                    tc.get('tc_name', ''),
                    tc.get('status', ''),
                    summary,
                    has_attachment,
                    executed_by
                )
            
            console.print(table)
            console.print(f"\n[green]Total test cases: {len(test_cases)}[/green]")
            
            # Show options menu
            console.print("\n[bold]Cycle Actions:[/bold]\n")
            console.print("1. Execute single test (select by number)")
            console.print("2. Execute all tests (requires CSV file)")
            console.print("3. Search test by name")
            console.print("9. Back")
            console.print("0. Main Menu")
            
            choice = IntPrompt.ask("\n[cyan]Enter your choice[/cyan]", choices=["0", "1", "2", "3", "9"])
            
            if choice == 1:
                execute_single_from_list(ctx, cycle_id, test_cases)
            elif choice == 2:
                execute_all_from_csv(ctx, cycle_id, test_cases)
            elif choice == 3:
                search_test_in_cycle(ctx, cycle_id, test_cases)
            elif choice == 9:
                return  # Go back to previous menu
            elif choice == 0:
                raise MainMenuRequest()  # Jump to main menu
        
        except MainMenuRequest:
            raise  # Re-raise to propagate to parent
        except KeyboardInterrupt:
            handle_interrupt()
            return
        except Exception as e:
            console.print(f"\n[red]Error: {e}[/red]")
            logger.error(f"Error in cycle menu: {e}", exc_info=True)
            input("\nPress Enter to continue...")


def execute_single_from_list(ctx, cycle_id, test_cases):
    """Execute a single test selected from the list."""
    api = ctx.obj['api']
    logger = ctx.obj['logger']
    
    try:
        console.print("[dim]Enter 0 to cancel[/dim]")
        choice = IntPrompt.ask(f"\n[cyan]Select test to execute (1-{len(test_cases)})[/cyan]", default=0)
        
        if choice == 0:
            return
        
        if choice < 1 or choice > len(test_cases):
            console.print("[red]Invalid selection[/red]")
            input("\nPress Enter to continue...")
            return
        
        test_case = test_cases[choice - 1]
        tc_id = test_case.get('testcase_id')
        
        # Ask for attachment file (mandatory)
        console.print(f"\n[yellow]Allowed file types:[/yellow] {', '.join(ALLOWED_EXTENSIONS)}")
        attachment_path = Prompt.ask("[cyan]Enter attachment file path[/cyan]")
        
        # Clean up the path (remove PowerShell drag-drop artifacts)
        attachment_path = attachment_path.strip()
        # Remove PowerShell execution operator
        if attachment_path.startswith('& '):
            attachment_path = attachment_path[2:]
        # Remove surrounding quotes (single or double)
        attachment_path = attachment_path.strip('"').strip("'")
        
        # Validate attachment file
        att_file = Path(attachment_path)
        if not att_file.exists():
            console.print(f"[red]File not found: {attachment_path}[/red]")
            input("\nPress Enter to continue...")
            return
        
        ext = att_file.suffix[1:].lower()
        if ext not in ALLOWED_EXTENSIONS:
            console.print(f"[red]Invalid file type: {ext}[/red]")
            console.print(f"[yellow]Allowed types: {', '.join(ALLOWED_EXTENSIONS)}[/yellow]")
            input("\nPress Enter to continue...")
            return
        
        # Execute the test
        console.print(f"\n[blue]Executing test: {test_case.get('tc_name')}...[/blue]")
        
        execution_id = api.execute_test(
            tc_id=tc_id,
            build_id=test_case.get('build_id'),
            cycle_id=cycle_id,
            testscenario_id=test_case.get('testscenario_id')
        )
        
        if not execution_id:
            console.print(f"\n[red]✗ Test execution failed[/red]")
            input("\nPress Enter to continue...")
            return
        
        console.print(f"[green]✓ Test executed successfully![/green]")
        console.print(f"Execution ID: {execution_id}")
        
        # Upload attachment
        console.print(f"\n[blue]Uploading attachment: {att_file.name}...[/blue]")
        upload_success = api.upload_attachment(
            testcase_id=tc_id,
            cycle_id=cycle_id,
            execution_id=execution_id,
            file_path=att_file
        )
        
        if upload_success:
            console.print(f"[green]✓ Attachment uploaded successfully![/green]")
        else:
            console.print(f"[red]✗ Attachment upload failed[/red]")
        
        input("\nPress Enter to continue...")
    
    except KeyboardInterrupt:
        handle_interrupt()
        return
    except Exception as e:
        console.print(f"[red]Error executing test: {e}[/red]")
        logger.error(f"Error executing test: {e}", exc_info=True)
        input("\nPress Enter to continue...")


def execute_all_from_csv(ctx, cycle_id, test_cases):
    """Execute all tests using CSV file for bulk execution."""
    api = ctx.obj['api']
    logger = ctx.obj['logger']
    
    try:
        # Show example CSV format
        console.print(f"\n[yellow]Allowed file types:[/yellow] {', '.join(ALLOWED_EXTENSIONS)}")
        
        # Show example CSV in table format
        console.print("\n[bold cyan]Required CSV Format:[/bold cyan]")
        example_table = Table(show_header=True, header_style="bold cyan", show_lines=True)
        example_table.add_column("test_case_name", style="green")
        example_table.add_column("status", style="yellow")
        example_table.add_column("attachment", style="white")
        
        example_table.add_row("TC_Android_01", "Passed", "C:\\Screenshots\\test1.png")
        example_table.add_row("TC_Android_02", "Passed", "C:\\Screenshots\\test2.jpg")
        example_table.add_row("TC_Android_03", "Passed", "C:\\Screenshots\\test3.png")
        
        console.print(example_table)
        console.print("[dim]Note: Use exact test case names from the list above. Status must be 'Passed' (case-sensitive)[/dim]")
        
        csv_file = Prompt.ask("\n[cyan]Enter CSV file path (blank to cancel)[/cyan]")
        if not csv_file:
            return
        
        # Clean up the path (remove PowerShell drag-drop artifacts)
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
        required_cols = {'test_case_name', 'status', 'attachment'}
        if not required_cols.issubset(set(csv_rows[0].keys())):
            console.print(f"[red]CSV must have columns: {required_cols}[/red]")
            input("\nPress Enter to continue...")
            return
        
        # Create lookup dict
        test_lookup = {tc.get('tc_name'): tc for tc in test_cases}
        
        # Match and validate
        matched = []
        skipped = []
        
        for row in csv_rows:
            tc_name = row['test_case_name']
            status = row['status']
            attachment = row['attachment']
            
            # Check status
            if status != 'Passed':
                skipped.append((tc_name, 'Invalid status (must be "Passed")', None))
                continue
            
            # Match test case
            if tc_name not in test_lookup:
                skipped.append((tc_name, 'Test case not found', attachment))
                continue
            
            # Validate attachment
            attachment_path = Path(attachment)
            if not attachment_path.exists():
                skipped.append((tc_name, f'File not found: {attachment}', attachment))
                continue
            
            ext = attachment_path.suffix[1:].lower()
            if ext not in ALLOWED_EXTENSIONS:
                skipped.append((tc_name, f'Invalid file type: {ext}', attachment))
                continue
            
            matched.append((tc_name, test_lookup[tc_name], attachment_path))
        
        # Show preview
        console.print("\n[bold]Preview:[/bold]")
        
        preview_table = Table(show_header=True, header_style="bold magenta")
        preview_table.add_column("Test Case Name")
        preview_table.add_column("Status")
        preview_table.add_column("Attachment")
        preview_table.add_column("File Size")
        
        for tc_name, tc, att_path in matched:
            file_size = f"{att_path.stat().st_size / 1024:.1f} KB"
            preview_table.add_row(
                tc_name,
                "[green]Will Execute[/green]",
                att_path.name,
                file_size
            )
        
        for tc_name, reason, att in skipped:
            preview_table.add_row(
                tc_name,
                f"[red]Skip: {reason}[/red]",
                att or '',
                ''
            )
        
        console.print(preview_table)
        console.print(f"\n[green]{len(matched)} to execute[/green], [red]{len(skipped)} to skip[/red]")
        
        if not matched:
            console.print("[yellow]Nothing to execute[/yellow]")
            input("\nPress Enter to continue...")
            return
        
        # Confirmation
        if not Confirm.ask("\nProceed with execution?"):
            console.print("[yellow]Cancelled[/yellow]")
            input("\nPress Enter to continue...")
            return
        
        # Execute
        console.print("\n[bold]Executing tests:[/bold]\n")
        
        success_count = 0
        fail_count = 0
        
        for tc_name, tc, att_path in matched:
            console.print(f"[blue]Processing: {tc_name}...[/blue]")
            
            try:
                # Execute test
                execution_id = api.execute_test(
                    tc_id=tc.get('testcase_id'),
                    build_id=tc.get('build_id'),
                    cycle_id=cycle_id,
                    testscenario_id=tc.get('testscenario_id')
                )
                
                if not execution_id:
                    console.print(f"  [red]✗ Execution failed[/red]")
                    fail_count += 1
                    continue
                
                # Upload attachment
                upload_ok = api.upload_attachment(
                    testcase_id=tc.get('testcase_id'),
                    cycle_id=cycle_id,
                    execution_id=execution_id,
                    file_path=att_path
                )
                
                if upload_ok:
                    console.print(f"  [green]✓ Executed & uploaded {att_path.name}[/green]")
                    success_count += 1
                else:
                    console.print(f"  [yellow]✓ Executed but upload failed[/yellow]")
                    fail_count += 1
            
            except Exception as e:
                console.print(f"  [red]✗ Error: {e}[/red]")
                logger.error(f"Error processing {tc_name}: {e}", exc_info=True)
                fail_count += 1
        
        # Summary
        console.print("\n[bold]Summary:[/bold]")
        console.print(f"[green]✓ Success: {success_count}[/green]")
        console.print(f"[red]✗ Failed: {fail_count}[/red]")
        console.print(f"[yellow]- Skipped: {len(skipped)}[/yellow]")
        input("\nPress Enter to continue...")
    
    except KeyboardInterrupt:
        handle_interrupt()
        return
    except Exception as e:
        console.print(f"[red]Error in bulk execution: {e}[/red]")
        logger.error(f"Error in bulk execution: {e}", exc_info=True)
        input("\nPress Enter to continue...")


def search_test_in_cycle(ctx, cycle_id, test_cases):
    """Search for a test case within the current cycle."""
    logger = ctx.obj['logger']
    
    try:
        search_term = Prompt.ask("\n[cyan]Enter test name to search (blank to cancel)[/cyan]")
        if not search_term:
            return
        
        # Filter test cases
        filtered = [tc for tc in test_cases if search_term.lower() in tc.get('tc_name', '').lower()]
        
        if not filtered:
            console.print(f"[yellow]No tests found matching '{search_term}'[/yellow]")
            input("\nPress Enter to continue...")
            return
        
        # Display results with numbers
        table = Table(title=f"\nSearch Results for '{search_term}'", show_header=True, header_style="bold magenta")
        table.add_column("#", style="cyan", no_wrap=True)
        table.add_column("Test ID", style="blue", no_wrap=True)
        table.add_column("Test Name", style="green")
        table.add_column("Status", style="yellow")
        
        for idx, tc in enumerate(filtered, 1):
            table.add_row(
                str(idx),
                str(tc.get('testcase_id', '')),
                tc.get('tc_name', ''),
                tc.get('status', '')
            )
        
        console.print(table)
        console.print(f"\n[green]Found {len(filtered)} test case(s)[/green]")
        input("\nPress Enter to continue...")
    
    except KeyboardInterrupt:
        handle_interrupt()
        return
    except Exception as e:
        console.print(f"[red]Error searching test cases: {e}[/red]")
        logger.error(f"Error searching test cases: {e}", exc_info=True)
        input("\nPress Enter to continue...")


def run_test_cycle_management():
    """Entry point for test cycle management module."""
    # Create context object
    class Context:
        def __init__(self):
            self.obj = {}
    
    ctx = Context()
    ctx.obj['logger'] = setup_logging()
    ctx.obj['config'] = load_config()
    ctx.obj['api'] = KualiteeAPI(ctx.obj['config'], ctx.obj['logger'])
    
    # Disable SSL warnings
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Show test cycle management menu
    show_test_cycle_menu(ctx)


if __name__ == '__main__':
    try:
        run_test_cycle_management()
    except KeyboardInterrupt:
        console.print("\n[yellow]Goodbye![/yellow]")
        sys.exit(0)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
