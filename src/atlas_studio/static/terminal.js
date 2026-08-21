// Atlas Studio Terminal View
// Interactive console for viewing change sets, plans, tasks, and lifecycle stages

(function () {
  'use strict';

  const terminal = {
    output: null,
    input: null,
    commandEl: null,
    history: [],
    historyIndex: -1,
    maxHistory: 100,
    data: {
      changeSets: [],
      plans: [],
      tasks: [],
      lifecycles: [],
    },
  };

  // Initialize terminal when DOM is ready
  function init() {
    terminal.output = document.getElementById('terminalOutput');
    terminal.input = document.getElementById('terminalInput');
    terminal.commandEl = document.getElementById('terminalCommand');

    if (!terminal.output || !terminal.input || !terminal.commandEl) return;

    terminal.input.addEventListener('submit', handleSubmit);
    terminal.commandEl.addEventListener('keydown', handleKeydown);

    // Show welcome message
    writeLine('Atlas Studio Terminal', 'header');
    writeLine('Type "help" for available commands.', 'info');
    writeLine('', 'output');

    // Log completed dev activities
    const devTasks = [
      'Created Terminal view with interactive console',
      'Fixed dropdown menu hover persistence issue',
      'Added WebSocket integration for real-time updates',
      'Implemented change sets, plans, tasks, lifecycle commands',
    ];
    devTasks.forEach((task, i) => {
      setTimeout(() => {
        if (window.logDevActivity) window.logDevActivity(task, 'completed');
      }, i * 100);
    });
  }

  // Handle form submission
  function handleSubmit(e) {
    e.preventDefault();
    const command = terminal.commandEl.value.trim();
    if (!command) return;

    // Add to history
    terminal.history.unshift(command);
    if (terminal.history.length > terminal.maxHistory) {
      terminal.history.pop();
    }
    terminal.historyIndex = -1;

    // Echo command
    writeLine(`atlas@dev:~$ ${command}`, 'command');

    // Parse and execute
    terminal.commandEl.value = '';
    executeCommand(command);
  }

  // Handle keyboard shortcuts
  function handleKeydown(e) {
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (terminal.historyIndex < terminal.history.length - 1) {
        terminal.historyIndex++;
        terminal.commandEl.value = terminal.history[terminal.historyIndex];
      }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (terminal.historyIndex > 0) {
        terminal.historyIndex--;
        terminal.commandEl.value = terminal.history[terminal.historyIndex];
      } else {
        terminal.historyIndex = -1;
        terminal.commandEl.value = '';
      }
    } else if (e.key === 'l' && e.ctrlKey) {
      e.preventDefault();
      clearTerminal();
    }
  }

  // Execute command
  function executeCommand(command) {
    const parts = command.split(/\s+/);
    const cmd = parts[0].toLowerCase();
    const args = parts.slice(1);

    switch (cmd) {
      case 'help':
        showHelp();
        break;
      case 'clear':
      case 'cls':
        clearTerminal();
        break;
      case 'changesets':
      case 'cs':
        listChangeSets();
        break;
      case 'show':
        if (args[0]) {
          showChangeSet(args[0]);
        } else {
          writeLine('Usage: show <change_set_id>', 'error');
        }
        break;
      case 'diff':
        if (args[0]) {
          showDiff(args[0]);
        } else {
          writeLine('Usage: diff <change_set_id>', 'error');
        }
        break;
      case 'plans':
        listPlans();
        break;
      case 'plan':
        if (args[0]) {
          showPlan(args[0]);
        } else {
          writeLine('Usage: plan <plan_id>', 'error');
        }
        break;
      case 'tasks':
        listTasks();
        break;
      case 'task':
        if (args[0]) {
          showTask(args[0]);
        } else {
          writeLine('Usage: task <task_id>', 'error');
        }
        break;
      case 'lifecycle':
      case 'lc':
        listLifecycles();
        break;
      case 'refresh':
        refreshAll();
        break;
      case 'status':
        showStatus();
        break;
      default:
        writeLine(`Command not found: ${cmd}`, 'error');
        writeLine('Type "help" for available commands.', 'info');
    }
  }

  // Write a line to terminal output
  function writeLine(text, className = 'output') {
    const line = document.createElement('div');
    line.className = `terminal-line ${className}`;
    line.textContent = text;
    terminal.output.appendChild(line);
    terminal.output.scrollTop = terminal.output.scrollHeight;
  }

  // Write raw HTML to terminal output
  function writeHtml(html) {
    const wrapper = document.createElement('div');
    wrapper.className = 'terminal-line';
    wrapper.innerHTML = html;
    terminal.output.appendChild(wrapper);
    terminal.output.scrollTop = terminal.output.scrollHeight;
  }

  // Clear terminal
  function clearTerminal() {
    terminal.output.innerHTML = '';
    writeLine('Terminal cleared.', 'info');
  }

  // Show help
  function showHelp() {
    writeLine('ATLAS STUDIO TERMINAL - AVAILABLE COMMANDS', 'header');
    writeLine('─────────────────────────────────────────────────────────────', 'separator');
    writeLine('', 'output');
    writeLine('CHANGE SETS', 'header');
    writeLine('  changesets, cs       List all change sets with status', 'output');
    writeLine('  show <id>            Show change set details + combined diff', 'output');
    writeLine('  diff <id>            Show per-file diffs for a change set', 'output');
    writeLine('', 'output');
    writeLine('PLANS & TASKS', 'header');
    writeLine('  plans                List all plans with status', 'output');
    writeLine('  plan <id>            Show plan details', 'output');
    writeLine('  tasks                List all tasks with status', 'output');
    writeLine('  task <id>            Show task details + output', 'output');
    writeLine('', 'output');
    writeLine('LIFECYCLE', 'header');
    writeLine('  lifecycle, lc        Show all lifecycle stages', 'output');
    writeLine('', 'output');
    writeLine('SYSTEM', 'header');
    writeLine('  status               Show platform status summary', 'output');
    writeLine('  refresh              Refresh all data from server', 'output');
    writeLine('  clear, cls           Clear terminal output', 'output');
    writeLine('  help                 Show this help message', 'output');
    writeLine('', 'output');
    writeLine('SHORTCUTS', 'header');
    writeLine('  ↑/↓                  Navigate command history', 'output');
    writeLine('  Ctrl+L               Clear terminal', 'output');
    writeLine('─────────────────────────────────────────────────────────────', 'separator');
  }

  // Fetch data from API
  async function fetchJson(url) {
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (err) {
      writeLine(`Error fetching ${url}: ${err.message}`, 'error');
      return null;
    }
  }

  // List change sets
  async function listChangeSets() {
    const data = await fetchJson('/api/change-sets');
    if (!data) return;

    terminal.data.changeSets = data;

    if (data.length === 0) {
      writeLine('No change sets found.', 'info');
      return;
    }

    writeLine('CHANGE SETS', 'header');
    writeLine('─────────────────────────────────────────────────────────────', 'separator');
    writeLine(
      'ID          TITLE                                    STATUS         FILES',
      'header'
    );
    writeLine('─────────────────────────────────────────────────────────────', 'separator');

    data.forEach((cs) => {
      const id = cs.id.substring(0, 8);
      const title = truncate(cs.title, 40);
      const status = cs.status.toUpperCase();
      const files = cs.files ? cs.files.length : 0;
      writeLine(
        `${id}    ${title.padEnd(40)} ${status.padEnd(14)} ${files}`,
        'output'
      );
    });

    writeLine('─────────────────────────────────────────────────────────────', 'separator');
    writeLine(`${data.length} change set(s) found.`, 'info');
  }

  // Show change set details
  async function showChangeSet(id) {
    const cs = await findChangeSet(id);
    if (!cs) return;

    writeLine('CHANGE SET DETAILS', 'header');
    writeLine('─────────────────────────────────────────────────────────────', 'separator');
    writeLine(`ID:          ${cs.id}`, 'output');
    writeLine(`TITLE:       ${cs.title}`, 'output');
    writeLine(`STATUS:      ${cs.status.toUpperCase()}`, 'output');
    writeLine(`CREATED:     ${formatDate(cs.created_at)}`, 'output');
    writeLine(`UPDATED:     ${formatDate(cs.updated_at)}`, 'output');
    writeLine(`PLAN:        ${cs.plan_id ? cs.plan_id.substring(0, 8) : 'N/A'}`, 'output');
    writeLine(`WORKSPACE:   ${cs.workspace_id ? cs.workspace_id.substring(0, 8) : 'N/A'}`, 'output');
    writeLine('', 'output');

    if (cs.summary) {
      writeLine('SUMMARY:', 'header');
      writeLine(cs.summary, 'output');
      writeLine('', 'output');
    }

    if (cs.files && cs.files.length > 0) {
      writeLine('FILES:', 'header');
      cs.files.forEach((f) => {
        writeLine(`  ${f.path}`, 'output');
      });
      writeLine('', 'output');
    }

    if (cs.branch) {
      writeLine(`BRANCH:      ${cs.branch}`, 'output');
    }
    if (cs.commit) {
      writeLine(`COMMIT:      ${cs.commit}`, 'output');
    }

    if (cs.combined_diff) {
      writeLine('COMBINED DIFF:', 'header');
      writeLine('─────────────────────────────────────────────────────────────', 'separator');
      writeLine(cs.combined_diff, 'output');
      writeLine('─────────────────────────────────────────────────────────────', 'separator');
    } else {
      writeLine('No diff available.', 'info');
    }

    if (cs.test_result && Object.keys(cs.test_result).length > 0) {
      writeLine('TEST RESULT:', 'header');
      writeLine(`Exit code: ${cs.test_result.exit_code}`, cs.test_result.exit_code === 0 ? 'success' : 'error');
      if (cs.test_result.stdout) {
        writeLine(cs.test_result.stdout, 'output');
      }
      if (cs.test_result.stderr) {
        writeLine(cs.test_result.stderr, 'error');
      }
    }
  }

  // Show diff for a change set
  async function showDiff(id) {
    const cs = await findChangeSet(id);
    if (!cs) return;

    if (!cs.files || cs.files.length === 0) {
      writeLine('No files in this change set.', 'info');
      return;
    }

    writeLine(`DIFF: ${cs.title}`, 'header');
    writeLine('─────────────────────────────────────────────────────────────', 'separator');

    for (const file of cs.files) {
      writeLine('', 'output');
      writeLine(`FILE: ${file.path}`, 'header');
      if (file.diff) {
        writeLine(file.diff, 'output');
      } else {
        writeLine('  No diff available for this file.', 'info');
      }
    }

    writeLine('─────────────────────────────────────────────────────────────', 'separator');
  }

  // Find change set by ID (full or prefix)
  async function findChangeSet(id) {
    // Check cache first
    const cached = terminal.data.changeSets.find(
      (cs) => cs.id === id || cs.id.startsWith(id)
    );
    if (cached) return cached;

    // Fetch from API
    const data = await fetchJson('/api/change-sets');
    if (!data) return null;

    terminal.data.changeSets = data;
    const found = data.find((cs) => cs.id === id || cs.id.startsWith(id));
    if (!found) {
      writeLine(`Change set not found: ${id}`, 'error');
      return null;
    }
    return found;
  }

  // List plans
  async function listPlans() {
    const data = await fetchJson('/api/plans');
    if (!data) return;

    terminal.data.plans = data;

    if (data.length === 0) {
      writeLine('No plans found.', 'info');
      return;
    }

    writeLine('PLANS', 'header');
    writeLine('─────────────────────────────────────────────────────────────', 'separator');
    writeLine(
      'ID          TITLE                                    STATUS         PRIORITY',
      'header'
    );
    writeLine('─────────────────────────────────────────────────────────────', 'separator');

    data.forEach((plan) => {
      const id = plan.id.substring(0, 8);
      const title = truncate(plan.title, 40);
      const status = plan.status.toUpperCase();
      const priority = plan.priority.toUpperCase();
      writeLine(
        `${id}    ${title.padEnd(40)} ${status.padEnd(14)} ${priority}`,
        'output'
      );
    });

    writeLine('─────────────────────────────────────────────────────────────', 'separator');
    writeLine(`${data.length} plan(s) found.`, 'info');
  }

  // Show plan details
  async function showPlan(id) {
    const plan = await findPlan(id);
    if (!plan) return;

    writeLine('PLAN DETAILS', 'header');
    writeLine('─────────────────────────────────────────────────────────────', 'separator');
    writeLine(`ID:          ${plan.id}`, 'output');
    writeLine(`TITLE:       ${plan.title}`, 'output');
    writeLine(`STATUS:      ${plan.status.toUpperCase()}`, 'output');
    writeLine(`PRIORITY:    ${plan.priority.toUpperCase()}`, 'output');
    writeLine(`CREATED:     ${formatDate(plan.created_at)}`, 'output');
    if (plan.decided_at) {
      writeLine(`DECIDED:     ${formatDate(plan.decided_at)}`, 'output');
    }
    writeLine('', 'output');

    if (plan.request) {
      writeLine('REQUEST:', 'header');
      writeLine(plan.request, 'output');
      writeLine('', 'output');
    }

    if (plan.recommendation) {
      writeLine('RECOMMENDATION:', 'header');
      writeLine(plan.recommendation, 'output');
      writeLine('', 'output');
    }

    if (plan.steps && plan.steps.length > 0) {
      writeLine('STEPS:', 'header');
      plan.steps.forEach((step, i) => {
        writeLine(`  ${i + 1}. ${step}`, 'output');
      });
      writeLine('', 'output');
    }

    if (plan.proposed_files && plan.proposed_files.length > 0) {
      writeLine('PROPOSED FILES:', 'header');
      plan.proposed_files.forEach((file) => {
        writeLine(`  ${file}`, 'output');
      });
    }
  }

  // Find plan by ID
  async function findPlan(id) {
    const cached = terminal.data.plans.find(
      (p) => p.id === id || p.id.startsWith(id)
    );
    if (cached) return cached;

    const data = await fetchJson('/api/plans');
    if (!data) return null;

    terminal.data.plans = data;
    const found = data.find((p) => p.id === id || p.id.startsWith(id));
    if (!found) {
      writeLine(`Plan not found: ${id}`, 'error');
      return null;
    }
    return found;
  }

  // List tasks
  async function listTasks() {
    const data = await fetchJson('/api/tasks');
    if (!data) return;

    terminal.data.tasks = data;

    if (data.length === 0) {
      writeLine('No tasks found.', 'info');
      return;
    }

    writeLine('TASKS', 'header');
    writeLine('─────────────────────────────────────────────────────────────', 'separator');
    writeLine(
      'ID          TITLE                                    STATUS      AGENT',
      'header'
    );
    writeLine('─────────────────────────────────────────────────────────────', 'separator');

    data.forEach((task) => {
      const id = task.id.substring(0, 8);
      const title = truncate(task.title, 40);
      const status = task.status.toUpperCase();
      const agent = task.agent_id ? task.agent_id.substring(0, 8) : 'N/A';
      writeLine(
        `${id}    ${title.padEnd(40)} ${status.padEnd(11)} ${agent}`,
        'output'
      );
    });

    writeLine('─────────────────────────────────────────────────────────────', 'separator');
    writeLine(`${data.length} task(s) found.`, 'info');
  }

  // Show task details
  async function showTask(id) {
    const task = await findTask(id);
    if (!task) return;

    writeLine('TASK DETAILS', 'header');
    writeLine('─────────────────────────────────────────────────────────────', 'separator');
    writeLine(`ID:          ${task.id}`, 'output');
    writeLine(`TITLE:       ${task.title}`, 'output');
    writeLine(`STATUS:      ${task.status.toUpperCase()}`, 'output');
    writeLine(`PRIORITY:    ${task.priority.toUpperCase()}`, 'output');
    writeLine(`AGENT:       ${task.agent_id ? task.agent_id.substring(0, 8) : 'N/A'}`, 'output');
    writeLine(`MODEL:       ${task.model || 'N/A'}`, 'output');
    writeLine(`CREATED:     ${formatDate(task.created_at)}`, 'output');
    if (task.completed_at) {
      writeLine(`COMPLETED:   ${formatDate(task.completed_at)}`, 'output');
    }
    if (task.duration_ms) {
      writeLine(`DURATION:    ${formatDuration(task.duration_ms)}`, 'output');
    }
    writeLine('', 'output');

    if (task.prompt) {
      writeLine('PROMPT:', 'header');
      writeLine(task.prompt, 'output');
      writeLine('', 'output');
    }

    if (task.output) {
      writeLine('OUTPUT:', 'header');
      writeLine(task.output, 'output');
      writeLine('', 'output');
    }

    if (task.reasoning) {
      writeLine('REASONING:', 'header');
      writeLine(task.reasoning, 'output');
      writeLine('', 'output');
    }

    if (task.grounding_status && task.grounding_status !== 'not_applicable') {
      writeLine('GROUNDING:', 'header');
      writeLine(`Status: ${task.grounding_status}`, 'output');
      if (task.grounding_issues && task.grounding_issues.length > 0) {
        writeLine('Issues:', 'warning');
        task.grounding_issues.forEach((issue) => {
          writeLine(`  - ${issue}`, 'warning');
        });
      }
    }
  }

  // Find task by ID
  async function findTask(id) {
    const cached = terminal.data.tasks.find(
      (t) => t.id === id || t.id.startsWith(id)
    );
    if (cached) return cached;

    const data = await fetchJson('/api/tasks');
    if (!data) return null;

    terminal.data.tasks = data;
    const found = data.find((t) => t.id === id || t.id.startsWith(id));
    if (!found) {
      writeLine(`Task not found: ${id}`, 'error');
      return null;
    }
    return found;
  }

  // List lifecycles
  async function listLifecycles() {
    const data = await fetchJson('/api/lifecycles');
    if (!data) return;

    terminal.data.lifecycles = data;

    if (data.length === 0) {
      writeLine('No lifecycles found.', 'info');
      return;
    }

    writeLine('LIFECYCLES', 'header');
    writeLine('─────────────────────────────────────────────────────────────', 'separator');
    writeLine(
      'ID          TITLE                                    STAGE         STATUS',
      'header'
    );
    writeLine('─────────────────────────────────────────────────────────────', 'separator');

    data.forEach((lc) => {
      const id = lc.id.substring(0, 8);
      const title = truncate(lc.title, 40);
      const stage = lc.stage.toUpperCase();
      const status = lc.status.toUpperCase();
      writeLine(
        `${id}    ${title.padEnd(40)} ${stage.padEnd(13)} ${status}`,
        'output'
      );
    });

    writeLine('─────────────────────────────────────────────────────────────', 'separator');
    writeLine(`${data.length} lifecycle(s) found.`, 'info');
  }

  // Show platform status
  async function showStatus() {
    writeLine('PLATFORM STATUS', 'header');
    writeLine('─────────────────────────────────────────────────────────────', 'separator');

    const [changeSets, plans, tasks, lifecycles] = await Promise.all([
      fetchJson('/api/change-sets'),
      fetchJson('/api/plans'),
      fetchJson('/api/tasks'),
      fetchJson('/api/lifecycles'),
    ]);

    terminal.data.changeSets = changeSets || [];
    terminal.data.plans = plans || [];
    terminal.data.tasks = tasks || [];
    terminal.data.lifecycles = lifecycles || [];

    const activeTasks = terminal.data.tasks.filter(
      (t) => t.status === 'running' || t.status === 'queued'
    );
    const completedTasks = terminal.data.tasks.filter(
      (t) => t.status === 'completed'
    );
    const failedTasks = terminal.data.tasks.filter(
      (t) => t.status === 'failed'
    );

    const pendingCS = terminal.data.changeSets.filter(
      (cs) => cs.status === 'pending_review'
    );
    const appliedCS = terminal.data.changeSets.filter(
      (cs) => cs.status === 'applied'
    );
    const committedCS = terminal.data.changeSets.filter(
      (cs) => cs.status === 'committed'
    );

    writeLine('TASKS', 'header');
    writeLine(`  Total:       ${terminal.data.tasks.length}`, 'output');
    writeLine(`  Active:      ${activeTasks.length}`, 'output');
    writeLine(`  Completed:   ${completedTasks.length}`, 'success');
    writeLine(`  Failed:      ${failedTasks.length}`, failedTasks.length > 0 ? 'error' : 'output');
    writeLine('', 'output');

    writeLine('CHANGE SETS', 'header');
    writeLine(`  Total:       ${terminal.data.changeSets.length}`, 'output');
    writeLine(`  Pending:     ${pendingCS.length}`, 'output');
    writeLine(`  Applied:     ${appliedCS.length}`, 'output');
    writeLine(`  Committed:   ${committedCS.length}`, 'success');
    writeLine('', 'output');

    writeLine('PLANS', 'header');
    writeLine(`  Total:       ${terminal.data.plans.length}`, 'output');
    const approvedPlans = terminal.data.plans.filter(
      (p) => p.status === 'approved' || p.status === 'in_progress'
    );
    writeLine(`  Active:      ${approvedPlans.length}`, 'output');
    writeLine('', 'output');

    writeLine('LIFECYCLES', 'header');
    writeLine(`  Total:       ${terminal.data.lifecycles.length}`, 'output');
    const activeLC = terminal.data.lifecycles.filter(
      (lc) => lc.status === 'active'
    );
    writeLine(`  Active:      ${activeLC.length}`, 'output');

    writeLine('─────────────────────────────────────────────────────────────', 'separator');
  }

  // Refresh all data
  async function refreshAll() {
    writeLine('Refreshing data...', 'info');
    terminal.data.changeSets = [];
    terminal.data.plans = [];
    terminal.data.tasks = [];
    terminal.data.lifecycles = [];
    writeLine('Data cache cleared. Fetch fresh data with commands.', 'success');
  }

  // Utility functions
  function truncate(str, max) {
    if (!str) return '';
    return str.length > max ? str.substring(0, max - 3) + '...' : str;
  }

  function formatDate(dateStr) {
    if (!dateStr) return 'N/A';
    try {
      const date = new Date(dateStr);
      return date.toLocaleString();
    } catch {
      return dateStr;
    }
  }

  function formatDuration(ms) {
    if (ms < 1000) return `${ms}ms`;
    if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
    return `${Math.floor(ms / 60000)}m ${Math.floor((ms % 60000) / 1000)}s`;
  }

  // WebSocket handler for real-time updates
  function handleWebSocketEvent(event) {
    if (!terminal.output) return;

    const data = event.data ? JSON.parse(event.data) : event;

    switch (data.type) {
      case 'forge.change_set':
        writeLine(`[EVENT] Change set ${data.change_set_id?.substring(0, 8) || ''}: ${data.status || 'update'}`, 'highlight');
        break;
      case 'task.progress':
        writeLine(`[EVENT] Task ${data.task_id?.substring(0, 8) || ''}: ${data.status || 'update'}`, 'highlight');
        break;
      case 'lifecycle.guide':
        writeLine(`[EVENT] Lifecycle: ${data.message || 'update'}`, 'highlight');
        break;
      case 'worker.action':
        writeLine(`[EVENT] Worker ${data.agent || ''}: ${data.action || 'action'} - ${data.outcome || ''}`, 'highlight');
        break;
    }
  }

  // Initialize on DOM ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Hook into existing WebSocket if available
  if (typeof window !== 'undefined') {
    window.AtlasTerminal = {
      handleEvent: handleWebSocketEvent,
      refresh: refreshAll,
    };
  }
})();

