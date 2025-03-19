"""
Centralized utility for managing native commands across the honeypot
"""

# list of native commands explicitly implemented in CommandProcessor
NATIVE_COMMANDS = [
    # file and Directory Management
    'ls', 'cd', 'pwd', 'cat', 'echo', 'mkdir', 'rm', 'touch', 'cp', 'mv',
    
    # system Information
    'whoami', 'uname', 'ps', 'date', 
    
    # system Interaction
    'clear', 'ping', 'ifconfig', 'sudo',
    
    # session Management
    'exit', 'quit', 'logout'
]
