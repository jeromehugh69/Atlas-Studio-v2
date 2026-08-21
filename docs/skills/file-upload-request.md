# File Upload Request Skill

## Purpose
Process uploaded files to extract requirements, analyze content, and create structured development requests.

## When to Use
- User uploads a specification document
- User shares a bug report file
- User provides a design document
- User shares code snippets or diffs
- User uploads configuration files

## Example Prompts

### Basic Usage
```
Review the uploaded file and create a development request based on its contents.
```

### Specific Implementation
```
Read the uploaded file at [file path]. Analyze the code/requirements and create a plan to implement the changes described.
```

### Delegate to Forge
```
Review the uploaded file, then delegate to Forge to implement the changes it describes. Scope the work, create a plan, and propose a change set.
```

### Multiple Files
```
I've attached multiple files. Analyze each one and create a combined implementation plan.
```

## File Types Supported

| Type | Examples | Processing |
|------|----------|------------|
| Text/Markdown | requirements.md, spec.txt | Extract requirements, user stories |
| Code | fix.py, changes.diff | Analyze syntax, extract TODOs |
| Config | config.yaml, .env.example | Validate syntax, extract settings |
| Design | design.md, mockup.txt | Extract UI specifications |
| Bug Report | issue.md, bug.txt | Extract steps, expected vs actual |

## Response Format

The skill will:
1. Analyze the file content
2. Classify the content type
3. Extract key requirements
4. Generate a structured plan
5. Present for approval
6. Delegate to appropriate skill

## Integration with Other Skills

- **development-lifecycle**: For code implementation requests
- **manage-atlas-platform**: For configuration changes
- **atlas-request-intake**: For routing and scoping

## Audit Trail

All file uploads are logged with:
- File name and type
- Content classification
- Requirements extracted
- Plan generated
- Delegation target
- User approval status
