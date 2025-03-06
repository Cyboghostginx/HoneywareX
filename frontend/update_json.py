"""
To Convert .DB to JSON exporter for frontend use
"""
import sqlite3, subprocess, json, time, os, sys, traceback
from datetime import datetime

# add parent directory to sys.path for imports
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)
sys.path.append(parent_dir)

try:
    from utils.log_setup import logger
    from config import DB_FILE as CONFIG_DB_FILE
except ImportError as e:
    print(f"Import error: {e}")
    # we logging here
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger('update_json')
    CONFIG_DB_FILE = os.path.join(script_dir, 'honeypot.db')

DB_FILE = os.path.join(script_dir, 'honeypot.db')
SESSIONS_JSON = os.path.join(script_dir, 'sessions.json')
COMMANDS_JSON = os.path.join(script_dir, 'commands.json')
CHECK_INTERVAL = 5  # seconds to check and convert file
DEBUG_MODE = True  

print(f"DB_FILE path: {DB_FILE}")
print(f"SESSIONS_JSON path: {SESSIONS_JSON}")
print(f"COMMANDS_JSON path: {COMMANDS_JSON}")

def get_db_connection():
    """Create a new SQLite connection with proper settings"""
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)  # increased timeout
        conn.row_factory = sqlite3.Row
        # enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        if DEBUG_MODE:
            print(f"Database connection error: {e}")
        return None

def export_sessions(last_mod_time):
    # always export regardless of modification time
    
    # log start of export
    log_msg = f"Exporting sessions to {SESSIONS_JSON}"
    logger.info(log_msg)
    if DEBUG_MODE:
        print(log_msg)
    
    try:
        # check if database file exists
        if not os.path.exists(DB_FILE):
            error_msg = f"Database file {DB_FILE} not found"
            logger.error(error_msg)
            if DEBUG_MODE:
                print(error_msg)
            
            # create empty JSON files to avoid frontend errors
            with open(SESSIONS_JSON, 'w') as f:
                json.dump([], f)
            return last_mod_time
            
        # get database connection
        conn = get_db_connection()
        if not conn:
            return last_mod_time
            
        cursor = conn.cursor()
        
        # check if tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
        sessions_table_exists = cursor.fetchone() is not None
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='auth_attempts'")
        auth_table_exists = cursor.fetchone() is not None
        
        log_msg = f"Tables found: sessions={sessions_table_exists}, auth_attempts={auth_table_exists}"
        logger.info(log_msg)
        if DEBUG_MODE:
            print(log_msg)
            
        if not sessions_table_exists:
            error_msg = "Sessions table does not exist in database"
            logger.error(error_msg)
            if DEBUG_MODE:
                print(error_msg)
                
            # create empty JSON files to avoid frontend errors
            with open(SESSIONS_JSON, 'w') as f:
                json.dump([], f)
            return last_mod_time
            
        # get all sessions
        cursor.execute('SELECT * FROM sessions ORDER BY start_time DESC')
        sessions_data = cursor.fetchall()
        
        log_msg = f"Found {len(sessions_data)} sessions in database"
        logger.info(log_msg)
        if DEBUG_MODE:
            print(log_msg)
            
        # convert sessions to dictionaries
        sessions = []
        for row in sessions_data:
            try:
                session_dict = dict(row)
                session_dict['auth_attempts'] = []  # Initialize empty list
                sessions.append(session_dict)
            except Exception as e:
                error_msg = f"Error converting session row to dict: {e}"
                logger.error(error_msg)
                if DEBUG_MODE:
                    print(error_msg)
        
        # if no sessions found, write empty array to avoid frontend errors
        if not sessions:
            warning_msg = "No sessions found in database"
            logger.warning(warning_msg)
            if DEBUG_MODE:
                print(warning_msg)
                
            with open(SESSIONS_JSON, 'w') as f:
                json.dump([], f)
            return last_mod_time
        
        # get auth attempts for each session if the table exists
        if auth_table_exists:
            for session in sessions:
                try:
                    # query ONLY auth attempts for this specific session_id
                    cursor.execute('''
                    SELECT * FROM auth_attempts 
                    WHERE session_id = ?
                    ORDER BY timestamp
                    ''', (session['id'],))
                    
                    # create separate dictionary for each auth attempt
                    auth_attempts = []
                    for row in cursor.fetchall():
                        attempt = dict(row)
                        # explicitly set session_id to avoid any confusion
                        attempt['session_id'] = session['id']
                        auth_attempts.append(attempt)
                    
                    session['auth_attempts'] = auth_attempts
                    
                    log_msg = f"Session {session['id']} has {len(auth_attempts)} auth attempts"
                    logger.info(log_msg)
                    if DEBUG_MODE:
                        print(log_msg)
                except Exception as e:
                    error_msg = f"Error processing auth attempts for session {session['id']}: {e}"
                    logger.error(error_msg)
                    if DEBUG_MODE:
                        print(error_msg)
                        traceback.print_exc()
                    
                    # ensure auth_attempts is always a list, even on error
                    session['auth_attempts'] = []
        
        # write the sessions to the JSON file
        try:
            # first write to a temporary file
            temp_file = f"{SESSIONS_JSON}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(sessions, f, indent=4)
            
            # then rename to the target file (atomic operation)
            os.replace(temp_file, SESSIONS_JSON)
            
            log_msg = f"Successfully wrote {len(sessions)} sessions to {SESSIONS_JSON}"
            logger.info(log_msg)
            if DEBUG_MODE:
                print(log_msg)
        except Exception as e:
            error_msg = f"Error writing sessions to JSON: {e}"
            logger.error(error_msg)
            if DEBUG_MODE:
                print(error_msg)
                traceback.print_exc()
                
            # try to write a minimal valid JSON as fallback
            try:
                with open(SESSIONS_JSON, 'w') as f:
                    json.dump([], f)
                logger.info("Wrote fallback empty array to sessions.json")
            except Exception as write_error:
                logger.error(f"Error writing fallback JSON: {write_error}")
        
        conn.close()
        
        # return current time as the new last_mod_time
        return time.time()
    except Exception as e:
        error_msg = f"Unexpected error exporting sessions: {e}"
        logger.error(error_msg)
        if DEBUG_MODE:
            print(error_msg)
            traceback.print_exc()
            
        # create a minimal valid JSON to avoid frontend errors
        try:
            with open(SESSIONS_JSON, 'w') as f:
                json.dump([], f)
            logger.info("Wrote empty array after error")
        except Exception as write_error:
            logger.error(f"Error writing empty JSON after exception: {write_error}")
            
        return last_mod_time

