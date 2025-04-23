#!/usr/bin/env python3
import os
import time
import datetime
import subprocess
import signal
import sys
import re
import argparse
from pathlib import Path

# Global variables
MONITOR_PID_FILE = os.path.expanduser("~/terminal_monitor/monitor.pid")
LOG_FILE = os.path.expanduser("~/terminal_monitor/terminal_commands.log")

def ensure_required_packages():
    """Install required packages if they're not already installed."""
    try:
        import pexpect
    except ImportError:
        print("Installing required package: pexpect")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pexpect"])

def create_monitor_dir():
    """Create the monitor directory if it doesn't exist."""
    monitor_dir = os.path.dirname(LOG_FILE)
    os.makedirs(monitor_dir, exist_ok=True)
    return monitor_dir

def log_command(command, log_file=LOG_FILE):
    """Log a command with timestamp to the specified file."""
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(log_file, 'a') as f:
        f.write(f"[{timestamp}] {command.strip()}\n")
        f.flush()  # Ensure it's written immediately

def start_monitoring():
    """Set up monitoring of terminal commands."""
    # Ensure we have necessary packages
    ensure_required_packages()
    
    # Create monitor directory and log file
    create_monitor_dir()
    
    print(f"Starting terminal command monitor...")
    print(f"Commands will be logged to: {LOG_FILE}")
    print("Running in background. Process ID:", os.getpid())
    
    # Save PID to file
    with open(MONITOR_PID_FILE, 'w') as f:
        f.write(str(os.getpid()))
    
    # Add a hook to the terminal configuration files
    setup_terminal_hooks(LOG_FILE)
    
    # Keep the script running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping terminal command monitor.")
        cleanup_hooks()
        # Remove PID file
        try:
            os.remove(MONITOR_PID_FILE)
        except:
            pass

def setup_terminal_hooks(log_file):
    """Set up hooks in the shell configuration files."""
    # For Bash
    bash_rc = os.path.expanduser("~/.bashrc")
    bash_hook = f'\nfunction log_command() {{ command_entered="$BASH_COMMAND"; echo "$command_entered" >> "{log_file}"; }}\ntrap log_command DEBUG\n'
    
    # For Zsh
    zsh_rc = os.path.expanduser("~/.zshrc")
    zsh_hook = f'\npreexec() {{ echo "$1" >> "{log_file}"; }}\n'
    
    # Add hooks to config files if they don't already contain them
    for config_file, hook in [(bash_rc, bash_hook), (zsh_rc, zsh_hook)]:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                content = f.read()
            
            if log_file not in content:
                with open(config_file, 'a') as f:
                    f.write(hook)
                print(f"Added command logging hook to {config_file}")
                print(f"Please restart your terminal or run 'source {config_file}' to activate monitoring")

def cleanup_hooks():
    """Remove the hooks from shell configuration files."""
    for config_file in [os.path.expanduser("~/.bashrc"), os.path.expanduser("~/.zshrc")]:
        if os.path.exists(config_file):
            with open(config_file, 'r') as f:
                lines = f.readlines()
            
            with open(config_file, 'w') as f:
                for line in lines:
                    if "log_command" not in line and "trap log_command DEBUG" not in line and "preexec()" not in line:
                        f.write(line)

def run_as_daemon():
    """Run the script as a daemon process."""
    # Create monitor directory if it doesn't exist
    create_monitor_dir()
    
    # Check if monitor is already running
    if os.path.exists(MONITOR_PID_FILE):
        with open(MONITOR_PID_FILE, 'r') as f:
            pid = f.read().strip()
        
        try:
            # Check if process is still running
            os.kill(int(pid), 0)
            print(f"Monitor already running with PID: {pid}")
            return
        except OSError:
            # Process not running, remove stale PID file
            os.remove(MONITOR_PID_FILE)
    
    # Fork the process
    try:
        pid = os.fork()
        if pid > 0:
            # Exit the parent process
            print(f"Monitor running in background with PID: {pid}")
            sys.exit(0)
    except OSError:
        print("Error: Unable to fork")
        sys.exit(1)
    
    # Detach from the parent environment
    os.chdir('/')
    os.setsid()
    os.umask(0)
    
    # Fork again
    try:
        pid = os.fork()
        if pid > 0:
            # Exit from the second parent
            sys.exit(0)
    except OSError:
        print("Error: Unable to fork second time")
        sys.exit(1)
    
    # Redirect standard file descriptors
    sys.stdout.flush()
    sys.stderr.flush()
    
    si = open(os.devnull, 'r')
    so = open(os.devnull, 'a+')
    se = open(os.devnull, 'a+')
    
    os.dup2(si.fileno(), sys.stdin.fileno())
    os.dup2(so.fileno(), sys.stdout.fileno())
    os.dup2(se.fileno(), sys.stderr.fileno())
    
    # Start the monitoring
    start_monitoring()

