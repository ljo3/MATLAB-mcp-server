"""
MATLAB MCP Server - A Model Context Protocol server for MATLAB integration.

This server provides tools for creating, executing, and managing MATLAB scripts
and functions through the MCP protocol.
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
from mcp.server.fastmcp import FastMCP, Image

# Configuration
MATLAB_PATH = os.getenv('MATLAB_PATH')
MATLAB_DIR = Path("src")
MAX_OUTPUT_LENGTH = 1000

# Initialize FastMCP server
mcp = FastMCP("MATLAB", dependencies=["mcp[cli]"])


class MATLABEngineManager:
    """Manages MATLAB engine initialization and lifecycle."""
    
    def __init__(self):
        self._engine = None
        self._initialize()
    
    def _initialize(self):
        """Initialize MATLAB engine with proper error handling."""
        self._ensure_matlab_engine_installed()
        import matlab.engine
        self._engine = matlab.engine.start_matlab()
        self._engine.addpath(str(MATLAB_DIR))
    
    def _ensure_matlab_engine_installed(self):
        """Ensure MATLAB engine is installed for the current Python environment."""
        try:
            import matlab.engine
            return
        except ImportError:
            self._install_matlab_engine()
    
    def _install_matlab_engine(self):
        """Install MATLAB engine for Python."""
        if not os.path.exists(MATLAB_PATH):
            raise RuntimeError(
                f"MATLAB installation not found at {MATLAB_PATH}. "
                "Set MATLAB_PATH environment variable to your MATLAB installation."
            )
        
        engine_setup = Path(MATLAB_PATH) / "extern/engines/python/setup.py"
        if not engine_setup.exists():
            raise RuntimeError(
                f"MATLAB Python engine setup not found at {engine_setup}. "
                "Verify your MATLAB installation."
            )
        
        print(f"Installing MATLAB engine from {engine_setup}...", file=sys.stderr)
        try:
            subprocess.run(
                [sys.executable, str(engine_setup), "install"],
                check=True,
                capture_output=True,
                text=True
            )
            print("MATLAB engine installed successfully.", file=sys.stderr)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"Failed to install MATLAB engine: {e.stderr}\n"
                "Try installing manually or check your MATLAB installation."
            )
    
    @property
    def engine(self):
        """Get the MATLAB engine instance."""
        return self._engine


class MATLABExecutor:
    """Handles MATLAB code execution and output capture."""
    
    def __init__(self, engine_manager: MATLABEngineManager):
        self.eng = engine_manager.engine
        self.matlab_dir = MATLAB_DIR
    
    @contextmanager
    def _output_capture(self, identifier: str):
        """Context manager for capturing MATLAB output."""
        temp_file = self.matlab_dir / f"temp_output_{identifier}.m"
        try:
            self.eng.eval(f"diary('{temp_file}')", nargout=0)
            yield temp_file
        finally:
            self.eng.eval("diary off", nargout=0)
    
    def _read_captured_output(self, temp_file: Path) -> str:
        """Read and clean up captured output file."""
        if temp_file.exists():
            with open(temp_file, 'r') as f:
                output = f.read().strip()
            temp_file.unlink(missing_ok=True)
            return output
        return "No output captured"
    
    def _capture_figures(self) -> List[Image]:
        """Capture all open MATLAB figures as images."""
        figures = []
        fig_handles = self.eng.eval('get(groot, "Children")', nargout=1)
        
        if not fig_handles:
            return figures
        
        for i, _ in enumerate(fig_handles):
            temp_file = self.matlab_dir / f"temp_fig_{i}.png"
            try:
                self.eng.eval(f"saveas(figure({i+1}), '{temp_file}')", nargout=0)
                with open(temp_file, 'rb') as f:
                    img_data = f.read()
                figures.append(Image(data=img_data, format='png'))
            finally:
                temp_file.unlink(missing_ok=True)
        
        return figures
    
    def _get_workspace_variables(self, exclude: Optional[List[str]] = None) -> Dict[str, str]:
        """Get workspace variables as strings."""
        exclude = exclude or ['args']
        variables = {}
        
        var_names = self.eng.eval('who', nargout=1)
        for var in var_names:
            if var in exclude:
                continue
            
            val = self.eng.workspace[var]
            val_str = str(val)
            
            # Truncate long values
            if len(val_str) > MAX_OUTPUT_LENGTH:
                val_str = val_str[:MAX_OUTPUT_LENGTH] + "... [truncated]"
            
            clean_var_name = var.strip().replace(' ', '_')
            variables[clean_var_name] = val_str
        
        return variables
    
    def _convert_to_matlab_types(self, args: Any):
        """Convert Python types to MATLAB types."""
        import matlab
        
        if isinstance(args, dict):
            return {k: self._convert_to_matlab_types(v) for k, v in args.items()}
        elif isinstance(args, list):
            # Check if list contains only numbers
            if all(isinstance(x, (int, float)) for x in args):
                return matlab.double(args)
            return [self._convert_to_matlab_types(x) for x in args]
        elif isinstance(args, (int, float)):
            return matlab.double([args])
        return args
    
    def execute_script(self, script_name: str, args: Optional[Dict[str, Any]] = None) -> dict:
        """Execute a MATLAB script and return results."""
        script_path = self.matlab_dir / f"{script_name}.m"
        if not script_path.exists():
            raise FileNotFoundError(f"Script {script_name}.m not found")
        
        self.eng.close('all', nargout=0)
        result = {}
        
        try:
            if args:
                matlab_args = self._convert_to_matlab_types(args)
                self.eng.workspace['args'] = matlab_args
            
            with self._output_capture(script_name) as temp_file:
                self.eng.eval(script_name, nargout=0)
            
            result['printed_output'] = self._read_captured_output(temp_file)
            result['figures'] = self._capture_figures()
            result.update(self._get_workspace_variables())
            
        except Exception as e:
            raise RuntimeError(f"MATLAB execution error: {str(e)}")
        
        return result
    
    def call_function(self, function_name: str, args: List[Any]) -> dict:
        """Call a MATLAB function with arguments."""
        function_path = self.matlab_dir / f"{function_name}.m"
        if not function_path.exists():
            raise FileNotFoundError(f"Function {function_name}.m not found")
        
        self.eng.close('all', nargout=0)
        result = {}
        
        try:
            matlab_args = [self._convert_to_matlab_types(arg) for arg in args]
            
            with self._output_capture(function_name) as temp_file:
                output = getattr(self.eng, function_name)(*matlab_args)
            
            result['output'] = str(output)
            result['printed_output'] = self._read_captured_output(temp_file)
            result['figures'] = self._capture_figures()
            
        except Exception as e:
            raise RuntimeError(f"MATLAB execution error: {str(e)}")
        
        return result


# Initialize manager and executor
MATLAB_DIR.mkdir(exist_ok=True)
engine_manager = MATLABEngineManager()
executor = MATLABExecutor(engine_manager)


# MCP Tool Definitions

@mcp.tool()
def create_script(script_name: str, code: str) -> str:
    """Create a new MATLAB script file.
    
    Args:
        script_name: Name of the script (without .m extension)
        code: MATLAB code to save
    
    Returns:
        Path to the created script
    """
    if not script_name.isidentifier():
        raise ValueError("Script name must be a valid MATLAB identifier")
    
    script_path = MATLAB_DIR / f"{script_name}.m"
    script_path.write_text(code)
    
    return str(script_path)


@mcp.tool()
def create_function(function_name: str, code: str) -> str:
    """Create a new MATLAB function file.
    
    Args:
        function_name: Name of the function (without .m extension)
        code: MATLAB function code including function definition
    
    Returns:
        Path to the created function file
    """
    if not function_name.isidentifier():
        raise ValueError("Function name must be a valid MATLAB identifier")
    
    if not code.strip().startswith('function'):
        raise ValueError("Code must start with function definition")
    
    function_path = MATLAB_DIR / f"{function_name}.m"
    function_path.write_text(code)
    
    return str(function_path)


@mcp.tool()
def execute_script(script_name: str, args: Optional[Dict[str, Any]] = None) -> dict:
    """Execute a MATLAB script and return results.
    
    Args:
        script_name: Name of the script to execute (without .m extension)
        args: Optional dictionary of arguments to pass to the script
    
    Returns:
        Dictionary containing printed output, figures, and workspace variables
    """
    return executor.execute_script(script_name, args)


@mcp.tool()
def call_function(function_name: str, args: List[Any]) -> dict:
    """Call a MATLAB function with arguments.
    
    Args:
        function_name: Name of the function to call (without .m extension)
        args: List of arguments to pass to the function
    
    Returns:
        Dictionary containing function output, printed output, and figures
    """
    return executor.call_function(function_name, args)


@mcp.resource("matlab://scripts/{script_name}")
def get_contents(script_name: str) -> str:
    """Get the content of a MATLAB script.
    
    Args:
        script_name: Name of the script (without .m extension)
    
    Returns:
        Content of the MATLAB script
    """
    script_path = MATLAB_DIR / f"{script_name}.m"
    if not script_path.exists():
        raise FileNotFoundError(f"Script {script_name}.m not found")
    
    return script_path.read_text()


if __name__ == "__main__":
    mcp.run(transport='stdio')