// OpenCode agent console embed
(function () {
  const embed = document.getElementById("opencodeEmbed");
  const frame = document.getElementById("opencodeFrame");
  const offline = document.getElementById("opencodeOffline");
  const startButton = document.getElementById("opencodeStart");
  const opencodeTabButton = document.getElementById("opencodeTabButton");
  const legacyTabButton = document.getElementById("legacyTabButton");
  const opencodePane = document.getElementById("opencodePane");
  const legacyPane = document.getElementById("legacyPane");
  const tabStatus = document.getElementById("opencodeTabStatus");
  if (!embed || !frame || !offline) return;

  function selectTab(which) {
    const openCodeActive = which !== "legacy";
    opencodeTabButton?.classList.toggle("active", openCodeActive);
    opencodeTabButton?.setAttribute("aria-selected", String(openCodeActive));
    legacyTabButton?.classList.toggle("active", !openCodeActive);
    legacyTabButton?.setAttribute("aria-selected", String(!openCodeActive));
    opencodePane?.classList.toggle("active", openCodeActive);
    legacyPane?.classList.toggle("active", !openCodeActive);
  }

  opencodeTabButton?.addEventListener("click", () => {
    selectTab("opencode");
    void probe();
  });
  legacyTabButton?.addEventListener("click", () => selectTab("legacy"));

  function showOnline(url) {
    if (!frame.src.endsWith(url)) frame.src = url;
    embed.hidden = false;
    offline.hidden = true;
    selectTab("opencode");
    if (tabStatus) tabStatus.textContent = "OPENCODE ONLINE";
  }

  function showOffline() {
    embed.hidden = true;
    offline.hidden = false;
    if (tabStatus) tabStatus.textContent = "OFFLINE";
  }

  async function probe() {
    try {
      const response = await fetch("/api/opencode/status");
      const data = await response.json();
      if (data.online) showOnline(data.embed_url || data.url);
      else showOffline();
    } catch (_) {
      showOffline();
    }
  }

  startButton?.addEventListener("click", async () => {
    startButton.disabled = true;
    startButton.textContent = "Starting...";
    try {
      const response = await fetch("/api/opencode/launch", { method: "POST" });
      const data = await response.json();
      if (data.embed_url || data.url) showOnline(data.embed_url || data.url);
      else showOffline();
    } catch (_) {
      showOffline();
    } finally {
      startButton.disabled = false;
      startButton.textContent = "Start OpenCode";
    }
  });

  document.getElementById("navOpenCode")?.addEventListener("click", () => {
    selectTab("opencode");
    void probe();
  });

  void probe();
})();
