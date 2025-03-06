"""
Database operations for the SSH honeypot
"""
import sqlite3
import datetime
from utils.log_setup import logger
from config import DB_FILE

def get_db_connection():
    """Create a new SQLite connection"""
    return sqlite3.connect(DB_FILE)

def init_db():
    """Initialize database tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # first check if tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'")
    sessions_table_exists = cursor.fetchone() is not None
    
    # create tables if they don't exist
    if not sessions_table_exists:
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            username TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            success BOOLEAN NOT NULL
        )
        ''')
        logger.info("Created sessions table")
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        command TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS auth_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id INTEGER NOT NULL,
        ip TEXT NOT NULL,
        username TEXT NOT NULL,
        password TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        success BOOLEAN NOT NULL,
        FOREIGN KEY (session_id) REFERENCES sessions(id)
    )
    ''')
    
    # only try to update sessions if the table exists
    if sessions_table_exists:
        # mark all active sessions as closed when server starts
        timestamp = datetime.datetime.now().isoformat()
        cursor.execute('''
        UPDATE sessions 
        SET end_time = ? 
        WHERE end_time IS NULL
        ''', (timestamp,))
        
        # log how many sessions were closed
        closed_count = cursor.rowcount
        if closed_count > 0:
            logger.info(f"Closed {closed_count} stale sessions during initialization")
    
    # after initializing the database, let's check what tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    logger.info(f"Tables in database: {[t[0] for t in tables]}")
    
    # check sessions table structure
    try:
        cursor.execute("PRAGMA table_info(sessions)")
        columns = cursor.fetchall()
        logger.info(f"Sessions table columns: {[c[1] for c in columns]}")
        
        # check if there are any rows in the sessions table
        cursor.execute("SELECT COUNT(*) FROM sessions")
        count = cursor.fetchone()[0]
        logger.info(f"Sessions table has {count} rows")
    except Exception as e:
        logger.error(f"Error checking sessions table: {e}")
    
    try:
        # repair any auth attempts with missing session_id
        repair_auth_attempts()
    except Exception as e:
        logger.error(f"Error repairing auth attempts: {e}")
    
    conn.commit()
    conn.close()
    logger.info("Database initialized")

def log_auth_attempt(ip, username, password, success, session_id=None):
    """Log an authentication attempt"""
    try:
        # make sure we have a valid session_id
        if session_id is None:
            logger.warning(f"Auth attempt without session_id: {username}:{password} from {ip}")
            return
            
        timestamp = datetime.datetime.now().isoformat()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO auth_attempts (ip, username, password, timestamp, success, session_id)
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (ip, username, password, timestamp, success, session_id))
        conn.commit()
        conn.close()
        logger.info(f"Logged auth attempt: {username}:{password} from {ip} (success={success}, session_id={session_id})")
    except sqlite3.Error as e:
        logger.error(f"Database error in log_auth_attempt: {e}")

def log_session_start(ip, username, success):
    """Log the start of a session and return its ID"""
    try:
        timestamp = datetime.datetime.now().isoformat()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO sessions (ip, username, start_time, success)
        VALUES (?, ?, ?, ?)
        ''', (ip, username, timestamp, success))
        conn.commit()
        session_id = cursor.lastrowid
        return session_id
    except sqlite3.Error as e:
        logger.error(f"Database error in log_session_start: {e}")
        return None
    finally:
        conn.close()

def log_session_end(session_id):
    """Update the session with its end time if it doesn't already have one"""
    try:
        # first, we check if the session already has an end time
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT end_time FROM sessions WHERE id = ?', (session_id,))
        result = cursor.fetchone()
        
        # if there's no result or end_time is already set, we can return
        if not result:
            logger.warning(f"Attempted to end non-existent session: {session_id}")
            conn.close()
            return
            
        if result[0] is not None:
            logger.info(f"Session {session_id} already has end time: {result[0]}")
            conn.close()
            return
        
        # set the end time
        timestamp = datetime.datetime.now().isoformat()
        cursor.execute('''
        UPDATE sessions SET end_time = ? WHERE id = ?
        ''', (timestamp, session_id))
        conn.commit()
        logger.info(f"Updated session {session_id} with end time: {timestamp}")
        conn.close()
    except sqlite3.Error as e:
        logger.error(f"Database error in log_session_end: {e}")

