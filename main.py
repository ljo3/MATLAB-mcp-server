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

# Initialize FastMCP server with SSE support
mcp = FastMCP("MATLAB", dependencies=["mcp[cli]", "uvicorn"])


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
    
    def run_file(self, file_path: str, args: Optional[Dict[str, Any]] = None) -> dict:
        """Execute a MATLAB file (.m file) and return results.
        
        Args:
            file_path: Path to the MATLAB file to execute (with or without .m extension)
            args: Optional dictionary of arguments to pass to the script/function
        
        Returns:
            Dictionary containing execution results, output, figures, and workspace variables
        """
        # Normalize file path
        if not file_path.endswith('.m'):
            file_path += '.m'
        
        matlab_file = Path(file_path)
        if not matlab_file.is_absolute():
            matlab_file = self.matlab_dir / matlab_file
        
        if not matlab_file.exists():
            raise FileNotFoundError(f"MATLAB file not found: {matlab_file}")
        
        file_name = matlab_file.stem
        result = {}
        
        try:
            # Read the file to determine if it's a function or script
            content = matlab_file.read_text()
            is_function = content.strip().startswith('function')
            
            if is_function:
                # It's a function - call it with arguments
                if args:
                    args_list = [args[k] for k in sorted(args.keys())] if isinstance(args, dict) else [args]
                else:
                    args_list = []
                result = self.call_function(file_name, args_list)
            else:
                # It's a script - execute it
                result = self.execute_script(file_name, args)
                
        except Exception as e:
            result['error'] = f"MATLAB file execution error: {str(e)}"
        
        return result


# Initialize manager and executor
MATLAB_DIR.mkdir(exist_ok=True)
engine_manager = MATLABEngineManager()
executor = MATLABExecutor(engine_manager)


# MCP Tool Definitions

@mcp.tool()
def check_matlab_code(code: str) -> dict:
    """Check MATLAB code syntax and structure without executing it.
    
    Args:
        code: MATLAB code to check
    
    Returns:
        Dictionary containing syntax check results, warnings, and suggestions
    """
    result = {
        'syntax_valid': True,
        'warnings': [],
        'suggestions': [],
        'line_count': 0
    }
    
    try:
        lines = code.strip().split('\n')
        result['line_count'] = len(lines)
        
        # Basic syntax checks
        for i, line in enumerate(lines, 1):
            line = line.strip()
            if not line or line.startswith('%'):
                continue
                
            # Check for common syntax issues
            if line.count('(') != line.count(')'):
                result['warnings'].append(f"Line {i}: Unmatched parentheses")
            if line.count('[') != line.count(']'):
                result['warnings'].append(f"Line {i}: Unmatched square brackets")
            if line.count('{') != line.count('}'):
                result['warnings'].append(f"Line {i}: Unmatched curly braces")
            
            # Check for missing semicolons on assignments
            if '=' in line and not line.endswith(';') and not line.endswith('...'):
                if not any(keyword in line for keyword in ['if', 'for', 'while', 'function', 'else', 'elseif']):
                    result['suggestions'].append(f"Line {i}: Consider adding semicolon to suppress output")
        
        # Use MATLAB engine for more detailed syntax checking
        temp_file = MATLAB_DIR / "temp_syntax_check.m"
        temp_file.write_text(code)
        
        try:
            # Try to parse the code without executing
            executor.eng.eval(f"checkcode('{temp_file}', '-string')", nargout=0)
        except Exception as e:
            result['syntax_valid'] = False
            result['warnings'].append(f"MATLAB syntax error: {str(e)}")
        finally:
            temp_file.unlink(missing_ok=True)
            
    except Exception as e:
        result['syntax_valid'] = False
        result['warnings'].append(f"Code analysis error: {str(e)}")
    
    return result


@mcp.tool()
def evaluate_matlab_code(code: str, variables: Optional[Dict[str, Any]] = None) -> dict:
    """Evaluate MATLAB code expressions and return results.
    
    Args:
        code: MATLAB code to evaluate
        variables: Optional dictionary of variables to set in workspace before evaluation
    
    Returns:
        Dictionary containing evaluation results, output, figures, and workspace variables
    """
    return executor.execute_script(code, variables)


@mcp.tool()
def run_matlab_file(file_path: str, args: Optional[Dict[str, Any]] = None) -> dict:
    """Execute a MATLAB file (.m file) and return results.
    
    Args:
        file_path: Path to the MATLAB file to execute (with or without .m extension)
        args: Optional dictionary of arguments to pass to the script/function
    
    Returns:
        Dictionary containing execution results, output, figures, and workspace variables
    """
    return executor.run_file(file_path, args)


