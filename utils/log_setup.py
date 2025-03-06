"""
Logging configuration for the SSH honeypot
"""
import logging
import sys
from config import LOG_FILE

# setup logging
logger = logging.getLogger('SSH_Honeypot')
logger.setLevel(logging.INFO)

# file handler
file_handler = logging.FileHandler(LOG_FILE)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
logger.addHandler(file_handler)

# console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(console_handler)