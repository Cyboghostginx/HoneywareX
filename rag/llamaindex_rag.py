"""
optimized rag implementation using llamaindex for the ssh honeypot
"""
import os
import time
import json
import textwrap
import concurrent.futures
import threading
from typing import List, Callable, Optional
from pathlib import Path
import tiktoken

# llamaindex imports
from llama_index.core import (
    SimpleDirectoryReader, VectorStoreIndex, StorageContext, load_index_from_storage,
    Settings, Document
)
from llama_index.llms.ollama import Ollama
from llama_index.embeddings.fastembed import FastEmbedEmbedding
from llama_index.core.node_parser import SentenceSplitter, TokenTextSplitter, LangchainNodeParser
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.memory import ChatMemoryBuffer
from llama_index.core.chat_engine import SimpleChatEngine
from llama_index.core import PromptTemplate, Prompt
from langchain.text_splitter import RecursiveCharacterTextSplitter
from config import RAG_OLLAMA_URL, RAG_COMMANDS_FILE, RAG_STREAM_OUTPUT, RAG_TOKEN_DELAY, USERNAME, RAG_MODEL

# honeypot imports
from utils.log_setup import logger
from core.server import active_command
from utils.command_utils import NATIVE_COMMANDS

# file paths
DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
COMMANDS_DOCS_FILE = RAG_COMMANDS_FILE
VECTOR_STORE_DIR = os.path.join(DOCS_DIR, "vector_store")
EMBED_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "embed_cache")

