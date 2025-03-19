"""
Direct inference with Ollama models without RAG
"""
import requests
import json
import time
from utils.log_setup import logger
from utils.command_utils import NATIVE_COMMANDS
from config import RAG_OLLAMA_URL, RAG_MODEL, RAG_TOKEN_DELAY, RAG_STREAM_OUTPUT
from core.server import active_command

class DirectOllamaInference:
    
    def __init__(self):
        """initialize the direct inference handler"""
        self.ollama_url = RAG_OLLAMA_URL
        self.model = RAG_MODEL
        self.api_url = f"{self.ollama_url}/api/generate"
        self.active_sessions = {}
        
        # list of commands that are natively implemented
        self.native_commands = NATIVE_COMMANDS
        
        logger.info(f"Initialized DirectOllamaInference with model {self.model}")
        
    def process_command(self, session_id, command, token_callback=None):
        # Maintain minimal session context
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = []
            
        try:
            # Handle streaming vs non-streaming mode based on config
            if RAG_STREAM_OUTPUT and token_callback:
                return self._stream_response(command, token_callback)
            else:
                return self._generate_response(command)
                
        except Exception as e:
            logger.error(f"Error in direct inference: {e}")
            return f"Error processing command: {str(e)}"
    
    def _generate_response(self, command):
        request_data = {
            "model": self.model,
            "prompt": command,
            "stream": False,
            "options": {
                "temperature": 0.1
            }
        }
        
        try:
            response = requests.post(self.api_url, json=request_data, timeout=3000)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "")
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama API error: {e}")
            return f"Error: Could not connect to Ollama API: {str(e)}"
    
    def _stream_response(self, command, token_callback):
        request_data = {
            "model": self.model,
            "prompt": command,
            "stream": True,
            "options": {
                "temperature": 0.1
            }
        }
        
        try:
            with requests.post(self.api_url, json=request_data, timeout=3000, stream=True) as response:
                response.raise_for_status()
                
                # process the streaming response
                full_response = ""
                for line in response.iter_lines():
                    # Add interruption check here
                    if active_command.get("interrupted", False):
                        logger.info(f"Direct inference streaming interrupted by user")
                        response.close()  # Important: Close the HTTP connection
                        break
                        
                    if line:
                        # decode and parse the JSON line
                        line_data = json.loads(line.decode('utf-8'))
                        if 'response' in line_data:
                            token = line_data['response']
                            full_response += token
                            
                            # call the token callback
                            token_callback(token)
                            
                            # apply token delay if configured
                            if RAG_TOKEN_DELAY > 0:
                                time.sleep(RAG_TOKEN_DELAY)
                
                return full_response
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama streaming API error: {e}")
            error_message = f"Error: Could not connect to Ollama API: {str(e)}"
            if token_callback:
                token_callback(error_message)
            return error_message
            
    def is_native_command(self, command):
        """Check if a command is natively implemented in the shell"""
        cmd = command.split()[0].lower() if command else ""
        return cmd in self.native_commands
            
    def cleanup_session(self, session_id):
        """Clean up session data"""
        if session_id in self.active_sessions:
            del self.active_sessions[session_id]
