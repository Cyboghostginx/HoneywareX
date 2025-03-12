#!/usr/bin/env python3
import os
import subprocess
import re
import sys
import json
from pathlib import Path

# Configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COMMANDS_FILE = os.path.join(BASE_DIR, "commands_exec.txt")
OUTPUT_FILE = os.path.join(BASE_DIR, "commands_doc.{ext}")

# Define extraction options
EXTRACTION_OPTIONS = {
    'all': 'Extract everything (command info and execution input/output)',
    'command_info': 'Extract only command information from man pages or help',
    'execution': 'Extract only command execution input and output'
}

# Define output format options
FORMAT_OPTIONS = {
    'txt': 'Plain text format with clear section markers',
    'json': 'Structured JSON format for easier parsing',
    'md': 'Markdown format for better readability'
}

def interactive_setup():
    """Interactive setup to configure extraction preferences"""
    print("\n=== Linux Command Documentation Generator for RAG ===\n")
    
    # Select extraction mode
    print("What would you like to extract from each command?")
    for i, (key, desc) in enumerate(EXTRACTION_OPTIONS.items(), 1):
        print(f"{i}. {key}: {desc}")
    
    while True:
        try:
            choice = input("\nEnter the number of your choice: ").strip()
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(EXTRACTION_OPTIONS):
                extract_mode = list(EXTRACTION_OPTIONS.keys())[choice_idx]
                break
            else:
                print("Invalid choice. Please enter a number from the list.")
        except ValueError:
            print("Please enter a valid number.")
    
    # Select output format
    print("\nSelect output format:")
    for i, (key, desc) in enumerate(FORMAT_OPTIONS.items(), 1):
        print(f"{i}. {key}: {desc}")
    
    while True:
        try:
            choice = input("\nEnter the number of your choice: ").strip()
            choice_idx = int(choice) - 1
            if 0 <= choice_idx < len(FORMAT_OPTIONS):
                output_format = list(FORMAT_OPTIONS.keys())[choice_idx]
                break
            else:
                print("Invalid choice. Please enter a number from the list.")
        except ValueError:
            print("Please enter a valid number.")
    
    return {
        'extract_mode': extract_mode,
        'output_format': output_format
    }

