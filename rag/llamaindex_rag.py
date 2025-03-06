"""
RAG implementation using LlamaIndex for the SSH honeypot
"""
import os
import time
import json
import nest_asyncio
from typing import List, Callable, Optional
from pathlib import Path
import tiktoken

# LlamaIndex imports
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
from llama_index.core import PromptTemplate
from langchain.text_splitter import RecursiveCharacterTextSplitter
from config import RAG_OLLAMA_URL, RAG_COMMANDS_FILE, RAG_STREAM_OUTPUT, RAG_TOKEN_DELAY

# honeypot imports
from utils.log_setup import logger

# initialize nest_asyncio to handle async operations
nest_asyncio.apply()

# file paths
DOCS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
COMMANDS_DOCS_FILE = RAG_COMMANDS_FILE
VECTOR_STORE_DIR = os.path.join(DOCS_DIR, "vector_store")

class LlamaIndexRAG:
    def __init__(
        self, 
        commands_file=COMMANDS_DOCS_FILE,
        storage_dir=VECTOR_STORE_DIR,
        model_name="llama3.2:3b",
        embed_model_name="BAAI/bge-large-en-v1.5",
        chunk_size=100,
        chunk_overlap=0,
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
        
        logger.info(f"Command docs file path: {self.commands_file}")
        logger.info(f"Vector store directory: {self.storage_dir}")
        logger.info(f"Using Ollama API at: {self.ollama_url}")
        
        # create necessary directories
        os.makedirs(self.storage_dir, exist_ok=True)
        
        # check if command docs file exists
        if not os.path.exists(self.commands_file):
            logger.error(f"Command documentation file not found: {self.commands_file}")
            logger.error("Please run prepare_command_docs.py first to generate the documentation")
            return
        
        # initialize LlamaIndex settings
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
        """Initialize LlamaIndex settings"""
        try:
            # set up LLM (Ollama)
            Settings.llm = Ollama(
                model=self.model_name, 
                base_url=self.ollama_url,
                temperature=0.2,
                prompt_key= "Act as a linux ssh server",
                request_timeout=60.0
            )
            
            # set up embedding model
            Settings.embed_model = FastEmbedEmbedding(model_name=self.embed_model_name)
            
            # set up text splitter with only === as the separator
            Settings.text_splitter = LangchainNodeParser(
                RecursiveCharacterTextSplitter(
                    separators=["==="],  # only use === as separator
                    chunk_size=self.chunk_size,
                    chunk_overlap=self.chunk_overlap
                )
            )
            
            logger.info("LlamaIndex settings initialized")
            return True
        except Exception as e:
            logger.error(f"Error initializing LlamaIndex settings: {e}")
            return False
    
    def _load_or_create_index(self):
        """Load existing index or create a new one"""
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
        """Create a new index from the commands file"""
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
            logger.info("Splitting document using === separator")
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
        if session_id not in self.session_memories:
            self.session_memories[session_id] = ChatMemoryBuffer.from_defaults(token_limit=25000)
        return self.session_memories[session_id]
    
    def cleanup_session(self, session_id):
        if session_id in self.session_memories:
            del self.session_memories[session_id]
    
    def generate_response(self, session_id, command_input, token_callback=None):
        if not self.initialized or not self.index:
            logger.error("RAG not initialized or index not available")
            return None
        
        if not command_input or command_input.strip() == "":
            logger.error("Empty command input")
            return None
            
        try:
            # get session memory
            memory = self.get_session_memory(session_id)
            
            # define system prompt template
            template = (
                "You are a Linux server. First rely on your built-in knowledge about Linux commands. Don't rely wholly on {context_str} it is just meant to enhance you, use your own powerful understanding. Don't explain under any condition so you don't expose yourself to the user as AI.\n"
                "Your hostname is server01.\n"
                "Don't add the usual linux prefix to your output.\n"
                "No self explanation at all from you even if in context, don't explain anything, just linux output."
            )
            
            # create chat engine with optimized parameters
            query_engine = self.index.as_chat_engine(
                chat_mode="context",
                similarity_top_k=2,
                memory=memory,
                system_prompt=template
            )
            
            # generate response
            start_time = time.time()
            full_response = ""
            
            # choose streaming or non-streaming mode based on config
            if RAG_STREAM_OUTPUT and token_callback:
                logger.info(f"Using streaming mode for command: '{command_input}'")
                
                try:
                    # get streaming response
                    stream_response = query_engine.stream_chat(command_input)
                    
                    # track streaming stats
                    token_count = 0
                    last_token_time = time.time()
                    
                    # process tokens as they arrive
                    for token in stream_response.response_gen:
                        full_response += token
                        token_count += 1
                        
                        # call the callback function with each token
                        token_callback(token)
                        
                        # check for hard timeout
                        if time.time() - start_time > 30:  # 30 second max
                            logger.warning(f"Hard timeout after 30 seconds for command: {command_input}")
                            break
                        
                        # token delay
                        if RAG_TOKEN_DELAY > 0:
                            time.sleep(RAG_TOKEN_DELAY)
                            
                    logger.info(f"Streaming complete: {token_count} tokens in {time.time() - start_time:.2f}s")
                    
                except Exception as e:
                    logger.error(f"Error during streaming: {e}")
                    if token_callback:
                        token_callback(f"\nError: {str(e)}")
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
            
            elapsed_time = time.time() - start_time
            logger.info(f"Generated response for '{command_input}' in {elapsed_time:.2f} seconds")
            
            return full_response
        except Exception as e:
            logger.error(f"Error generating response for command '{command_input}': {e}")
            return f"Error executing command: {str(e)}"

    def clean_command_output(self, command_input, response_text):
        """Clean command output to remove markdown and explanatory elements"""
        import re
        
        # remove markdown code block markers
        response_text = re.sub(r'```(?:bash|shell)?\n', '', response_text)
        response_text = re.sub(r'\n```', '', response_text)
        response_text = re.sub(r'^```(?:bash|shell)?$', '', response_text, flags=re.MULTILINE)
        response_text = re.sub(r'^```$', '', response_text, flags=re.MULTILINE)
        
        # remove bold/italic markdown
        response_text = re.sub(r'\*\*(.*?)\*\*', r'\1', response_text)  # Bold
        response_text = re.sub(r'\*(.*?)\*', r'\1', response_text)      # Italic
        
        # remove numbered lists formatting
        response_text = re.sub(r'^\s*\d+\.\s+', '', response_text, flags=re.MULTILINE)
        
        # remove bullet points
        response_text = re.sub(r'^\s*[\*\-•]\s+', '', response_text, flags=re.MULTILINE)
        
        # remove headers that look like explanations
        response_text = re.sub(r'^#+\s+.*?:$', '', response_text, flags=re.MULTILINE)
        
        # remove empty lines at beginning
        response_text = re.sub(r'^\s+', '', response_text)
        
        # consolidate multiple newlines into at most two
        response_text = re.sub(r'\n{3,}', '\n\n', response_text)

        # clean up any leading/trailing whitespace
        response_text = response_text.strip()
        
        return response_text.strip()