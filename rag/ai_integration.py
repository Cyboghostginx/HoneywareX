"""
Integration module for AI capabilities (both RAG and direct inference)
"""
import os
import sys
import requests
from utils.log_setup import logger
from config import AI_ENABLED, AI_MODE, RAG_OLLAMA_URL, RAG_MODEL

def check_ollama_availability(model_name):
    """
    Check if Ollama is installed, running, and has the required model.
    """
    import requests
    
    # first we want to check if Ollama is running by trying to connect to its API
    try:
        # Attempt to connect to Ollama API
        response = requests.get(RAG_OLLAMA_URL, timeout=5)
        if response.status_code != 200:
            return False, f"Ollama is not responding correctly (Status code: {response.status_code})"
    except requests.exceptions.ConnectionError:
        return False, "Ollama is not running or not installed. Please install Ollama from https://ollama.com"
    except requests.exceptions.Timeout:
        return False, "Connection to Ollama timed out. Please check if Ollama is running properly."
    except Exception as e:
        return False, f"Error connecting to Ollama: {str(e)}"
    
    # next we check if the required model is available
    try:
        # to list available models
        response = requests.get(f"{RAG_OLLAMA_URL}/api/tags", timeout=5)
        if response.status_code != 200:
            return False, f"Couldn't retrieve model list from Ollama (Status code: {response.status_code})"
        
        models = response.json().get('models', [])
        model_names = [model.get('name') for model in models]
        
        # here we check if our model is in the list
        if model_name not in model_names:
            return False, f"The required model '{model_name}' is not installed. Please run 'ollama pull {model_name}'"
            
        return True, f"Ollama is running and the '{model_name}' model is available"
    except Exception as e:
        return False, f"Error checking for model availability: {str(e)}"

def integrate_ai_with_command_processor(command_processor):
    # import the mode setting from config but don't modify it
    from config import AI_MODE as configured_mode
    
    # use a local variable for potential mode changes
    current_mode = configured_mode.lower()
    
    if not AI_ENABLED:
        logger.info("AI capabilities are disabled in configuration")
        return command_processor
    
    # check Ollama availability regardless of mode
    ollama_available, message = check_ollama_availability(RAG_MODEL)
    if not ollama_available:
        logger.error(f"Ollama not available: {message}")
        print(f"[!] AI will be disabled: {message}")
        return command_processor
    
    print(f"[*] {message}")
    
    if current_mode == "rag":
        # use RAG integration
        try:
            print("[*] Initializing RAG system with LlamaIndex...")
            # we use a delayed import to avoid dependencies if not using RAG
            from rag.rag_integration import integrate_rag_with_command_processor
            enhanced_processor = integrate_rag_with_command_processor(command_processor)
            print("[*] RAG system initialized successfully")
            return enhanced_processor
        except Exception as e:
            logger.error(f"Error initializing RAG: {e}")
            print(f"[!] Failed to initialize RAG system: {e}")
            print("[*] Falling back to direct inference mode")
            # fall back to direct inference if RAG fails
            current_mode = "direct"
    
    if current_mode == "direct":
        # use direct inference
        try:
            print("[*] Initializing direct model inference...")
            from rag.direct_inference import DirectOllamaInference
            
            # create the direct inference handler
            direct_inference = DirectOllamaInference()
            
            # ADDED: Set the known commands from the command processor
            if hasattr(command_processor, 'known_commands'):
                direct_inference.set_known_commands(command_processor.known_commands)
                logger.info("Set known commands for direct inference")
            
            # store reference to original execute_command and process_command methods
            original_execute = command_processor.execute_command
            original_process = command_processor.process_command
            
            # enhance the process_command method to handle non-native commands
            def enhanced_process_command(session_id, command):
                # split command and arguments
                parts = command.split()
                if not parts:
                    return ""
                
                cmd = parts[0].lower()
                
                # check if this is a command we implement natively
                if hasattr(command_processor, 'known_commands') and cmd in command_processor.known_commands:
                    # check if the command is also in implemented_commands - otherwise use AI
                    if direct_inference.is_native_command(command):
                        # this is a fully implemented command - use the original implementation
                        return original_process(session_id, command)
                    else:
                        # this is a recognized but not natively implemented command - use AI
                        return direct_inference.process_command(session_id, command)
                else:
                    # not a recognized command - use original (which will show command not found)
                    return original_process(session_id, command)
            
            # enhance the execute_command method for streaming
            def enhanced_execute_command(session_id, command, token_callback=None):
                # split command and arguments
                parts = command.split()
                if not parts:
                    return ""
                
                cmd = parts[0].lower()
                
                # check if this is a command we implement natively
                if hasattr(command_processor, 'known_commands') and cmd in command_processor.known_commands:
                    # check if the command is also in implemented_commands - otherwise use AI
                    if direct_inference.is_native_command(command):
                        # this is a fully implemented command - use the original implementation
                        return original_execute(session_id, command)
                    else:
                        # this is a recognized but not natively implemented command - use AI
                        return direct_inference.process_command(session_id, command, token_callback)
                else:
                    # not a recognized command - use original (which will show command not found)
                    return original_execute(session_id, command)
                
            # replace the methods in the command processor
            command_processor.process_command = enhanced_process_command
            command_processor.execute_command = enhanced_execute_command
            
            # add a reference to the direct inference handler - this makes it accessible
            # to server.py for streaming detection in the same way as smart_rag
            command_processor.direct_inference = direct_inference
            
            # for compatibility with server.py streaming code, also set smart_rag
            # this ensures the streaming detection in server.py works
            command_processor.smart_rag = direct_inference
            
            print("[*] Direct inference system initialized successfully")
            return command_processor
            
        except Exception as e:
            logger.error(f"Error initializing direct inference: {e}")
            print(f"[!] Failed to initialize direct inference: {e}")
            return command_processor
    
    # if we get here, no valid AI mode was configured
    logger.warning(f"Unknown AI_MODE: {configured_mode}, AI capabilities disabled")
    print(f"[!] Unknown AI_MODE: {configured_mode}, AI capabilities disabled")
    return command_processor
