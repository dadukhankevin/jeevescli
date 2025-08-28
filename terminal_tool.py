import os
import select
import subprocess
import sys
import threading
import time
from typing import Dict, List
from dataclasses import dataclass
from .base_cli import Tool
from pydantic import PrivateAttr


@dataclass
class TerminalProcess:
    """Represents a running terminal process"""
    id: str
    command: str
    process: subprocess.Popen
    output_lines: List[str]
    start_time: float
    is_running: bool = True


class TerminalTool(Tool):
    model_config = {"arbitrary_types_allowed": True}
    dependencies: List[Tool] = []
    stop_token: str = "</terminal>"
    _terminals: Dict[str, TerminalProcess] = PrivateAttr(default_factory=dict)
    _next_id: int = PrivateAttr(default=1)
    
    def __init__(self, **kwargs):
        super().__init__(stop_token="</terminal>", **kwargs)
    
    @property
    def system_description(self) -> str:
        return """
        <terminal>
            <command>shell command to run</command>
        </terminal>
        
        <terminal>
            <read_terminal>terminal_id</read_terminal>
        </terminal>
        
        <terminal>
            <kill_terminal>terminal_id</kill_terminal>
        </terminal>
        
        Run shell commands in separate processes. Commands run asynchronously and you can check their output or kill them later.
        
        IMPORTANT: 
        - Commands execute in subprocess with shell=True
        - Complex quoting often fails - use simple commands
        - For multi-line files, use edit_file tool instead of printf/echo
        - Check terminal output with read_terminal to see if commands worked
        - Commands that fail silently are useless - always verify results
        """
    
    @property
    def status_prompt(self) -> str:
        if not self._terminals:
            return "No active terminals."
        
        status = f"Recent Terminals:\n"
        for term_id, term in list(self._terminals.items())[-3:]:  # Show last 3
            runtime = time.time() - term.start_time
            state = "running" if term.is_running else "finished"
            
            # Show last few lines of output as preview
            preview = ""
            if term.output_lines:
                last_lines = term.output_lines[-2:]
                preview = " | " + " ".join(line[:50] for line in last_lines)
            
            status += f"  {term_id}: '{term.command[:40]}...' ({state}, {runtime:.1f}s){preview}\n"
        
        status += "\nUse <terminal><read_terminal>id</read_terminal></terminal> to read full output"
        
        return status
    
    def execute(self, data: dict) -> str:
        # Check what action to perform
        if 'command' in data:
            return self._run_command(data['command'])
        elif 'read_terminal' in data:
            return self._read_terminal(data['read_terminal'])
        elif 'kill_terminal' in data:
            return self._kill_terminal(data['kill_terminal'])
        else:
            raise ValueError("No valid terminal action specified")
    
    def _run_command(self, command: str) -> str:
        """Start a new terminal process"""
        term_id = str(self._next_id)
        self._next_id += 1
        
        # Start process with pipes for output capture
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            cwd=os.getcwd()
        )
        
        # Create terminal process object
        terminal = TerminalProcess(
            id=term_id,
            command=command,
            process=process,
            output_lines=[],
            start_time=time.time()
        )
        
        self._terminals[term_id] = terminal
        
        # Start background thread to capture output
        threading.Thread(
            target=self._capture_output,
            args=(terminal,),
            daemon=True
        ).start()
        
        return f"Started terminal {term_id}: '{command}'"
    
    def _capture_output(self, terminal: TerminalProcess):
        """Background thread to capture process output"""
        stdout = terminal.process.stdout
        stderr = terminal.process.stderr
        
        while terminal.process.poll() is None:
            ready, _, _ = select.select([stdout, stderr], [], [], 0.1)
            for stream in ready:
                line = stream.readline()
                if line:
                    prefix = "ERROR: " if stream == stderr else ""
                    terminal.output_lines.append(f"{prefix}{line.rstrip()}")
        
        # Capture remaining output
        for line in stdout:
            terminal.output_lines.append(line.rstrip())
        for line in stderr:
            terminal.output_lines.append(f"ERROR: {line.rstrip()}")
        
        exit_code = terminal.process.wait()
        if exit_code != 0:
            terminal.output_lines.append(f"Process exited with code {exit_code}")
        
        terminal.is_running = False
    
    def _read_terminal(self, term_id: str) -> str:
        """Read output from a terminal"""
        if term_id not in self._terminals:
            raise KeyError(f"Terminal {term_id} not found")
        
        terminal = self._terminals[term_id]
        
        if not terminal.output_lines:
            status = "running" if terminal.is_running else "finished"
            if not terminal.is_running:
                # Auto-remove finished terminal after read
                del self._terminals[term_id]
                return f"Terminal {term_id} ({status}): No output yet (removed)"
            return f"Terminal {term_id} ({status}): No output yet"
        
        # Return recent output (last 50 lines)
        recent_lines = terminal.output_lines[-50:]
        output = "\n".join(recent_lines)
        
        status = "running" if terminal.is_running else "finished"
        if not terminal.is_running:
            # Auto-remove finished terminal after read
            del self._terminals[term_id]
            return f"Terminal {term_id} ({status}):\n{output}\n(removed)"
        return f"Terminal {term_id} ({status}):\n{output}"
    
    def _kill_terminal(self, term_id: str) -> str:
        """Kill a terminal process"""
        if term_id not in self._terminals:
            raise KeyError(f"Terminal {term_id} not found")
        
        terminal = self._terminals[term_id]
        
        if not terminal.is_running:
            return f"Terminal {term_id} is already finished"
        
        try:
            terminal.process.terminate()
            
            # Wait a bit for graceful termination
            try:
                terminal.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                # Force kill if it doesn't terminate gracefully
                terminal.process.kill()
                terminal.process.wait()
            
            terminal.is_running = False
            return f"Killed terminal {term_id}"
            
        except Exception as e:
            return f"Error killing terminal {term_id}: {e}"
    
    def cleanup_finished_terminals(self):
        """Remove finished terminals from memory (optional cleanup)"""
        finished = [tid for tid, term in self._terminals.items() if not term.is_running]
        for tid in finished:
            del self._terminals[tid]
        return f"Cleaned up {len(finished)} finished terminals"
