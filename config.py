
"""
Our Configuration settings for the SSH honeypot
"""
import os

# server configuration
HOST = "0.0.0.0"
PORT = 2222
USERNAME = "honeypot"
PASSWORD = "password"

# file paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, 'honeypot.log')
DB_FILE = os.path.join(BASE_DIR, './frontend/honeypot.db')
HOST_KEY_FILE = os.path.join(BASE_DIR, 'host_key.pem')
FILESYSTEM_DIR = os.path.join(BASE_DIR, 'fake_filesystem')

# hostname for the honeypot
HOSTNAME = "server01"

# frontend configuration
FRONTEND_HOST = "localhost"
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
FRONTEND_PORT = 8000  # The port your frontend server runs on
FRONTEND_URL = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"

# RAG configuration
RAG_ENABLED = True
RAG_MODEL = "Cyboghost/llama-linux:latest" #Cyboghost/llama-linux:latest
RAG_COMMANDS_FILE = os.path.join(BASE_DIR, './rag/data/commands_doc.txt')
RAG_STORAGE_DIR = os.path.join(BASE_DIR, './rag/data/vector_store')  # Vector store directory
RAG_OLLAMA_URL = "http://localhost:11434"
RAG_STREAM_OUTPUT = True
RAG_TOKEN_DELAY = 0.0

# create directories if they don't exist
os.makedirs(os.path.dirname(RAG_COMMANDS_FILE), exist_ok=True)
os.makedirs(RAG_STORAGE_DIR, exist_ok=True)
