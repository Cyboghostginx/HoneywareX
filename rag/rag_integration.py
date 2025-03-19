"""
Only uses RAG for commands not natively implemented in the honeypot
"""
import os
import sys
import types
from utils.log_setup import logger
from utils.command_utils import NATIVE_COMMANDS
from config import RAG_OLLAMA_URL, RAG_MODEL, RAG_COMMANDS_FILE, RAG_STREAM_OUTPUT
from core.server import active_command

# absolute paths
DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
COMMANDS_DOCS_FILE = RAG_COMMANDS_FILE

class SmartRAGIntegration:
    def __init__(self, known_commands=None, ollama_url=RAG_OLLAMA_URL, model_name=None):
        logger.info("Initializing SmartRAGIntegration")
        # use config value by default, allow override if explicitly provided
        self.model_name = model_name if model_name is not None else RAG_MODEL
        logger.info(f"Using model: {self.model_name}")
        self.ollama_url = ollama_url
        self.rag = None
        self.initialized = False
        self.known_commands = known_commands or set()
        self.streaming_sessions = {}  # track active streaming sessions
        
        # check if command docs file exists
        if not os.path.exists(COMMANDS_DOCS_FILE):
            logger.error(f"Command documentation file not found: {COMMANDS_DOCS_FILE}")
            logger.error("Please run prepare_command_docs.py first to generate the documentation")
            return
            
        logger.info(f"Command docs file found at: {COMMANDS_DOCS_FILE}")
            
        # only import LlamaIndexRAG when needed (to avoid unnecessary dependencies)
        try:
            # import the LlamaIndex RAG module
            from rag.llamaindex_rag import LlamaIndexRAG
            
            # initialize the RAG system
            logger.info(f"Initializing LlamaIndexRAG at {self.ollama_url}")
            self.rag = LlamaIndexRAG(ollama_url=self.ollama_url)
            
            if self.rag and self.rag.initialized:
                self.initialized = True
                logger.info("Smart RAG integration initialized successfully")
            else:
                logger.error("Failed to initialize RAG component")
        except ImportError as e:
            logger.error(f"Could not import LlamaIndexRAG - missing dependencies: {e}")
        except Exception as e:
            logger.error(f"Error initializing SmartRAGIntegration: {e}")
    
    def is_native_command(self, command_input):
        """Check if the command is natively handled by the honeypot or is invalid"""
        if not command_input or command_input.strip() == "":
            return True  # empty commands are handled natively
            
        # extract the main command (first word)
        command = command_input.strip().split()[0] if command_input.strip() else ""
        
        # check if it's a native command (directly implemented)
        if command in NATIVE_COMMANDS:
            return True
        
        # check if it's an unknown command (not in the known commands list), treat unknown commands as "native" so they get the proper "command not found" message
        if command not in self.known_commands:
            return True
        
        # if it's a known command but not native, use RAG
        return False
    
    def check_ollama_status(self):
        """Check if Ollama is still available"""
        import requests
        
        try:
            # quick health check
            response = requests.get(self.ollama_url, timeout=1)
            return response.status_code == 200
        except:
            return False
    
    def generate_response(self, session_id, command_input, token_callback=None):
        """Generate a response using RAG, but only for non-native commands"""
        if not self.initialized or not self.rag:
            logger.warning("RAG not initialized, cannot generate response")
            return "RAG system is not initialized. Commands requiring context will not work."
                
        if not command_input or command_input.strip() == "":
            logger.warning("Empty command input, skipping RAG")
            return None
        
        # quick check if Ollama is still available
        if not self.check_ollama_status():
            logger.error("Ollama is no longer available")
            return "Error: Ollama is not responding. RAG-based commands will not work."
                
        # skip native commands
        if self.is_native_command(command_input):
            logger.info(f"Skipping RAG for native command: {command_input.split()[0]}")
            return None
                
        # for non-native commands, use RAG with optional streaming
        # generate response with optional streaming
        try:
            logger.info(f"Generating RAG response for: {command_input}")
            
            # store the token callback for this session if streaming is enabled
            if RAG_STREAM_OUTPUT and token_callback:
                self.streaming_sessions[session_id] = token_callback
                logger.info(f"Enabled streaming for session {session_id}")
            
            # Check for interruption before making the RAG request
            return self.rag.generate_response(session_id, command_input, token_callback)
        except Exception as e:
            # Check if the exception was caused by an interruption
            if active_command.get("interrupted", False) and active_command.get("session_id") == session_id:
                logger.info(f"RAG request interrupted by user for session {session_id}")
                return "^C"
            logger.error(f"Error generating RAG response: {e}")
            return f"Error executing command: {str(e)}"
    
    def cleanup_session(self, session_id):
        """Clean up RAG session memory"""
        if self.initialized and self.rag:
            try:
                self.rag.cleanup_session(session_id)
                logger.info(f"Cleaned up RAG session: {session_id}")
                
                # remove streaming callback if exists
                if session_id in self.streaming_sessions:
                    del self.streaming_sessions[session_id]
                    logger.info(f"Removed streaming callback for session: {session_id}")
            except Exception as e:
                logger.error(f"Error cleaning up RAG session: {e}")


