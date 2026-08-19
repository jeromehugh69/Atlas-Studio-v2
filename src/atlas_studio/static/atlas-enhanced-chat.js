/**
 * Atlas Enhanced Chat Panel
 * Handles suggested prompts and dynamic input fields
 */

const PROMPTS = {
  workspace: {
    title: "WORKSPACE EXPLORER",
    description: "Browse and inspect project files",
    example: "Show me the project structure under /src",
    inputs: ["workspacePath", "workspaceFilter"]
  },
  code: {
    title: "CODE EDITOR",
    description: "View and edit source code",
    example: "Read the contents of src/main.py",
    inputs: ["codeFilePath", "codeOperation"]
  },
  terminal: {
    title: "TERMINAL",
    description: "Execute commands in project context",
    example: "Run the test suite with pytest",
    inputs: ["terminalCommand", "terminalWorkdir"]
  },
  plan: {
    title: "PLAN VIEWER",
    description: "View and manage implementation plans",
    example: "Show me all active implementation plans",
    inputs: ["planAction", "planId"]
  },
  request: {
    title: "REQUEST INTAKE",
    description: "Submit a new development request",
    example: "I need to add user authentication to the API",
    inputs: ["requestType", "requestPriority", "requestDescription"]
  },
  lifecycle: {
    title: "LIFECYCLE",
    description: "Track development progress",
    example: "What's the current status of the deployment pipeline?",
    inputs: ["lifecycleStage", "lifecycleAction"]
  },
  security: {
    title: "SECURITY",
    description: "Review security posture and audit",
    example: "Show me the audit log for the last 24 hours",
    inputs: ["securityCheck", "securityTimeRange"]
  },
  chat: {
    title: "AI ASSISTANT",
    description: "Chat with Atlas about code",
    example: "Explain how the authentication flow works",
    inputs: ["chatContext", "chatFocus"]
  }
};

let activeFeature = null;

function initEnhancedChat() {
  const promptCards = document.querySelectorAll('.prompt-card');
  const promptSelectButtons = document.querySelectorAll('.prompt-select');
  const dynamicInputs = document.getElementById('dynamicInputs');
  const textInput = document.getElementById('textInput');
  const composer = document.getElementById('composer');
  
  // Prompt card selection
  promptSelectButtons.forEach(button => {
    button.addEventListener('click', (e) => {
      e.stopPropagation();
      const prompt = e.target.dataset.prompt;
      selectFeature(prompt);
    });
  });
  
  promptCards.forEach(card => {
    card.addEventListener('click', () => {
      const feature = card.dataset.feature;
      selectFeature(feature);
    });
  });
  
  // Send button handler
  composer.addEventListener('submit', (e) => {
    e.preventDefault();
    sendRequest();
  });
  
  // Keyboard shortcut
  document.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      sendRequest();
    }
  });
}

function selectFeature(feature) {
  const promptCards = document.querySelectorAll('.prompt-card');
  const dynamicInputs = document.getElementById('dynamicInputs');
  const textInput = document.getElementById('textInput');
  
  // Update active state
  promptCards.forEach(card => {
    if (card.dataset.feature === feature) {
      card.classList.add('active');
    } else {
      card.classList.remove('active');
    }
  });
  
  activeFeature = feature;
  
  // Hide all input groups
  document.querySelectorAll('.input-group').forEach(group => {
    group.hidden = true;
  });
  
  // Show dynamic inputs container
  dynamicInputs.hidden = false;
  
  // Show the appropriate input group
  const inputGroup = document.getElementById(`${feature}Inputs`);
  if (inputGroup) {
    inputGroup.hidden = false;
  }
  
  // Set example prompt
  const prompt = PROMPTS[feature];
  if (prompt && textInput) {
    textInput.placeholder = prompt.example;
    textInput.focus();
  }
}

function sendRequest() {
  const textInput = document.getElementById('textInput');
  const message = textInput.value.trim();
  
  if (!message) return;
  
  // Collect form data based on active feature
  const formData = {
    message: message,
    feature: activeFeature,
    inputs: {}
  };
  
  if (activeFeature) {
    const inputGroup = document.getElementById(`${activeFeature}Inputs`);
    if (inputGroup) {
      const inputs = inputGroup.querySelectorAll('input, select, textarea');
      inputs.forEach(input => {
        if (input.id && input.value) {
          formData.inputs[input.id] = input.value;
        }
      });
    }
  }
  
  // Dispatch event for main app to handle
  const event = new CustomEvent('atlas-request', {
    detail: formData
  });
  document.dispatchEvent(event);
  
  // Clear inputs
  textInput.value = '';
  clearInputFields();
}

function clearInputFields() {
  document.querySelectorAll('.atlas-input').forEach(input => {
    if (input.tagName === 'SELECT') {
      input.selectedIndex = 0;
    } else if (input.tagName === 'TEXTAREA') {
      input.value = '';
    } else {
      input.value = '';
    }
  });
}

function getInputData() {
  const data = {};
  if (activeFeature) {
    const inputGroup = document.getElementById(`${activeFeature}Inputs`);
    if (inputGroup) {
      const inputs = inputGroup.querySelectorAll('input, select, textarea');
      inputs.forEach(input => {
        if (input.id) {
          data[input.id] = input.value;
        }
      });
    }
  }
  return data;
}

function resetPrompts() {
  document.querySelectorAll('.prompt-card').forEach(card => {
    card.classList.remove('active');
  });
  document.getElementById('dynamicInputs').hidden = true;
  activeFeature = null;
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initEnhancedChat);
} else {
  initEnhancedChat();
}

// Export for module usage
if (typeof module !== 'undefined') {
  module.exports = {
    PROMPTS,
    selectFeature,
    sendRequest,
    clearInputFields,
    getInputData,
    resetPrompts
  };
}
