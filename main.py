"""
Main file for SSH honeypot
"""
import sys, signal, threading, os, subprocess
from config import HOST, PORT, USERNAME, PASSWORD, FILESYSTEM_DIR, AI_ENABLED, AI_MODE, RAG_MODEL, RAG_OLLAMA_URL, FRONTEND_DIR, FRONTEND_HOST, FRONTEND_PORT
from utils.log_setup import logger
from core.database import init_db
from core.virtual_filesystem import VirtualFilesystem
from core.command_processor import CommandProcessor
from core.server import start_server, stop_event
from utils.utils import get_local_ip, generate_host_key, format_connection_info
from rag.ai_integration import integrate_ai_with_command_processor, check_ollama_availability

def start_db_exporter():
    """Starting the database to JSON exporter as a subprocess"""
    try:
        # our path to the frontend directory and update script
        frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'frontend')
        update_script = os.path.join(frontend_dir, 'update_json.py')
        
        # check to see if that update script is available
        if not os.path.exists(update_script):
            logger.error(f"Update script not found at {update_script}")
            print(f"[!] Update script not found at {update_script}")
            return False
        
        # make script executable on Unix-like systems
        if os.name == 'posix':
            os.chmod(update_script, 0o755)
        
        # here we choose the correct Python command based on platform
        python_cmd = 'python3' if os.name == 'posix' else 'python'
        
        # start the script as a subprocess in the correct directory
        logger.info(f"Starting DB to JSON updater from {update_script}")
        print(f"[*] Starting DB to JSON updater from {update_script}")

        # start the frontend server
        print("[*] Starting frontend server...")
        frontend_thread = start_frontend_server(FRONTEND_DIR, FRONTEND_PORT)
        
        # using cwd parameter to run in the correct directory
        process = subprocess.Popen(
            [python_cmd, update_script],
            cwd=frontend_dir,
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        
        # now we check if the DB updater process started successfully
        if process.poll() is None:  # Process is running
            logger.info("DB to JSON updater started successfully")
            print("[*] DB to JSON updater started successfully")
            return True
        else:
            # process exited immediately, get error output
            _, stderr = process.communicate()
            error_msg = stderr.decode('utf-8', errors='ignore')
            logger.error(f"DB to JSON updater failed to start: {error_msg}")
            print(f"[!] DB to JSON updater failed to start: {error_msg}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to start DB to JSON updater: {e}")
        print(f"[!] Failed to start DB to JSON updater: {e}")
        return False

def signal_handler(signum, frame):
    """Handle interrupt signals to gracefully shut down the server"""
    print("\n[*] Received shutdown signal. Cleaning up...")
    
    # close all active sessions
    try:
        from core.database import get_db_connection
        import datetime
        
        # connect to database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # mark all active sessions as closed
        timestamp = datetime.datetime.now().isoformat()
        cursor.execute('''
        UPDATE sessions 
        SET end_time = ? 
        WHERE end_time IS NULL
        ''', (timestamp,))
        
        # report how many sessions were closed
        closed_count = cursor.rowcount
        if closed_count > 0:
            print(f"[*] Closed {closed_count} active sessions")
        
        # commit any of our database changes
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[!] Error closing sessions: {e}")
    
    # set stop event to terminate server
    stop_event.set()
    sys.exit(0)

def start_frontend_server(frontend_dir, port):
    """Start a simple HTTP server to serve the frontend files"""
    import http.server
    import socketserver
    import threading
    
    class MyHTTPRequestHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=frontend_dir, **kwargs)
    
    def run_server():
        try:
            with socketserver.TCPServer(("", port), MyHTTPRequestHandler) as httpd:
                print(f"[*] Frontend server started at port {port}")
                httpd.serve_forever()
        except Exception as e:
            print(f"[!] Error starting frontend server: {e}")
    
    # Start the server in a separate thread
    server_thread = threading.Thread(target=run_server)
    server_thread.daemon = True
    server_thread.start()
    
    return server_thread

def main():
    # register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # initialize the database
    print("[*] Initializing database...")
    init_db()
    
    # start the database to JSON updater
    start_db_exporter()
    
    # generate or load host key
    print("[*] Setting up SSH host key...")
    host_key = generate_host_key()
    
    # initialize virtual filesystem
    print("[*] Initializing virtual filesystem...")
    filesystem = VirtualFilesystem(FILESYSTEM_DIR)
    
    # initialize command processor
    command_processor = CommandProcessor(filesystem)

    # initialize AI integration if enabled
    if AI_ENABLED:
        print(f"[*] Initializing AI capabilities in {AI_MODE} mode...")
        print("[*] Checking Ollama availability...")
        command_processor = integrate_ai_with_command_processor(command_processor)
    else:
        print("[*] AI capabilities disabled")
    
    # get local IP for connection info
    local_ip = get_local_ip()
    print(format_connection_info(USERNAME, local_ip, PORT, PASSWORD))
    
    # start the server
    server_thread = threading.Thread(
        target=start_server,
        args=(HOST, PORT, command_processor, host_key)
    )
    server_thread.daemon = True
    server_thread.start()
    
    # keep the main thread running
    try:
        while server_thread.is_alive():
            server_thread.join(1)
    except KeyboardInterrupt:
        signal_handler(None, None)

if __name__ == "__main__":
    main()