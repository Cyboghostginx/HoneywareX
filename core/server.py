"""
SSH server implementation for the honeypot with fixed tab completion and arrow keys
"""
import socket, threading, paramiko, os, time
from utils.log_setup import logger
from core.database import log_session_start, log_session_end, log_command, log_auth_attempt, get_db_connection
from config import USERNAME, PASSWORD, RAG_STREAM_OUTPUT, RAG_TOKEN_DELAY

# stop event for graceful shutdown
stop_event = threading.Event()

class HoneypotServer(paramiko.ServerInterface):
    def __init__(self, client_ip):
        self.client_ip = client_ip
        self.username = None
        self.event = threading.Event()
        # create a session when the connection is established
        self.session_id = log_session_start(self.client_ip, "unknown", False)
        logger.info(f"Created new session {self.session_id} for client {self.client_ip}")

    def check_auth_password(self, username, password):
        # for the honeypot, we'll accept the configured credentials
        success = (username == USERNAME and password == PASSWORD)
        
        # double-check that session_id exists
        if self.session_id is None:
            logger.error("Session ID is None during auth attempt, creating new session")
            self.session_id = log_session_start(self.client_ip, "unknown", False)
        
        # log authentication attempt with explicit session ID
        logger.info(f"Logging auth attempt for session {self.session_id}: {username}:{password}")
        log_auth_attempt(self.client_ip, username, password, success, self.session_id)
        
        if success:
            self.username = username
            logger.info(f"Successful authentication from {self.client_ip}: username={username}, password={password}")
            
            # update the session with the correct username and set success to true
            try:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute('''
                UPDATE sessions 
                SET username = ?, success = ? 
                WHERE id = ?
                ''', (username, True, self.session_id))
                conn.commit()
                conn.close()
                logger.info(f"Updated session {self.session_id} with username {username} and success=True")
            except Exception as e:
                logger.error(f"Error updating session: {e}")
            
            return paramiko.AUTH_SUCCESSFUL
        
        # log failed attempt
        logger.info(f"Failed authentication attempt from {self.client_ip}: username={username}, password={password}")
        return paramiko.AUTH_FAILED

    def check_channel_request(self, kind, chanid):
        if kind == "session":
            return paramiko.OPEN_SUCCEEDED
        return paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_shell_request(self, channel):
        self.event.set()
        return True

    def check_channel_pty_request(self, channel, term, width, height, pixelwidth, pixelheight, modes):
        return True

    def get_allowed_auths(self, username):
        return "password"


