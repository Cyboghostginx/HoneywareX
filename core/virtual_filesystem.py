"""
Virtual filesystem implementation for the SSH honeypot with session isolation
"""
import os
import json
import shutil
import copy
from utils.log_setup import logger
from utils.filesystem_data import file_system, sample_files
from config import FILESYSTEM_DIR

class VirtualFilesystem:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.master_fs_data = file_system  # keep an untouched master copy
        self.fs_data = copy.deepcopy(file_system)  # working copy for default state
        self.session_filesystems = {}  # dictionary to store per-session filesystem data
        self.session_base_dirs = {}  # dictionary to store per-session base directories
        
        # initialize the master filesystem once
        self.initialize_filesystem()
        
    def initialize_filesystem(self):
        """Create the base filesystem structure from the fs_data dictionary"""
        if not os.path.exists(self.base_dir):
            os.makedirs(self.base_dir)
        
        # clear existing filesystem for a fresh start if needed
        if os.path.exists(self.base_dir) and os.listdir(self.base_dir):
            logger.info(f"Clearing existing filesystem at {self.base_dir}")
            for item in os.listdir(self.base_dir):
                item_path = os.path.join(self.base_dir, item)
                try:
                    if os.path.isdir(item_path):
                        shutil.rmtree(item_path)
                    else:
                        os.remove(item_path)
                except Exception as e:
                    logger.error(f"Error removing {item_path}: {e}")
        
        # ensure all structures from fs_data are created in the filesystem
        self._create_fs_structure("", self.fs_data)
        
        # create any additional sample files
        for path, content in sample_files.items():
            self.create_sample_file(path.lstrip('/'), content)
        
        # verify that all files and directories exist in the real filesystem
        self._verify_filesystem_integrity()
        
        logger.info(f"Initialized master virtual filesystem at {self.base_dir}")
    
    def initialize_session(self, session_id):
        """Initialize a new filesystem for a specific session"""
        # create session-specific directory
        session_dir = os.path.join(self.base_dir, f"session_{session_id}")
        self.session_base_dirs[session_id] = session_dir
        
        # create a copy of the filesystem data for this session
        self.session_filesystems[session_id] = copy.deepcopy(self.master_fs_data)
        
        # create the filesystem for this session
        if not os.path.exists(session_dir):
            os.makedirs(session_dir)
            
            # clone the master filesystem to this session directory
            self._copy_directory(self.base_dir, session_dir, exclude=["session_"])
            
            logger.info(f"Initialized session filesystem for session {session_id} at {session_dir}")
        
        return session_dir
    
    def _copy_directory(self, src, dst, exclude=None):
        """Copy a directory recursively, excluding certain patterns"""
        exclude = exclude or []
        
        for item in os.listdir(src):
            if any(pattern in item for pattern in exclude):
                continue
                
            s = os.path.join(src, item)
            d = os.path.join(dst, item)
            if os.path.isdir(s):
                os.makedirs(d, exist_ok=True)
                self._copy_directory(s, d, exclude)
            else:
                try:
                    shutil.copy2(s, d)
                except Exception as e:
                    logger.error(f"Error copying {s} to {d}: {e}")
    
    def cleanup_session(self, session_id):
        """Clean up a session's filesystem"""
        if session_id in self.session_base_dirs:
            session_dir = self.session_base_dirs[session_id]
            if os.path.exists(session_dir):
                try:
                    shutil.rmtree(session_dir)
                    logger.info(f"Cleaned up session filesystem for session {session_id}")
                except Exception as e:
                    logger.error(f"Error cleaning up session directory {session_dir}: {e}")
            
            # remove session data
            del self.session_base_dirs[session_id]
            
        if session_id in self.session_filesystems:
            del self.session_filesystems[session_id]
    
    def _create_fs_structure(self, current_path, directory_dict):
        """Recursively create the filesystem structure from the dictionary"""
        for name, content in directory_dict.items():
            path = os.path.join(current_path, name)
            real_path = os.path.join(self.base_dir, path)
            
            if isinstance(content, dict):
                # this is a directory
                os.makedirs(real_path, exist_ok=True)
                self._create_fs_structure(path, content)
            else:
                # this is a file
                dir_path = os.path.dirname(real_path)
                os.makedirs(dir_path, exist_ok=True)
                with open(real_path, 'w') as f:
                    f.write(content)
    
    def create_sample_file(self, relative_path, content, session_id=None):
        # determine the base directory based on session
        base_dir = self.session_base_dirs.get(session_id, self.base_dir)
        
        file_path = os.path.join(base_dir, relative_path)
        dir_path = os.path.dirname(file_path)
        os.makedirs(dir_path, exist_ok=True)
        with open(file_path, 'w') as f:
            f.write(content)
    
    def get_real_path(self, virtual_path, session_id=None):
        # determine the base directory based on session
        base_dir = self.session_base_dirs.get(session_id, self.base_dir)
        
        if virtual_path.startswith('/'):
            virtual_path = virtual_path[1:]  # remove leading slash
        return os.path.join(base_dir, virtual_path)
    
    def list_directory(self, virtual_path, session_id=None):
        # get the session-specific filesystem data
        fs_data = self.session_filesystems.get(session_id, self.fs_data)
        
        # get the real path using the session-specific base directory
        real_path = self.get_real_path(virtual_path, session_id)
        
        if not os.path.exists(real_path):
            # special case for root directory
            if virtual_path == "/" or virtual_path == "":
                files = list(fs_data.keys())
                result = []
                for f in sorted(files):
                    result.append(f"\033[1;34m{f}/\033[0m" if isinstance(fs_data[f], dict) else f)
                return "  ".join(result)
                
            # for other paths, try to find them in fs_data
            if virtual_path.startswith('/'):
                path_parts = virtual_path.strip('/').split('/')
            else:
                path_parts = virtual_path.split('/')
                
            # try to find the directory in fs_data
            current = fs_data
            for part in path_parts:
                if part and part in current:
                    current = current[part]
                else:
                    return f"ls: cannot access '{virtual_path}': No such file or directory"
                    
            # if we found a directory, list its contents
            if isinstance(current, dict):
                files = list(current.keys())
                
                # create the directory in the real filesystem if it doesn't exist
                os.makedirs(real_path, exist_ok=True)
                
                # create any files that exist in fs_data but not in real filesystem
                for f in files:
                    file_path = os.path.join(real_path, f)
                    if not os.path.exists(file_path):
                        if isinstance(current[f], dict):
                            # this is a directory
                            os.makedirs(file_path, exist_ok=True)
                        else:
                            # this is a file
                            with open(file_path, 'w') as file:
                                file.write(current[f])
                
                # now list the directory from the real filesystem
                result = []
                for f in sorted(files):
                    if isinstance(current[f], dict):
                        result.append(f"\033[1;34m{f}/\033[0m")  # blue for directories
                    else:
                        result.append(f)
                
                return "  ".join(result)
            else:
                return f"ls: cannot access '{virtual_path}': Not a directory"
        
        if not os.path.isdir(real_path):
            return f"ls: cannot access '{virtual_path}': Not a directory"
        
        try:
            files = os.listdir(real_path)
            if not files:
                return ""  # empty directory
            
            # format output similar to ls command
            result = []
            for f in sorted(files):
                full_path = os.path.join(real_path, f)
                if os.path.isdir(full_path):
                    result.append(f"\033[1;34m{f}/\033[0m")  # blue for directories
                elif os.access(full_path, os.X_OK):
                    result.append(f"\033[1;32m{f}*\033[0m")  # green for executables
                else:
                    result.append(f)
            
            return "  ".join(result)
        except Exception as e:
            logger.error(f"Error listing directory {virtual_path}: {e}")
            return f"ls: cannot access '{virtual_path}': {str(e)}"
    
    def read_file(self, virtual_path, session_id=None):
        # get the session-specific filesystem data
        fs_data = self.session_filesystems.get(session_id, self.fs_data)
        
        # get the real path using the session-specific base directory
        real_path = self.get_real_path(virtual_path, session_id)
        
        if not os.path.exists(real_path):
            # if the file doesn't exist in the real filesystem, check if it exists in fs_data
            if virtual_path.startswith('/'):
                path_parts = virtual_path.strip('/').split('/')
            else:
                path_parts = virtual_path.split('/')
                
            # try to find the file in fs_data
            current = fs_data
            for part in path_parts[:-1]:  # navigate directories
                if part and part in current:
                    current = current[part]
                else:
                    return f"cat: {virtual_path}: No such file or directory"
                    
            # check if file exists
            filename = path_parts[-1]
            if filename in current and not isinstance(current[filename], dict):
                # file exists in fs_data but not in real filesystem
                # write it to the real filesystem and then read it
                content = current[filename]
                self.write_file(virtual_path, content, session_id)
                return content
            else:
                return f"cat: {virtual_path}: No such file or directory"
        
        if os.path.isdir(real_path):
            return f"cat: {virtual_path}: Is a directory"
        
        try:
            with open(real_path, 'r') as f:
                content = f.read()
                # replace literal '\n' with actual newlines if they exist
                if '\\n' in content:
                    content = content.replace('\\n', '\n')
                return content
        except Exception as e:
            logger.error(f"Error reading file {virtual_path}: {e}")
            return f"cat: {virtual_path}: {str(e)}"
    
    def write_file(self, virtual_path, content, session_id=None):
        # get the real path using the session-specific base directory
        real_path = self.get_real_path(virtual_path, session_id)
        
        try:
            os.makedirs(os.path.dirname(real_path), exist_ok=True)
            with open(real_path, 'w') as f:
                f.write(content)
            
            # update the session filesystem data
            if session_id in self.session_filesystems:
                # update the filesystem data structure
                if virtual_path.startswith('/'):
                    path_parts = virtual_path.strip('/').split('/')
                else:
                    path_parts = virtual_path.split('/')
                
                current = self.session_filesystems[session_id]
                # navigate to the parent directory
                for part in path_parts[:-1]:
                    if part:
                        if part not in current:
                            current[part] = {}
                        current = current[part]
                
                # set the file content
                if path_parts[-1]:
                    current[path_parts[-1]] = content
            
            return True
        except Exception as e:
            logger.error(f"Error writing to file {virtual_path}: {e}")
            return False
    
    def create_directory(self, virtual_path, session_id=None):
        # get the real path using the session-specific base directory
        real_path = self.get_real_path(virtual_path, session_id)
        
        if os.path.exists(real_path):
            return f"mkdir: cannot create directory '{virtual_path}': File exists"
        
        try:
            os.makedirs(real_path)
            
            # update the session filesystem data
            if session_id in self.session_filesystems:
                # update the filesystem data structure
                if virtual_path.startswith('/'):
                    path_parts = virtual_path.strip('/').split('/')
                else:
                    path_parts = virtual_path.split('/')
                
                current = self.session_filesystems[session_id]
                # navigate and create directories as needed
                for part in path_parts:
                    if part:
                        if part not in current:
                            current[part] = {}
                        current = current[part]
            
            return ""  # success, no output
        except Exception as e:
            logger.error(f"Error creating directory {virtual_path}: {e}")
            return f"mkdir: cannot create directory '{virtual_path}': {str(e)}"
    
    def remove_file(self, virtual_path, session_id=None, recursive=False):
        """Remove a file or directory, with support for recursive directory removal"""
        # get the real path using the session-specific base directory
        real_path = self.get_real_path(virtual_path, session_id)
        
        if not os.path.exists(real_path):
            return f"cannot remove '{virtual_path}': No such file or directory"
        
        try:
            if os.path.isdir(real_path):
                # check if directory is empty
                if len(os.listdir(real_path)) > 0:
                    if not recursive:
                        return f"cannot remove '{virtual_path}': Is a directory"
                    else:
                        # recursively remove directory and all contents
                        shutil.rmtree(real_path)
                else:
                    # empty directory
                    os.rmdir(real_path)
            else:
                # regular file
                os.remove(real_path)
            
            # update the session filesystem data structure
            if session_id in self.session_filesystems:
                # update the filesystem data structure
                if virtual_path.startswith('/'):
                    path_parts = virtual_path.strip('/').split('/')
                else:
                    path_parts = virtual_path.split('/')
                
                if not path_parts:
                    return ""
                
                # navigate to the parent directory in our data structure
                current = self.session_filesystems[session_id]
                parent = current
                for i, part in enumerate(path_parts[:-1]):
                    if part and part in parent:
                        parent = parent[part]
                    else:
                        # path doesn't exist in our data structure
                        return ""
                
                # remove the file or directory from the data structure
                if path_parts[-1] in parent:
                    del parent[path_parts[-1]]
            
            return ""  # success, no output
        except PermissionError:
            return f"cannot remove '{virtual_path}': Permission denied"
        except IsADirectoryError:
            return f"cannot remove '{virtual_path}': Is a directory"
        except Exception as e:
            logger.error(f"Error removing {virtual_path}: {e}")
            return f"cannot remove '{virtual_path}': {str(e)}"
    
    def file_exists(self, virtual_path, session_id=None):
        # get the real path using the session-specific base directory
        real_path = self.get_real_path(virtual_path, session_id)
        return os.path.exists(real_path)
    
    def is_directory(self, virtual_path, session_id=None):
        # get the real path using the session-specific base directory
        real_path = self.get_real_path(virtual_path, session_id)
        return os.path.isdir(real_path)
    
    def _verify_filesystem_integrity(self):
        self._verify_directory_integrity("", self.fs_data)
    
    def _verify_directory_integrity(self, current_path, directory_dict):
        for name, content in directory_dict.items():
            path = os.path.join(current_path, name)
            real_path = os.path.join(self.base_dir, path)
            
            if isinstance(content, dict):
                # this is a directory
                if not os.path.exists(real_path):
                    os.makedirs(real_path, exist_ok=True)
                    logger.info(f"Created missing directory: {path}")
                self._verify_directory_integrity(path, content)
            else:
                # this is a file
                if not os.path.exists(real_path):
                    dir_path = os.path.dirname(real_path)
                    os.makedirs(dir_path, exist_ok=True)
                    with open(real_path, 'w') as f:
                        f.write(content)
                    logger.info(f"Created missing file: {path}")