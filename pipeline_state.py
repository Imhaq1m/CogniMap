"""
Pipeline State Manager — Tracks extraction progress with file-based state.
Thread-safe with FileLock for multi-worker environments.
"""

import json
import time
from pathlib import Path
from filelock import FileLock

OUTPUT_DIR = Path(__file__).parent / "output"
STATUS_FILE = OUTPUT_DIR / "pipeline_status.json"
STATUS_LOCK_PATH = OUTPUT_DIR / "pipeline_status.lock"


class PipelineState:
    """Manages pipeline state with atomic reads/writes and file locking."""
    
    def __init__(self, status_file=None, lock_path=None):
        self.status_file = status_file or STATUS_FILE
        self.lock_path = lock_path or STATUS_LOCK_PATH
        self._lock = FileLock(self.lock_path)
        self._ensure_output_dir()
        self._init_status_file()
    
    def _ensure_output_dir(self):
        """Create output directory if it doesn't exist."""
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _init_status_file(self):
        """Initialize status file if it doesn't exist."""
        if not self.status_file.exists():
            self._write_state({
                "running": False,
                "step": "Idle",
                "log": [],
                "error": None
            })
    
    def _write_state(self, state):
        """Atomically write state to file using tmp + rename."""
        with self._lock:
            tmp_file = self.status_file.with_suffix(".tmp")
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            tmp_file.replace(self.status_file)
    
    def _read_state(self):
        """Read state from file with error handling."""
        try:
            with self._lock:
                with open(self.status_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            return {
                "running": False,
                "step": "Error",
                "log": [],
                "error": "Failed to read status"
            }
    
    def start(self, step="Starting...", log_line=None):
        """Start pipeline — returns False if already running."""
        with self._lock:
            try:
                with open(self.status_file, "r", encoding="utf-8") as f:
                    disk_state = json.load(f)
                
                if disk_state.get("running"):
                    return False
                
                new_state = {
                    "running": True,
                    "step": step,
                    "log": [log_line] if log_line else [],
                    "error": None,
                    "start_time": time.time()
                }
                self._write_state(new_state)
                return True
            except Exception:
                # If file doesn't exist or is corrupted, create fresh
                new_state = {
                    "running": True,
                    "step": step,
                    "log": [log_line] if log_line else [],
                    "error": None,
                    "start_time": time.time()
                }
                self._write_state(new_state)
                return True
    
    def update(self, step: str, log_line: str = None):
        """Update pipeline step."""
        state = self._read_state()
        state["step"] = step
        if log_line:
            state["log"].append(log_line)
            if len(state["log"]) > 150:
                state["log"] = state["log"][-150:]
        self._write_state(state)
    
    def finish(self, error: str = None):
        """Mark pipeline as finished."""
        state = self._read_state()
        state["running"] = False
        if error:
            state["error"] = error
            state["step"] = "Error"
        else:
            state["step"] = "Finished"
        self._write_state(state)
    
    def get_state(self):
        """Get current pipeline state."""
        return self._read_state()
    
    @property
    def is_running(self):
        """Check if pipeline is currently running."""
        state = self._read_state()
        return state.get("running", False)


# Singleton instance
pipeline_state = PipelineState()
