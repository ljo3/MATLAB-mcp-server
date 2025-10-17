# MATLAB MCP Server

A Model Context Protocol (MCP) server that provides AI assistants with the ability to create, execute, and manage MATLAB code. This server enables seamless integration between AI tools and MATLAB environments.

## 🌟 Features

- **Code Validation**: Check MATLAB syntax without execution
- **Code Execution**: Run MATLAB expressions and capture results
- **File Management**: Create, read, and execute MATLAB files
- **Testing Support**: Run MATLAB test files with detailed results
- **Toolbox Detection**: Discover installed MATLAB toolboxes
- **Coding Guidelines**: Built-in MATLAB best practices prompts

## 📋 Prerequisites

Before setting up the MATLAB MCP server, ensure you have:

1. **MATLAB Installation**: A working MATLAB installation with Python engine support
2. **Miniconda/Anaconda**: For Python environment management
3. **VS Code**: With MCP extension for testing (optional but recommended)

## 🛠️ Installation & Setup

### 1. Clone or Create Project Directory

```bash
# Create project directory
mkdir matlab-mcp
cd matlab-mcp

# Or clone if you have a repository
git clone <your-repo-url> matlab-mcp
cd matlab-mcp
```

### 2. Set Up Conda Environment

Create a dedicated Python environment for the MCP server:

```bash
# Create environment with Python 3.11
conda create -n mcp python=3.11

# Activate the environment
conda activate mcp

# Install required packages
pip install uv
uv pip install mcp[cli]
```

### 3. Configure MATLAB Python Engine

The server will automatically attempt to install the MATLAB Python engine if not found. To ensure proper setup:

1. Set the `MATLAB_PATH` environment variable to your MATLAB installation directory:

   ```bash
   # Windows
   set MATLAB_PATH=C:\Program Files\MATLAB\R2024b

   # macOS/Linux
   export MATLAB_PATH=/Applications/MATLAB_R2024b.app
   ```

2. The server will automatically install the MATLAB engine for Python on first run if needed.

### 4. Project Structure

Your project should have the following structure:

```
matlab-mcp/
├── main.py              # MCP server implementation
├── src/                 # MATLAB files directory (auto-created)
├── .vscode/
│   └── mcp.json        # VS Code MCP configuration
└── README.md           # This file
```

### 5. Configure VS Code MCP Integration

Create `.vscode/mcp.json` for VS Code integration:

```json
{
  "servers": {
    "MATLAB": {
      "type": "stdio",
      "command": "C:\\Users\\<username>\\miniconda3\\envs\\mcp\\python.exe",
      "args": [
        "-m",
        "uv",
        "run",
        "--with",
        "mcp[cli]",
        "mcp",
        "run",
        "C:\\Users\\<username>\\path\\to\\matlab-mcp\\main.py"
      ],
      "env": {
        "UV_LINK_MODE": "copy"
      }
    }
  }
}
```

**Important**: Replace `<username>` and paths with your actual system paths.

### 6. Place main.py File

Ensure your `main.py` file (the MCP server implementation) is in the root of your project directory. The file should contain all the MATLAB MCP tools and be executable by the Python environment.

## 🚀 Usage

### Starting the Server

#### Via VS Code

1. Open VS Code in your project directory
2. Open `.vscode/mcp.json`
3. Click "Start MCP" button that appears

#### Via Command Line

```bash
# Activate conda environment
conda activate mcp

# Run the server
uv run --with mcp[cli] mcp run main.py
```

### Available Tools

1. **`check_matlab_code`**: Validate MATLAB syntax without execution
2. **`evaluate_matlab_code`**: Execute MATLAB expressions and return results
3. **`create_matlab_file`**: Create new MATLAB files with code
4. **`run_matlab_file`**: Execute existing MATLAB files
5. **`run_matlab_test_file`**: Run MATLAB test files with structured results
6. **`detect_matlab_toolboxes`**: List installed MATLAB toolboxes

### Available Resources

- **`matlab://scripts/{script_name}`**: Read MATLAB file contents

### Available Prompts

- **`matlab_coding_guidelines`**: Get MATLAB coding best practices and standards

## 🧪 Testing the Server

Use these example prompts with your AI assistant to test each tool:

### Basic Syntax Check

```
Check this MATLAB code for syntax errors:
x = [1, 2, 3
y = sin(x
plot(x, y)
```

### Code Evaluation

```
Evaluate this MATLAB expression: 2 + 3 * 4
```

### File Creation

```
Create a MATLAB function called "calculate_mean" that takes an array and returns its mean
```

### File Execution

```
Run the MATLAB file "calculate_mean" with the array [1, 2, 3, 4, 5]
```

### Test File Creation and Execution

```
Create and run a test file for the calculate_mean function
```

### Toolbox Detection

```
Show me what MATLAB toolboxes are installed on my system
```

### Coding Guidelines

```
Show me the MATLAB coding guidelines
```

## 📁 File Management

- **MATLAB Files**: Created in `src/` directory
- **Automatic Extension**: `.m` extension added automatically if not specified
- **Path Handling**: Supports both relative and absolute paths
- **File Validation**: Automatic filename validation for MATLAB compatibility

## ⚙️ Configuration

### Environment Variables

- `MATLAB_PATH`: Path to your MATLAB installation (required for engine setup)
- `UV_LINK_MODE`: Set to "copy" for better compatibility

### Customization

- **MATLAB Directory**: Change `MATLAB_DIR` in `main.py` to customize where files are stored
- **Output Limits**: Modify `MAX_OUTPUT_LENGTH` to control output truncation
- **Coding Guidelines**: Update the `matlab_coding_guidelines` prompt to match your standards

## 🔧 Troubleshooting

### Common Issues

1. **MATLAB Engine Not Found**

   - Ensure MATLAB is installed and `MATLAB_PATH` is set correctly
   - The server will attempt automatic installation

2. **Permission Errors**

   - Ensure the `src/` directory is writable
   - Check file permissions for the project directory

3. **Server Won't Start**

   - Verify conda environment is activated
   - Check that all dependencies are installed
   - Ensure `main.py` path in `mcp.json` is correct

4. **Files Created in Wrong Location**
   - Check the working directory when server starts
   - Verify `MATLAB_DIR` path resolution

## 📝 Development

### Adding New Tools

To add new MCP tools, use the `@mcp.tool()` decorator:

```python
@mcp.tool()
def your_new_tool(param: str) -> dict:
    """Your tool description."""
    # Implementation
    return {"result": "success"}
```

### Adding New Resources

To add new MCP resources, use the `@mcp.resource()` decorator:

```python
@mcp.resource("your://resource/{param}")
def get_resource(param: str) -> str:
    """Resource description."""
    # Implementation
    return "resource content"
```

**Note**: This MCP server requires a valid MATLAB installation and license to function properly. Ensure MATLAB is properly configured and accessible before using the server.
