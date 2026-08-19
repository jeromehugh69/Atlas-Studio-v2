# AI Coding Assistant - Frontend UI Integration

## Overview

Add Cursor-like AI coding assistant capabilities to the Atlas Studio Frontend UI. The AI assistant will be able to:
- Read and understand the codebase
- Create implementation plans
- Write and edit code
- Run commands
- Search for files and content
- Execute tasks autonomously with user approval

## Current State

**Existing Chat Panel:**
- `src/atlas_studio/static/atlas-chat-panel.html` - Chat UI with textarea input
- `src/atlas_studio/static/app.js` - Chat form submission, message rendering
- `src/atlas_studio/static/live-atlas.js` - Live assistant features

**Current Capabilities:**
- Send messages to agents
- View responses
- File attachments
- Voice input

**Missing Capabilities:**
- No file browsing/selection
- No code editing
- No command execution
- No workspace context
- No implementation planning
- No diff viewing

## Target State

**AI Coding Assistant Features:**

| Feature | Description | Priority |
|---------|-------------|----------|
| File Explorer | Browse workspace files, select context | P0 |
| Code Editor | Inline code editing with syntax highlighting | P0 |
| Command Terminal | Run commands with output display | P0 |
| Implementation Planner | Generate and execute implementation plans | P1 |
| Diff Viewer | View code changes before applying | P1 |
| Workspace Context | Auto-include relevant files | P1 |
| Approval Workflow | User approval for file changes | P0 |

## Architecture

### Backend Components

**New API Endpoints:**
```
POST /api/assistant/chat          # Enhanced chat with tool support
POST /api/assistant/plan          # Generate implementation plan
POST /api/assistant/execute       # Execute approved plan steps
GET  /api/assistant/files         # List workspace files
GET  /api/assistant/file          # Read file content
POST /api/assistant/file          # Write/update file
POST /api/assistant/command       # Run shell command
GET  /api/assistant/context       # Get workspace context
```

**New Modules:**
```
src/atlas_studio/assistant/
├── __init__.py
├── chat.py              # Enhanced chat with tool calling
├── planner.py           # Implementation plan generation
├── executor.py          # Plan step execution
├── file_manager.py      # File operations
├── command_runner.py    # Shell command execution
└── context.py           # Workspace context management
```

### Frontend Components

**New UI Panels:**
```
src/atlas_studio/static/
├── assistant-panel.html       # Main assistant container
├── assistant-panel.css        # Assistant styles
├── assistant-panel.js         # Assistant logic
├── file-explorer.js           # File tree component
├── code-editor.js             # Code editing component
├── terminal-panel.js          # Command execution component
├── plan-viewer.js             # Implementation plan display
└── diff-viewer.js             # Code diff display
```

## Implementation Plan

### Phase 1: Backend Foundation (Week 1)

#### Ticket 1.1: File Manager Module
**File:** `src/atlas_studio/assistant/file_manager.py`

