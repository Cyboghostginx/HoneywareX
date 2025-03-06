import os
import subprocess
import re
import sys
from pathlib import Path

# configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
COMMANDS_FILE = os.path.join(BASE_DIR, "commands_exec.txt")
OUTPUT_FILE = os.path.join(BASE_DIR, "commands_doc.txt")

def read_commands_from_file():
    """Read the list of commands from the command_examples.txt file"""
    if not os.path.exists(COMMANDS_FILE):
        print(f"Error: Commands file not found: {COMMANDS_FILE}")
        return []
        
    commands = []
    try:
        with open(COMMANDS_FILE, 'r') as f:
            for line in f:
                # remove comments and strip whitespace
                line = line.split('#', 1)[0].strip()
                if line:  # skip empty lines
                    commands.append(line)
        print(f"Loaded {len(commands)} commands from {COMMANDS_FILE}")
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
            text=True,
            timeout=3  # add timeout to prevent hanging
        )
        if result.returncode == 0:
            return result.stdout
        else:
            return None
    except Exception as e:
        print(f"  Error getting help for {command}: {e}")
        return None

def get_command_execution(command):
    """Execute the command and get its output"""
    # skip dangerous commands
    first_word = command.split()[0]
    dangerous_commands = ['rm', 'dd', 'mkfs', 'fdisk', 'parted', 'sudo', 'su',
                         'chown', 'chmod', 'chroot', 'kill', 'pkill']
    
    if first_word in dangerous_commands and '--help' not in command and '--version' not in command and '-V' not in command:
        return f"# Note: Command '{command}' not executed for safety reasons. Use with caution."
        
    # check if it's a shell builtin that doesn't produce output
    shell_builtins = ['cd', 'exit', 'quit', 'logout', 'source', '.', 'export', 'eval', 'alias']
    if first_word in shell_builtins and '--help' not in command and '--version' not in command:
        return f"# Note: '{first_word}' is a shell builtin command that typically doesn't produce output when successful."
    
    try:
        # for commands with pipes or redirects, use shell=True but with caution
        if '|' in command or '>' in command or '<' in command:
            result = subprocess.run(
                command, 
                shell=True,
                capture_output=True, 
                text=True,
                timeout=5
            )
        else:
            # execute normally for simple commands
            result = subprocess.run(
                command.split(), 
                capture_output=True, 
                text=True,
                timeout=5
            )
        
        # sombine stdout and stderr
        output = result.stdout
        if not output.strip() and result.stderr:
            output = result.stderr
            
        # limit output size for large responses
        if len(output) > 3000:
            output = output[:3000] + "\n... (output truncated)"
            
        return output.strip()
    except subprocess.TimeoutExpired:
        return f"# Command '{command}' execution timed out after 5 seconds"
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

def format_documentation(command, man_content, help_content, execution_output):
    """Format the documentation for a command for RAG"""
    # use first word as the command name for documentation
    cmd_name = command.split()[0]
    
    # start with command header
    doc = f"=== COMMAND: {cmd_name} ===\n\n"
    
    # DESCRIPTION section
    description = None
    if man_content:
        # clean up the man page content
        cleaned_man = re.sub(r'\b\x08.', '', man_content)  # remove backspace formatting
        cleaned_man = re.sub(r'\x1b\[[0-9;]*m', '', cleaned_man)  # remove ANSI color codes
        
        # extract the name and description section
        name_section = extract_section(cleaned_man, "NAME")
        if name_section:
            description = name_section.strip()
    
    if not description and help_content:
        # try to get description from first line of help
        description = help_content.strip().split('\n')[0]
    
    if description:
        doc += f"DESCRIPTION: {description}\n\n"
    else:
        doc += f"DESCRIPTION: The '{cmd_name}' command is a Unix/Linux utility.\n\n"
    
    # USAGE section
    usage = None
    if man_content:
        synopsis = extract_section(cleaned_man, "SYNOPSIS")
        if synopsis:
            usage = synopsis.strip()
    
    if not usage and help_content:
        # try to extract usage from help output
        usage_match = re.search(r'[Uu]sage:?\s+(.*?)(?:\n\n|\n[^\s])', help_content, re.DOTALL)
        if usage_match:
            usage = usage_match.group(1).strip()
    
    if usage:
        doc += f"USAGE: {usage}\n\n"
    else:
        doc += f"USAGE: {cmd_name} [OPTIONS] [ARGUMENTS]\n\n"
    
    # OPTIONS section
    options = None
    if man_content:
        options = extract_section(cleaned_man, "OPTIONS")
    
    if not options and help_content:
        # extract options from help content - look for indented lines with dashes
        option_lines = re.findall(r'^\s+(-\S+.*?)$', help_content, re.MULTILINE)
        if option_lines:
            options = "\n".join(option_lines)
    
    if options:
        doc += f"OPTIONS:\n{options}\n\n"
    
    # EXECUTION EXAMPLE section
    doc += "EXECUTION EXAMPLE:\n"
    doc += "COMMAND INPUT:\n"
    doc += f"{command}\n\n"
    
    doc += "COMMAND OUTPUT:\n"
    if execution_output:
        # use proper indentation for multiline output
        output_lines = execution_output.split('\n')
        for line in output_lines:
            doc += f"{line}\n"
    else:
        doc += "(No output)\n"
    
    # end marker
    doc += "\n=== END COMMAND ===\n\n"
    return doc

def main():
    """Main function to create the command documentation file"""
    # read commands from the file
    commands = read_commands_from_file()
    if not commands:
        print("No commands found. Exiting.")
        sys.exit(1)
    
    # create output directory if it doesn't exist
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    
    print(f"Preparing documentation for {len(commands)} commands...")
    
    with open(OUTPUT_FILE, 'w') as f:
        f.write("# Linux Command Documentation for SSH Honeypot RAG\n\n")
        
        total_commands = len(commands)
        documented_count = 0
        
        for i, command in enumerate(commands, 1):
            print(f"Processing command {i}/{total_commands}: {command}...")
            
            # get base command (first word) for documentation
            base_command = command.split()[0]
            
            # get documentation from man pages
            print(f"  Getting man page for {base_command}...")
            man_content = get_man_page(base_command)
            
            # if man page failed, try --help
            help_content = None
            if not man_content:
                print(f"  Man page not found, trying --help for {base_command}...")
                help_content = get_help_output(base_command)
            
            # get actual execution output
            print(f"  Executing command: {command}...")
            execution_output = get_command_execution(command)
            
            # format the documentation
            doc = format_documentation(command, man_content, help_content, execution_output)
            
            # write to file
            f.write(doc)
            
            # update counts
            if man_content or help_content:
                documented_count += 1
                print(f"  Documentation for {base_command} complete.")
            else:
                print(f"  No documentation found for {base_command}.")
    
    print(f"\nDocumentation completed. {documented_count}/{total_commands} commands documented.")
    print(f"Output file: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()