def integrate_rag_with_command_processor(command_processor):
    """Integrate Smart RAG with the CommandProcessor class"""
    logger.info("Integrating RAG with CommandProcessor")
    
    try:
        # initialize the Smart RAG system with the known commands list
        logger.info("Creating SmartRAGIntegration instance")
        smart_rag = SmartRAGIntegration(
            known_commands=command_processor.known_commands
        )
        
        if not smart_rag.initialized:
            logger.error("Failed to initialize Smart RAG, continuing without RAG capabilities")
            return command_processor
        
        # store the RAG instance in the command processor
        command_processor.smart_rag = smart_rag
        
        # get references to the original methods
        original_execute = command_processor.execute_command
        original_cleanup = command_processor.cleanup_session
        
        # define the wrapper for execute_command
        def execute_wrapper(self, session_id, command, token_callback=None):
            try:
                # handle empty commands
                if not command or command.strip() == "":
                    logger.info("Empty command received")
                    return original_execute(session_id, command)
                    
                # extract main command for logging
                main_cmd = command.strip().split()[0] if command.strip() else "empty"
                
                # first check if this is a native command the honeypot can handle directly
                if hasattr(self, 'smart_rag') and self.smart_rag.is_native_command(command):
                    logger.info(f"Using native handler for command: {main_cmd}")
                    return original_execute(session_id, command)
                    
                # if not native, try to use RAG
                if hasattr(self, 'smart_rag') and self.smart_rag.initialized:
                    try:
                        logger.info(f"Attempting RAG for non-native command: {main_cmd}")
                        rag_response = self.smart_rag.generate_response(session_id, command, token_callback)
                        
                        # if RAG response is available, use it
                        if rag_response:
                            logger.info(f"Using RAG response for command: {main_cmd}")
                            self.last_exit_code[session_id] = 0
                            return rag_response
                        else:
                            logger.info(f"RAG returned no response for: {main_cmd}")
                    except Exception as e:
                        logger.error(f"Error in RAG response generation: {e}")
                
                # if RAG fails or isn't available, fall back to original command execution
                logger.info(f"Falling back to default handling for command: {main_cmd}")
                return original_execute(session_id, command)
            except Exception as e:
                logger.error(f"Unhandled exception in execute_command: {e}")
                return f"Error executing command: {str(e)}"
        
        # define the wrapper for cleanup_session
        def cleanup_wrapper(self, session_id):
            # clean up RAG session memory
            if hasattr(self, 'smart_rag') and self.smart_rag.initialized:
                try:
                    self.smart_rag.cleanup_session(session_id)
                except Exception as e:
                    logger.error(f"Error cleaning up RAG session: {e}")
            
            # call original cleanup
            return original_cleanup(session_id)
        
        # create a custom class that will replace the methods
        class PatchedCommandProcessor(type(command_processor)):
            def execute_command(self, session_id, command, token_callback=None):
                return execute_wrapper(self, session_id, command, token_callback)
                
            def cleanup_session(self, session_id):
                return cleanup_wrapper(self, session_id)
        
        # set the patched class as the class of the command processor
        command_processor.__class__ = PatchedCommandProcessor
        
        logger.info("Smart RAG successfully integrated with CommandProcessor")
    except Exception as e:
        logger.error(f"Failed to integrate Smart RAG: {e}")
    
    return command_processor