def export_commands(last_mod_time):
    # always export regardless of modification time
    
    log_msg = f"Exporting commands to {COMMANDS_JSON}"
    logger.info(log_msg)
    if DEBUG_MODE:
        print(log_msg)
    
    try:
        # we check if database file exists
        if not os.path.exists(DB_FILE):
            error_msg = f"Database file {DB_FILE} not found for commands export"
            logger.error(error_msg)
            if DEBUG_MODE:
                print(error_msg)
                
            # Create empty JSON file
            with open(COMMANDS_JSON, 'w') as f:
                json.dump([], f)
            return last_mod_time
        
        # get database connection
        conn = get_db_connection()
        if not conn:
            return last_mod_time
            
        cursor = conn.cursor()
        
        # check if commands table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='commands'")
        commands_table_exists = cursor.fetchone() is not None
        
        if not commands_table_exists:
            error_msg = "Commands table does not exist in database"
            logger.error(error_msg)
            if DEBUG_MODE:
                print(error_msg)
                
            # create empty JSON file
            with open(COMMANDS_JSON, 'w') as f:
                json.dump([], f)
            return last_mod_time
        
        # get all commands
        cursor.execute('SELECT * FROM commands ORDER BY timestamp DESC')
        commands_data = cursor.fetchall()
        
        log_msg = f"Found {len(commands_data)} commands in database"
        logger.info(log_msg)
        if DEBUG_MODE:
            print(log_msg)
        
        # convert to list of dictionaries
        commands = []
        for row in commands_data:
            try:
                command_dict = dict(row)
                commands.append(command_dict)
            except Exception as e:
                error_msg = f"Error converting command row to dict: {e}"
                logger.error(error_msg)
                if DEBUG_MODE:
                    print(error_msg)
        
        # write to JSON file
        try:
            # first write to a temporary file
            temp_file = f"{COMMANDS_JSON}.tmp"
            with open(temp_file, 'w') as f:
                json.dump(commands, f, indent=4)
            
            # then rename to the target file (atomic operation)
            os.replace(temp_file, COMMANDS_JSON)
            
            log_msg = f"Successfully wrote {len(commands)} commands to {COMMANDS_JSON}"
            logger.info(log_msg)
            if DEBUG_MODE:
                print(log_msg)
        except Exception as e:
            error_msg = f"Error writing commands to JSON: {e}"
            logger.error(error_msg)
            if DEBUG_MODE:
                print(error_msg)
                traceback.print_exc()
                
            # try to write a minimal valid JSON as fallback
            try:
                with open(COMMANDS_JSON, 'w') as f:
                    json.dump([], f)
                logger.info("Wrote fallback empty array to commands.json")
            except:
                pass
        
        conn.close()
        
        # return current time as the new last_mod_time
        return time.time()
    except Exception as e:
        error_msg = f"Unexpected error exporting commands: {e}"
        logger.error(error_msg)
        if DEBUG_MODE:
            print(error_msg)
            traceback.print_exc()
            
        # create a minimal valid JSON
        try:
            with open(COMMANDS_JSON, 'w') as f:
                json.dump([], f)
        except:
            pass
            
        return last_mod_time

