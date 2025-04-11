"""
centralized utility for managing native commands across the honeypot
"""

# list of native commands explicitly implemented in CommandProcessor
NATIVE_COMMANDS = [
    # file and Directory Management
    'ls', 'cd', 'pwd', 'cat', 'echo', 'mkdir', 'rm', 'touch', 'cp', 'mv',
    
    # system Information
    'whoami', 'uname', 'ps', 'date', 
    
    # system Interaction
    'clear', 'ping', 'ifconfig', 'sudo', 'set'
    
    # session Management
    'exit', 'quit', 'logout'
]

def is_native_command(command_input):
    if not command_input or command_input.strip() == "":
        return True  # empty commands are handled natively
    
    # extract the main command (first word)
    command = command_input.strip().split()[0].lower() if command_input.strip() else ""
    
    return command in NATIVE_COMMANDS
