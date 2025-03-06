"""
Utility functions for the SSH honeypot
"""
import socket
import paramiko
import os
from utils.log_setup import logger
from config import HOST_KEY_FILE, FRONTEND_URL, FRONTEND_HOST, FRONTEND_PORT

def get_local_ip():
    """Get the local IP address"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception as e:
        logger.error(f"Error getting local IP: {e}")
        return "127.0.0.1"

# display frontend URL
local_ip = get_local_ip()
frontend_url = f"http://{local_ip}:{FRONTEND_PORT}"

def generate_host_key():
    """Generate a new RSA host key if it doesn't exist"""
    if not os.path.exists(HOST_KEY_FILE):
        logger.info(f"Host key file not found. Generating a new RSA key...")
        key = paramiko.RSAKey.generate(2048)
        key.write_private_key_file(HOST_KEY_FILE)
        logger.info(f"New RSA key generated and saved to {HOST_KEY_FILE}")
    
    return paramiko.RSAKey(filename=HOST_KEY_FILE)

def format_connection_info(username, local_ip, port, password):
    return f"""
{'='*50}
SSH Honeypot Ready! (Use Command Below To Connect): 
--
ssh {username}@{local_ip} -p {port}
--
Password: {password}
{'='*50}
You can as well check your logged session in the frontend dashboard using the URL below:
--
Frontend Dashboard URL: {frontend_url}
{'='*50}
"""