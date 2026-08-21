---
name: file-upload-request
description: |
  Process uploaded files to extract requirements, analyze content, and create structured development requests. Handles specifications, bug reports, design documents, code snippets, and any file-based input to generate actionable plans.
  USE WHEN user says:
  - "Review this file"
  - "Look at this upload"
  - "Analyze this document"
  - "Create a request from this file"
  - "Implement what's in this file"
  - "Fix the issues in this file"
  - "Add the features described here"
  - Any request involving an uploaded file attachment.
---

# Workflow Routing (SYSTEM PROMPT)

Route file-based requests to the correct handler based on file content and user intent:

| File Content Type | User Intent | Handler | Action |
|-------------------|-------------|---------|--------|
| Specification or requirements doc | Implement features | development-lifecycle | Extract requirements, create plan, delegate to Forge |
| Bug report or issue description | Fix the bug | development-lifecycle | Analyze root cause, create fix plan, delegate to Forge |
| Design document or mockup | Implement UI changes | development-lifecycle + interface-ux | Extract design specs, create implementation plan |
| Code snippet or diff | Apply changes | development-lifecycle | Review code, create change set, delegate to Forge |
| Configuration file | Update settings | manage-atlas-platform | Validate config, apply changes |
| Research or analysis | Create request | atlas-request-intake | Summarize findings, route to appropriate skill |

**Delegation Rule:** When delegating to another skill, include the original file content, extracted requirements, and any constraints.

---

# When to Activate This Skill

Activate this skill when:
1. The user uploads any file attachment.
2. The user references an uploaded file in their request.
3. The user asks to analyze, review, or process a file.
4. The user wants to create a development request from file contents.

Do NOT activate this skill when:
- No file is attached or referenced.
- The request is purely conversational.
- A different skill is already handling the request.

---

# File Upload Request Processing

## Source Policy (MANDATORY)

When analyzing uploaded files, ONLY reference trusted sources:
- Official documentation and standards
- Peer-reviewed publications
- Open-source project repositories
- No external URLs or cloud services

## Processing Steps

### 1. File Analysis
- Read and parse the uploaded file content
- Identify file type (text, code, config, document, etc.)
- Extract key information: requirements, issues, changes, specifications
- Note any file-specific context (language, framework, format)

### 2. Content Classification
Classify the file content into one of these categories:

| Category | Indicators | Example |
|----------|------------|---------|
| Requirements Spec | Features, user stories, acceptance criteria | `requirements.md`, `user-stories.txt` |
| Bug Report | Steps to reproduce, expected vs actual | `bug-report.md`, `issue.txt` |
| Design Doc | Mockups, wireframes, UI specifications | `design.md`, `mockup.txt` |
| Code Snippet | Source code, diffs, patches | `fix.py`, `changes.diff` |
| Configuration | Settings, env vars, config files | `config.yaml`, `.env.example` |
| Research | Analysis, findings, recommendations | `research.md`, `analysis.txt` |
| Mixed | Multiple categories | Combined document |

### 3. Requirement Extraction
For each identified requirement or change:
- **What**: Clear description of the change
- **Why**: Purpose or problem being solved
- **Files**: Affected files and components
- **Tests**: Expected test criteria
- **Priority**: Urgency level (high/medium/low)

### 4. Plan Generation
Create a structured development plan:

```
PLAN: [Short descriptive title]

REQUEST: [Original user request with file reference]

FILE_ANALYSIS:
- File type: [type]
- Content category: [category]
- Key findings: [summary]

REQUIREMENTS:
1. [Requirement 1]
   - Acceptance criteria: [criteria]
   - Affected files: [files]
2. [Requirement 2]
   ...

APPROACH:
- [Implementation step 1]
- [Implementation step 2]
...

TEST_CRITERIA:
- [ ] [Test 1]
- [ ] [Test 2]
...

RISKS:
- [Risk 1 and mitigation]
...

ROLLBACK:
- [How to revert if needed]
```

### 5. Response Format

**Internal Audit Reasoning:**
- FILE_RECEIVED: [File name, type, size]
- CONTENT_CATEGORY: [Classification]
- REQUIREMENTS_EXTRACTED: [Count and summary]
- PLAN_GENERATED: [Yes/No]
- DELEGATION_TARGET: [Skill to handle implementation]

**User-Facing Response:**
Present the analysis and plan in natural language:

```
I've analyzed your uploaded file [filename]. Here's what I found:

**File Analysis:**
- Type: [file type]
- Content: [brief summary]

**Requirements Extracted:**
1. [Requirement 1]
2. [Requirement 2]
...

**Proposed Plan:**
[Plan summary with key steps]

**Next Steps:**
Approve the request to begin governed implementation, or let me know if you'd like to adjust the scope.
```

### 6. Approval Trigger
After presenting the analysis, trigger the structured approval control:
- Include the extracted requirements in the approval request
- Reference the original file for audit trail
- Set appropriate scope based on file content complexity

### 7. Delegation
Once approved, delegate to the appropriate skill:
- Include original file content
- Include extracted requirements
- Include generated plan
- Include any constraints or special instructions

## File Type Handlers

### Text Files (.txt, .md, .rst)
- Parse markdown/rst formatting
- Extract headers, lists, code blocks
- Identify requirements from bullet points or numbered lists

### Code Files (.py, .js, .ts, .java, etc.)
- Parse syntax and structure
- Identify functions, classes, methods
- Extract inline comments as requirements
- Detect TODO/FIXME/BUG markers

### Configuration Files (.yaml, .json, .env, etc.)
- Validate syntax
- Extract key-value pairs as settings
- Compare with current configuration if available

### Diff/Patch Files (.diff, .patch)
- Parse added/removed lines
- Identify affected files
- Extract change intent from context

### Design Documents
- Extract specifications from text descriptions
- Note any visual references (mockups, wireframes)
- Identify UI component requirements

## Special Cases

### Empty or Unreadable Files
```
The uploaded file appears to be empty or unreadable. Could you:
1. Verify the file uploaded correctly
2. Provide a brief description of what you'd like to accomplish
3. Try uploading the file again
```

### Multiple Files
```
I see multiple files attached. I'll analyze each one:
1. [filename1] - [brief analysis]
2. [filename2] - [brief analysis]
...

Should I create a combined plan, or handle each file separately?
```

### Very Large Files
```
The uploaded file is quite large. I'll focus on the key sections:
- [Section 1 summary]
- [Section 2 summary]
...

For a complete analysis, you may want to break this into smaller files.
```

## Response Patterns

### Simple Request
```
I've reviewed your file and created a plan to [action]. The changes will affect [files]. Approve the request to begin implementation.
```

### Complex Request
```
Your file contains [number] requirements. I've organized them into a phased plan:
- Phase 1: [quick wins]
- Phase 2: [core changes]
- Phase 3: [cleanup/tests]

This approach minimizes risk and allows for incremental testing. Approve to begin with Phase 1.
```

### Needs Clarification
```
I've analyzed your file, but I need one clarification before creating the plan:
[Specific question about ambiguous requirement]

This will help me scope the work accurately.
```

## References

- [references/governance.md](../atlas-request-intake/references/governance.md) - Lifecycle governance rules
- [references/record-policy.md](../atlas-request-intake/references/record-policy.md) - Record protection policies