def search_command_log(search_term, log_file=LOG_FILE, case_sensitive=False, show_time=True, 
                      limit=None, regex=False, before=0, after=0):
    """
    Search for matching commands in the command log file
    
    Args:
        search_term (str): Term to search for in commands
        log_file (str): Path to log file
        case_sensitive (bool): Whether search should be case sensitive
        show_time (bool): Whether to show timestamps in results
        limit (int): Maximum number of results to show
        regex (bool): Whether to treat search_term as a regular expression
        before (int): Number of commands to show before each match
        after (int): Number of commands to show after each match
    """
    # Check if monitor is running
    if not os.path.exists(MONITOR_PID_FILE):
        print("Error: Terminal monitor doesn't appear to be running.")
        print("Start the monitor first with: terminal_monitor start")
        sys.exit(1)
    
    # Check if log file exists
    if not os.path.exists(log_file):
        print(f"Error: Log file not found at {log_file}")
        print("Make sure the terminal monitoring script is running.")
        sys.exit(1)
    
    try:
        # Read all lines from the log file
        with open(log_file, 'r') as f:
            lines = f.readlines()
        
        # Prepare search function based on settings
        if regex:
            try:
                if case_sensitive:
                    pattern = re.compile(search_term)
                else:
                    pattern = re.compile(search_term, re.IGNORECASE)
                search_func = lambda cmd: pattern.search(cmd) is not None
            except re.error as e:
                print(f"Error in regular expression: {e}")
                sys.exit(1)
        else:
            if case_sensitive:
                search_func = lambda cmd: search_term in cmd
            else:
                search_term = search_term.lower()
                search_func = lambda cmd: search_term in cmd.lower()
        
        # Extract command part and perform search
        matches = []
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            # Extract timestamp and command
            try:
                # Format: [YYYY-MM-DD HH:MM:SS] command
                timestamp_end = line.find(']')
                if timestamp_end > 0:
                    timestamp = line[1:timestamp_end]
                    command = line[timestamp_end+1:].strip()
                else:
                    timestamp = ""
                    command = line
            except Exception:
                timestamp = ""
                command = line
            
            # Check if this line matches the search criteria
            if search_func(command):
                matches.append((i, timestamp, command))
        
        # Apply limit if specified
        if limit and len(matches) > limit:
            matches = matches[-limit:]
        
        # Display results with context if requested
        if matches:
            print(f"Found {len(matches)} matching commands:")
            print("-" * 60)
            
            lines_shown = set()  # Keep track of lines already displayed

            for match_index, timestamp, command in matches:
                # Show lines before the match if requested
                if before > 0:
                    start_idx = max(0, match_index - before)
                    for i in range(start_idx, match_index):
                        if i not in lines_shown:
                            context_line = lines[i].strip()
                            if context_line:
                                # Parse the context line
                                try:
                                    ts_end = context_line.find(']')
                                    ctx_timestamp = context_line[1:ts_end] if ts_end > 0 else ""
                                    ctx_command = context_line[ts_end+1:].strip() if ts_end > 0 else context_line
                                    
                                    if show_time and ctx_timestamp:
                                        print(f"\033[90m[{ctx_timestamp}]\033[0m {ctx_command}")
                                    else:
                                        print(f"{ctx_command}")
                                    lines_shown.add(i)
                                except Exception:
                                    print(context_line)
                                    lines_shown.add(i)
                
                # Show the matching line
                if show_time and timestamp:
                    print(f"\033[1;32m[{timestamp}]\033[0m \033[1m{command}\033[0m")
                else:
                    print(f"\033[1m{command}\033[0m")
                lines_shown.add(match_index)
                
                # Show lines after the match if requested
                if after > 0:
                    end_idx = min(len(lines), match_index + after + 1)
                    for i in range(match_index + 1, end_idx):
                        if i not in lines_shown:
                            context_line = lines[i].strip()
                            if context_line:
                                # Parse the context line
                                try:
                                    ts_end = context_line.find(']')
                                    ctx_timestamp = context_line[1:ts_end] if ts_end > 0 else ""
                                    ctx_command = context_line[ts_end+1:].strip() if ts_end > 0 else context_line
                                    
                                    if show_time and ctx_timestamp:
                                        print(f"\033[90m[{ctx_timestamp}]\033[0m {ctx_command}")
                                    else:
                                        print(f"{ctx_command}")
                                    lines_shown.add(i)
                                except Exception:
                                    print(context_line)
                                    lines_shown.add(i)
                
                print("-" * 60)
        else:
            print(f"No commands matching '{search_term}' found in the log.")
            
    except Exception as e:
        print(f"Error searching log file: {e}")
        sys.exit(1)