def log_command(session_id, command):
    """Log a command associated with a session"""
    try:
        timestamp = datetime.datetime.now().isoformat()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
        INSERT INTO commands (session_id, command, timestamp)
        VALUES (?, ?, ?)
        ''', (session_id, command, timestamp))
        conn.commit()
        logger.info(f"Logged command for session {session_id}: {command}")
    except sqlite3.Error as e:
        logger.error(f"Database error in log_command: {e}")
    finally:
        conn.close()

def get_recent_sessions(limit=10):
    """Get recent sessions with their commands"""
    try:
        conn = get_db_connection()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT id, ip, username, start_time, end_time, success 
        FROM sessions 
        ORDER BY start_time DESC 
        LIMIT ?
        ''', (limit,))
        
        sessions = []
        for row in cursor.fetchall():
            session = dict(row)
            
            # get commands for this session
            cmd_cursor = conn.cursor()
            cmd_cursor.execute('''
            SELECT command, timestamp 
            FROM commands 
            WHERE session_id = ? 
            ORDER BY timestamp
            ''', (session['id'],))
            
            session['commands'] = [dict(cmd) for cmd in cmd_cursor.fetchall()]
            sessions.append(session)
            
        return sessions
    except sqlite3.Error as e:
        logger.error(f"Database error in get_recent_sessions: {e}")
        return []
    finally:
        conn.close()

def get_command_stats():
    """Get statistics about command usage"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT command, COUNT(*) as count 
        FROM commands 
        GROUP BY command 
        ORDER BY count DESC 
        LIMIT 10
        ''')
        
        return cursor.fetchall()
    except sqlite3.Error as e:
        logger.error(f"Database error in get_command_stats: {e}")
        return []
    finally:
        conn.close()

def repair_auth_attempts():
    """Fix any auth attempts with missing or invalid session_id"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # find auth attempts with NULL session_id
    cursor.execute("SELECT COUNT(*) FROM auth_attempts WHERE session_id IS NULL")
    null_count = cursor.fetchone()[0]
    
    # find auth attempts with invalid session_id
    cursor.execute('''
    SELECT COUNT(*) FROM auth_attempts a
    LEFT JOIN sessions s ON a.session_id = s.id
    WHERE s.id IS NULL AND a.session_id IS NOT NULL
    ''')
    invalid_count = cursor.fetchone()[0]
    
    if null_count > 0 or invalid_count > 0:
        logger.info(f"Found {null_count} auth attempts with NULL session_id and {invalid_count} with invalid session_id")
        
        # try to associate them based on IP and timestamp
        cursor.execute('''
        UPDATE auth_attempts
        SET session_id = (
            SELECT s.id FROM sessions s
            WHERE s.ip = auth_attempts.ip
            AND auth_attempts.timestamp BETWEEN s.start_time AND COALESCE(s.end_time, datetime('now'))
            ORDER BY s.start_time DESC
            LIMIT 1
        )
        WHERE session_id IS NULL OR session_id NOT IN (SELECT id FROM sessions)
        ''')
        
        conn.commit()
        logger.info(f"Repaired {cursor.rowcount} auth attempts with session_id")
        
        # if any still remain without valid session_id, delete them
        cursor.execute('''
        DELETE FROM auth_attempts
        WHERE session_id IS NULL OR session_id NOT IN (SELECT id FROM sessions)
        ''')
        
        conn.commit()
        logger.info(f"Deleted {cursor.rowcount} unrepairable auth attempts")
    
    conn.close()