def run_forever():
    """Run the export process continuously"""
    last_sessions_mod = 0
    last_commands_mod = 0
    
    start_msg = f"Starting JSON update monitor (interval: {CHECK_INTERVAL}s, debug mode: {DEBUG_MODE})"
    print(start_msg)
    logger.info(start_msg)
    
    # force initial export regardless of modification time
    export_sessions(0)
    export_commands(0)
    
    try:
        while True:
            try:
                # update session data
                last_sessions_mod = export_sessions(last_sessions_mod)
                
                # update commands data
                last_commands_mod = export_commands(last_commands_mod)
                
                # sleep for the check interval
                time.sleep(CHECK_INTERVAL)
            except KeyboardInterrupt:
                logger.info("JSON update monitor stopped by user")
                break
            except Exception as e:
                error_msg = f"Error in update cycle: {e}"
                logger.error(error_msg)
                if DEBUG_MODE:
                    print(error_msg)
                    traceback.print_exc()
                    
                # still sleep to avoid tight loop on error
                time.sleep(CHECK_INTERVAL)
    except KeyboardInterrupt:
        logger.info("JSON update monitor stopped by user")
    
    logger.info("JSON update monitor stopped")
    print("JSON update monitor stopped")

def check_permissions():
    """Check permissions for JSON files and database"""
    try:
        # check for database read access
        db_readable = os.access(DB_FILE, os.R_OK) if os.path.exists(DB_FILE) else False
        
        # check for JSON write access
        json_dir = os.path.dirname(SESSIONS_JSON) or '.'
        dir_writable = os.access(json_dir, os.W_OK)
        
        # test actual file write
        test_file = os.path.join(json_dir, '.test_write')
        file_writable = False
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            file_writable = True
        except:
            file_writable = False
            
        return {
            'db_exists': os.path.exists(DB_FILE),
            'db_readable': db_readable,
            'dir_writable': dir_writable,
            'file_writable': file_writable
        }
    except Exception as e:
        logger.error(f"Error checking permissions: {e}")
        return {'error': str(e)}

if __name__ == '__main__':
    # parse command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--debug':
            DEBUG_MODE = True
            print("Running in debug mode (foreground)...")
            
            # check permissions before starting
            perm_check = check_permissions()
            print(f"Permission check: {perm_check}")
            
            run_forever()
        elif sys.argv[1] == '--background':
            run_forever()
        elif sys.argv[1] == '--check':
            # just check permissions and exit
            perm_check = check_permissions()
            print(f"Permission check: {perm_check}")
            sys.exit(0)
        elif sys.argv[1] == '--once':
            # run once and exit
            DEBUG_MODE = True
            print("Running export once...")
            export_sessions(0)
            export_commands(0)
            print("Export completed")
            sys.exit(0)
        else:
            print(f"Unknown argument: {sys.argv[1]}")
            print("Usage: python update_json.py [--debug|--background|--check|--once]")
            sys.exit(1)
    else:
        # start as a background process
        print("Starting JSON update monitor in background...")
        if os.name == 'posix':  # Unix/Linux/MacOS
            subprocess.Popen(
                ['python3', __file__, '--background'], 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                start_new_session=True
            )
            print("Started JSON update script in background. Check logs for activity.")
        elif os.name == 'nt':  # Windows
            subprocess.Popen(
                ['pythonw', __file__, '--background'], 
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            print("Started JSON update script in background (Windows).")
        else:
            print("Unsupported operating system. Running in foreground...")
            run_forever()