class LlamaIndexRAG:
    def __init__(
        self, 
        commands_file=COMMANDS_DOCS_FILE,
        storage_dir=VECTOR_STORE_DIR,
        model_name=RAG_MODEL,
        embed_model_name="BAAI/bge-large-en-v1.5",
        chunk_size=100,  # increased for better context
        chunk_overlap=0,  # added overlap for better continuity
        ollama_url=RAG_OLLAMA_URL
    ):
        # set absolute paths to avoid any issues
        self.commands_file = commands_file
        self.base_storage_dir = storage_dir
        
        # extract filename from commands_file to use as a subdirectory
        self.file_basename = os.path.basename(commands_file)
        self.storage_dir = os.path.join(self.base_storage_dir, self.file_basename)
        
        self.model_name = model_name 
        self.embed_model_name = embed_model_name
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.ollama_url = ollama_url
        self.initialized = False
        self.session_memories = {}  # store memories for each session
        
        # add response caching
        self.response_cache = {}
        self.cache_ttl = 600  # cache lifetime in seconds (10 minutes)
        self.cache_timestamps = {}
        self.max_cache_size = 50  # maximum number of cached responses
        
        logger.info(f"Command docs file path: {self.commands_file}")
        logger.info(f"Vector store directory: {self.storage_dir}")
        logger.info(f"Using Ollama API at: {self.ollama_url}")
        logger.info(f"Initialized response caching system (TTL: {self.cache_ttl}s, max size: {self.max_cache_size})")
        
        # create necessary directories
        os.makedirs(self.storage_dir, exist_ok=True)
        os.makedirs(EMBED_CACHE_DIR, exist_ok=True)  # Create embedding cache directory
        
        # check if command docs file exists
        if not os.path.exists(self.commands_file):
            logger.error(f"Command documentation file not found: {self.commands_file}")
            logger.error("Please run prepare_command_docs.py first to generate the documentation")
            return
        
        # initialize llamaindex settings
        if not self._initialize_settings():
            return
        
        # load or create the index
        self.index = self._load_or_create_index()
        
        if self.index:
            self.initialized = True
            logger.info(f"LlamaIndex RAG initialized with model {model_name}")
        else:
            logger.error("Failed to initialize LlamaIndex RAG")
    
    def _initialize_settings(self):
        """initialize llamaindex settings with optimized parameters"""
        try:
            # Set environment variables to control embedding model cache location
            os.environ["FASTEMBED_CACHE_PATH"] = EMBED_CACHE_DIR
            os.environ["TRANSFORMERS_CACHE"] = EMBED_CACHE_DIR
            os.environ["HF_HOME"] = EMBED_CACHE_DIR
            logger.info(f"Set embedding cache environment variables to: {EMBED_CACHE_DIR}")
            
            # set up LLM (Ollama)
            Settings.llm = Ollama(
                model=self.model_name, 
                base_url=self.ollama_url,
                temperature=0.1,
                context_window=2048,
                request_timeout=60000
            )
            
            # set up embedding model
            Settings.embed_model = FastEmbedEmbedding(model_name=self.embed_model_name)
            
            # improved text splitter with more hierarchical separation
            Settings.text_splitter = LangchainNodeParser(
                RecursiveCharacterTextSplitter(
                    separators=["==="],  # more semantic separators
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap,
                    length_function=len  # use character count for consistency
                )
            )
            
            logger.info("LlamaIndex settings initialized with optimized parameters")
            return True
        except Exception as e:
            logger.error(f"Error initializing LlamaIndex settings: {e}")
            return False
    
    def _load_or_create_index(self):
        """load existing index or create a new one"""
        try:
            # check if storage directory exists and has content
            if os.path.exists(self.storage_dir) and len(os.listdir(self.storage_dir)) > 0:
                logger.info(f"Loading existing index from {self.storage_dir}")
                # load existing index
                storage_context = StorageContext.from_defaults(persist_dir=self.storage_dir)
                return load_index_from_storage(storage_context)
            else:
                logger.info(f"Creating new index from command documentation file")
                # create new index from documents
                return self._create_new_index()
        except Exception as e:
            logger.error(f"Error loading or creating index: {e}")
            return None
    
    def _create_new_index(self):
        """create a new index from the commands file"""
        try:
            # double check if commands file exists and has content
            if not os.path.exists(self.commands_file):
                logger.error(f"Commands file not found: {self.commands_file}")
                return None
                
            file_size = os.path.getsize(self.commands_file)
            if file_size == 0:
                logger.error(f"Commands file is empty: {self.commands_file}")
                return None
                
            logger.info(f"Commands file exists and has size: {file_size} bytes")
            
            # load the document
            logger.info(f"Loading command documentation from {self.commands_file}")
            documents = SimpleDirectoryReader(input_files=[self.commands_file]).load_data()
            
            if not documents:
                logger.warning("No command documentation loaded")
                return None
            
            # log document info
            logger.info(f"Loaded documentation with {len(documents[0].text)} characters")
            
            # check token count
            try:
                encoding = tiktoken.get_encoding("cl100k_base")
                num_tokens = len(encoding.encode(documents[0].text))
                logger.info(f"Document contains approximately {num_tokens} tokens")
            except Exception as e:
                logger.warning(f"Could not count tokens: {e}")
            
            # get nodes from documents
            logger.info(f"Splitting document using configured separators")
            nodes = Settings.text_splitter.get_nodes_from_documents(documents)
            logger.info(f"Created {len(nodes)} nodes from documentation")
            
            # create index
            logger.info("Creating vector index")
            index = VectorStoreIndex(nodes)
            
            # persist index
            logger.info(f"Persisting index to {self.storage_dir}")
            index.storage_context.persist(persist_dir=self.storage_dir)
            
            return index
        except Exception as e:
            logger.error(f"Error creating new index: {e}")
            return None
    
    def get_session_memory(self, session_id):
        """get or create memory buffer for a session"""
        if session_id not in self.session_memories:
            self.session_memories[session_id] = ChatMemoryBuffer.from_defaults(token_limit=25000)
        return self.session_memories[session_id]
    
    def cleanup_session(self, session_id):
        """clean up resources for a session"""
        if session_id in self.session_memories:
            del self.session_memories[session_id]
            logger.info(f"Cleaned up memory for session {session_id}")
    
    def generate_response(self, session_id, command_input, token_callback=None):
        """generate a response for a command using rag with optimized handling"""
        if not self.initialized or not self.index:
            logger.error("RAG not initialized or index not available")
            return None
        
        if not command_input or command_input.strip() == "":
            logger.error("Empty command input")
            return None
        
        # prepare cache key - normalize command by removing extra spaces and lowercasing
        cache_key = ' '.join(command_input.lower().split())
        current_time = time.time()
        
        # check if response is in cache and not expired
        if cache_key in self.response_cache and current_time - self.cache_timestamps.get(cache_key, 0) < self.cache_ttl:
            logger.info(f"Using cached response for: '{command_input}'")
            cached_response = self.response_cache[cache_key]
            
            # for streaming, simulate streaming from cache
            if RAG_STREAM_OUTPUT and token_callback:
                # Always stream by lines to preserve exact formatting
                for line in cached_response.split('\n'):
                    # check for interruption
                    if active_command.get("interrupted", False) and active_command.get("session_id") == session_id:
                        logger.info(f"Interrupting cached response streaming for session {session_id}")
                        break
                    # Send complete line with newline to preserve exact formatting
                    token_callback(line + '\n')
                    if RAG_TOKEN_DELAY > 0:
                        time.sleep(RAG_TOKEN_DELAY)
            return cached_response
            
        try:
            # get session memory
            memory = self.get_session_memory(session_id)
            
            # define system prompt template
            template = Prompt("""
                <s>[INST] <<SYS>>
                You are a Linux server. First rely on your built-in knowledge about Linux commands. Don't rely wholly on {context_str} it is just meant to enhance you, use your own powerful understanding. Don't explain under any condition so you don't expose yourself to the user as AI.
                Your hostname is haskoli.
                Don't add the usual linux prefix to your output.
                No self explanation at all from you even if in context, don't explain anything, just linux output.
                Please don't explain anything just output so users don't know you are an AI.


                Refer to the following context: {context_str}

                Continue the conversation: {query_str}
            """)
            
            # create chat engine with optimized parameters
            query_engine = self.index.as_query_engine(
                text_qa_template=template,
                similarity_top_k=2,
                memory=memory,
                streaming=True
            )
            
            # generate response
            start_time = time.time()
            full_response = ""
            
            # add adaptive timeout based on command complexity
            timeout_seconds = min(45, 15 + len(command_input.split()) * 1.5)
            
            # choose streaming or non-streaming mode based on config
            if RAG_STREAM_OUTPUT and token_callback:
                logger.info(f"using streaming mode for command: '{command_input}'")
                
                try:
                    # get streaming response
                    stream_response = query_engine.query(command_input)
                    
                    # process tokens as they arrive - simpler streaming like notebook
                    full_response = ""
                    for token in stream_response.response_gen:
                        # check for interruption
                        if active_command.get("interrupted", False) and active_command.get("session_id") == session_id:
                            logger.info(f"interrupting response streaming for session {session_id}")
                            break
                            
                        full_response += token
                        token_callback(token)
                        
                        # token delay if configured
                        if RAG_TOKEN_DELAY > 0:
                            time.sleep(RAG_TOKEN_DELAY)
                            
                    logger.info(f"streaming complete for: '{command_input}'")
                        
                except Exception as e:
                    logger.error(f"error during streaming: {e}")
                    if token_callback:
                        token_callback(f"\nerror: {str(e)}")
            else:
                logger.info(f"Using non-streaming mode for command: '{command_input}'")
                try:
                    response = query_engine.chat(command_input)
                    full_response = response.response
                except Exception as e:
                    logger.error(f"Error in non-streaming mode: {e}")
                    full_response = f"Error executing command: {str(e)}"
            
            # clean the response
            full_response = self.clean_command_output(command_input, full_response)
            
            # cache the response if it's not an error and not too long
            if not full_response.startswith("Error") and len(full_response) < 10000:
                self.response_cache[cache_key] = full_response
                self.cache_timestamps[cache_key] = current_time
                
                # clean up oldest entries if cache exceeds size limit
                if len(self.response_cache) > self.max_cache_size:
                    oldest_key = min(self.cache_timestamps, key=self.cache_timestamps.get)
                    del self.response_cache[oldest_key]
                    del self.cache_timestamps[oldest_key]
                    logger.debug(f"Removed oldest cache entry: {oldest_key}")
            
            elapsed_time = time.time() - start_time
            logger.info(f"Generated response for '{command_input}' in {elapsed_time:.2f} seconds")
            
            return full_response
        except Exception as e:
            logger.error(f"Error generating response for command '{command_input}': {e}")
            return f"Error executing command: {str(e)}"

    def clean_command_output(self, command_input, response_text):
        """enhanced cleaning of command output to remove markdown and explanatory elements"""
        import re
        
        # extract command for context-aware cleaning
        cmd = command_input.split()[0].lower() if command_input else ""
        
        # 1. remove markdown code block markers more aggressively
        response_text = re.sub(r'```(?:bash|shell|console|terminal)?', '', response_text)
        response_text = re.sub(r'```', '', response_text)
        
        # 2. remove instruction/explanation paragraphs (often start with "here's", "this is", etc.)
        response_text = re.sub(r'^(?:here\'s|this is|the following|i\'ll|let me|this command|when you).+?:\n', '', response_text, flags=re.MULTILINE|re.IGNORECASE)
        
        # 3. remove explanatory lines at the end (common in rag responses)
        response_text = re.sub(r'\n(?:this shows|this displays|this lists|this command).+$', '', response_text, flags=re.MULTILINE|re.IGNORECASE)
        
        # 4. remove bold/italic markdown more thoroughly
        response_text = re.sub(r'\*\*(.*?)\*\*', r'\1', response_text)  # bold
        response_text = re.sub(r'\*(.*?)\*', r'\1', response_text)      # italic
        response_text = re.sub(r'__(.*?)__', r'\1', response_text)      # alternative bold
        response_text = re.sub(r'_(.*?)_', r'\1', response_text)        # alternative italic
        
        # 5. better handling of command line prompts
        response_text = re.sub(r'^.+?@.+?:~[$#]\s*', '', response_text, flags=re.MULTILINE)
        
        # 6. remove markdown headers
        response_text = re.sub(r'^#+\s+.*$', '', response_text, flags=re.MULTILINE)
        
        # 7. remove numbered lists and bullet points
        response_text = re.sub(r'^\s*\d+\.\s+', '', response_text, flags=re.MULTILINE)
        response_text = re.sub(r'^\s*[\*\-•]\s+', '', response_text, flags=re.MULTILINE)
        
        # 8. command-specific cleaning
        if cmd in ['ls', 'dir']:
            # for ls, prefer columnar format without additional text
            response_text = re.sub(r'total \d+\s*\n', '', response_text)
        elif cmd in ['cat', 'less', 'more']:
            # for file viewing commands, remove any leading spaces on new lines
            response_text = re.sub(r'\n\s+', '\n', response_text)
        elif cmd in ['grep', 'find']:
            # for search commands, ensure results are properly formatted
            # remove any "matches found" summary lines
            response_text = re.sub(r'\n\d+ matches found\.?$', '', response_text, flags=re.IGNORECASE)
        
        # 9. clean up whitespace
        response_text = re.sub(r'\n{3,}', '\n\n', response_text)  # max double newlines
        response_text = response_text.strip()
        
        return response_text