```python
from __future__ import annotations
import os
from pathlib import Path
from typing import Any

class FileManager:
    """Manage workspace files for the AI assistant."""
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
    
    def list_files(self, path: str = ".", max_depth: int = 3) -> list[dict[str, Any]]:
        """List files in workspace with hierarchy."""
        target = self.workspace_root / path
        if not target.exists():
            return []
        
        files = []
        for item in sorted(target.iterdir()):
            if item.name.startswith(".") or item.name in ["node_modules", "__pycache__", ".git"]:
                continue
            
            file_info = {
                "name": item.name,
                "path": str(item.relative_to(self.workspace_root)),
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else 0,
            }
            
            if item.is_dir() and max_depth > 0:
                file_info["children"] = self.list_files(
                    str(item.relative_to(self.workspace_root)),
                    max_depth - 1
                )
            
            files.append(file_info)
        
        return files
    
    def read_file(self, file_path: str) -> str:
        """Read file content."""
        target = self.workspace_root / file_path
        if not target.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        if not str(target.resolve()).startswith(str(self.workspace_root)):
            raise ValueError("Access denied: path traversal blocked")
        
        return target.read_text(encoding="utf-8", errors="replace")
    
    def write_file(self, file_path: str, content: str) -> dict[str, Any]:
        """Write file content with approval tracking."""
        target = self.workspace_root / file_path
        if not str(target.resolve()).startswith(str(self.workspace_root)):
            raise ValueError("Access denied: path traversal blocked")
        
        # Create backup
        backup_path = target.with_suffix(target.suffix + ".backup")
        if target.exists():
            backup_path.write_text(target.read_text(encoding="utf-8"))
        
        # Write new content
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        
        return {
            "path": file_path,
            "size": len(content),
            "backup": str(backup_path) if backup_path.exists() else None,
        }
    
    def search_files(self, pattern: str, path: str = ".") -> list[dict[str, Any]]:
        """Search files by name pattern."""
        target = self.workspace_root / path
        results = []
        
        for item in target.rglob(pattern):
            if item.is_file():
                results.append({
                    "name": item.name,
                    "path": str(item.relative_to(self.workspace_root)),
                    "size": item.stat().st_size,
                })
        
        return results
    
    def search_content(self, query: str, path: str = ".") -> list[dict[str, Any]]:
        """Search file content by query."""
        target = self.workspace_root / path
        results = []
        
        for item in target.rglob("*"):
            if item.is_file() and item.suffix in [".py", ".js", ".ts", ".tsx", ".jsx", ".html", ".css", ".md", ".json", ".yaml", ".yml"]:
                try:
                    content = item.read_text(encoding="utf-8", errors="replace")
                    if query.lower() in content.lower():
                        results.append({
                            "path": str(item.relative_to(self.workspace_root)),
                            "matches": content.lower().count(query.lower()),
                        })
                except Exception:
                    continue
        
        return results
```

#### Ticket 1.2: Command Runner Module
**File:** `src/atlas_studio/assistant/command_runner.py`

```python
from __future__ import annotations
import asyncio
import subprocess
from pathlib import Path
from typing import Any

class CommandRunner:
    """Run shell commands with safety controls."""
    
    def __init__(self, workspace_root: Path, allowed_commands: list[str] | None = None):
        self.workspace_root = workspace_root.resolve()
        self.allowed_commands = allowed_commands or [
            "python", "pip", "uv", "node", "npm", "npx",
            "git", "ls", "cat", "grep", "find", "wc",
            "pytest", "ruff", "mypy", "bandit",
        ]
    
    async def run(self, command: str, timeout: int = 30) -> dict[str, Any]:
        """Run a command and return output."""
        # Safety check
        cmd_parts = command.split()
        if not cmd_parts:
            return {"error": "Empty command"}
        
        base_cmd = cmd_parts[0]
        if base_cmd not in self.allowed_commands:
            return {"error": f"Command not allowed: {base_cmd}"}
        
        try:
            process = await asyncio.create_subprocess_shell(
                command,
                cwd=str(self.workspace_root),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            
            return {
                "exit_code": process.returncode,
                "stdout": stdout.decode("utf-8", errors="replace"),
                "stderr": stderr.decode("utf-8", errors="replace"),
            }
        
        except asyncio.TimeoutError:
            process.kill()
            return {"error": f"Command timed out after {timeout}s"}
        except Exception as e:
            return {"error": str(e)}
```

#### Ticket 1.3: Context Manager Module
**File:** `src/atlas_studio/assistant/context.py`