def handle_connection(client, addr, command_processor, host_key):
    transport = None
    channel = None
    session_closed = False
    
    try:
        transport = paramiko.Transport(client)
        transport.add_server_key(host_key)
        server = HoneypotServer(addr[0])
        transport.start_server(server=server)

        channel = transport.accept(20)
        if channel is None:
            logger.info(f"No channel from {addr[0]}")
            return
            
        logger.info(f"Channel accepted from {addr[0]}")

        # initialize session in command processor
        command_processor.initialize_session(server.session_id)
        logger.info(f"Initialized session {server.session_id} for client {addr[0]}")

        # send welcome message
        channel.send("Welcome to Ubuntu 20.04.4 LTS (GNU/Linux 5.4.0-107-generic x86_64)\r\n")
        channel.send("==\r\n")
        channel.send("Adetayo Adebimpe (ama59@hi.is)\r\n")
        channel.send("==\r\n")
        channel.send("This project looks into how we can leverage RAG to enhance context awareness where dynamic ability is required in linux SSH honeypot.\r\n")
        channel.send("==\r\n\n")
        
        # send initial prompt
        prompt = command_processor.get_prompt(server.session_id)
        channel.send(prompt)

        buffer = ""          # current command buffer
        cursor_pos = 0       # cursor position in the buffer
        command_history = []
        history_index = -1
        tab_buffer = ""      # store the original buffer when tab is pressed
        
        # variable to track if we're in the middle of an escape sequence
        in_escape_sequence = False
        escape_buffer = ""
        
        # track ping state
        in_continuous_ping = False
        ping_interval = 1.0  # default ping interval
        last_ping_time = 0   # track last ping time
        
        # flag to track if we're currently streaming RAG output
        in_streaming_rag = False
        streaming_start_time = 0
        streaming_last_output = 0  # track last time we sent streaming output
        streaming_heartbeat = 0.5  # send a subtle indicator every 0.5 seconds of silence
        streaming_inactivity_timeout = 2.0  # consider streaming done after 2 seconds of inactivity
        streaming_timeout = 45.0  # maximum time to wait for streaming output (seconds)
        streaming_thread = None  # will hold the thread for streaming processing
        
        # define token callback function for streaming RAG output with real-time cleanup
        def token_callback(token):
            nonlocal channel, in_streaming_rag, streaming_start_time, streaming_last_output
            if channel and not channel.closed:
                # clean markdown from the token in real-time
                token = clean_token(token)
                
                # process line breaks properly for terminal display
                token = token.replace('\n', '\r\n')
                
                # send to client
                channel.send(token)
                
                # update streaming state
                in_streaming_rag = True
                streaming_start_time = time.time()
                streaming_last_output = time.time()  # update last output time

        # helper function to clean markdown from tokens
        def clean_token(token):
            # Strip bold/italic markdown
            token = token.replace('**', '')
            token = token.replace('*', '')
            
            # strip bullet points if token starts with one
            if token.strip().startswith('- ') or token.strip().startswith('• '):
                token = token.replace('- ', '', 1).replace('• ', '', 1)
            
            # strip numbered list markers
            if len(token.strip()) > 0 and token.strip()[0].isdigit() and '. ' in token:
                parts = token.split('. ', 1)
                if parts[0].isdigit():
                    token = parts[1]
            
            # remove code block markers
            token = token.replace('```', '')
            
            return token
        
        while not stop_event.is_set():
            try:
                # set a timeout for data reception (allows ping to continue)
                if in_continuous_ping or in_streaming_rag:
                    channel.settimeout(0.1)
                else:
                    channel.settimeout(None)
                
                try:
                    data = channel.recv(1024).decode('utf-8', errors='ignore')
                    
                    # check for client disconnection
                    if not data and not (in_continuous_ping or in_streaming_rag):
                        logger.info(f"Client {addr[0]} disconnected")
                        # log session end
                        if not session_closed and hasattr(server, 'session_id') and server.session_id is not None:
                            log_session_end(server.session_id)
                            session_closed = True
                            logger.info(f"Logged session end for {server.session_id} due to client disconnect")
                        break
                        
                except socket.timeout:
                    # timeout is expected during continuous ping or streaming RAG
                    data = ""
                except socket.error as e:
                    # socket error could indicate client disconnection
                    logger.info(f"Socket error with {addr[0]}: {e} - Assuming client disconnected")
                    if not session_closed and hasattr(server, 'session_id') and server.session_id is not None:
                        log_session_end(server.session_id)
                        session_closed = True
                        logger.info(f"Logged session end for {server.session_id} due to socket error")
                    break
                
                current_time = time.time()
                if in_continuous_ping and (current_time - last_ping_time >= ping_interval):
                    # get the next ping line
                    ping_line = command_processor.ping_iteration(server.session_id)
                    if ping_line:
                        channel.send(ping_line + "\r\n")
                        last_ping_time = current_time
                    else:
                        # ping has been stopped externally
                        in_continuous_ping = False
                        # send a new prompt
                        prompt = command_processor.get_prompt(server.session_id)
                        channel.send(prompt)
                
                # check if streaming has timed out or completed
                if in_streaming_rag:
                    # check for maximum timeout
                    if current_time - streaming_start_time > streaming_timeout:
                        logger.warning(f"RAG streaming timed out after {streaming_timeout} seconds")
                        in_streaming_rag = False
                        # send a new prompt
                        channel.send("\r\n")
                        prompt = command_processor.get_prompt(server.session_id)
                        channel.send(prompt)
                    
                    # check for inactivity timeout (shorter duration)
                    elif current_time - streaming_last_output > streaming_inactivity_timeout:
                        logger.info("RAG streaming detected as complete due to inactivity")
                        in_streaming_rag = False
                        # send a new prompt
                        channel.send("\r\n")
                        prompt = command_processor.get_prompt(server.session_id)
                        channel.send(prompt)
                    
                    # check for heartbeat during pauses (very subtle cursor movement)
                    elif current_time - streaming_last_output > streaming_heartbeat:
                        # Send a subtle heartbeat during pauses to keep connection active
                        channel.send("\033[s\033[u")  # Save then restore cursor position
                        streaming_last_output = current_time  # Reset heartbeat timer but not main inactivity timer
                
                # process any user input
                i = 0
                while i < len(data):
                    char = data[i]
                    i += 1
                    
                    # handle escape sequences (for arrow keys)
                    if char == "\x1b":  # ESC character
                        in_escape_sequence = True
                        escape_buffer = char
                        continue
                        
                    if in_escape_sequence:
                        escape_buffer += char
                        
                        # check for arrow key sequences
                        if escape_buffer == "\x1b[A":  # Up arrow
                            in_escape_sequence = False
                            escape_buffer = ""
                            
                            if not (in_continuous_ping or in_streaming_rag): # don't process when streaming
                                # handle up arrow (history previous)
                                if command_history:
                                    # move up in history
                                    if history_index < len(command_history) - 1:
                                        history_index += 1
                                    
                                    # clear current line
                                    channel.send("\r" + " " * (len(prompt) + len(buffer)) + "\r")
                                    channel.send(prompt)
                                    
                                    # display the historical command
                                    buffer = command_history[-(history_index+1)]
                                    cursor_pos = len(buffer)  # place cursor at end of command
                                    channel.send(buffer)
                        
                        elif escape_buffer == "\x1b[B":  # down arrow
                            in_escape_sequence = False
                            escape_buffer = ""
                            
                            if not (in_continuous_ping or in_streaming_rag):  # only when not in special modes
                                # handle down arrow (history next)
                                # move down in history
                                if history_index > 0:
                                    history_index -= 1
                                    # clear current line
                                    channel.send("\r" + " " * (len(prompt) + len(buffer)) + "\r")
                                    channel.send(prompt)
                                    
                                    # display the historical command
                                    buffer = command_history[-(history_index+1)]
                                    cursor_pos = len(buffer)  # place cursor at end of command
                                    channel.send(buffer)
                                else:
                                    # if at the bottom of history, clear the line
                                    history_index = -1
                                    channel.send("\r" + " " * (len(prompt) + len(buffer)) + "\r")
                                    channel.send(prompt)
                                    buffer = ""
                                    cursor_pos = 0
                        
                        elif escape_buffer == "\x1b[C":  # right arrow
                            in_escape_sequence = False
                            escape_buffer = ""
                            
                            if not (in_continuous_ping or in_streaming_rag):  # only when not in special modes
                                # move cursor right if not at end of buffer
                                if cursor_pos < len(buffer):
                                    cursor_pos += 1
                                    channel.send("\x1b[C")  # send cursor right command
                        
                        elif escape_buffer == "\x1b[D":  # left arrow
                            in_escape_sequence = False
                            escape_buffer = ""
                            
                            if not (in_continuous_ping or in_streaming_rag):  # only when not in special modes
                                # move cursor left if not at beginning of buffer
                                if cursor_pos > 0:
                                    cursor_pos -= 1
                                    channel.send("\x1b[D")  # send cursor left command
                        
                        # if we've collected enough chars and still don't have a match, cancel the sequence
                        elif len(escape_buffer) >= 3:
                            in_escape_sequence = False
                            escape_buffer = ""
                            
                        continue
                    
                    # handle tab completion
                    if char == "\t" and not (in_continuous_ping or in_streaming_rag):
                        # store original buffer if this is the first tab press
                        if not tab_buffer:
                            tab_buffer = buffer
                        
                        # get current directory
                        current_dir = command_processor.current_dirs.get(server.session_id, "/home/honeypot")
                        
                        # split the command to get the last part for completion
                        cmd_parts = buffer.split()
                        
                        # only attempt completion if we have a partial filename
                        if len(cmd_parts) > 0:
                            # get the part to complete (last part of the command)
                            to_complete = cmd_parts[-1] if cmd_parts else ""
                            
                            # handle relative vs absolute paths
                            dir_path = current_dir
                            base_name = to_complete
                            
                            if to_complete:
                                if to_complete.startswith('/'):
                                    # it's an absolute path
                                    dir_path = os.path.dirname(to_complete) or '/'
                                    base_name = os.path.basename(to_complete)
                                elif '/' in to_complete:
                                    # it's a relative path with subdirectories
                                    rel_dir = os.path.dirname(to_complete)
                                    dir_path = os.path.normpath(os.path.join(current_dir, rel_dir))
                                    base_name = os.path.basename(to_complete)
                            
                            try:
                                # get directory contents from virtual filesystem
                                dir_listing = command_processor.filesystem.list_directory(dir_path, server.session_id)
                                
                                # parse directory listing to get filenames
                                if isinstance(dir_listing, str) and not "cannot access" in dir_listing:
                                    # clean up color codes and split into items
                                    dir_listing = dir_listing.replace("\033[1;34m", "").replace("\033[1;32m", "").replace("\033[0m", "")
                                    dir_items = dir_listing.split("  ")
                                    dir_items = [item.rstrip('*/') for item in dir_items if item]  # Remove trailing /, *, etc.
                                    
                                    # find matches
                                    completions = [item for item in dir_items if item.startswith(base_name)]
                                    
                                    if len(completions) == 1:
                                        # single match - autocomplete
                                        completion = completions[0]
                                        
                                        # check if it's a directory
                                        if dir_path == '/':
                                            full_path = '/' + completion
                                        else:
                                            full_path = os.path.join(dir_path, completion)
                                            
                                        is_dir = command_processor.filesystem.is_directory(full_path, server.session_id)
                                        if is_dir:
                                            completion += "/"
                                        
                                        # replace the partial filename with the complete one
                                        if len(cmd_parts) > 0:
                                            if to_complete.startswith('/'):
                                                # absolute path
                                                cmd_parts[-1] = os.path.join(os.path.dirname(to_complete), completion)
                                            elif '/' in to_complete:
                                                # relative path with directory
                                                rel_dir = os.path.dirname(to_complete)
                                                cmd_parts[-1] = os.path.join(rel_dir, completion)
                                            else:
                                                # simple filename
                                                cmd_parts[-1] = completion
                                        else:
                                            cmd_parts = [completion]
                                        
                                        # display the completed command
                                        channel.send("\r" + " " * (len(prompt) + len(buffer)) + "\r")
                                        channel.send(prompt)
                                        buffer = " ".join(cmd_parts)
                                        cursor_pos = len(buffer)  # place cursor at end
                                        channel.send(buffer)
                                    
                                    elif len(completions) > 1:
                                        # multiple matches - show possibilities
                                        channel.send("\r\n")
                                        for comp in completions:
                                            channel.send(comp + "  ")
                                        channel.send("\r\n")
                                        channel.send(prompt + buffer)
                            except Exception as e:
                                logger.error(f"Error during tab completion: {str(e)}")
                                channel.send("\r\n")
                                channel.send(prompt + buffer)
                    
                    # handle Ctrl+C
                    elif char == "\x03":
                        # cancel streaming RAG if active
                        if in_streaming_rag:
                            in_streaming_rag = False
                            channel.send("^C\r\n")
                            # reset buffer and show new prompt
                            buffer = ""
                            cursor_pos = 0
                            prompt = command_processor.get_prompt(server.session_id)
                            channel.send(prompt)
                        elif in_continuous_ping:
                            # stop the ping and show stats
                            in_continuous_ping = False
                            channel.send("^C\r\n")
                            stats = command_processor.stop_ping(server.session_id)
                            if stats:
                                # properly format each line of the statistics with proper CRLF
                                for line in stats.split('\n'):
                                    channel.send(line + "\r\n")
                            
                            # reset buffer and show new prompt
                            buffer = ""
                            cursor_pos = 0
                            prompt = command_processor.get_prompt(server.session_id)
                            channel.send(prompt)
                        else:
                            # regular Ctrl+C handling
                            buffer = ""
                            cursor_pos = 0
                            tab_buffer = ""
                            channel.send("^C\r\n")  # show ^C and start a new line
                            prompt = command_processor.get_prompt(server.session_id)
                            channel.send(prompt)
                    
                    # handle enter key
                    elif char == "\r" and not (in_continuous_ping or in_streaming_rag):
                        command = buffer.strip()
                        buffer = ""
                        cursor_pos = 0
                        tab_buffer = ""  # reset tab completion buffer
                        history_index = -1  # reset history position
                        
                        # echo newline for proper formatting
                        channel.send("\r\n")
                        
                        if command:
                            # save to history (avoid duplicates at the end)
                            if not command_history or command_history[-1] != command:
                                command_history.append(command)
                                # keep history at a reasonable size
                                if len(command_history) > 100:
                                    command_history.pop(0)
                                    
                            logger.info(f"Command from {addr[0]} (user {server.username}): {command}")
                            log_command(server.session_id, command)
                            
                            # check for exit command
                            if command.lower() in ["exit", "quit", "logout"]:
                                logger.info(f"Client {addr[0]} exited the session")
                                channel.close()
                                break
                                
                            # check for ping command specifically
                            if command.startswith("ping "):
                                response = command_processor.process_command(server.session_id, command)
                                
                                # check if this is a continuous ping
                                lines = response.split('\n')
                                if "PING_CONTINUES" in lines:
                                    # remove the PING_CONTINUES marker
                                    lines = [l for l in lines if l != "PING_CONTINUES"]
                                    
                                    # send the ping header
                                    channel.send("\n".join(lines) + "\r\n")
                                    
                                    # enter continuous ping mode
                                    in_continuous_ping = True
                                    last_ping_time = time.time()  # initialize last ping time
                                    
                                    # extract ping interval if specified
                                    parts = command.split()
                                    for idx, part in enumerate(parts):
                                        if part == "-i" and idx + 1 < len(parts):
                                            try:
                                                ping_interval = float(parts[idx + 1])
                                            except (ValueError, IndexError):
                                                ping_interval = 1.0
                                    
                                    continue  # skip prompt display
                                else:
                                    # normal ping with count, send the full response
                                    lines = response.split('\n')
                                    for line in lines:
                                        channel.send(line + "\r\n")
                            else:
                                # check if this is a RAG command with streaming enabled
                                if hasattr(command_processor, 'smart_rag') and \
                                   not command_processor.smart_rag.is_native_command(command) and \
                                   RAG_STREAM_OUTPUT:
                                    # enter streaming mode
                                    in_streaming_rag = True
                                    streaming_start_time = time.time()
                                    streaming_last_output = time.time()
                                    
                                    # define a function to handle the RAG processing in a separate thread
                                    def process_rag_command():
                                        nonlocal in_streaming_rag
                                        try:
                                            # process command with streaming
                                            command_processor.execute_command(server.session_id, command, token_callback)
                                            
                                            # wait a very short time to ensure any final tokens are processed
                                            time.sleep(0.1)
                                            
                                            # set flag that streaming is done
                                            in_streaming_rag = False
                                            
                                            # send a newline and prompt when complete
                                            if channel and not channel.closed:
                                                channel.send("\r\n")
                                                prompt = command_processor.get_prompt(server.session_id)
                                                channel.send(prompt)
                                                
                                            logger.info(f"RAG streaming completed for command: {command}")
                                        except Exception as e:
                                            logger.error(f"Error in RAG command processing: {e}")
                                            # make sure we clean up on error
                                            in_streaming_rag = False
                                            
                                            if channel and not channel.closed:
                                                channel.send(f"\r\nError: {str(e)}\r\n")
                                                prompt = command_processor.get_prompt(server.session_id)
                                                channel.send(prompt)
                                    
                                    # start the processing in a background thread
                                    streaming_thread = threading.Thread(target=process_rag_command)
                                    streaming_thread.daemon = True
                                    streaming_thread.start()
                                    
                                    # continue with the main loop - the thread will handle prompt display when finished
                                else:
                                    # process regular command without streaming
                                    response = command_processor.process_command(server.session_id, command)
                                    
                                    # handle special responses
                                    if response == "logout":
                                        logger.info(f"Client {addr[0]} exited the session")
                                        channel.close()
                                        break
                                    elif response == "\033[2J\033[H":  # clear screen
                                        channel.send(response)
                                    else:
                                        # regular command output - use proper line formatting
                                        if response:
                                            # process multiline responses properly
                                            lines = response.replace('\r', '').split('\n')
                                            for line in lines:
                                                # send each line with proper CRLF
                                                channel.send(line + "\r\n")
                        
                        # send new prompt if not in streaming or continuous ping
                        if not (in_streaming_rag or in_continuous_ping):
                            prompt = command_processor.get_prompt(server.session_id)
                            channel.send(prompt)
                    
                    # handle newline (ignore it, we handle CR)
                    elif char == "\n":
                        continue
                    
                    # handle backspace
                    elif char in ("\x7f", "\x08") and not (in_continuous_ping or in_streaming_rag):
                        if cursor_pos > 0:  # only if cursor is not at the beginning
                            # if cursor is at the end of the buffer
                            if cursor_pos == len(buffer):
                                buffer = buffer[:-1]
                                cursor_pos -= 1
                                # send backspace sequence: move back, space over the character, move back again
                                channel.send("\b \b")
                            else:
                                # cursor is in the middle of the buffer
                                # remove character at cursor_pos - 1
                                buffer = buffer[:cursor_pos-1] + buffer[cursor_pos:]
                                cursor_pos -= 1
                                
                                # redraw the entire line from the cursor position
                                channel.send("\b \b")  # delete the character under cursor
                                # redraw the rest of the line
                                channel.send(buffer[cursor_pos:] + " ")
                                # move cursor back to the correct position
                                channel.send("\b" * (len(buffer) - cursor_pos + 1))
                    
                    # handle Ctrl+D (EOF)
                    elif char == "\x04" and not (in_continuous_ping or in_streaming_rag):
                        if not buffer:  # only exit if buffer is empty
                            logger.info(f"Client {addr[0]} sent EOF")
                            channel.close()
                            break
                    
                    # handle regular characters when not in special modes
                    elif not (in_continuous_ping or in_streaming_rag) and ord(char) >= 32:
                        # insert character at cursor position
                        if cursor_pos == len(buffer):
                            # cursor at end - simply append
                            buffer += char
                            cursor_pos += 1
                            channel.send(char)  # echo input
                        else:
                            # cursor in the middle - insert and redraw
                            buffer = buffer[:cursor_pos] + char + buffer[cursor_pos:]
                            cursor_pos += 1
                            
                            # send the new character and the rest of the line
                            channel.send(char + buffer[cursor_pos:])
                            
                            # move cursor back to the position after the inserted character
                            channel.send("\b" * (len(buffer) - cursor_pos))
                        
            except Exception as e:
                logger.error(f"Error handling connection data from {addr[0]}: {str(e)}")
                break
                
    except Exception as e:
        logger.error(f"Error handling connection from {addr[0]}: {str(e)}")
    finally:
        # only log session end if not already closed
        if not session_closed and hasattr(server, 'session_id') and server.session_id is not None:
            log_session_end(server.session_id)
            session_closed = True
            logger.info(f"Logged session end for {server.session_id}")
        
        # close channel if still open
        if channel and not channel.closed:
            try:
                channel.close()
                logger.info(f"Closed channel for {addr[0]}")
            except Exception as e:
                logger.error(f"Error closing channel: {e}")
        
        # close transport if active
        if transport and transport.is_active():
            try:
                transport.close()
                logger.info(f"Closed transport for {addr[0]}")
            except Exception as e:
                logger.error(f"Error closing transport: {e}")
        
        # always clean up the session in command processor
        if hasattr(server, 'session_id') and server.session_id is not None:
            # make sure any active pings are stopped
            if hasattr(command_processor, 'ping_active') and server.session_id in command_processor.ping_active:
                command_processor.ping_active[server.session_id]['active'] = False
            
            # clean up the session in command processor
            command_processor.cleanup_session(server.session_id)
            logger.info(f"Cleaned up session {server.session_id} for client {addr[0]}")
        
        logger.info(f"Connection closed for {addr[0]}")

def start_server(host, port, command_processor, host_key):
    """Start the SSH honeypot server"""
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((host, port))
        server_socket.listen(100)
        logger.info(f"SSH server running on {host}:{port}")
        
        while not stop_event.is_set():
            try:
                server_socket.settimeout(1.0)  # 1 second timeout for accepting connections
                client, addr = server_socket.accept()
                logger.info(f"Connection from {addr[0]}:{addr[1]}")
                
                # handle each connection in a separate thread
                thread = threading.Thread(
                    target=handle_connection, 
                    args=(client, addr, command_processor, host_key)
                )
                thread.daemon = True
                thread.start()
            except socket.timeout:
                # just a timeout, continue the loop
                continue
            except Exception as e:
                if not stop_event.is_set():
                    logger.error(f"Error accepting connection: {e}")
    except Exception as e:
        logger.error(f"Error starting server: {e}")
    finally:
        logger.info("Server shutting down...")
        server_socket.close()