def stop_monitor():
    """Stop the monitor if it's running."""
    if not os.path.exists(MONITOR_PID_FILE):
        print("Monitor is not running.")
        return
        
    try:
        with open(MONITOR_PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        
        # Try to kill the process
        os.kill(pid, signal.SIGTERM)
        print(f"Sent termination signal to monitor process (PID: {pid})")
        
        # Clean up
        cleanup_hooks()
        os.remove(MONITOR_PID_FILE)
        print("Monitor stopped and hooks removed.")
    except Exception as e:
        print(f"Error stopping monitor: {e}")
        # Clean up anyway
        try:
            os.remove(MONITOR_PID_FILE)
        except:
            pass

def show_status():
    """Show the status of the monitor."""
    if not os.path.exists(MONITOR_PID_FILE):
        print("Monitor is not running.")
        return
        
    try:
        with open(MONITOR_PID_FILE, 'r') as f:
            pid = int(f.read().strip())
        
        # Check if process is running
        try:
            os.kill(pid, 0)
            print(f"Monitor is running with PID: {pid}")
            print(f"Log file: {LOG_FILE}")
            
            # Show log file size and entry count
            if os.path.exists(LOG_FILE):
                size = os.path.getsize(LOG_FILE)
                size_str = f"{size} bytes"
                if size > 1024:
                    size_str = f"{size/1024:.2f} KB"
                if size > 1024*1024:
                    size_str = f"{size/(1024*1024):.2f} MB"
                
                with open(LOG_FILE, 'r') as f:
                    line_count = sum(1 for _ in f)
                
                print(f"Log size: {size_str}")
                print(f"Commands logged: {line_count}")
        except OSError:
            print("Monitor process appears to have died.")
            print("You may need to clean up the PID file and hooks.")
    except Exception as e:
        print(f"Error checking monitor status: {e}")

def main():
    # Define commands and create parser
    parser = argparse.ArgumentParser(description='Terminal command monitor and search tool')
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Start command
    start_parser = subparsers.add_parser('start', help='Start the terminal monitor')
    start_parser.add_argument('--daemon', action='store_true', help='Run as daemon process')
    
    # Stop command
    subparsers.add_parser('stop', help='Stop the terminal monitor')
    
    # Status command
    subparsers.add_parser('status', help='Check monitor status')
    
    # Search/blast command
    blast_parser = subparsers.add_parser('blast', help='Search command history')
    blast_parser.add_argument('search_term', nargs='?', help='Term to search for in command history')
    blast_parser.add_argument('-i', '--case-insensitive', action='store_true', help='Case insensitive search')
    blast_parser.add_argument('-n', '--no-time', action='store_true', help='Hide timestamps')
    blast_parser.add_argument('-l', '--limit', type=int, help='Limit number of results')
    blast_parser.add_argument('-r', '--regex', action='store_true', help='Treat search term as regex')
    blast_parser.add_argument('-B', '--before', type=int, default=0, help='Show N commands before each match')
    blast_parser.add_argument('-A', '--after', type=int, default=0, help='Show N commands after each match')
    blast_parser.add_argument('-C', '--context', type=int, help='Show N commands before and after each match')
    
    # Parse arguments
    args = parser.parse_args()
    
    # If no arguments provided, show help
    if len(sys.argv) == 1:
        parser.print_help()
        sys.exit(0)
    
    # Execute command
    if args.command == 'start':
        if args.daemon:
            run_as_daemon()
        else:
            start_monitoring()
    elif args.command == 'stop':
        stop_monitor()
    elif args.command == 'status':
        show_status()
    elif args.command == 'blast':
        # If no search term is provided, show blast help
        if args.search_term is None:
            blast_parser.print_help()
            sys.exit(0)
        
        # If context is specified, set before and after
        if args.context is not None:
            args.before = args.context
            args.after = args.context
        
        # Search for the term
        search_command_log(
            args.search_term,
            case_sensitive=not args.case_insensitive,
            show_time=not args.no_time,
            limit=args.limit,
            regex=args.regex,
            before=args.before,
            after=args.after
        )

if __name__ == '__main__':
    main()