def read_commands_from_file(file_path):
    """Read the list of commands from the file, ignoring comments"""
    if not os.path.exists(file_path):
        print(f"Error: Commands file not found: {file_path}")
        return []
        
    commands = []
    try:
        with open(file_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                # Remove comments and strip whitespace
                line = line.split('#', 1)[0].strip()
                if line:  # Skip empty lines and comments
                    commands.append(line)
        print(f"Loaded {len(commands)} commands from {file_path}")
        return commands
    except Exception as e:
        print(f"Error reading commands file: {e}")
        return []

def get_man_page(command):
    """Get the man page content for a command"""
    try:
        cmd = command.split()[0]
        result = subprocess.run(
            ["man", cmd], 
            capture_output=True, 
            text=True,
            env={"MANWIDTH": "80"}
        )
        if result.returncode == 0:
            return result.stdout
        else:
            return None
    except Exception as e:
        print(f"  Error getting man page for {command}: {e}")
        return None

def get_help_output(command):
    """Get the --help output for a command"""
    try:
        cmd = command.split()[0]
        result = subprocess.run(
            [cmd, "--help"], 
            capture_output=True, 
            text=True
        )
        if result.returncode == 0:
            return result.stdout
        else:
            return None
    except Exception as e:
        print(f"  Error getting help for {command}: {e}")
        return None

def get_command_execution(command, max_output=10000):
    """Execute the command and get its output"""
    # Skip dangerous commands
    first_word = command.split()[0]
    dangerous_commands = ['rm', 'dd', 'mkfs', 'fdisk', 'parted', 'sudo', 'su',
                         'chown', 'chmod', 'chroot', 'kill', 'pkill', 'reboot',
                         'halt', 'poweroff', 'shutdown', 'init', 'passwd']
    
    if first_word in dangerous_commands and '--help' not in command and '--version' not in command and '-V' not in command:
        return f"# Note: Command '{command}' not executed for safety reasons. Use with caution."
        
    # Check if it's a shell builtin that doesn't produce output
    shell_builtins = ['cd', 'exit', 'quit', 'logout', 'source', '.', 'export', 'eval', 'alias']
    if first_word in shell_builtins and '--help' not in command and '--version' not in command:
        return f"# Note: '{first_word}' is a shell builtin command that typically doesn't produce output when successful."
    
    try:
        # For commands with pipes or redirects, use shell=True but with caution
        if '|' in command or '>' in command or '<' in command:
            result = subprocess.run(
                command, 
                shell=True,
                capture_output=True, 
                text=True
            )
        else:
            # Execute normally for simple commands
            result = subprocess.run(
                command.split(), 
                capture_output=True, 
                text=True
            )
        
        # Combine stdout and stderr
        output = result.stdout
        if not output.strip() and result.stderr:
            output = result.stderr
            
        # Limit output size for very large responses
        if len(output) > max_output:
            output = output[:max_output] + f"\n... (output truncated at {max_output} characters)"
            
        return output.strip()
    except Exception as e:
        return f"# Error executing '{command}': {str(e)}"

def extract_section(content, section_name):
    """Extract a section from man page content"""
    if not content:
        return None
        
    pattern = rf'{section_name}\n(.*?)(?:\n\n[A-Z]+|\Z)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None

def extract_command_info(command, man_content, help_content, execution_output, extract_mode):
    """Extract information about a command based on the extraction mode"""
    # Use first word as the command name for documentation
    cmd_name = command.split()[0]
    
    # Clean up the man page content if it exists
    cleaned_man = None
    if man_content:
        cleaned_man = re.sub(r'\b\x08.', '', man_content)  # Remove backspace formatting
        cleaned_man = re.sub(r'\x1b\[[0-9;]*m', '', cleaned_man)  # Remove ANSI color codes
    
    # Initialize result dictionary
    result = {
        'command': cmd_name,
        'full_command': command
    }
    
    # Extract command information
    if extract_mode in ['all', 'command_info']:
        # Extract description
        description = None
        if cleaned_man:
            name_section = extract_section(cleaned_man, "NAME")
            if name_section:
                description = name_section.strip()
        
        if not description and help_content:
            # Try to get description from first line of help
            description = help_content.strip().split('\n')[0]
        
        if description:
            result['description'] = description
        else:
            result['description'] = f"The '{cmd_name}' command is a Unix/Linux utility."
        
        # Extract usage
        usage = None
        if cleaned_man:
            synopsis = extract_section(cleaned_man, "SYNOPSIS")
            if synopsis:
                usage = synopsis.strip()
        
        if not usage and help_content:
            # Try to extract usage from help output
            usage_match = re.search(r'[Uu]sage:?\s+(.*?)(?:\n\n|\n[^\s])', help_content, re.DOTALL)
            if usage_match:
                usage = usage_match.group(1).strip()
        
        if usage:
            result['usage'] = usage
        else:
            result['usage'] = f"{cmd_name} [OPTIONS] [ARGUMENTS]"
        
        # Extract options
        options = None
        if cleaned_man:
            options = extract_section(cleaned_man, "OPTIONS")
        
        if not options and help_content:
            # Extract options from help content - look for indented lines with dashes
            option_lines = re.findall(r'^\s+(-\S+.*?)$', help_content, re.MULTILINE)
            if option_lines:
                options = "\n".join(option_lines)
        
        if options:
            result['options'] = options
    
    # Extract execution example
    if extract_mode in ['all', 'execution']:
        result['execution_input'] = command
        result['execution_output'] = execution_output if execution_output else "(No output)"
    
    return result

def format_output_text(cmd_info):
    """Format command information as text"""
    output = f"=== COMMAND: {cmd_info['command']} ===\n\n"
    
    if 'description' in cmd_info:
        output += f"DESCRIPTION: {cmd_info['description']}\n\n"
    
    if 'usage' in cmd_info:
        output += f"USAGE: {cmd_info['usage']}\n\n"
    
    if 'options' in cmd_info:
        output += f"OPTIONS:\n{cmd_info['options']}\n\n"
    
    if 'execution_input' in cmd_info:
        output += "EXECUTION EXAMPLE:\n"
        output += f"COMMAND INPUT:\n{cmd_info['execution_input']}\n\n"
        output += f"COMMAND OUTPUT:\n{cmd_info['execution_output']}\n"
    
    output += "\n=== END COMMAND ===\n\n"
    return output

def format_output_markdown(cmd_info):
    """Format command information as markdown"""
    output = f"# {cmd_info['command']}\n\n"
    
    if 'description' in cmd_info:
        output += f"## Description\n{cmd_info['description']}\n\n"
    
    if 'usage' in cmd_info:
        output += f"## Usage\n```\n{cmd_info['usage']}\n```\n\n"
    
    if 'options' in cmd_info:
        output += f"## Options\n```\n{cmd_info['options']}\n```\n\n"
    
    if 'execution_input' in cmd_info:
        output += "## Example\n\n"
        output += f"Command:\n```bash\n{cmd_info['execution_input']}\n```\n\n"
        output += f"Output:\n```\n{cmd_info['execution_output']}\n```\n\n"
    
    output += "---\n\n"
    return output

def main():
    """Main function to create the command documentation file"""
    # Interactive setup
    config = interactive_setup()
    
    # Set output file with correct extension
    output_file = OUTPUT_FILE.format(ext=config['output_format'])
    
    # Read commands from the file
    commands = read_commands_from_file(COMMANDS_FILE)
    if not commands:
        print("No commands found. Exiting.")
        sys.exit(1)
    
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    print(f"\nPreparing documentation for {len(commands)} commands...")
    print(f"Extraction mode: {config['extract_mode']}")
    print(f"Output format: {config['output_format']}")
    
    # Initialize collection for JSON output
    all_commands_info = []
    
    # Initialize output file
    with open(output_file, 'w') as f:
        # Write header based on format
        if config['output_format'] == 'text':
            f.write("# Linux Command Documentation for RAG\n\n")
        elif config['output_format'] == 'markdown':
            f.write("# Linux Command Documentation\n\nThis document contains information about various Linux commands for use in RAG systems.\n\n")
        elif config['output_format'] == 'json':
            # JSON header will be added at the end
            pass
        
        total_commands = len(commands)
        documented_count = 0
        
        for i, command in enumerate(commands, 1):
            print(f"Processing command {i}/{total_commands}: {command}...")
            
            # Get base command (first word) for documentation
            base_command = command.split()[0]
            
            # Determine what needs to be extracted
            need_man_help = config['extract_mode'] in ['all', 'command_info']
            need_execution = config['extract_mode'] in ['all', 'execution']
            
            # Get documentation only if needed
            man_content = None
            help_content = None
            
            if need_man_help:
                print(f"  Getting man page for {base_command}...")
                man_content = get_man_page(base_command)
                
                # If man page failed, try --help
                if not man_content:
                    print(f"  Man page not found, trying --help for {base_command}...")
                    help_content = get_help_output(base_command)
            
            # Get actual execution output if needed
            execution_output = None
            if need_execution:
                print(f"  Executing command: {command}...")
                execution_output = get_command_execution(command)
            
            # Extract command information
            cmd_info = extract_command_info(
                command, man_content, help_content, execution_output, 
                config['extract_mode']
            )
            
            # Format and write output based on selected format
            if config['output_format'] == 'txt':
                formatted_output = format_output_text(cmd_info)
                f.write(formatted_output)
            elif config['output_format'] == 'md':
                formatted_output = format_output_markdown(cmd_info)
                f.write(formatted_output)
            elif config['output_format'] == 'json':
                all_commands_info.append(cmd_info)
            
            # Update counts
            if ((need_man_help and (man_content or help_content)) or 
                (need_execution and execution_output)):
                documented_count += 1
                print(f"  Documentation for {base_command} complete.")
            else:
                print(f"  No documentation found for {base_command}.")
        
        # Write JSON at the end if json format was selected
        if config['output_format'] == 'json':
            json.dump(all_commands_info, f, indent=2)
    
    print(f"\nDocumentation completed. {documented_count}/{total_commands} commands documented.")
    print(f"Output file: {output_file}")

if __name__ == "__main__":
    main()