@mcp.tool()
def run_matlab_test_file(test_file_path: str, test_options: Optional[Dict[str, Any]] = None) -> dict:
    """Run a MATLAB test file with appropriate test handling.
    
    Args:
        test_file_path: Path to the MATLAB test file to run
        test_options: Optional dictionary of test options (e.g., verbose, output_detail)
    
    Returns:
        Dictionary containing test results, passed/failed tests, and detailed output
    """
    # Normalize file path
    if not test_file_path.endswith('.m'):
        test_file_path += '.m'
    
    test_file = Path(test_file_path)
    if not test_file.is_absolute():
        test_file = MATLAB_DIR / test_file
    
    if not test_file.exists():
        raise FileNotFoundError(f"Test file not found: {test_file}")
    
    test_name = test_file.stem
    result = {
        'test_name': test_name,
        'passed': 0,
        'failed': 0,
        'total': 0,
        'test_details': [],
        'output': ''
    }
    
    try:
        # Clear workspace and close figures
        executor.eng.close('all', nargout=0)
        
        # Run the test using MATLAB's testing framework
        with executor._output_capture('test') as temp_file:
            try:
                # Try to run as a test class or function
                test_result = executor.eng.eval(f"runtests('{test_name}')", nargout=1)
                
                # Extract test results if available
                if hasattr(test_result, 'Passed'):
                    result['passed'] = sum(test_result.Passed)
                    result['failed'] = sum(test_result.Failed)
                    result['total'] = len(test_result.Passed)
                    
                    # Get detailed results
                    for i, (name, passed, failed) in enumerate(zip(
                        getattr(test_result, 'Name', []),
                        test_result.Passed,
                        test_result.Failed
                    )):
                        result['test_details'].append({
                            'name': str(name),
                            'passed': bool(passed),
                            'failed': bool(failed)
                        })
                        
            except Exception:
                # Fallback: run as regular script and look for test patterns
                executor.eng.eval(test_name, nargout=0)
                result['output'] = 'Test executed as script (no formal test framework detected)'
        
        result['output'] += executor._read_captured_output(temp_file)
        result['figures'] = executor._capture_figures()
        
    except Exception as e:
        result['error'] = f"Test execution error: {str(e)}"
        result['output'] = str(e)
    
    return result


@mcp.tool()
def create_matlab_file(filename: str, code: str) -> dict:
    """Create a new MATLAB file with the specified code.
    
    IMPORTANT: Before creating MATLAB code, use the 'matlab_coding_guidelines' prompt
    to ensure the code follows proper MATLAB conventions and best practices.
    
    Args:
        filename: Name of the MATLAB file (with or without .m extension)
        code: MATLAB code to write to the file
    
    Returns:
        Dictionary with debugging information and path to the created file
    """
    import os
    from pathlib import Path
    
    # Add .m extension if not present
    if not filename.endswith('.m'):
        filename += '.m'
    
    # Validate filename
    file_stem = filename[:-2]  # Remove .m extension
    if not file_stem.replace('_', '').isalnum():
        raise ValueError("Filename must contain only letters, numbers, and underscores")
    
    # Create file path - ensure MATLAB_DIR exists
    MATLAB_DIR.mkdir(parents=True, exist_ok=True)
    file_path = MATLAB_DIR / filename
    
    debug_info = {
        'filename': filename,
        'matlab_dir': str(MATLAB_DIR),
        'matlab_dir_absolute': str(MATLAB_DIR.absolute()),
        'file_path': str(file_path),
        'file_path_absolute': str(file_path.absolute()),
        'matlab_dir_exists': MATLAB_DIR.exists(),
        'cwd': os.getcwd(),
        'code_length': len(code)
    }
    
    # Write code to file using Python's built-in file operations
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(code)
        
        debug_info['file_created'] = True
        debug_info['file_exists_after_write'] = file_path.exists()
        
        # Try to read back the file to verify
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                read_content = f.read()
            debug_info['content_matches'] = read_content == code
            debug_info['read_content_length'] = len(read_content)
        else:
            debug_info['content_matches'] = False
            debug_info['read_content_length'] = 0
            
    except Exception as e:
        debug_info['error'] = f"Failed to write MATLAB file: {str(e)}"
        debug_info['file_created'] = False
        debug_info['file_exists_after_write'] = False
    
    return debug_info


@mcp.tool()
def detect_matlab_toolboxes() -> dict:
    """Detect which MATLAB toolboxes are installed using ver command.
    
    Returns:
        Dictionary containing the raw output from MATLAB's ver command
    """
    result = {}
    
    try:
        # Get the raw ver output
        with executor._output_capture('ver') as temp_file:
            executor.eng.eval('ver', nargout=0)
        
        ver_output = executor._read_captured_output(temp_file)
        result['ver_output'] = ver_output
        
    except Exception as e:
        result['error'] = f"Error getting ver output: {str(e)}"
    
    return result


@mcp.prompt()
def matlab_coding_guidelines() -> str:
    """MATLAB coding guidelines and best practices for file creation.
    
    Returns comprehensive guidelines for writing clean, maintainable MATLAB code.
    """
    return """
MATLAB Coding Guidelines:

1. NAMING CONVENTIONS:
   - Functions: camelCase (e.g., calculateMean, plotResults)
   - Variables: descriptive names (e.g., sampleRate, inputData)
   - Constants: UPPER_CASE (e.g., MAX_ITERATIONS)

2. FUNCTION STRUCTURE:
   - Start with function signature: function [out1, out2] = myFunction(in1, in2)
   - Add help text immediately after function line
   - Include input validation
   - Use meaningful variable names

3. DOCUMENTATION:
   - Add help text for all functions
   - Comment complex algorithms
   - Include examples in help text

4. ERROR HANDLING:
   - Validate inputs using nargin, isa(), size()
   - Use meaningful error messages
   - Handle edge cases

5. CODE STYLE:
   - Use consistent indentation
   - Add semicolons to suppress output
   - Group related code with blank lines
   - Avoid magic numbers, use named constants

Example function template:
function result = processData(inputData, threshold)
    %PROCESSDATA Process input data with given threshold
    %   result = processData(inputData, threshold) processes the input
    %   data and returns the result based on the threshold.
    %
    %   Inputs:
    %       inputData - numeric array of data points
    %       threshold - scalar threshold value
    %
    %   Output:
    %       result - processed data array
    
    % Input validation
    if nargin < 2
        error('Two inputs required: inputData and threshold');
    end
    
    if ~isnumeric(inputData)
        error('inputData must be numeric');
    end
    
    % Main processing
    result = inputData(inputData > threshold);
end
"""


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
    import uvicorn
    
    # For SSE transport, we need to run as a web server
    # The FastMCP will handle SSE automatically when run via uvicorn
    uvicorn.run(mcp.app, host="127.0.0.1", port=8000)
