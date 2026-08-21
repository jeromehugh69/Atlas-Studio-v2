# Atlas Studio — Prompt Reference Guide

A quick-reference catalog of prompts you can send to Atlas. Type these in the chat panel to trigger platform features.

---

## Chat & Conversation

| Feature | Prompt |
|---------|--------|
| Start a conversation | `Hello Atlas` or `What can you help me with?` |
| Ask a technical question | `How does the lifecycle pipeline work?` |
| Request an explanation | `Explain the change set approval process` |
| Ask about the platform | `What agents are available?` |
| Get status | `What tasks are currently running?` |

---

## Task Delegation

Atlas can delegate work to specialist agents. Use these prompts to trigger delegation:

| Feature | Prompt |
|---------|--------|
| Delegate to Forge | `Have Forge add a health check endpoint` |
| Delegate to Sage | `Ask Sage to research the best approach for caching` |
| Create a task | `Create a task to refactor the auth module` |
| Request code changes | `Add input validation to the user registration form` |
| Request a new feature | `Build a dark mode toggle for the settings page` |
| Request a bug fix | `Fix the issue where the task list doesn't refresh` |
| Request documentation | `Write API documentation for the /chat endpoint` |

---

## Development Workflow

| Feature | Prompt |
|---------|--------|
| Create a change set | `Create a change set for the new login page` |
| Review a change set | `Show me the pending change sets` |
| Approve implementation | `Approve change set abc123` |
| Run tests | `Run the test suite` |
| Check code quality | `Review the code in src/main.py` |
| Request a refactor | `Refactor the database layer to use async` |

---

## Commit Flow (Slash Commands)

| Feature | Prompt |
|---------|--------|
| Commit a change set | `/commit abc12345` |
| Commit with message | `/commit abc12345 --message "Add login page"` |
| Commit to branch | `/commit abc12345 --branch main --message "Feature: login"` |

---

## Theme & Appearance

| Feature | Prompt |
|---------|--------|
| Switch to light mode | `Switch to light mode` or click the moon icon |
| Switch to dark mode | `Switch to dark mode` or click the moon icon |

---

## Agent Management

| Feature | Prompt |
|---------|--------|
| List all agents | `Show me all available agents` |
| Create a new agent | `Create an agent called Sentinel for security review` |
| Check agent tools | `What tools does Forge have access to?` |
| Agent capabilities | `What can Atlas do vs what Forge can do?` |

---

## Workspace & Files

| Feature | Prompt |
|---------|--------|
| Read a file | `Read the contents of src/config.py` |
| List workspace files | `Show me the project file structure` |
| Search code | `Find all functions that handle authentication` |
| Check git status | `What's the current git status?` |
| View recent commits | `Show me the last 5 commits` |

---

## Lifecycle & Implementation

| Feature | Prompt |
|---------|--------|
| Show lifecycle stages | `What stage is the project in?` |
| View implementation plan | `Show me the current implementation plan` |
| Check project status | `What's the status of the current sprint?` |
| View change history | `Show me recent changes to the codebase` |

---

## Terminal & Console

| Feature | Prompt |
|---------|--------|
| Open terminal view | `Open the terminal` (navigate to Build > Terminal) |
| View change sets in terminal | Type `changesets` in the Terminal console |
| View tasks in terminal | Type `tasks` in the Terminal console |
| View lifecycle in terminal | Type `lifecycle` in the Terminal console |
| Help in terminal | Type `help` in the Terminal console |

---

## Security & Compliance

| Feature | Prompt |
|---------|--------|
| Check security posture | `Show me the current security posture` |
| View audit trail | `What's in the audit log?` |
| Check permissions | `What are Atlas's current permissions?` |
| Request external access | `I need to research React best practices online` |

---

## Analytics & Metrics

| Feature | Prompt |
|---------|--------|
| View platform metrics | `Show me the analytics dashboard` |
| Check task statistics | `How many tasks have been completed?` |
| View model performance | `What model is running and how fast?` |
| System health | `Is the platform healthy?` |

---

## Workflows

| Feature | Prompt |
|---------|--------|
| View workflows | `Show me available workflows` |
| Create a workflow | `Create a workflow for code review with approval gates` |
| Request a workflow | `I need a workflow for deploying to production` |

---

## Voice & Speech

| Feature | Prompt |
|---------|--------|
| Enable voice output | Voice responses play automatically when configured |
| Disable voice | `Stop voice responses` |

---

## Avatar & 3D

| Feature | Prompt |
|---------|--------|
| View avatar | Navigate to Experience > Workers |
| Generate avatar | Upload an image in the Workers page to generate a local 3D avatar |
| Chat with worker | Click "Open conversation" on any worker card |

---

## Settings & Configuration

| Feature | Prompt |
|---------|--------|
| View settings | Navigate to Settings |
| Change user profile | `Update my display name to [name]` |
| Toggle kill switch | `Stop all agents` or `Release the kill switch` |
| Check model config | `What model is currently configured?` |

---

## Tips

- **Be specific**: Instead of "fix the bug", say "fix the issue where the login form submits without validating the email field"
- **Name the agent**: "Have Forge..." or "Ask Sage..." to target a specific agent
- **Use slash commands**: `/commit` for git operations
- **Check DEV TASKS**: Delegate work appears in the DEV TASKS panel on the dashboard
- **Speed metric**: Check the SPEED METRIC card on the dashboard to see response times
