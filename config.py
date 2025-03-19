"""
Our Configuration settings for the SSH honeypot
"""
import os

# server configuration
HOST = "0.0.0.0"
PORT = 2222
USERNAME = "haskoli"
PASSWORD = "password"

# file paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, 'honeypot.log')
DB_FILE = os.path.join(BASE_DIR, './frontend/honeypot.db')
HOST_KEY_FILE = os.path.join(BASE_DIR, 'host_key.pem')
FILESYSTEM_DIR = os.path.join(BASE_DIR, 'fake_filesystem')

# hostname for the honeypot
HOSTNAME = "ubuntu01"
USERNAME = "haskoli"  # This username will be used throughout the application
HOME_DIRECTORY = f"/home/{USERNAME}"  # Define the home directory based on username

# frontend configuration
FRONTEND_HOST = "localhost"
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')
FRONTEND_PORT = 8000  # The port your frontend server runs on
FRONTEND_URL = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"

# AI model configuration
AI_ENABLED = True
AI_MODE = "rag"  # Options: "rag" or "direct"

# Ollama model configuration
RAG_MODEL = "Cyboghost/gemma3-linux:latest" #Cyboghost/llama-linux:latest #Cyboghost/gemma3-linux:latest
RAG_OLLAMA_URL = "http://localhost:11434"
RAG_STREAM_OUTPUT = True   # Controls streaming for both RAG and direct inference
RAG_TOKEN_DELAY = 0.0      # Delay between tokens for streamed output (seconds)

# RAG-specific configuration (only used when AI_MODE = "rag")
RAG_COMMANDS_FILE = os.path.join(BASE_DIR, './rag/data/commands_doc.txt')
RAG_STORAGE_DIR = os.path.join(BASE_DIR, './rag/data/vector_store')  # Vector store directory

# create directories if they don't exist
os.makedirs(os.path.dirname(RAG_COMMANDS_FILE), exist_ok=True)
os.makedirs(RAG_STORAGE_DIR, exist_ok=True)
