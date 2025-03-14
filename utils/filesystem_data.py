"""
Filesystem structure definition for the SSH honeypot
"""
import os
import json
import re
from utils.log_setup import logger
from config import BASE_DIR, USERNAME  # Import USERNAME from config

# path to the filesystem JSON data
JSON_FILE = os.path.join(BASE_DIR, 'files.json')

# load filesystem structure from JSON
try:
    with open(JSON_FILE, 'r') as f:
        file_system_raw = json.load(f)
    
    # convert to string for comprehensive replacement
    json_str = json.dumps(file_system_raw)
    
    # replace all instances of "haskoli" with USERNAME
    json_str = re.sub(r'([^a-zA-Z0-9])haskoli([^a-zA-Z0-9])', f'\\1{USERNAME}\\2', json_str)
    
    # convert back to a dictionary
    file_system = json.loads(json_str)
    
    logger.info(f"Successfully loaded filesystem structure from JSON, replacing 'haskoli' with '{USERNAME}'")
except FileNotFoundError:
    logger.error(f"Filesystem JSON file not found: {JSON_FILE}")
    # fallback to a minimal filesystem if JSON file not found
    file_system = {
        "bin": {},
        "boot": {},
        "dev": {},
        "etc": {},
        "home": {
            USERNAME: {  # use USERNAME from config
                ".bashrc": "# ~/.bashrc: executed by bash for non-login shells",
                "readme.txt": "Welcome to the server!"
            }
        },
        "opt": {},
        "tmp": {},
        "usr": {
            "bin": {},
            "local": {
                "bin": {}
            }
        },
        "var": {
            "log": {},
            "www": {
                "html": {}
            }
        }
    }
    logger.info("Using fallback filesystem structure")
except json.JSONDecodeError as e:
    logger.error(f"Error parsing filesystem JSON: {e}")
    # fallback to a minimal filesystem if JSON is invalid
    file_system = {
        "home": {
            USERNAME: {  # Use USERNAME from config
                ".bashrc": "# ~/.bashrc: executed by bash for non-login shells",
                "readme.txt": "Welcome to the server!"
            }
        }
    }
    logger.info("Using minimal fallback filesystem structure due to JSON error")

# sample files to create
sample_files = {
    f"/home/{USERNAME}/notes.txt": "These are my personal notes.",
    "/var/log/honeypot.log": "Feb 28 10:23:45 Honeypot service started"
}

# verify that the filesystem structure has all root directories
# this is a sanity check to ensure we have a proper Linux directory structure
required_dirs = ["bin", "boot", "dev", "etc", "home", "opt", "root", "tmp", "usr", "var"]
for dir_name in required_dirs:
    if dir_name not in file_system:
        file_system[dir_name] = {}
        logger.info(f"Added missing root directory: {dir_name}")