```python
from __future__ import annotations
from pathlib import Path
from typing import Any

class ContextManager:
    """Manage workspace context for AI assistant."""
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root.resolve()
    
    def get_project_context(self) -> dict[str, Any]:
        """Get project context for AI assistant."""
        context = {
            "name": self.workspace_root.name,
            "root": str(self.workspace_root),
            "files": [],
            "config": {},
            "dependencies": [],
        }
        
        # Read pyproject.toml if exists
        pyproject = self.workspace_root / "pyproject.toml"
        if pyproject.exists():
            context["config"]["pyproject"] = self._parse_pyproject(pyproject)
        
        # Read package.json if exists
        package_json = self.workspace_root / "package.json"
        if package_json.exists():
            context["config"]["package"] = self._parse_package_json(package_json)
        
        # Get key files
        key_files = ["README.md", "CONTRIBUTING.md", "Dockerfile", "compose.yaml"]
        for file in key_files:
            path = self.workspace_root / file
            if path.exists():
                context["files"].append({
                    "name": file,
                    "path": file,
                    "content": path.read_text(encoding="utf-8", errors="replace")[:1000],
                })
        
        return context
    
    def get_file_context(self, file_path: str) -> dict[str, Any]:
        """Get detailed context for a specific file."""
        target = self.workspace_root / file_path
        if not target.exists():
            return {}
        
        content = target.read_text(encoding="utf-8", errors="replace")
        
        return {
            "path": file_path,
            "name": target.name,
            "extension": target.suffix,
            "size": len(content),
            "lines": content.count("\n") + 1,
            "content": content,
            "imports": self._extract_imports(content, target.suffix),
        }
    
    def _parse_pyproject(self, path: Path) -> dict[str, Any]:
        """Parse pyproject.toml."""
        try:
            import tomllib
            with open(path, "rb") as f:
                return tomllib.load(f)
        except Exception:
            return {}
    
    def _parse_package_json(self, path: Path) -> dict[str, Any]:
        """Parse package.json."""
        import json
        try:
            return json.loads(path.read_text())
        except Exception:
            return {}
    
    def _extract_imports(self, content: str, extension: str) -> list[str]:
        """Extract imports from file content."""
        imports = []
        for line in content.split("\n")[:50]:  # First 50 lines
            if extension == ".py":
                if line.startswith("import ") or line.startswith("from "):
                    imports.append(line.strip())
            elif extension in [".js", ".ts", ".tsx", ".jsx"]:
                if line.startswith("import ") or line.startswith("const ") and "require(" in line:
                    imports.append(line.strip())
        return imports
```

### Phase 2: Frontend Components (Week 1-2)

#### Ticket 2.1: File Explorer Component
**File:** `src/atlas_studio/static/file-explorer.js`

```javascript
class FileExplorer {
    constructor(container, onSelect) {
        this.container = container;
        this.onSelect = onSelect;
        this.files = [];
        this.selected = null;
        this.render();
    }
    
    async load(path = ".") {
        const response = await fetch(`/api/assistant/files?path=${path}`);
        this.files = await response.json();
        this.render();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="file-explorer-header">
                <span>FILE EXPLORER</span>
                <button class="refresh-btn" onclick="this.fileExplorer.load()">↻</button>
            </div>
            <div class="file-tree">
                ${this.renderFiles(this.files)}
            </div>
        `;
        
        this.container.querySelectorAll('.file-item').forEach(item => {
            item.onclick = () => this.selectFile(item.dataset.path);
        });
    }
    
    renderFiles(files, depth = 0) {
        return files.map(file => `
            <div class="file-item ${file.type} ${this.selected === file.path ? 'selected' : ''}" 
                 data-path="${file.path}" 
                 style="padding-left: ${depth * 16}px">
                <span class="icon">${file.type === 'directory' ? '📁' : '📄'}</span>
                <span class="name">${file.name}</span>
                ${file.type === 'file' ? `<span class="size">${this.formatSize(file.size)}</span>` : ''}
            </div>
            ${file.children ? this.renderFiles(file.children, depth + 1) : ''}
        `).join('');
    }
    
    selectFile(path) {
        this.selected = path;
        this.onSelect(path);
        this.render();
    }
    
    formatSize(bytes) {
        if (bytes < 1024) return `${bytes} B`;
        if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
        return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
    }
}
```

#### Ticket 2.2: Code Editor Component
**File:** `src/atlas_studio/static/code-editor.js`

```javascript
class CodeEditor {
    constructor(container, onSave) {
        this.container = container;
        this.onSave = onSave;
        this.currentFile = null;
        this.content = '';
        this.render();
    }
    
