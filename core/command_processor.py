"""
where all commands are processed
"""
import os
import datetime
import socket
import random
import time
import ipaddress
from utils.log_setup import logger
from config import HOSTNAME, BASE_DIR, USERNAME, HOME_DIRECTORY

class CommandProcessor:
    def __init__(self, filesystem):
        self.filesystem = filesystem
        self.command_history = {}  # store command history per session
        self.hostname = HOSTNAME
        self.current_dirs = {}  # track current directory per session
        self.last_exit_code = {}  # track last exit code per session
        self.known_commands = set()  # set of commands known to exist
        self.ping_active = {}  # track active ping sessions
        self.env_vars = {}  # track environment variables per session
        self.load_known_commands()
        
    def load_known_commands(self):
        """Load the list of known Linux commands from commands.txt file"""
        commands_file = os.path.join(BASE_DIR, 'commands.txt')
        try:
            if os.path.exists(commands_file):
                with open(commands_file, 'r') as f:
                    for line in f:
                        # remove comments and strip whitespace
                        line = line.split('#', 1)[0].strip()
                        if line:  # skip empty lines
                            self.known_commands.add(line)
                logger.info(f"Loaded {len(self.known_commands)} known commands")
            else:
                logger.warning(f"Commands file not found: {commands_file}")
                # add some basic commands as fallback
                basic_commands = [
                    "ls", "cd", "pwd", "cat", "echo", "mkdir", "rm", "cp", "mv",
                    "touch", "grep", "find", "whoami", "hostname", "uname", "ps",
                    "kill", "date", "clear", "ping", "wget", "curl", "ssh", "scp",
                    "apt", "apt-get", "yum", "dnf", "systemctl", "service", "ifconfig",
                    "ip", "netstat", "ss", "sudo", "su", "passwd", "useradd", "usermod",
                    "groupadd", "chmod", "chown", "tar", "gzip", "gunzip", "zip", "unzip",
                    "vi", "vim", "nano", "top", "htop", "df", "du", "free", "exit", "logout",
                    "reboot", "shutdown", "mount", "umount", "scp", "sftp"
                ]
                self.known_commands.update(basic_commands)
                logger.info(f"Using {len(self.known_commands)} default known commands")
        except Exception as e:
            logger.error(f"Error loading commands file: {e}")
            # ensure we have at least the commands we implement
            implemented_commands = ["ls", "cd", "pwd", "cat", "echo", "mkdir", "rm", "touch", 
                                  "whoami", "uname", "ps", "date", "clear", "ping", "exit", "logout"]
            self.known_commands.update(implemented_commands)
        
    def initialize_session(self, session_id):
        """Initialize a new session state"""
        self.command_history[session_id] = []
        self.current_dirs[session_id] = f"/home/{USERNAME}"
        self.last_exit_code[session_id] = 0
        self.env_vars[session_id] = {}  # initialize empty environment variables
        
        # initialize a separate filesystem for this session
        self.filesystem.initialize_session(session_id)
    
    def cleanup_session(self, session_id):
        """Clean up session data when a session ends"""
        if session_id in self.command_history:
            del self.command_history[session_id]
        if session_id in self.current_dirs:
            del self.current_dirs[session_id]
        if session_id in self.last_exit_code:
            del self.last_exit_code[session_id]
        if session_id in self.ping_active:
            del self.ping_active[session_id]
        if session_id in self.env_vars:
            del self.env_vars[session_id]
        
        # clean up the filesystem for this session
        self.filesystem.cleanup_session(session_id)
    
    def get_prompt(self, session_id):
        """Get command prompt based on current directory"""
        current_dir = self.current_dirs.get(session_id, f"/home/{USERNAME}")
        prompt_dir = current_dir
        if current_dir.startswith(f"/home/{USERNAME}"):
            prompt_dir = current_dir.replace(f"/home/{USERNAME}", "~")
        return f"{USERNAME}@{self.hostname}:{prompt_dir}$ "
    
    def process_command(self, session_id, command):
        """Process a user command and generate a realistic response"""
        if session_id not in self.command_history:
            self.initialize_session(session_id)
        
        self.command_history[session_id].append(command)
        
        # Parse the command properly to handle quotes and redirection
        cmd_parts, redirect_type, redirect_file = self._parse_command_with_redirection(command)
        
        # If redirection is detected, handle it properly
        if redirect_type:
            # Get the command without redirection
            cmd_without_redirect = " ".join(cmd_parts)
            
            # Execute the command to get its output
            response = self.execute_command(session_id, cmd_without_redirect)
            
            # Check if there was an error in the command execution
            if "No such file or directory" in response or "not found" in response:
                # If there was an error, return it without doing redirection
                self.last_exit_code[session_id] = 1
                return response
            
            # Resolve path for output file
            current_dir = self.current_dirs.get(session_id, f"/home/{USERNAME}")
            if not redirect_file.startswith('/'):
                output_path = os.path.normpath(os.path.join(current_dir, redirect_file))
            else:
                output_path = redirect_file
            
            # For append mode, read existing content first
            content_to_write = response
            if redirect_type == '>>' and self.filesystem.file_exists(output_path, session_id):
                existing_content = self.filesystem.read_file(output_path, session_id)
                if existing_content and not existing_content.endswith('\n'):
                    existing_content += '\n'
                content_to_write = existing_content + response
            
            # Write to the file (append or overwrite)
            result = self.filesystem.write_file(output_path, content_to_write, session_id)
            
            if result:
                self.last_exit_code[session_id] = 0
                return ""  # Successful redirection produces no output
            else:
                self.last_exit_code[session_id] = 1
                return f"bash: {redirect_file}: Permission denied"
        
        # Handle piping (basic implementation)
        if "|" in command:
            # For now, we'll just handle the first command and return a generic response
            command = command.split("|")[0].strip()
            self.last_exit_code[session_id] = 0
            return "Command executed. Piping not fully supported in this environment."
        
        # Execute the command normally if no redirection was detected
        return self.execute_command(session_id, command)
    
    def _parse_command_with_redirection(self, command):
        """
        Parse a command string, handling quotes and redirection.
        Returns a tuple of (cmd_parts, redirect_type, redirect_file)
        """
        cmd_str = command
        redirect_type = None
        redirect_file = None
        
        # Look for redirection outside of quotes
        in_single_quotes = False
        in_double_quotes = False
        i = 0
        
        # First find if there's redirection
        redirect_pos = -1
        
        while i < len(command):
            char = command[i]
            
            # Track quotes state
            if char == '"' and not in_single_quotes:
                in_double_quotes = not in_double_quotes
            elif char == "'" and not in_double_quotes:
                in_single_quotes = not in_single_quotes
            
            # Look for redirection operators, but only outside quotes
            if not in_single_quotes and not in_double_quotes:
                if char == '>' and i + 1 < len(command) and command[i + 1] == '>':
                    redirect_pos = i
                    redirect_type = '>>'
                    break
                elif char == '>' and (i == 0 or command[i - 1] != '>'):
                    redirect_pos = i
                    redirect_type = '>'
                    break
            
            i += 1
        
        # If redirection found, split the command
        if redirect_pos >= 0:
            cmd_str = command[:redirect_pos].strip()
            
            # Extract the redirect file portion
            if redirect_type == '>>':
                redirect_part = command[redirect_pos + 2:].strip()
            else:  # '>'
                redirect_part = command[redirect_pos + 1:].strip()
            
            # Parse the redirect file, handling quotes
            if redirect_part:
                redirect_file = self._extract_filename(redirect_part)
        
        # Parse the command part into arguments
        cmd_parts = self._split_command(cmd_str)
        
        return cmd_parts, redirect_type, redirect_file

    def _extract_filename(self, text):
        """Extract a filename from text, handling quotes"""
        # Check if the filename is quoted
        if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
            # Return without the quotes
            return text[1:-1]
        
        # Otherwise, take the first word
        return text.split()[0]

    def _split_command(self, cmd_str):
        """Split a command string into parts, respecting quotes"""
        parts = []
        current_part = ""
        in_single_quotes = False
        in_double_quotes = False
        i = 0
        
        while i < len(cmd_str):
            char = cmd_str[i]
            
            # Handle quotes
            if char == '"' and not in_single_quotes:
                in_double_quotes = not in_double_quotes
                current_part += char
            elif char == "'" and not in_double_quotes:
                in_single_quotes = not in_single_quotes
                current_part += char
            # Handle spaces outside quotes as separators
            elif char.isspace() and not in_single_quotes and not in_double_quotes:
                if current_part:
                    parts.append(current_part)
                    current_part = ""
            else:
                current_part += char
            
            i += 1
        
        # Add the last part if there is one
        if current_part:
            parts.append(current_part)
        
        return parts
    
    def execute_command(self, session_id, command):
        """Execute a specific command"""
        # For commands with quotes, we need to parse more carefully
        if '"' in command or "'" in command:
            parts = self._split_command(command)
        else:
            # Simple space splitting for commands without quotes
            parts = command.split()
        
        if not parts:
            return ""
        
        # Extract the command name and arguments
        cmd = parts[0].lower()
        
        # Process quotes in arguments for commands that need it
        if cmd in ["cat", "echo", "touch", "mkdir", "rm", "mv", "cp"]:
            args = []
            for arg in parts[1:]:
                # Remove surrounding quotes if present
                if (arg.startswith('"') and arg.endswith('"')) or (arg.startswith("'") and arg.endswith("'")):
                    args.append(arg[1:-1])
                else:
                    args.append(arg)
        else:
            args = parts[1:] if len(parts) > 1 else []
        
        # handle different commands
        if cmd == "ls":
            return self.cmd_ls(session_id, args)
        elif cmd == "cd":
            return self.cmd_cd(session_id, args)
        elif cmd == "pwd":
            return self.cmd_pwd(session_id)
        elif cmd == "cat":
            return self.cmd_cat(session_id, args)
        elif cmd == "echo":
            return self.cmd_echo(session_id, args)
        elif cmd == "mkdir":
            return self.cmd_mkdir(session_id, args)
        elif cmd == "rm":
            return self.cmd_rm(session_id, args)
        elif cmd == "touch":
            return self.cmd_touch(session_id, args)
        elif cmd == "whoami":
            return self.cmd_whoami(session_id)
        elif cmd == "uname":
            return self.cmd_uname(session_id, args)
        elif cmd == "ps":
            return self.cmd_ps(session_id)
        elif cmd == "date":
            return self.cmd_date(session_id)
        elif cmd == "ping":
            return self.cmd_ping(session_id, args)
        elif cmd == "cp":
            return self.cmd_cp(session_id, args)
        elif cmd == "mv":
            return self.cmd_mv(session_id, args)
        elif cmd == "sudo":
            return self.cmd_sudo(session_id, args)
        elif cmd == "set":
            return self.cmd_set(session_id, args)
        elif cmd == "ifconfig":
            return self.cmd_ifconfig(session_id, args)
        elif cmd == "clear":
            return "\033[2J\033[H"  # ANSI escape codes to clear screen
        elif cmd in ["exit", "quit", "logout"]:
            return "logout"
        else:
            # we check here if the command exists but is not implemented yet in native commands.
            if cmd in self.known_commands:
                self.last_exit_code[session_id] = 0
                return f"{cmd}: command is recognized but not implemented in this environment."
            else:
                self.last_exit_code[session_id] = 127
                return f"bash: {cmd}: command not found"
    
    def cmd_set(self, session_id, args=None):
        """handle the set command to display or modify shell variables"""
        # if no arguments, display all variables
        if not args:
            # get the environment variables we want to display
            # we'll show both system and user-defined variables
            env_vars = {
                "HOME": f"/home/{USERNAME}",
                "USER": USERNAME,
                "SHELL": "/bin/bash",
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                "PWD": self.current_dirs.get(session_id, f"/home/{USERNAME}"),
                "LANG": "en_US.UTF-8",
                "TERM": "xterm-256color",
                "MAIL": f"/var/mail/{USERNAME}",
                "LOGNAME": USERNAME,
                "HOSTNAME": self.hostname,
                "HISTSIZE": "1000",
                "HISTFILESIZE": "2000"
            }
            
            # add any custom variables set by the user in this session
            if session_id in self.env_vars:
                env_vars.update(self.env_vars[session_id])
            
            # format and return the variables
            result = []
            for name, value in sorted(env_vars.items()):
                result.append(f"{name}={value}")
            
            self.last_exit_code[session_id] = 0
            return "\n".join(result)
        
        # handle setting a variable (VAR=value syntax)
        elif len(args) == 1 and '=' in args[0]:
            # parse and set the variable
            var_parts = args[0].split('=', 1)
            var_name = var_parts[0]
            var_value = var_parts[1] if len(var_parts) > 1 else ""
            
            # if value is quoted, remove the quotes
            if var_value and var_value[0] == var_value[-1] and var_value[0] in ('"', "'"):
                var_value = var_value[1:-1]
            
            # set the variable
            self.env_vars[session_id][var_name] = var_value
            self.last_exit_code[session_id] = 0
            return ""
        
        # handle set with options
        else:
            # process common set options
            if '-o' in args:
                return "Usage: set -o option[=value]\nTry 'help set' for more information."
            elif '-x' in args:
                return "set: shell debugging enabled"
            elif '-e' in args:
                return "set: exit immediately if a command exits with a non-zero status"
            else:
                self.last_exit_code[session_id] = 1
                return f"set: invalid option or argument: {' '.join(args)}\nTry 'help set' for more information."

    def cmd_ping(self, session_id, args):
        """
        Handle ping command with realistic behavior including DNS resolution,
        continuous pinging, and Ctrl+C interruption
        """
        if not args:
            self.last_exit_code[session_id] = 1
            return "Usage: ping [-c count] [-i interval] [-t ttl] destination"
        
        # Parse arguments
        count = None
        interval = 1.0
        ttl = random.randint(42, 64)  # Realistic TTL values
        destination = None
        
        i = 0
        while i < len(args):
            if args[i] == '-c' and i + 1 < len(args):
                try:
                    count = int(args[i + 1])
                    i += 2
                    continue
                except ValueError:
                    i += 1
            elif args[i] == '-i' and i + 1 < len(args):
                try:
                    interval = float(args[i + 1])
                    i += 2
                    continue
                except ValueError:
                    i += 1
            elif args[i] == '-t' and i + 1 < len(args):
                try:
                    ttl = int(args[i + 1])
                    i += 2
                    continue
                except ValueError:
                    i += 1
            else:
                destination = args[i]
                i += 1
        
        if not destination:
            self.last_exit_code[session_id] = 1
            return "ping: usage error: Destination address required"
        
        # attempt to resolve the hostname
        try:
            # determine if the destination is an IP address or hostname
            try:
                ipaddress.ip_address(destination)
                resolved_ip = destination
                hostname = destination
            except ValueError:
                resolved_ip = socket.gethostbyname(destination)
                hostname = destination
            
            # for loopback addresses, use a different format
            if resolved_ip.startswith('127.'):
                ping_header = f"PING {hostname} ({resolved_ip}): 56(84) bytes of data."
            else:
                ping_header = f"PING {hostname} ({resolved_ip}): 56 data bytes"
            
            # Set up ping results data
            self.ping_active[session_id] = {
                'active': True,
                'hostname': hostname,
                'ip': resolved_ip,
                'ttl': ttl,
                'sequence': 0,
                'transmitted': 0,
                'received': 0,
                'times': []
            }
            
            # create the initial response with header
            response = [ping_header]
            
            # if count is specified, ping that many times
            if count is not None:
                for i in range(count):
                    if not self.ping_active.get(session_id, {}).get('active', False):
                        break
                    
                    time_ms = self._generate_ping_time(resolved_ip)
                    self.ping_active[session_id]['sequence'] += 1
                    self.ping_active[session_id]['transmitted'] += 1
                    self.ping_active[session_id]['received'] += 1
                    self.ping_active[session_id]['times'].append(time_ms)
                    
                    seq = self.ping_active[session_id]['sequence'] - 1
                    response.append(f"64 bytes from {resolved_ip}: icmp_seq={seq} ttl={ttl} time={time_ms:.3f} ms")
                    
                    if i < count - 1:  # don't sleep after the last ping
                        time.sleep(interval)
                
                # add statistics at the end
                response.extend(self._generate_ping_stats(self.ping_active[session_id]))
                self.ping_active[session_id]['active'] = False
                
            else:
                # the user will need to use Ctrl+C to stop
                response.append("PING_CONTINUES")
            
            self.last_exit_code[session_id] = 0
            return "\n".join(response)
            
        except socket.gaierror:
            self.last_exit_code[session_id] = 1
            return f"ping: cannot resolve {destination}: Unknown host"
        except socket.error as e:
            self.last_exit_code[session_id] = 1
            return f"ping: error: {str(e)}"

    def ping_iteration(self, session_id):
        """Generate a single ping response for continuous ping mode"""
        if not self.ping_active.get(session_id, {}).get('active', False):
            return None
        
        ping_data = self.ping_active[session_id]
        time_ms = self._generate_ping_time(ping_data['ip'])
        ping_data['sequence'] += 1
        ping_data['transmitted'] += 1
        ping_data['received'] += 1
        ping_data['times'].append(time_ms)
        
        seq = ping_data['sequence'] - 1
        return f"64 bytes from {ping_data['ip']}: icmp_seq={seq} ttl={ping_data['ttl']} time={time_ms:.3f} ms"

    def stop_ping(self, session_id):
        """Stop an active ping and return statistics"""
        if session_id in self.ping_active:
            self.ping_active[session_id]['active'] = False
            stats = self._generate_ping_stats(self.ping_active[session_id])
            return "\n".join(stats)
        return None

    def _generate_ping_time(self, ip):
        """Generate a realistic ping time based on the IP address"""
        # local IPs have low latency
        if ip.startswith('127.') or ip.startswith('192.168.') or ip.startswith('10.'):
            base = random.uniform(0.1, 5.0)
            jitter = random.uniform(0.01, 0.5)
        # we know reserved or special IPs have medium latency
        elif ip.startswith('172.') or ip.startswith('169.254'):
            base = random.uniform(5.0, 20.0)
            jitter = random.uniform(0.5, 2.0)
        # public IPs have higher and more variable latency
        else:
            base = random.uniform(30.0, 200.0)
            jitter = random.uniform(1.0, 15.0)
        
        return base + (random.random() * jitter)

    def _generate_ping_stats(self, ping_data):
        """Generate ping statistics summary"""
        stats = []
        stats.append(f"--- {ping_data['hostname']} ping statistics ---")
        
        # calculate packet loss
        transmitted = ping_data['transmitted']
        received = ping_data['received']
        if transmitted > 0:
            loss_pct = ((transmitted - received) / transmitted) * 100
        else:
            loss_pct = 0
        
        stats.append(f"{transmitted} packets transmitted, {received} packets received, {loss_pct:.1f}% packet loss")
        
        # calculate min/avg/max/stddev if we have times
        if ping_data['times']:
            min_time = min(ping_data['times'])
            max_time = max(ping_data['times'])
            avg_time = sum(ping_data['times']) / len(ping_data['times'])
            
            # calculate standard deviation
            if len(ping_data['times']) > 1:
                variance = sum((t - avg_time) ** 2 for t in ping_data['times']) / len(ping_data['times'])
                stddev = variance ** 0.5
            else:
                stddev = 0
            
            stats.append(f"round-trip min/avg/max/stddev = {min_time:.3f}/{avg_time:.3f}/{max_time:.3f}/{stddev:.3f} ms")
        
        return stats
    
    def cmd_ls(self, session_id, args):
        """handle ls command with improved support for -la flags"""
        # parse flags and targets
        flags = [arg for arg in args if arg.startswith("-")]
        targets = [arg for arg in args if not arg.startswith("-")]
        
        current_dir = self.current_dirs.get(session_id, "/home/haskoli")
        
        # process flags
        show_hidden = False
        long_format = False
        show_indicators = False
        
        # check for combined flags
        for flag in flags:
            if 'a' in flag:
                show_hidden = True
            if 'l' in flag:
                long_format = True
            if 'F' in flag:
                show_indicators = True
        
        # if no targets, use current directory
        if not targets:
            targets = [current_dir]
        
        results = []
        for target in targets:
            # resolve the path
            if not target.startswith('/'):
                target_path = os.path.normpath(os.path.join(current_dir, target))
            else:
                target_path = target
            
            # if multiple targets, show directory names
            if len(targets) > 1:
                results.append(f"{target_path}:")
            
            # get directory contents
            dir_listing = self.filesystem.list_directory(target_path, session_id)
            
            # process directory listing
            if isinstance(dir_listing, str) and "cannot access" not in dir_listing:
                # remove ansi color codes for processing
                plain_listing = dir_listing.replace("\033[1;34m", "").replace("\033[1;32m", "").replace("\033[0m", "")
                
                # split into individual files
                files = [f.rstrip('*/') for f in plain_listing.split("  ") if f]
                
                # filter hidden files if not showing hidden
                if not show_hidden:
                    files = [f for f in files if not f.startswith('.')]
                
                # process according to format
                if long_format:
                    # long format (-l)
                    long_results = []
                    for filename in sorted(files):
                        # check if it's a directory
                        file_path = os.path.join(target_path, filename)
                        is_dir = self.filesystem.is_directory(file_path, session_id)
                        
                        # simulate permissions, size, date
                        perm = "drwxr-xr-x" if is_dir else "-rw-r--r--"
                        size = "4096" if is_dir else str(random.randint(100, 10000))
                        date = datetime.datetime.now().strftime("%b %d %H:%M")
                        owner = USERNAME
                        group = USERNAME
                        
                        # form the long listing line
                        display_name = filename
                        if is_dir and show_indicators:
                            display_name += "/"
                        
                        # add color if it's a directory (maintained for visual output)
                        if is_dir:
                            display_name = f"\033[1;34m{display_name}\033[0m"
                            
                        line = f"{perm} 1 {owner} {group} {size.rjust(8)} {date} {display_name}"
                        long_results.append(line)
                    
                    results.append("\n".join(long_results))
                else:
                    # regular format
                    formatted_files = []
                    for filename in sorted(files):
                        file_path = os.path.join(target_path, filename)
                        is_dir = self.filesystem.is_directory(file_path, session_id)
                        
                        display_name = filename
                        # add indicator if requested
                        if is_dir and show_indicators:
                            display_name += "/"
                        
                        # add color for directories (maintained for visual output)
                        if is_dir:
                            display_name = f"\033[1;34m{display_name}\033[0m"
                        
                        formatted_files.append(display_name)
                    
                    results.append("  ".join(formatted_files))
            else:
                # error message or empty directory
                results.append(dir_listing)
            
            if len(targets) > 1 and target != targets[-1]:
                results.append("")
        
        self.last_exit_code[session_id] = 0
        return "\n".join(results)
    
    def cmd_ifconfig(self, session_id, args=None):
        """Handle ifconfig command with realistic output"""
        # determine which interfaces to show based on args
        show_all = not args
        interfaces_to_show = args if args else ["eth0", "lo"]
        
        # define realistic interface data
        interfaces = {
            "eth0": {
                "ip": "192.168.1.100",
                "netmask": "255.255.255.0",
                "broadcast": "192.168.1.255",
                "mac": "52:54:00:" + ":".join([f"{random.randint(0, 255):02x}" for _ in range(3)]),
                "mtu": 1500,
                "rx_packets": random.randint(10000, 50000),
                "rx_bytes": random.randint(1000000, 5000000),
                "tx_packets": random.randint(8000, 40000),
                "tx_bytes": random.randint(800000, 4000000),
                "collisions": 0
            },
            "lo": {
                "ip": "127.0.0.1",
                "netmask": "255.0.0.0",
                "mac": "00:00:00:00:00:00",
                "mtu": 65536,
                "rx_packets": random.randint(1000, 5000),
                "rx_bytes": random.randint(100000, 500000),
                "tx_packets": random.randint(1000, 5000),
                "tx_bytes": random.randint(100000, 500000),
                "collisions": 0
            }
        }
        
        results = []
        for iface in interfaces_to_show:
            if iface in interfaces:
                data = interfaces[iface]
                results.append(f"{iface}: flags=4163<UP,BROADCAST,RUNNING,MULTICAST>  mtu {data['mtu']}")
                results.append(f"        inet {data['ip']}  netmask {data['netmask']}  broadcast {data.get('broadcast', '')}")
                results.append(f"        inet6 fe80::5054:{data['mac'].split(':')[3]}:{data['mac'].split(':')[4]}:{data['mac'].split(':')[5]}/64  scope link")
                results.append(f"        ether {data['mac']}  txqueuelen 1000  (Ethernet)")
                results.append(f"        RX packets {data['rx_packets']}  bytes {data['rx_bytes']} ({int(data['rx_bytes']/1024/1024)} MB)")
                results.append(f"        RX errors 0  dropped 0  overruns 0  frame 0")
                results.append(f"        TX packets {data['tx_packets']}  bytes {data['tx_bytes']} ({int(data['tx_bytes']/1024/1024)} MB)")
                results.append(f"        TX errors 0  dropped 0 overruns 0  carrier 0  collisions {data['collisions']}")
                results.append("")
            elif show_all:
                # if interface doesn't exist but we're showing all interfaces, just skip it
                continue
            else:
                # if specifically requested interface doesn't exist
                results.append(f"ifconfig: interface {iface} does not exist")
        
        self.last_exit_code[session_id] = 0
        return "\n".join(results)
    
    def cmd_cd(self, session_id, args):
        """Handle cd command"""
        current_dir = self.current_dirs.get(session_id, f"/home/{USERNAME}")
        
        if not args:  # cd with no args
            self.current_dirs[session_id] = f"/home/{USERNAME}"
            self.last_exit_code[session_id] = 0
            return ""
        
        target = args[0]
        
        # handle special cases
        if target == "~" or target == "$HOME":
            self.current_dirs[session_id] = f"/home/{USERNAME}"
            self.last_exit_code[session_id] = 0
            return ""
        elif target == "..":
            # move up one directory
            parent_dir = os.path.dirname(current_dir)
            # don't go beyond root
            if parent_dir == "":
                parent_dir = "/"
                
            # check if parent directory exists
            if self.filesystem.file_exists(parent_dir, session_id):
                self.current_dirs[session_id] = parent_dir
                self.last_exit_code[session_id] = 0
                return ""
            else:
                self.last_exit_code[session_id] = 1
                return f"bash: cd: {target}: No such file or directory"
        elif target == ".":
            # stay in current directory
            self.last_exit_code[session_id] = 0
            return ""
        elif target.startswith("/"):
            # absolute path
            new_dir = target
        else:
            # relative path
            new_dir = os.path.normpath(os.path.join(current_dir, target))
        
        # check if directory exists in our virtual filesystem
        if not self.filesystem.file_exists(new_dir, session_id):
            self.last_exit_code[session_id] = 1
            return f"bash: cd: {target}: No such file or directory"
        
        # make sure it's a directory
        if not self.filesystem.is_directory(new_dir, session_id):
            self.last_exit_code[session_id] = 1
            return f"bash: cd: {target}: Not a directory"
        
        # update current directory
        self.current_dirs[session_id] = new_dir
        self.last_exit_code[session_id] = 0
        return ""
    
    def cmd_cp(self, session_id, args):
        """Handle cp command"""
        if len(args) < 2:
            self.last_exit_code[session_id] = 1
            return "cp: missing file operand"
        
        current_dir = self.current_dirs.get(session_id, f"/home/{USERNAME}")
        
        # last argument is the destination
        destination = args[-1]
        # all other arguments are sources
        sources = args[:-1]
        
        # filter out flags
        sources = [src for src in sources if not src.startswith('-')]
        
        if not sources:
            self.last_exit_code[session_id] = 1
            return "cp: missing file operand"
        
        # resolve destination path
        if not destination.startswith('/'):
            dest_path = os.path.normpath(os.path.join(current_dir, destination))
        else:
            dest_path = destination
        
        # check if destination is a directory
        is_dest_dir = self.filesystem.is_directory(dest_path, session_id)
        
        results = []
        for source in sources:
            # resolve source path
            if not source.startswith('/'):
                source_path = os.path.normpath(os.path.join(current_dir, source))
            else:
                source_path = source
            
            # check if source exists
            if not self.filesystem.file_exists(source_path, session_id):
                results.append(f"cp: cannot stat '{source}': No such file or directory")
                continue
            
            # if destination is a directory, we copy the source into it
            if is_dest_dir:
                source_name = os.path.basename(source_path)
                target_path = os.path.join(dest_path, source_name)
            else:
                # if multiple sources, destination must be a directory
                if len(sources) > 1:
                    results.append(f"cp: target '{destination}' is not a directory")
                    break
                target_path = dest_path
            
            # copy the file or directory
            if self.filesystem.is_directory(source_path, session_id):
                # for simplicity, we don't handle recursive copying in this basic implementation
                results.append(f"cp: omitting directory '{source}'")
            else:
                # copy file (read content from source and write to destination)
                content = self.filesystem.read_file(source_path, session_id)
                success = self.filesystem.write_file(target_path, content, session_id)
                if not success:
                    results.append(f"cp: cannot create regular file '{target_path}': Permission denied")
        
        self.last_exit_code[session_id] = 0 if not results else 1
        return "\n".join(results)

    def cmd_mv(self, session_id, args):
        """Handle mv command"""
        if len(args) < 2:
            self.last_exit_code[session_id] = 1
            return "mv: missing file operand"
        
        current_dir = self.current_dirs.get(session_id, f"/home/{USERNAME}")
        
        # last argument is the destination
        destination = args[-1]
        # all other arguments are sources
        sources = args[:-1]
        
        # filter out flags
        sources = [src for src in sources if not src.startswith('-')]
        
        if not sources:
            self.last_exit_code[session_id] = 1
            return "mv: missing file operand"
        
        # resolve destination path
        if not destination.startswith('/'):
            dest_path = os.path.normpath(os.path.join(current_dir, destination))
        else:
            dest_path = destination
        
        # check if destination is a directory
        is_dest_dir = self.filesystem.is_directory(dest_path, session_id)
        
        results = []
        for source in sources:
            # resolve source path
            if not source.startswith('/'):
                source_path = os.path.normpath(os.path.join(current_dir, source))
            else:
                source_path = source
            
            # check if source exists
            if not self.filesystem.file_exists(source_path, session_id):
                results.append(f"mv: cannot stat '{source}': No such file or directory")
                continue
            
            # if destination is a directory, we move the source into it
            if is_dest_dir:
                source_name = os.path.basename(source_path)
                target_path = os.path.join(dest_path, source_name)
            else:
                # if multiple sources, destination must be a directory
                if len(sources) > 1:
                    results.append(f"mv: target '{destination}' is not a directory")
                    break
                target_path = dest_path
            
            # move the file or directory (copy + remove)
            if self.filesystem.is_directory(source_path, session_id):
                
                # create the target directory if it doesn't exist
                if not self.filesystem.file_exists(target_path, session_id):
                    self.filesystem.create_directory(target_path, session_id)
                
                # get all files in the source directory
                dir_contents = self.filesystem.list_directory(source_path, session_id)
                if isinstance(dir_contents, str) and "cannot access" not in dir_contents:
                    # clean up ANSI color codes and process files
                    dir_contents = dir_contents.replace("\033[1;34m", "").replace("\033[1;32m", "").replace("\033[0m", "")
                    files = [f.rstrip('*/') for f in dir_contents.split("  ") if f]
                    
                    # move each file to the target directory
                    for filename in files:
                        src_file = os.path.join(source_path, filename)
                        dst_file = os.path.join(target_path, filename)
                        
                        if self.filesystem.is_directory(src_file, session_id):
                            self.filesystem.create_directory(dst_file, session_id)
                        else:
                            # copy file contents
                            content = self.filesystem.read_file(src_file, session_id)
                            self.filesystem.write_file(dst_file, content, session_id)
                            # remove source file
                            self.filesystem.remove_file(src_file, session_id)
                    
                    # remove the source directory
                    self.filesystem.remove_file(source_path, session_id)
            else:
                # move file (copy + remove)
                content = self.filesystem.read_file(source_path, session_id)
                success = self.filesystem.write_file(target_path, content, session_id)
                if success:
                    # remove the source file
                    self.filesystem.remove_file(source_path, session_id)
                else:
                    results.append(f"mv: cannot create regular file '{target_path}': Permission denied")
        
        self.last_exit_code[session_id] = 0 if not results else 1
        return "\n".join(results)
    
    def cmd_pwd(self, session_id):
        """Handle pwd command"""
        self.last_exit_code[session_id] = 0
        return self.current_dirs.get(session_id, f"/home/{USERNAME}")
    
    def cmd_cat(self, session_id, args):
        """Handle cat command"""
        if not args:
            self.last_exit_code[session_id] = 1
            return "cat: missing operand"
        
        current_dir = self.current_dirs.get(session_id, f"/home/{USERNAME}")
        
        results = []
        error_found = False
        
        for filename in args:
            # Resolve the path
            if not filename.startswith('/'):
                file_path = os.path.normpath(os.path.join(current_dir, filename))
            else:
                file_path = filename
            
            # Check if file exists
            if not self.filesystem.file_exists(file_path, session_id):
                error_found = True
                results.append(f"cat: {filename}: No such file or directory")
                continue
            
            # Check if it's a directory
            if self.filesystem.is_directory(file_path, session_id):
                error_found = True
                results.append(f"cat: {filename}: Is a directory")
                continue
                
            content = self.filesystem.read_file(file_path, session_id)
            
            # make sure multiline content is properly formatted
            if '\n' in content and not content.endswith('\n'):
                content += '\n'
                
            results.append(content)
        
        self.last_exit_code[session_id] = 0 if not error_found else 1
        return "\n".join(results)
    
    def cmd_echo(self, session_id, args):
        """Handle echo command with proper handling of quotes and escapes"""
        if not args:
            # Empty echo just produces a newline
            self.last_exit_code[session_id] = 0
            return ""
        
        # Check for options
        options = []
        non_option_args = []
        
        for arg in args:
            if arg.startswith('-'):
                options.append(arg)
            else:
                non_option_args.append(arg)
        
        # Process options
        no_newline = '-n' in options  # Don't add a newline at the end
        interpret_escapes = '-e' in options  # Interpret backslash escapes
        
        # Join the non-option arguments
        result = " ".join(non_option_args)
        
        # Handle escape sequences if -e is specified
        if interpret_escapes:
            result = result.replace("\\n", "\n")
            result = result.replace("\\t", "\t")
            result = result.replace("\\r", "\r")
            result = result.replace("\\b", "\b")
            result = result.replace("\\a", "\a")
            result = result.replace("\\v", "\v")
            result = result.replace("\\\\", "\\")
            result = result.replace('\\"', '"')
            result = result.replace("\\'", "'")
        
        # Set the exit code and return the result
        self.last_exit_code[session_id] = 0
        return result
    
    def cmd_mkdir(self, session_id, args):
        """Handle mkdir command"""
        if not args:
            self.last_exit_code[session_id] = 1
            return "mkdir: missing operand"
        
        current_dir = self.current_dirs.get(session_id, f"/home/{USERNAME}")
        
        results = []
        for dirname in args:
            # skip flags
            if dirname.startswith('-'):
                continue
                
            # resolve the path
            if not dirname.startswith('/'):
                dir_path = os.path.normpath(os.path.join(current_dir, dirname))
            else:
                dir_path = dirname
            
            result = self.filesystem.create_directory(dir_path, session_id)
            if result:
                results.append(result)
        
        self.last_exit_code[session_id] = 0 if not results else 1
        return "\n".join(results)
    
    def cmd_sudo(self, session_id, args):
        """Handle sudo command - always denies permission"""
        if not args:
            self.last_exit_code[session_id] = 1
            return "sudo: no command specified"
        
        # if sudo is used with -h or --help, show a fake help message
        if args[0] in ["-h", "--help"]:
            self.last_exit_code[session_id] = 0
            return """usage: sudo -h | -K | -k | -V
    usage: sudo -v [-AknS] [-g group] [-h host] [-p prompt] [-u user]
    usage: sudo -l [-AknS] [-g group] [-h host] [-p prompt] [-U user] [-u user] [command]
    usage: sudo [-AbEHknPS] [-C num] [-g group] [-h host] [-p prompt] [-T timeout] [-u user] [VAR=value] [-i | -s] [command]
    usage: sudo -e [-AknS] [-C num] [-g group] [-h host] [-p prompt] [-T timeout] [-u user] file ..."""
        
        # always deny permission
        self.last_exit_code[session_id] = 1
        
        # get the command that was attempted
        cmd = args[0] if args else "unknown"
        
        # check for other variants
        if cmd == "su" or (cmd.startswith("-") and len(args) > 1 and args[1] == "su"):
            return "sudo: sorry, you must have a tty to run sudo"
        
        return f"sudo: unable to execute {cmd}: Permission denied"
    
    def cmd_rm(self, session_id, args):
        """Handle rm command with support for removing directories with -rf"""
        if not args:
            self.last_exit_code[session_id] = 1
            return "rm: missing operand"
        
        # parse flags
        recursive = "-r" in args or "-rf" in args or "-fr" in args or "--recursive" in args
        force = "-f" in args or "-rf" in args or "-fr" in args or "--force" in args
        
        # filter out flags
        targets = [arg for arg in args if not arg.startswith('-')]
        
        if not targets:
            self.last_exit_code[session_id] = 1
            return "rm: missing operand"
        
        current_dir = self.current_dirs.get(session_id, f"/home/{USERNAME}")
        
        results = []
        for target in targets:
            # resolve the path
            if not target.startswith('/'):
                target_path = os.path.normpath(os.path.join(current_dir, target))
            else:
                target_path = target
            
            # check if path exists
            if not self.filesystem.file_exists(target_path, session_id):
                if not force:
                    results.append(f"rm: cannot remove '{target}': No such file or directory")
                continue
                
            # check if it's a directory
            if self.filesystem.is_directory(target_path, session_id):
                # check if directory is empty
                dir_listing = self.filesystem.list_directory(target_path, session_id)
                is_empty = isinstance(dir_listing, str) and not dir_listing.strip()
                
                if not recursive and not is_empty:
                    results.append(f"rm: cannot remove '{target}': Is a directory")
                    continue
                    
                # remove all contents first
                if not is_empty and recursive:
                    # for a real implementation, we'd delete every content
                    # here we're simplifying by just allowing the virtual filesystem to handle it
                    result = self.filesystem.remove_file(target_path, session_id, recursive=True)
                    if result:
                        results.append(result)
                else:
                    # for empty directories
                    result = self.filesystem.remove_file(target_path, session_id)
                    if result:
                        results.append(result)
            else:
                # regular file removal
                result = self.filesystem.remove_file(target_path, session_id)
                if result:
                    results.append(result)
        
        self.last_exit_code[session_id] = 0 if not results else 1
        return "\n".join(results)
    
    def cmd_touch(self, session_id, args):
        """Handle touch command"""
        if not args:
            self.last_exit_code[session_id] = 1
            return "touch: missing file operand"
        
        current_dir = self.current_dirs.get(session_id, f"/home/{USERNAME}")
        
        for filename in args:
            # resolve the path
            if not filename.startswith('/'):
                file_path = os.path.normpath(os.path.join(current_dir, filename))
            else:
                file_path = filename
            
            # create or update the file
            if not self.filesystem.file_exists(file_path, session_id):
                self.filesystem.write_file(file_path, "", session_id)
        
        self.last_exit_code[session_id] = 0
        return ""
    
    def cmd_whoami(self, session_id):
        """Handle whoami command"""
        self.last_exit_code[session_id] = 0
        return f"{USERNAME}"
    
    def cmd_uname(self, session_id, args):
        """Handle uname command"""
        # get current time for system information
        current_time = datetime.datetime.now()
        current_time_str = current_time.strftime("%a %b %d %I:%M:%S %p %Z %Y")
        # check for any of the flags below
        if "-a" in args:
            self.last_exit_code[session_id] = 0
            return f"Linux server01 5.4.0-107-generic #121-Ubuntu SMP {current_time_str} x86_64 x86_64 x86_64 GNU/Linux"
        if "-r" in args:
            self.last_exit_code[session_id] = 0
            return "5.4.0-107-generic"
        if "-n" in args:
            self.last_exit_code[session_id] = 0
            return "ubuntu01"
        
        # default behavior
        self.last_exit_code[session_id] = 0
        return "Linux"
    
    def cmd_ps(self, session_id):
        """Handle ps command"""
        self.last_exit_code[session_id] = 0
        return "  PID TTY          TIME CMD\n 1234 pts/0    00:00:00 bash\n 1235 pts/0    00:00:00 ps"
    
    def cmd_date(self, session_id):
        """Handle date command"""
        self.last_exit_code[session_id] = 0
        return datetime.datetime.now().strftime("%a %b %d %H:%M:%S %Z %Y")
