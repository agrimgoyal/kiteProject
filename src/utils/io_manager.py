# src/utils/io_manager.py
import os
import json
import pandas as pd
import threading
import time
import logging
from typing import Dict, Any, Optional

class CSVManager:
    """Efficient CSV file manager with rate limiting"""
    
    def __init__(self, min_save_interval: float = 30.0):
        self.min_save_interval = min_save_interval
        self.last_save_times = {}
        self.lock = threading.RLock()
    
    def save_dataframe(self, df: pd.DataFrame, filepath: str, force: bool = False) -> bool:
        """Save a DataFrame to CSV with rate limiting"""
        with self.lock:
            current_time = time.time()
            
            # Check if we've saved this file recently
            if not force and filepath in self.last_save_times:
                time_since_last_save = current_time - self.last_save_times[filepath]
                
                if time_since_last_save < self.min_save_interval:
                    logging.debug(f"Skipping save for {filepath} - saved {time_since_last_save:.1f}s ago")
                    return False
            
            # Update save time before actual save to prevent concurrent saves
            self.last_save_times[filepath] = current_time
                
        try:
            # Create a temporary filename
            temp_path = f"{filepath}.temp"
            
            # Write to a temporary file
            df.to_csv(temp_path, index=False)
            
            # Atomic rename
            try:
                # On Windows, we need to handle file replacement differently
                if os.name == 'nt':
                    # Remove existing file if it exists
                    if os.path.exists(filepath):
                        os.remove(filepath)
                # Rename the temp file to the actual file
                os.rename(temp_path, filepath)
                logging.debug(f"Successfully saved data to {filepath}")
            except Exception as rename_error:
                logging.error(f"Error during file rename: {rename_error}")
                # Fallback - direct copy if rename fails
                import shutil
                shutil.copy2(temp_path, filepath)
                logging.debug(f"Used fallback method to save {filepath}")
                # Clean up the temp file
                try:
                    os.remove(temp_path)
                except:
                    pass
                    
            return True
                    
        except Exception as e:
            logging.error(f"Error saving CSV file {filepath}: {e}")
            
            # Reset last save time so it can be tried again soon
            with self.lock:
                if filepath in self.last_save_times:
                    self.last_save_times[filepath] = current_time - self.min_save_interval + 5.0
                    
            return False

class StateManager:
    """State persistence manager"""
    
    def __init__(self, filepath: str, save_interval: float = 30.0):
        self.filepath = filepath
        self.save_interval = save_interval
        self.data = {}
        self.last_save = 0
        self.lock = threading.RLock()
        
        # Load existing data
        self.load()
    
    def load(self) -> None:
        """Load state from file"""
        try:
            if os.path.exists(self.filepath):
                with open(self.filepath, 'r') as f:
                    self.data = json.load(f)
                logging.debug(f"Loaded state from {self.filepath}")
        except Exception as e:
            logging.error(f"Error loading state from {self.filepath}: {e}")
            self.data = {}
    
    def save(self, force: bool = False) -> bool:
        """Save state to file with rate limiting"""
        with self.lock:
            current_time = time.time()
            
            if not force and (current_time - self.last_save) < self.save_interval:
                return False
                
            # Mark as saved before actual save
            self.last_save = current_time
                
        try:
            # Create a temporary file
            temp_path = f"{self.filepath}.temp"
            
            # Write to temporary file
            with open(temp_path, 'w') as f:
                json.dump(self.data, f, indent=2)
                
            # Atomic rename
            try:
                if os.name == 'nt' and os.path.exists(self.filepath):
                    os.remove(self.filepath)
                os.rename(temp_path, self.filepath)
                logging.debug(f"Saved state to {self.filepath}")
            except Exception as rename_error:
                logging.error(f"Error during state file rename: {rename_error}")
                # Fallback
                import shutil
                shutil.copy2(temp_path, self.filepath)
                try:
                    os.remove(temp_path)
                except:
                    pass
                    
            return True
                
        except Exception as e:
            logging.error(f"Error saving state to {self.filepath}: {e}")
            return False
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get value from state"""
        return self.data.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        """Set value in state"""
        with self.lock:
            self.data[key] = value
    
    def delete(self, key: str) -> None:
        """Delete key from state"""
        with self.lock:
            if key in self.data:
                del self.data[key]