    async loadFile(path) {
        const response = await fetch(`/api/assistant/file?path=${path}`);
        const data = await response.json();
        this.currentFile = path;
        this.content = data.content;
        this.render();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="code-editor-header">
                <span class="file-name">${this.currentFile || 'No file selected'}</span>
                <div class="editor-actions">
                    <button class="save-btn" onclick="this.codeEditor.save()" ${!this.currentFile ? 'disabled' : ''}>
                        Save (Ctrl+S)
                    </button>
                    <button class="format-btn" onclick="this.codeEditor.format()">
                        Format
                    </button>
                </div>
            </div>
            <div class="editor-container">
                <textarea class="code-textarea" 
                          spellcheck="false"
                          oninput="this.codeEditor.onInput(event)"
                          onkeydown="this.codeEditor.onKeyDown(event)">${this.escapeHtml(this.content)}</textarea>
                <pre class="code-highlight"><code></code></pre>
            </div>
        `;
    }
    
    onInput(event) {
        this.content = event.target.value;
        this.updateHighlight();
    }
    
    onKeyDown(event) {
        if ((event.ctrlKey || event.metaKey) && event.key === 's') {
            event.preventDefault();
            this.save();
        }
        if (event.key === 'Tab') {
            event.preventDefault();
            const textarea = event.target;
            const start = textarea.selectionStart;
            const end = textarea.selectionEnd;
            this.content = this.content.substring(0, start) + '    ' + this.content.substring(end);
            textarea.value = this.content;
            textarea.selectionStart = textarea.selectionEnd = start + 4;
        }
    }
    
    async save() {
        if (!this.currentFile) return;
        
        const response = await fetch('/api/assistant/file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                path: this.currentFile,
                content: this.content,
            }),
        });
        
        if (response.ok) {
            this.onSave(this.currentFile);
        }
    }
    
    updateHighlight() {
        // Simple syntax highlighting
        const code = this.container.querySelector('.code-highlight code');
        if (code) {
            code.textContent = this.content;
        }
    }
    
    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}
```

#### Ticket 2.3: Terminal Panel Component
**File:** `src/atlas_studio/static/terminal-panel.js`

```javascript
class TerminalPanel {
    constructor(container) {
        this.container = container;
        this.history = [];
        this.currentCommand = '';
        this.render();
    }
    
    render() {
        this.container.innerHTML = `
            <div class="terminal-header">
                <span>TERMINAL</span>
                <button class="clear-btn" onclick="this.terminal.clear()">Clear</button>
            </div>
            <div class="terminal-output">
                ${this.history.map(item => `
                    <div class="terminal-line ${item.type}">
                        <span class="prompt">$ ${item.command}</span>
                        <pre class="output">${item.output}</pre>
                    </div>
                `).join('')}
            </div>
            <div class="terminal-input">
                <span class="prompt">$</span>
                <input type="text" 
                       class="command-input"
                       placeholder="Enter command..."
                       onkeydown="this.terminal.onKeyDown(event)"
                       value="${this.currentCommand}">
            </div>
        `;
    }
    
    async runCommand(command) {
        this.history.push({ type: 'command', command, output: '' });
        this.render();
        
        const response = await fetch('/api/assistant/command', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command }),
        });
        
        const result = await response.json();
        const lastEntry = this.history[this.history.length - 1];
        lastEntry.output = result.stdout || result.stderr || result.error;
        lastEntry.type = result.exit_code === 0 ? 'success' : 'error';
        this.render();
    }
    
    onKeyDown(event) {
        if (event.key === 'Enter') {
            const command = event.target.value.trim();
            if (command) {
                this.runCommand(command);
                this.currentCommand = '';
                event.target.value = '';
            }
        }
    }
    
    clear() {
        this.history = [];
        this.render();
    }
}
```

#### Ticket 2.4: Assistant Panel Integration
**File:** `src/atlas_studio/static/assistant-panel.js`

```javascript
class AssistantPanel {
    constructor() {
        this.fileExplorer = null;
        this.codeEditor = null;
        this.terminal = null;
        this.chat = null;
        this.selectedFiles = [];
        this.render();
    }
    
    render() {
        const panel = document.getElementById('assistant-panel');
        if (!panel) return;
        
        panel.innerHTML = `
            <div class="assistant-layout">
                <aside class="assistant-sidebar">
                    <div id="file-explorer" class="sidebar-section"></div>
                    <div id="selected-files" class="sidebar-section">
                        <div class="section-header">CONTEXT FILES</div>
                        <div id="contextFiles"></div>
                    </div>
                </aside>
                
                <main class="assistant-main">
                    <div class="assistant-tabs">
                        <button class="tab active" data-tab="chat">Chat</button>
                        <button class="tab" data-tab="editor">Editor</button>
                        <button class="tab" data-tab="terminal">Terminal</button>
                        <button class="tab" data-tab="plan">Plan</button>
                    </div>
                    
                    <div class="tab-content active" id="chat-tab">
                        <div id="assistant-chat"></div>
                    </div>
                    
                    <div class="tab-content" id="editor-tab">
                        <div id="code-editor"></div>
                    </div>
                    
                    <div class="tab-content" id="terminal-tab">
                        <div id="terminal-panel"></div>
                    </div>
                    
                    <div class="tab-content" id="plan-tab">
                        <div id="plan-viewer"></div>
                    </div>
                </main>
            </div>
        `;
        
        this.initializeComponents();
        this.setupTabs();
    }
    
    initializeComponents() {
        this.fileExplorer = new FileExplorer(
            document.getElementById('file-explorer'),
            (path) => this.addContextFile(path)
        );
        
        this.codeEditor = new CodeEditor(
            document.getElementById('code-editor'),
            (path) => this.onFileSaved(path)
        );
        
        this.terminal = new TerminalPanel(
            document.getElementById('terminal-panel')
        );
        
        this.fileExplorer.load();
    }
    
    setupTabs() {
        document.querySelectorAll('.assistant-tabs .tab').forEach(tab => {
            tab.onclick = () => {
                document.querySelectorAll('.assistant-tabs .tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
                tab.classList.add('active');
                document.getElementById(`${tab.dataset.tab}-tab`).classList.add('active');
            };
        });
    }
    
    addContextFile(path) {
        if (!this.selectedFiles.includes(path)) {
            this.selectedFiles.push(path);
            this.updateContextFiles();
            this.codeEditor.loadFile(path);
        }
    }
    
    updateContextFiles() {
        const container = document.getElementById('contextFiles');
        container.innerHTML = this.selectedFiles.map(path => `
            <div class="context-file">
                <span>${path.split('/').pop()}</span>
                <button onclick="assistant.removeContextFile('${path}')">×</button>
            </div>
        `).join('');
    }
    
    removeContextFile(path) {
        this.selectedFiles = this.selectedFiles.filter(f => f !== path);
        this.updateContextFiles();
    }
    
    async sendChat(message) {
        const context = this.selectedFiles.map(path => 
            this.codeEditor.currentFile === path ? this.codeEditor.content : null
        ).filter(Boolean);
        
        const response = await fetch('/api/assistant/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                message,
                context_files: this.selectedFiles,
                file_contents: context,
            }),
        });
        
        const result = await response.json();
        return result;
    }
    
    onFileSaved(path) {
        console.log(`File saved: ${path}`);
    }
}

// Initialize assistant panel
let assistant;
document.addEventListener('DOMContentLoaded', () => {
    assistant = new AssistantPanel();
});
```

### Phase 3: Backend API Endpoints (Week 2)

#### Ticket 3.1: Assistant API Endpoints
**File:** `src/atlas_studio/assistant/chat.py`

```python
from __future__ import annotations
from typing import Any
from ..providers import ModelProvider

class AssistantChat:
    """Enhanced chat with tool calling for AI assistant."""
    
    def __init__(self, provider: ModelProvider, file_manager, command_runner, context_manager):
        self.provider = provider
        self.file_manager = file_manager
        self.command_runner = command_runner
        self.context_manager = context_manager
    
    async def chat(self, message: str, context_files: list[str] = None, file_contents: list[str] = None) -> dict[str, Any]:
        """Process chat message with tool calling."""
        # Build system prompt with context
        system = self._build_system_prompt(context_files, file_contents)
        
        # Call model with tools
        tools = self._get_tools()
        
        response = await self.provider.chat_with_tools(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
            model="default",
            tools=tools,
            temperature=0.3,
        )
        
        # Process tool calls
        result = {"response": response.get("content", ""), "actions": []}
        
        for tool_call in response.get("tool_calls", []):
            action = await self._execute_tool_call(tool_call)
            result["actions"].append(action)
        
        return result
    
    def _build_system_prompt(self, context_files, file_contents) -> str:
        """Build system prompt with context."""
        prompt = """You are Atlas AI Assistant, a coding assistant for Atlas Studio.

You can:
1. Read and understand code files
2. Search for files and content
3. Write and edit code
4. Run shell commands
5. Create implementation plans

Always explain what you're doing before taking action.
Get user approval before making file changes.
Use the provided tools to help with coding tasks.
"""
        
        if context_files:
            prompt += f"\n\nSelected context files: {', '.join(context_files)}"
        
        if file_contents:
            for i, content in enumerate(file_contents):
                if content:
                    prompt += f"\n\nFile {i+1} content:\n```\n{content[:2000]}\n```"
        
        return prompt
    
    def _get_tools(self) -> list[dict]:
        """Get available tools for the assistant."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Read the content of a file",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path to read"}
                        },
                        "required": ["path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Write content to a file (requires approval)",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string", "description": "File path to write"},
                            "content": {"type": "string", "description": "Content to write"}
                        },
                        "required": ["path", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_files",
                    "description": "Search for files by name pattern",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string", "description": "Search pattern (e.g., *.py)"},
                            "path": {"type": "string", "description": "Directory to search in"}
                        },
                        "required": ["pattern"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_content",
                    "description": "Search file content for a query",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"},
                            "path": {"type": "string", "description": "Directory to search in"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "Run a shell command",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "Command to run"}
                        },
                        "required": ["command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_plan",
                    "description": "Create an implementation plan",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "goal": {"type": "string", "description": "Implementation goal"},
                            "files": {"type": "array", "items": {"type": "string"}, "description": "Files to modify"}
                        },
                        "required": ["goal"]
                    }
                }
            },
        ]
    
    async def _execute_tool_call(self, tool_call: dict) -> dict[str, Any]:
        """Execute a tool call."""
        name = tool_call["function"]["name"]
        args = tool_call["function"]["arguments"]
        
        if name == "read_file":
            content = self.file_manager.read_file(args["path"])
            return {"tool": name, "result": content}
        
        elif name == "write_file":
            # Requires approval
            return {"tool": name, "requires_approval": True, "args": args}
        
        elif name == "search_files":
            results = self.file_manager.search_files(args["pattern"], args.get("path", "."))
            return {"tool": name, "result": results}
        
        elif name == "search_content":
            results = self.file_manager.search_content(args["query"], args.get("path", "."))
            return {"tool": name, "result": results}
        
        elif name == "run_command":
            result = await self.command_runner.run(args["command"])
            return {"tool": name, "result": result}
        
        elif name == "create_plan":
            return {"tool": name, "requires_approval": True, "args": args}
        
        return {"tool": name, "error": f"Unknown tool: {name}"}
```

#### Ticket 3.2: API Routes
**File:** `src/atlas_studio/assistant/routes.py`

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any

router = APIRouter(prefix="/api/assistant", tags=["assistant"])

class ChatRequest(BaseModel):
    message: str
    context_files: list[str] = []
    file_contents: list[str] = []

class CommandRequest(BaseModel):
    command: str
    timeout: int = 30

class FileWriteRequest(BaseModel):
    path: str
    content: str

@router.post("/chat")
async def chat(request: ChatRequest):
    """Process chat message with tool calling."""
    # Implementation depends on your dependency injection
    pass

@router.get("/files")
async def list_files(path: str = "."):
    """List workspace files."""
    pass

@router.get("/file")
async def read_file(path: str):
    """Read file content."""
    pass

@router.post("/file")
async def write_file(request: FileWriteRequest):
    """Write file content."""
    pass

@router.post("/command")
async def run_command(request: CommandRequest):
    """Run shell command."""
    pass

@router.get("/context")
async def get_context():
    """Get workspace context."""
    pass
```

## Files to Create/Modify

| File | Changes |
|------|---------|
| `src/atlas_studio/assistant/__init__.py` | Create |
| `src/atlas_studio/assistant/file_manager.py` | Create |
| `src/atlas_studio/assistant/command_runner.py` | Create |
| `src/atlas_studio/assistant/context.py` | Create |
| `src/atlas_studio/assistant/chat.py` | Create |
| `src/atlas_studio/assistant/routes.py` | Create |
| `src/atlas_studio/static/assistant-panel.html` | Create |
| `src/atlas_studio/static/assistant-panel.css` | Create |
| `src/atlas_studio/static/assistant-panel.js` | Create |
| `src/atlas_studio/static/file-explorer.js` | Create |
| `src/atlas_studio/static/code-editor.js` | Create |
| `src/atlas_studio/static/terminal-panel.js` | Create |
| `src/atlas_studio/main.py` | Add assistant router |

## Testing

1. Verify file explorer lists workspace files correctly
2. Test code editor can read and save files
3. Test terminal runs allowed commands
4. Verify chat responds with tool calls
5. Test approval workflow for file changes
6. Verify context files are included in chat
7. Test search functionality works

## Success Criteria

- [ ] File explorer shows workspace file tree
- [ ] Code editor can read, edit, and save files
- [ ] Terminal runs allowed commands with output
- [ ] Chat responds with tool calls for file operations
- [ ] Approval required for file write operations
- [ ] Context files are included in AI prompts
- [ ] Search files and content works
- [ ] All existing tests pass
