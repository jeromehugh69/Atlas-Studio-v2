(() => {
  const state = { tools: [], sources: [], plugins: [], agents: [], tasks: [], plans: [], lifecycles: [], approvals: [], changeSets: [], lifecycleGuide: { entries: [], notifications: [], unread: 0 }, selectedTool: null, selectedSource: null, workspaceLoaded: false, openFolders: new Set() };
  const byId = id => document.getElementById(id);
  const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, character => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character]);
  const label = value => String(value ?? "").replaceAll("_", " ");

  function notify(message) {
    const toastNode = byId("toast");
    if (!toastNode) return;
    toastNode.textContent = message;
    toastNode.style.display = "block";
    window.setTimeout(() => { toastNode.style.display = "none"; }, 2800);
  }

  function renderRecordValue(value) {
    if (value === null || value === undefined || value === "") return `<span class="record-empty">Not recorded</span>`;
    if (typeof value === "boolean") return value ? "Yes" : "No";
    if (Array.isArray(value)) {
      if (!value.length) return `<span class="record-empty">None recorded</span>`;
      if (value.every(item => ["string", "number", "boolean"].includes(typeof item))) return `<div class="detail-tags">${value.map(item => `<span>${escapeHtml(item)}</span>`).join("")}</div>`;
      return `<pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
    }
    if (typeof value === "object") return `<pre>${escapeHtml(JSON.stringify(value, null, 2))}</pre>`;
    const text = String(value);
    return text.includes("\n") || text.length > 180 ? `<pre>${escapeHtml(text)}</pre>` : escapeHtml(text);
  }

  function openRecordDetail(kind, record) {
    if (!record) return;
    const titles = { task: "Task", agent: "Agent", plan: "Plan", lifecycle: "Lifecycle", changeSet: "Change set" };
    const title = record.title || record.name || record.id || "Record details";
    byId("recordDetailKind").textContent = `${titles[kind] || label(kind)} record`.toUpperCase();
    byId("recordDetailTitle").textContent = title;
    byId("recordDetailBody").innerHTML = `<dl class="record-detail-grid">${Object.entries(record).map(([key, value]) => `<div><dt>${escapeHtml(label(key))}</dt><dd>${renderRecordValue(value)}</dd></div>`).join("")}</dl>`;
    const action = byId("recordDetailAction");
    const destinations = { task: ["Open Tasks", "tasksView"], agent: ["Edit agent", "agent-edit"], plan: ["Open Projects", "projects"], lifecycle: ["Open lifecycle", "qa"], changeSet: ["Open Implementation", "implementation"] };
    const destination = destinations[kind];
    action.hidden = !destination;
    if (destination) {
      action.textContent = destination[0];
      action.onclick = () => {
        byId("recordDetailDialog").close();
        if (destination[1] === "agent-edit") openAgentEditor(record.id);
        else document.querySelector(`.top-navigation [data-view="${destination[1]}"]`)?.click();
      };
    }
    byId("recordDetailDialog").showModal();
  }

  function openRegisteredRecord(element) {
    const { recordKind: kind, recordId: id } = element.dataset;
    if (kind === "source") return openSource(id);
    if (kind === "tool") return openTool(id);
    const collections = { task: state.tasks, agent: state.agents, plan: state.plans, lifecycle: state.lifecycles, changeSet: state.changeSets, plugin: state.plugins };
    openRecordDetail(kind, (collections[kind] || []).find(item => String(item.id) === id));
  }

  async function json(url, options) {
    const response = await fetch(url, options);
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(body.detail || `Request failed with HTTP ${response.status}`);
    }
    return response.json();
  }

  function requestPasscode(summary, challengeCode = "") {
    const dialog = byId("approvalPasscodeDialog");
    const form = byId("approvalPasscodeForm");
    byId("approvalActionSummary").textContent = summary;
    byId("approvalChallengePanel").hidden = !challengeCode;
    byId("approvalChallengeCode").textContent = challengeCode || "000000";
    byId("approvalPasscode").value = "";
    dialog.showModal();
    window.setTimeout(() => byId("approvalPasscode").focus(), 30);
    return new Promise(resolve => {
      let settled = false;
      const finish = value => {
        if (settled) return;
        settled = true;
        form.removeEventListener("submit", submit);
        byId("cancelPasscode").removeEventListener("click", cancel);
        byId("cancelPasscodeTop").removeEventListener("click", cancel);
        if (dialog.open) dialog.close();
        resolve(value);
      };
      const submit = event => { event.preventDefault(); finish(byId("approvalPasscode").value); };
      const cancel = () => finish(null);
      form.addEventListener("submit", submit);
      byId("cancelPasscode").addEventListener("click", cancel);
      byId("cancelPasscodeTop").addEventListener("click", cancel);
      dialog.addEventListener("cancel", cancel, { once: true });
    });
  }

  function populateSelect(select, values, placeholder) {
    if (!select) return;
    const previous = select.value;
    select.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>` + values.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
    select.value = previous;
  }

  function renderTools() {
    const directory = byId("toolDirectory");
    if (!directory) return;
    const query = byId("toolSearch")?.value.trim().toLowerCase() || "";
    const category = byId("toolCategory")?.value || "";
    const visible = state.tools.filter(tool => {
      const searchable = [tool.name, tool.description, tool.category, ...tool.capabilities].join(" ").toLowerCase();
      return (!query || searchable.includes(query)) && (!category || tool.category === category);
    });
    byId("toolLibraryCount").textContent = `${state.tools.length} REGISTERED`;
    byId("toolAssignedTotal").textContent = state.tools.reduce((total, tool) => total + tool.assigned_count, 0);
    byId("toolRestrictedTotal").textContent = state.tools.filter(tool => tool.restricted).length;
    directory.innerHTML = visible.map(tool => `
      <article class="library-card record-selectable" data-risk="${escapeHtml(tool.risk_level)}" data-record-kind="tool" data-record-id="${escapeHtml(tool.id)}" role="button" tabindex="0">
        <header><span>${escapeHtml(tool.category)}</span><strong>${tool.trust_level === "platform_verified" ? "PLATFORM VERIFIED" : escapeHtml(label(tool.trust_level).toUpperCase())}</strong></header>
        <h3>${escapeHtml(tool.name)}</h3>
        <p>${escapeHtml(tool.description)}</p>
        <div class="library-card-meta"><span>Risk: <b>${escapeHtml(tool.risk_level)}</b></span><span>${tool.assigned_count} agent${tool.assigned_count === 1 ? "" : "s"}</span><span>${tool.authorization_required ? "Authorization required" : "Assignable"}</span></div>
        <footer><button type="button" data-tool-view="${escapeHtml(tool.id)}">View details</button><button class="feature-primary" type="button" data-tool-request="${escapeHtml(tool.id)}">Request / add</button></footer>
      </article>`).join("") || `<div class="feature-empty"><strong>No registered tools match this search</strong><p>Change the search term or category filter.</p></div>`;
    directory.querySelectorAll("[data-tool-view]").forEach(button => button.addEventListener("click", () => openTool(button.dataset.toolView)));
    directory.querySelectorAll("[data-tool-request]").forEach(button => button.addEventListener("click", () => openTool(button.dataset.toolRequest, true)));
  }

  function openTool(toolId, focusRequest = false) {
    const tool = state.tools.find(item => item.id === toolId);
    if (!tool) return;
    state.selectedTool = tool;
    byId("toolDialogTitle").textContent = tool.name;
    const agentOptions = state.agents.map(agent => `<option value="${escapeHtml(agent.id)}">${escapeHtml(agent.name)} - ${escapeHtml(agent.role)}</option>`).join("");
    byId("toolDialogBody").innerHTML = `
      <div class="trust-banner"><strong>PLATFORM VERIFIED</strong><span>${escapeHtml(tool.runtime_status)} capability</span></div>
      <p class="dialog-description">${escapeHtml(tool.description)}</p>
      <dl class="tool-detail-grid">
        <div><dt>Provider</dt><dd>${escapeHtml(tool.provider)}</dd></div><div><dt>Version</dt><dd>${escapeHtml(tool.version)}</dd></div>
        <div><dt>Source</dt><dd>${escapeHtml(tool.source)}</dd></div><div><dt>Risk</dt><dd>${escapeHtml(tool.risk_level)}</dd></div>
        <div><dt>Data access</dt><dd>${escapeHtml(tool.data_access)}</dd></div><div><dt>Audit</dt><dd>${tool.audit_required ? "Required" : "Optional"}</dd></div>
      </dl>
      <section class="detail-section"><strong>Capabilities</strong><div class="detail-tags">${tool.capabilities.map(item => `<span>${escapeHtml(item)}</span>`).join("")}</div></section>
      <section class="detail-section"><strong>Required permissions</strong><div class="detail-tags">${tool.required_permissions.map(item => `<span>${escapeHtml(item)}</span>`).join("")}</div></section>
      <section class="detail-section"><strong>Environments</strong><div class="detail-tags">${tool.environments.map(item => `<span>${escapeHtml(item)}</span>`).join("")}</div></section>
      <section class="detail-section"><strong>Currently assigned agents</strong><p>${tool.allowed_agents.length ? tool.allowed_agents.map(escapeHtml).join(" · ") : "No agent assignment"}</p></section>
      <div class="capability-request-controls"><label>Agent<select id="toolRequestAgent"><option value="">Workspace capability review</option>${agentOptions}</select></label><label>Environment<select id="toolRequestEnvironment"><option value="workspace">Workspace</option><option value="sandbox">Sandbox</option><option value="production">Production</option></select></label></div>
      <p class="feature-notice">A request records security and compatibility review. It never silently grants the selected capability.</p>`;
    byId("requestToolButton").dataset.toolId = tool.id;
    byId("toolDialog").showModal();
    if (focusRequest) window.setTimeout(() => byId("toolRequestAgent")?.focus(), 40);
  }

  async function requestTool() {
    const toolId = byId("requestToolButton").dataset.toolId;
    if (!toolId) return;
    try {
      const result = await json(`/api/tool-library/${encodeURIComponent(toolId)}/request`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          agent_id: byId("toolRequestAgent")?.value || null,
          environment: byId("toolRequestEnvironment")?.value || "workspace",
          reason: "Developer requested capability review from the Tool Library",
        }),
      });
      byId("toolDialog").close();
      notify(label(result.status));
    } catch (error) {
      notify(error.message);
    }
  }

  function renderSources() {
    const query = byId("knowledgeSearch")?.value.trim().toLowerCase() || "";
    const category = byId("knowledgeCategory")?.value || "";
    const visible = state.sources.filter(source => {
      const searchable = [source.name, source.authority, source.source_type, ...source.relevance].join(" ").toLowerCase();
      return (!query || searchable.includes(query)) && (!category || source.category === category);
    });
    const results = byId("knowledgeResults");
    if (results) {
      results.innerHTML = visible.map(source => `
        <article class="knowledge-card record-selectable" data-record-kind="source" data-record-id="${escapeHtml(source.id)}" role="button" tabindex="0">
          <header><span>LEVEL ${source.hierarchy_level}</span><strong>${escapeHtml(label(source.trust_level).toUpperCase())}</strong></header>
          <h3>${escapeHtml(source.name)}</h3><p>${escapeHtml(source.authority)} · ${escapeHtml(source.source_type)}</p>
          <dl><div><dt>Version</dt><dd>${escapeHtml(source.version)}</dd></div><div><dt>Status</dt><dd>${escapeHtml(source.status)}</dd></div><div><dt>Jurisdiction</dt><dd>${escapeHtml(source.jurisdiction)}</dd></div></dl>
          <div class="detail-tags">${source.relevance.map(item => `<span>${escapeHtml(item)}</span>`).join("")}</div>
          <button type="button" data-source-view="${escapeHtml(source.id)}">View details${source.content_url ? " and approved content" : ""}</button>
        </article>`).join("") || `<div class="feature-empty"><strong>No approved source matches this search</strong><p>Request a source addition if the required authority is not registered.</p></div>`;
      results.querySelectorAll("[data-source-view]").forEach(button => button.addEventListener("click", () => openSource(button.dataset.sourceView)));
    }
    const healthy = state.sources.filter(source => source.verification_status === "available").length;
    if (byId("sourceHealthSummary")) byId("sourceHealthSummary").textContent = `${healthy}/${state.sources.length} AVAILABLE`;
    if (byId("sourceHealth")) byId("sourceHealth").innerHTML = state.sources.map(source => `<div class="source-health-row ${source.verification_status === "available" ? "ok" : "warn"}"><i></i><span><strong>${escapeHtml(source.name)}</strong><small>${escapeHtml(source.authority)}</small></span><b>${escapeHtml(label(source.verification_status))}</b></div>`).join("");
  }

  async function openSource(sourceId) {
    const source = state.sources.find(item => item.id === sourceId);
    if (!source) return;
    state.selectedSource = source;
    byId("sourceDialogTitle").textContent = source.name;
    const body = byId("sourceDialogBody");
    body.innerHTML = `<div class="source-metadata"><dl class="tool-detail-grid"><div><dt>Authority</dt><dd>${escapeHtml(source.authority)}</dd></div><div><dt>Type</dt><dd>${escapeHtml(source.source_type)}</dd></div><div><dt>Version</dt><dd>${escapeHtml(source.version)}</dd></div><div><dt>Status</dt><dd>${escapeHtml(source.status)}</dd></div><div><dt>Jurisdiction</dt><dd>${escapeHtml(source.jurisdiction)}</dd></div><div><dt>Verification</dt><dd>${escapeHtml(label(source.verification_status))}</dd></div></dl></div><pre class="source-preview">Loading approved local source...</pre>`;
    byId("sourceDialog").showModal();
    if (!source.content_url) {
      body.querySelector(".source-preview").textContent = "No approved content file is attached to this source record.";
      return;
    }
    try {
      const response = await fetch(source.content_url);
      if (!response.ok) throw new Error(`Source preview failed with HTTP ${response.status}`);
      body.querySelector(".source-preview").textContent = await response.text();
    } catch (error) {
      body.querySelector(".source-preview").textContent = error.message;
    }
  }

  function requestSelectedSourceChange() {
    const source = state.selectedSource;
    if (!source) return;
    const form = byId("sourceRequestForm");
    form.elements.name.value = source.name;
    form.elements.authority.value = source.authority;
    form.elements.source_type.value = [...form.elements.source_type.options].some(option => option.value === source.source_type) ? source.source_type : "Internal documentation";
    form.elements.location.value = source.location || "";
    form.elements.jurisdiction.value = source.jurisdiction || "";
    form.elements.version.value = source.version || "";
    byId("sourceDialog").close();
    byId("sourceRequestTitle").textContent = `Request change: ${source.name}`;
    byId("sourceRequestDialog").showModal();
  }

  function renderProjects() {
    const target = byId("projectDirectory");
    if (!target) return;
    target.innerHTML = state.plans.map(plan => {
      const lifecycle = state.lifecycles.find(item => item.plan_id === plan.id);
      return `<article class="feature-panel record-selectable" data-record-kind="plan" data-record-id="${escapeHtml(plan.id)}" role="button" tabindex="0"><header><div><small>${escapeHtml(plan.priority)} priority</small><h3>${escapeHtml(plan.title)}</h3></div><span>${escapeHtml(label(lifecycle?.stage || plan.status).toUpperCase())}</span></header><p>${escapeHtml(plan.request)}</p><dl class="feature-definition"><div><dt>Plan</dt><dd>${escapeHtml(label(plan.status))}</dd></div><div><dt>Workspace</dt><dd>${plan.workspace_id ? "Isolated and ready" : "Not created"}</dd></div><div><dt>Lifecycle</dt><dd>${escapeHtml(label(lifecycle?.stage || "not started"))}</dd></div></dl><footer><button type="button" data-project-open="${plan.workspace_id ? "workspace" : "plans"}">${plan.workspace_id ? "Open workspace" : "Review plan"}</button>${lifecycle ? `<button type="button" data-project-open="qa">Lifecycle details</button>` : ""}</footer></article>`;
    }).join("") || `<div class="feature-empty"><strong>No projects yet</strong><p>Request and approve a plan to create the first governed project workspace.</p><button class="feature-primary" type="button" data-project-open="plans">Request project plan</button></div>`;
    target.querySelectorAll("[data-project-open]").forEach(button => button.addEventListener("click", () => document.querySelector(`.top-navigation [data-view="${button.dataset.projectOpen}"]`)?.click()));
  }

  async function refreshPlugins() {
    const target = byId("pluginDirectory");
    if (!target) return;
    try {
      state.plugins = await json("/api/plugins");
      byId("pluginCount").textContent = `${state.plugins.length} ENABLED`;
      target.innerHTML = state.plugins.map(plugin => `<article class="library-card record-selectable" data-record-kind="plugin" data-record-id="${escapeHtml(plugin.id)}" role="button" tabindex="0"><header><span>${escapeHtml(label(plugin.kind))}</span><strong>${escapeHtml(plugin.status)}</strong></header><h3>${escapeHtml(plugin.name)}</h3><p>${escapeHtml(plugin.description)}</p><div class="library-card-meta"><span>Local only</span><span>${escapeHtml(plugin.edit_policy)}</span></div><footer><button type="button" data-plugin-open="${escapeHtml(plugin.manifest_path)}">Open skill file</button></footer></article>`).join("") || `<div class="feature-empty"><strong>No local plugins found</strong><p>Bundled Atlas skills will appear here after the application image is rebuilt.</p></div>`;
      target.querySelectorAll("[data-plugin-open]").forEach(button => button.addEventListener("click", () => openWorkspaceFile(button.dataset.pluginOpen, true)));
    } catch (error) { target.innerHTML = `<div class="feature-empty"><strong>Plugin registry unavailable</strong><p>${escapeHtml(error.message)}</p></div>`; }
  }

  async function refreshLibrary() {
    const target = byId("libraryDirectory");
    if (!target) return;
    try {
      const [tools, plugins, sources, plans] = await Promise.all([json("/api/tool-library"), json("/api/plugins"), json("/api/sources"), json("/api/plans")]);
      const collections = [
        ["Registered tools", tools.length, "Permission-aware runtime capabilities", "toolsView"],
        ["Plugins & skills", plugins.length, "Bundled local extension manifests", "plugins"],
        ["Knowledge", sources.length, "Approved sources with provenance", "knowledge"],
        ["Projects", plans.length, "Plans, workspaces, and lifecycle evidence", "projects"],
      ];
      byId("librarySummary").textContent = `${collections.reduce((total, item) => total + item[1], 0)} ITEMS`;
      target.innerHTML = collections.map(([name, count, description, view]) => `<article class="feature-panel"><header><div><small>LIBRARY COLLECTION</small><h3>${escapeHtml(name)}</h3></div><span>${count}</span></header><p>${escapeHtml(description)}</p><button type="button" data-library-view="${view}">Open ${escapeHtml(name)}</button></article>`).join("");
      target.querySelectorAll("[data-library-view]").forEach(button => button.addEventListener("click", () => document.querySelector(`.top-navigation [data-view="${button.dataset.libraryView}"]`)?.click()));
    } catch (error) {
      target.innerHTML = `<div class="feature-empty"><strong>Library unavailable</strong><p>${escapeHtml(error.message)}</p></div>`;
    }
  }

  async function openAgentEditor(agentId) {
    const agent = state.agents.find(item => String(item.id) === String(agentId));
    if (!agent) return;
    if (!state.plugins.length) state.plugins = await json("/api/plugins");
    byId("editAgentId").value = agent.id;
    byId("editAgentName").value = agent.name;
    byId("editAgentRole").value = agent.role;
    byId("editAgentDescription").value = agent.description;
    byId("editAgentReadOnly").checked = agent.read_only;
    byId("editAgentAuthorization").checked = agent.requires_user_authorization;
    byId("editAgentSkills").innerHTML = state.plugins.map(skill => { const id = skill.id.replaceAll("-", "_"); const required = id === "development_lifecycle" || (agent.name === "Atlas" && id === "atlas_request_intake"); return `<label><input type="checkbox" value="${escapeHtml(id)}" ${(agent.skills || []).includes(id) || required ? "checked" : ""} ${required ? "disabled" : ""}> ${escapeHtml(skill.name)}</label>`; }).join("");
    byId("editAgentTools").innerHTML = state.tools.map(tool => `<label><input type="checkbox" value="${escapeHtml(tool.id)}" ${agent.tools.includes(tool.id) ? "checked" : ""}> ${escapeHtml(label(tool.name || tool.id))}</label>`).join("");
    byId("agentEditTitle").textContent = `Edit ${agent.name}`;
    byId("agentEditDialog").showModal();
  }

  async function saveAgentEdit(event) {
    event.preventDefault();
    const id = byId("editAgentId").value;
    const current = state.agents.find(agent => String(agent.id) === id);
    if (!current) return;
    const proposed = { name: byId("editAgentName").value.trim(), role: byId("editAgentRole").value.trim(), description: byId("editAgentDescription").value.trim(), skills: [...byId("editAgentSkills").querySelectorAll("input:checked")].map(input => input.value), tools: [...byId("editAgentTools").querySelectorAll("input:checked")].map(input => input.value), read_only: byId("editAgentReadOnly").checked, requires_user_authorization: byId("editAgentAuthorization").checked };
    const changes = Object.fromEntries(Object.entries(proposed).filter(([key, value]) => JSON.stringify(value) !== JSON.stringify(current[key])));
    if (!Object.keys(changes).length) { byId("agentEditDialog").close(); return notify("No agent changes to save."); }
    try {
      const approvalId = await authorizeProtectedAction({ action: "agent_permission", purpose: `Update ${current.name}`, target: id, actor: "local-user", payload: changes });
      if (!approvalId) return;
      const updated = await json(`/api/agents/${id}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...changes, approval_id: approvalId }) });
      state.agents = state.agents.map(agent => agent.id === updated.id ? updated : agent);
      byId("agentEditDialog").close();
      await window.refreshAtlasAgents?.();
      notify(`${updated.name} updated.`);
    } catch (error) { notify(error.message); }
  }

  function renderTasks(tasks = state.tasks) {
    state.tasks = tasks || [];
    const board = byId("developerTaskBoard");
    if (!board) return;
    byId("featureTaskCount").textContent = `${state.tasks.length} TASK${state.tasks.length === 1 ? "" : "S"}`;
    const columns = [
      ["queued", "Queued"], ["running", "In progress"], ["completed", "Completed"], ["failed", "Needs review"],
    ];
    board.innerHTML = columns.map(([status, title]) => {
      const items = state.tasks.filter(task => task.status === status || (status === "failed" && task.status === "cancelled"));
      return `<section class="lifecycle-column"><header><strong>${title}</strong><span>${items.length}</span></header><div>${items.map(task => `<article class="record-selectable" data-record-kind="task" data-record-id="${escapeHtml(task.id)}" role="button" tabindex="0"><strong>${escapeHtml(task.title)}</strong><small>${escapeHtml(task.status)} · ${escapeHtml(task.model)} · grounding: ${escapeHtml(task.grounding_status || "pending")}</small><p>${escapeHtml(task.output || "No result recorded yet.")}</p><span class="record-open-hint">Open task details</span></article>`).join("") || `<p class="column-empty">No ${title.toLowerCase()} tasks.</p>`}</div></section>`;
    }).join("");
    const implementation = byId("implementationActivity");
    if (implementation) implementation.innerHTML = state.tasks.slice(0, 8).map(task => `<article class="record-selectable" data-record-kind="task" data-record-id="${escapeHtml(task.id)}" role="button" tabindex="0"><span class="task-status ${escapeHtml(task.status)}">${escapeHtml(task.status)}</span><div><strong>${escapeHtml(task.title)}</strong><small>${escapeHtml(task.id)} · ${task.duration_ms == null ? "duration pending" : `${task.duration_ms} ms`}</small></div><p>${task.completed_at ? "Execution record available; source and QA evidence must be attached separately." : "Awaiting a completed execution record."}</p></article>`).join("") || `<div class="feature-empty"><strong>No implementation records</strong><p>Approved work will be traceable here from task through sandbox and production authorization.</p></div>`;
  }

  async function refreshLifecycleGovernance() {
    const acceptance = byId("lifecycleAcceptance");
    if (!acceptance) return;
    try {
      const data = await json("/api/lifecycle/governance");
      const testCase = data.acceptance_test;
      byId("lifecycleCaseState").textContent = testCase.id.toUpperCase();
      acceptance.innerHTML = testCase.steps.map((stage, index) => `<article><i>${index + 1}</i><div><strong>${escapeHtml(stage.stage)}</strong><small>${escapeHtml(stage.owners.join(", "))} · ${escapeHtml(stage.action)}</small><p>Evidence: ${escapeHtml(stage.evidence.join(", "))}</p></div></article>`).join("");
      byId("hallucinationControls").innerHTML = data.hallucination_controls.map(item => `<article><div><strong>${escapeHtml(item.control)}</strong><small>${escapeHtml(item.enforcement)}</small><p>${escapeHtml(item.effect)}</p></div></article>`).join("");
      const missing = data.audit_coverage.reduce((count, area) => count + area.missing_events.length, 0);
      byId("auditCoverageState").textContent = missing ? `${missing} NOT YET OBSERVED` : "ALL OBSERVED";
      byId("auditCoverage").innerHTML = data.audit_coverage.map(area => `<article><strong>${escapeHtml(area.area)}</strong><small>${area.observed_events.length}/${area.events.length} event types observed</small><p>${area.events.map(event => `<span class="${area.observed_events.includes(event) ? "observed" : "pending"}">${escapeHtml(event)}</span>`).join("")}</p></article>`).join("");
      byId("auditCoverageNote").textContent = data.logging.note;
    } catch (error) {
      acceptance.innerHTML = `<p class="feature-notice">${escapeHtml(error.message)}</p>`;
    }
  }

  function renderPlans() {
    const target = byId("planWorkspace");
    if (!target) return;
    const capable = state.agents.filter(agent => !agent.read_only && agent.tools.includes("files_write"));
    byId("planAgent").innerHTML = capable.map(agent => `<option value="${agent.id}" ${agent.name === "Forge" ? "selected" : ""}>${escapeHtml(agent.name)} - ${escapeHtml(agent.role)}</option>`).join("");
    byId("taskAgent").innerHTML = state.agents.filter(agent => agent.read_only).map(agent => `<option value="${agent.id}">${escapeHtml(agent.name)} - ${escapeHtml(agent.role)}</option>`).join("");
    const readyPlans = state.plans.filter(plan => plan.workspace_id && plan.status === "in_progress");
    byId("workerWorkspace").innerHTML = readyPlans.map(plan => `<option value="${plan.workspace_id}">${escapeHtml(plan.title)}</option>`).join("");
    target.innerHTML = state.plans.map(plan => `<article class="record-selectable" data-record-kind="plan" data-record-id="${escapeHtml(plan.id)}" role="button" tabindex="0"><header><div><small>${escapeHtml(plan.priority.toUpperCase())} · ${escapeHtml(plan.status.replaceAll("_", " ").toUpperCase())}</small><h3>${escapeHtml(plan.title)}</h3></div><span>${plan.workspace_id ? "ISOLATED WORKSPACE" : "NOT STARTED"}</span></header><p>${escapeHtml(plan.request)}</p><div class="detail-tags">${(plan.steps || []).map(step => `<span>${escapeHtml(step)}</span>`).join("")}</div><footer><small>${plan.workspace_id ? `Workspace ${escapeHtml(plan.workspace_id)}` : "Awaiting your decision"}</small>${plan.status === "pending_approval" ? `<div><button type="button" data-plan-reject="${plan.id}">Reject</button><button class="feature-primary" type="button" data-plan-approve="${plan.id}">Approve & create workspace</button></div>` : `<span class="record-open-hint">Open plan details</span>`}</footer></article>`).join("") || `<div class="feature-empty"><strong>No plans yet</strong><p>Request a plan before assigning implementation work.</p></div>`;
    target.querySelectorAll("[data-plan-approve]").forEach(button => button.addEventListener("click", () => decidePlan(button.dataset.planApprove, "approved")));
    target.querySelectorAll("[data-plan-reject]").forEach(button => button.addEventListener("click", () => decidePlan(button.dataset.planReject, "rejected")));
    target.querySelectorAll('[data-record-kind="plan"]').forEach(card => {
      const plan = state.plans.find(item => item.id === card.dataset.recordId);
      if (!plan) return;
      const recommendation = document.createElement("section");
      recommendation.className = "forge-recommendation-brief";
      recommendation.innerHTML = `<header><strong>Forge recommendation</strong><span>${plan.status === "pending_approval" ? "USER DECISION REQUIRED" : escapeHtml(label(plan.status).toUpperCase())}</span></header><p>${escapeHtml(plan.recommendation)}</p><dl><div><dt>Impact</dt><dd>${escapeHtml(plan.impact)}</dd></div><div><dt>Test plan</dt><dd>${escapeHtml(plan.test_plan)}</dd></div><div><dt>Rollback</dt><dd>${escapeHtml(plan.rollback_plan)}</dd></div><div><dt>Likely files</dt><dd>${plan.proposed_files?.length ? plan.proposed_files.map(escapeHtml).join(", ") : "Unconfirmed until evidence-based inspection"}</dd></div></dl>`;
      card.insertBefore(recommendation, card.querySelector("footer"));
      const actions = card.querySelector("footer div") || card.querySelector("footer");
      if (plan.status === "pending_approval") {
        const edit = document.createElement("button");
        edit.type = "button"; edit.dataset.planEditRecommendation = plan.id; edit.textContent = "Edit recommendation";
        edit.addEventListener("click", event => { event.stopPropagation(); openForgeRecommendation(plan.id); });
        actions.prepend(edit);
      }
      const remove = document.createElement("button");
      remove.type = "button"; remove.className = "feature-danger"; remove.textContent = "Delete request";
      remove.addEventListener("click", event => { event.stopPropagation(); deletePlanRequest(plan.id); });
      actions.append(remove);
    });
  }

  function openForgeRecommendation(planId) {
    const plan = state.plans.find(item => item.id === planId);
    if (!plan) return notify("The recommendation is unavailable.");
    byId("forgeRecommendationPlanId").value = plan.id;
    byId("forgeRecommendationTitle").textContent = `Review ${plan.title}`;
    byId("forgeRecommendationText").value = plan.recommendation || "";
    byId("forgeRecommendationImpact").value = plan.impact || "";
    byId("forgeRecommendationTests").value = plan.test_plan || "";
    byId("forgeRecommendationRollback").value = plan.rollback_plan || "";
    byId("forgeRecommendationFiles").value = (plan.proposed_files || []).join("\n");
    byId("forgeRecommendationDialog").showModal();
  }

  async function saveForgeRecommendation(event) {
    event.preventDefault();
    const planId = byId("forgeRecommendationPlanId").value;
    const payload = {
      recommendation: byId("forgeRecommendationText").value.trim(), impact: byId("forgeRecommendationImpact").value.trim(),
      test_plan: byId("forgeRecommendationTests").value.trim(), rollback_plan: byId("forgeRecommendationRollback").value.trim(),
      proposed_files: byId("forgeRecommendationFiles").value.split("\n").map(value => value.trim()).filter(Boolean),
      reason: byId("forgeRecommendationReason").value.trim(),
    };
    try {
      await json(`/api/plans/${planId}/recommendation`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      byId("forgeRecommendationDialog").close();
      await Promise.all([refreshPlans(), refreshLifecycleGuide()]);
      notify("Forge recommendation revised. No files were changed.");
    } catch (error) { notify(error.message); }
  }

  async function deletePlanRequest(planId) {
    const plan = state.plans.find(item => item.id === planId);
    if (!plan) return;
    const payload = { operation: "soft_delete", plan_id: plan.id, title: plan.title };
    try {
      const approvalId = await authorizeProtectedAction({ action: "plan_delete", purpose: `Delete change request: ${plan.title}`, target: plan.id, actor: "local-user", payload });
      if (!approvalId) return;
      const response = await fetch(`/api/plans/${plan.id}?approval_id=${encodeURIComponent(approvalId)}`, { method: "DELETE" });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `Request failed with HTTP ${response.status}`);
      await Promise.all([refreshPlans(), refreshLifecycleGuide(), refreshLifecycles()]);
      notify("Request removed from active work. Its audit history was retained.");
    } catch (error) { notify(error.message); }
  }

  async function refreshPlans() {
    try { state.plans = await json("/api/plans"); renderPlans(); }
    catch (error) { if (byId("planWorkspace")) byId("planWorkspace").textContent = error.message; }
  }

  function openLifecycleDestination(view) {
    const button = document.querySelector(`.top-navigation [data-view="${view}"], .app-sidebar [data-view="${view}"]`);
    button?.click();
  }

  function renderLifecycleNotifications() {
    const data = state.lifecycleGuide;
    const count = byId("lifecycleNotificationCount");
    if (count) count.textContent = data.unread || 0;
    const renderItems = compact => (data.notifications || []).map(item => `<article class="lifecycle-notification" data-priority="${escapeHtml(item.priority)}" data-state="${escapeHtml(item.status)}"><i></i><div><small>${escapeHtml(item.priority.toUpperCase())} · ${escapeHtml(item.project)}</small><strong>${escapeHtml(item.title)}</strong>${compact ? "" : `<p>${escapeHtml(item.message)}</p>`}<footer><button type="button" data-lifecycle-go="${escapeHtml(item.destination)}">Go to task</button>${item.status === "unread" ? `<button type="button" data-notification-state="acknowledged" data-notification-id="${escapeHtml(item.notification_id)}">Acknowledge</button>` : ""}<button type="button" data-notification-state="dismissed" data-notification-id="${escapeHtml(item.notification_id)}">Dismiss</button></footer></div></article>`).join("") || `<div class="feature-empty compact"><strong>No active next steps</strong><p>Create a change request to begin a governed lifecycle.</p></div>`;
    if (byId("lifecycleNotificationMenu")) byId("lifecycleNotificationMenu").innerHTML = renderItems(true);
    if (byId("lifecycleGuideNotifications")) byId("lifecycleGuideNotifications").innerHTML = renderItems(false);
    document.querySelectorAll("[data-lifecycle-go]").forEach(button => button.addEventListener("click", () => openLifecycleDestination(button.dataset.lifecycleGo)));
    document.querySelectorAll("[data-notification-state]").forEach(button => button.addEventListener("click", () => setLifecycleNotification(button.dataset.notificationId, button.dataset.notificationState)));
  }

  function renderLifecycleGuide() {
    renderLifecycleNotifications();
    const entries = state.lifecycleGuide.entries || [];
    if (byId("lifecycleGuideSummary")) byId("lifecycleGuideSummary").textContent = `${entries.length} ACTIVE CHANGE${entries.length === 1 ? "" : "S"}`;
    const board = byId("lifecycleGuideBoard");
    if (!board) return;
    board.innerHTML = entries.map(entry => {
      const plan = entry.plan, next = entry.next_action;
      const reviews = (entry.tasks || []).filter(task => task.title.startsWith("Lifecycle review —"));
      return `<article class="lifecycle-guide-project" data-plan-id="${escapeHtml(plan.id)}"><header><div><small>${escapeHtml(plan.priority.toUpperCase())} · ${escapeHtml(label(plan.status).toUpperCase())}</small><h3>${escapeHtml(plan.title)}</h3><p>${escapeHtml(plan.request)}</p></div><div class="lifecycle-progress"><strong>${entry.progress}%</strong><span><i style="width:${entry.progress}%"></i></span><small>LIFECYCLE COMPLETE</small><button class="feature-danger lifecycle-delete-top" type="button" data-guide-delete="${escapeHtml(plan.id)}">Delete implementation</button></div></header><section class="lifecycle-step-track">${entry.stages.map((stage, index) => `<button type="button" data-lifecycle-go="${escapeHtml(stage.destination)}" data-state="${escapeHtml(stage.status)}"><i>${index + 1}</i><span><strong>${escapeHtml(stage.label)}</strong><small>${escapeHtml(stage.owner)} · ${escapeHtml(label(stage.status))}</small></span></button>`).join("")}</section><div class="lifecycle-guide-detail"><section class="forge-recommendation-brief"><header><strong>Forge recommendation</strong><span>${plan.status === "pending_approval" ? "EDITABLE" : "RECORDED"}</span></header><p>${escapeHtml(plan.recommendation)}</p><dl><div><dt>Impact</dt><dd>${escapeHtml(plan.impact)}</dd></div><div><dt>Test plan</dt><dd>${escapeHtml(plan.test_plan)}</dd></div><div><dt>Rollback</dt><dd>${escapeHtml(plan.rollback_plan)}</dd></div><div><dt>Likely files</dt><dd>${plan.proposed_files?.length ? plan.proposed_files.map(escapeHtml).join(", ") : "Unconfirmed until evidence-based inspection"}</dd></div></dl></section><section class="lifecycle-review-team"><header><strong>Relevant agent reviews</strong><button type="button" data-retry-reviews="${escapeHtml(plan.id)}">Retry failed reviews</button></header><div>${reviews.map(task => `<article data-state="${escapeHtml(task.status)}"><span>${escapeHtml(task.title.replace("Lifecycle review — ", ""))}</span><small>${escapeHtml(label(task.status))}</small>${task.output ? `<p>${escapeHtml(task.output.slice(0, 500))}</p>` : ""}</article>`).join("") || `<p>No review tasks have been recorded.</p>`}</div><form data-add-reviewer="${escapeHtml(plan.id)}"><select name="agent_id" aria-label="Additional review agent">${state.agents.map(agent => `<option value="${escapeHtml(agent.id)}">${escapeHtml(agent.name)} · ${escapeHtml(agent.role)}</option>`).join("")}</select><input name="focus" minlength="5" maxlength="2000" value="Provide an additional role-specific review" aria-label="Review focus" required><button type="submit">Add reviewer</button></form></section></div><footer class="lifecycle-user-action"><div><small>NEXT USER STEP · ${escapeHtml(next.priority.toUpperCase())}</small><strong>${escapeHtml(next.title)}</strong><p>${escapeHtml(next.message)}</p></div><div><button type="button" data-lifecycle-go="${escapeHtml(next.destination)}">Go to task</button>${plan.status === "pending_approval" ? `<button type="button" data-guide-edit="${escapeHtml(plan.id)}">Edit recommendation</button><button class="feature-primary" type="button" data-guide-approve="${escapeHtml(plan.id)}">Approve</button>` : ""}<button class="feature-danger" type="button" data-guide-delete="${escapeHtml(plan.id)}">Delete request</button></div></footer></article>`;
    }).join("") || `<div class="feature-empty"><strong>No lifecycle is active</strong><p>Open Plans and request a change. The guide will then identify every review, approval, implementation, QA, and release step.</p><button type="button" data-lifecycle-go="plans">Request a change plan</button></div>`;
    board.querySelectorAll("[data-lifecycle-go]").forEach(button => button.addEventListener("click", () => openLifecycleDestination(button.dataset.lifecycleGo)));
    board.querySelectorAll("[data-guide-edit]").forEach(button => button.addEventListener("click", () => openForgeRecommendation(button.dataset.guideEdit)));
    board.querySelectorAll("[data-guide-approve]").forEach(button => button.addEventListener("click", () => decidePlan(button.dataset.guideApprove, "approved")));
    board.querySelectorAll("[data-guide-delete]").forEach(button => button.addEventListener("click", () => deletePlanRequest(button.dataset.guideDelete)));
    board.querySelectorAll("[data-retry-reviews]").forEach(button => button.addEventListener("click", () => retryPlanReviews(button.dataset.retryReviews)));
    board.querySelectorAll("[data-add-reviewer]").forEach(form => form.addEventListener("submit", addPlanReviewer));
  }

  async function refreshLifecycleGuide() {
    try { state.lifecycleGuide = await json("/api/lifecycle-guide"); renderLifecycleGuide(); }
    catch (error) { if (byId("lifecycleGuideBoard")) byId("lifecycleGuideBoard").innerHTML = `<p class="feature-notice">${escapeHtml(error.message)}</p>`; }
  }

  async function setLifecycleNotification(notificationId, status) {
    try {
      await json(`/api/lifecycle-notifications/${encodeURIComponent(notificationId)}/state`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) });
      await refreshLifecycleGuide();
    } catch (error) { notify(error.message); }
  }

  async function retryPlanReviews(planId) {
    try { await json(`/api/plans/${planId}/reviews`, { method: "POST" }); await refreshLifecycleGuide(); notify("Failed specialist reviews were queued again."); }
    catch (error) { notify(error.message); }
  }

  async function addPlanReviewer(event) {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      await json(`/api/plans/${form.dataset.addReviewer}/reviewers`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ agent_id: form.elements.agent_id.value, focus: form.elements.focus.value.trim() }) });
      await refreshLifecycleGuide();
      notify("Additional review agent added without granting implementation access.");
    } catch (error) { notify(error.message); }
  }

  async function createPlan(event) {
    event.preventDefault();
    try {
      await json("/api/plans", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: byId("planTitle").value, request: byId("planRequest").value, implementation_agent_id: byId("planAgent").value, priority: byId("planPriority").value }) });
      event.currentTarget.reset();
      await refreshPlans();
      notify("Plan created and waiting for your approval.");
    } catch (error) { notify(error.message); }
  }

  async function decidePlan(id, decision) {
    const plan = state.plans.find(item => item.id === id);
    const reason = "Decision recorded in Atlas Studio";
    try {
      const approval = await json("/api/approvals", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "plan_decision", purpose: `${decision} plan ${plan?.title || id}`, target: id, actor: "local-user", payload: { decision, reason }, ttl_minutes: 15 }) });
      const passcode = await requestPasscode(`${decision === "approved" ? "Approve" : "Reject"} plan: ${plan?.title || id}`, approval.challenge_code);
      if (!passcode) return;
      await json(`/api/approvals/${approval.id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: "approved", user_authorized: true, approval_passcode: passcode, reason }) });
      await json(`/api/plans/${id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision, reason, user_authorized: true, approval_id: approval.id }) });
      await Promise.all([refreshPlans(), json("/api/tasks").then(renderTasks), refreshLifecycleGuide()]);
      notify(decision === "approved" ? "Plan approved; isolated workspace and Forge task created." : "Plan rejected.");
    } catch (error) { notify(error.message); }
  }

  async function createTask(event) {
    event.preventDefault();
    try {
      await json("/api/tasks", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: byId("taskTitle").value, prompt: byId("taskPrompt").value, agent_id: byId("taskAgent").value, priority: byId("taskPriority").value, user_authorized: false }) });
      event.currentTarget.reset();
      state.tasks = await json("/api/tasks");
      renderTasks();
    } catch (error) { notify(error.message); }
  }

  function renderQa() {
    const quanta = state.agents.find(agent => agent.name === "Quanta");
    const testCapability = Boolean(quanta?.tools.includes("test_execute"));
    const latest = state.lifecycles.flatMap(item => item.evidence || []).filter(item => item.source === "quanta-full-pipeline").at(-1);
    const gates = ["Repository test discovery", "API and policy tests", "UI contract tests", "Lifecycle governance tests", "Evidence and audit capture"];
    byId("qaGates").innerHTML = gates.map((gate, index) => `<article class="qa-gate"><i>${index + 1}</i><div><strong>${gate}</strong><p>${latest ? `Latest full pipeline ${escapeHtml(latest.status)} with exit code ${escapeHtml(latest.exit_code)}.` : testCapability ? "Quanta is ready; start a full pipeline from a project in the Test stage." : "No test execution capability is assigned."}</p></div><span>${latest ? escapeHtml(latest.status.toUpperCase()) : "AWAITING EVIDENCE"}</span></article>`).join("");
  }

  function lifecycleEvidenceSuggestions(lifecycle, completedTasks) {
    const taskSuggestions = completedTasks.map(task => {
      const agent = state.agents.find(item => String(item.id) === String(task.agent_id));
      const agentName = agent?.name || "Assigned agent";
      const category = agentName === "Sentinel" ? "Security review" : agentName === "Quanta" ? "QA evidence" : ["Pixel", "Scribe", "Echo"].includes(agentName) ? "Artifact review" : "Review evidence";
      const references = (task.evidence_refs || []).join(", ");
      const finding = String(task.output || "No narrative finding was recorded.").slice(0, 1200);
      return {
        label: `${category} — ${agentName}: ${task.title}`,
        taskId: task.id,
        text: `[Agent-authored draft — verify before use]\nCategory: ${category}\nSource agent: ${agentName}${agent?.role ? ` (${agent.role})` : ""}\nTask: ${task.title}\nFinding: ${finding}\nEvidence references: ${references || "No structured evidence references recorded; this draft cannot satisfy a machine-evidence gate by itself."}`.slice(0, 1950),
      };
    });
    const recordedSuggestions = (lifecycle.evidence || []).filter(item => item.status === "passed").map((item, index) => ({
      label: `Recorded ${label(item.type || "gate")} evidence — ${item.source || `record ${index + 1}`}`,
      taskId: item.task_id || "",
      text: `[Recorded evidence summary — review before use]\nType: ${label(item.type || "gate")}\nStage: ${label(item.stage || lifecycle.stage)}\nSource: ${item.source || "lifecycle record"}\nStatus: ${item.status}\nEvidence: ${item.evidence || item.command || item.commit || item.change_set_id || "See the linked lifecycle record for machine details."}`.slice(0, 1950),
    }));
    return [...recordedSuggestions, ...taskSuggestions];
  }

  function renderLifecycles() {
    const board = byId("lifecycleBoard");
    if (!board) return;
    const nextStage = { development: "test", test: "sandbox", sandbox: "production" };
    const evidenceType = { test: "implementation", sandbox: "test", production: "sandbox" };
    board.innerHTML = state.lifecycles.map(item => {
      const next = nextStage[item.stage];
      const completedTasks = state.tasks.filter(task => task.plan_id === item.plan_id && task.status === "completed");
      const suggestions = lifecycleEvidenceSuggestions(item, completedTasks);
      const suggestionControl = `<div class="evidence-suggestion"><label>Agent and evidence suggestions<select name="evidence_suggestion"><option value="">${suggestions.length ? "Choose a reviewable draft" : "No evidence-backed suggestions available"}</option>${suggestions.map(suggestion => `<option value="${escapeHtml(suggestion.text)}" data-task-id="${escapeHtml(suggestion.taskId)}">${escapeHtml(suggestion.label)}</option>`).join("")}</select></label><button type="button" data-use-evidence-suggestion ${suggestions.length ? "" : "disabled"}>Insert suggestion</button><small>Suggestions are editable drafts. They never replace required test, security, artifact, approval, or release records.</small></div>`;
      return `<article class="record-selectable" data-record-kind="lifecycle" data-record-id="${escapeHtml(item.id)}" role="button" tabindex="0"><header><div><small>${escapeHtml(item.stage.toUpperCase())} · ${escapeHtml(item.status.toUpperCase())}</small><h3>${escapeHtml(item.title)}</h3></div><span>${escapeHtml(Object.entries(item.gates).map(([key, value]) => `${key}:${value}`).join(" · "))}</span></header><p>${item.evidence.length ? escapeHtml(item.evidence.at(-1).evidence) : "No gate evidence has been recorded yet."}</p>${next ? `<form data-lifecycle-form="${item.id}" data-target-stage="${next}" data-evidence-type="${evidenceType[next]}">${suggestionControl}<label>Gate evidence<textarea name="evidence" required placeholder="Record the test run, security review, artifact, or release evidence."></textarea></label><label>Completed task<select name="task_id"><option value="">No linked task</option>${completedTasks.map(task => `<option value="${task.id}">${escapeHtml(task.title)}</option>`).join("")}</select></label><button class="feature-primary" type="submit">Promote to ${escapeHtml(next)}</button></form>` : `<footer><strong>Production lifecycle complete</strong><span class="record-open-hint">Open lifecycle details</span></footer>`}</article>`;
    }).join("") || `<div class="feature-empty"><strong>No active development lifecycle</strong><p>Approve an implementation plan to create an isolated workspace and lifecycle.</p></div>`;
    board.querySelectorAll("[data-lifecycle-form]").forEach(form => form.addEventListener("submit", promoteLifecycle));
    board.querySelectorAll("[data-use-evidence-suggestion]").forEach(button => button.addEventListener("click", event => {
      event.stopPropagation();
      const form = button.closest("[data-lifecycle-form]");
      const option = form.elements.evidence_suggestion.selectedOptions[0];
      if (!option?.value) return notify("Choose an agent or recorded-evidence suggestion first.");
      form.elements.evidence.value = option.value;
      if (option.dataset.taskId && [...form.elements.task_id.options].some(item => item.value === option.dataset.taskId)) form.elements.task_id.value = option.dataset.taskId;
      form.elements.evidence.focus();
      notify("Draft inserted. Review and edit it before submission.");
    }));
    board.querySelectorAll('[data-record-kind="lifecycle"]').forEach(card => {
      const lifecycle = state.lifecycles.find(item => String(item.id) === card.dataset.recordId);
      if (lifecycle?.stage !== "test") return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "feature-primary";
      button.textContent = "Run full QA pipeline";
      button.addEventListener("click", event => { event.stopPropagation(); runQaPipeline(lifecycle.plan_id); });
      card.insertBefore(button, card.querySelector("form"));
    });
    const sandbox = byId("sandboxQueue");
    if (sandbox) {
      const items = state.lifecycles.filter(item => item.stage === "sandbox");
      sandbox.innerHTML = items.map(item => `<article><strong>${escapeHtml(item.title)}</strong><p>Sandbox evidence is active; Production remains locked pending one-time approval.</p></article>`).join("") || `<strong>No sandbox run is active</strong><p>Only work that passes the Test gate appears here.</p>`;
    }
    renderEnvironmentSwimlanes();
  }

  async function runQaPipeline(planId) {
    const plan = state.plans.find(item => item.id === planId);
    if (!plan?.workspace_id) return notify("The approved plan workspace is unavailable.");
    const command = ["python", "-m", "pytest", "-q"], timeout_seconds = 300;
    const payload = { plan_id: plan.id, workspace_id: plan.workspace_id, command, timeout_seconds };
    const target = `qa-pipeline:${plan.id}`;
    try {
      const approvalId = await authorizeProtectedAction({ action: "test_execute", purpose: `Run Quanta's full QA pipeline for: ${plan.title}`, target, actor: "Quanta", payload });
      if (!approvalId) return;
      const task = await json("/api/qa/pipeline-runs", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plan_id: plan.id, workspace_id: plan.workspace_id, approval_id: approvalId, timeout_seconds }) });
      state.tasks = await json("/api/tasks");
      renderTasks();
      notify(`Full QA pipeline queued as task ${task.id.slice(0, 8)}.`);
    } catch (error) { notify(error.message); }
  }

  const environmentForStage = stage => ["development", "test"].includes(stage) ? "workspace" : stage;

  function renderEnvironmentSwimlanes() {
    const board = byId("environmentSwimlanes");
    if (!board) return;
    const lanes = [
      ["workspace", "Workspace", "Development and test work with approved local tools."],
      ["sandbox", "Sandbox", "Isolated validation with deny-network-by-default execution."],
      ["production", "Production", "Sensitive release state protected by explicit authorization."],
    ];
    board.innerHTML = lanes.map(([environment, title, description]) => {
      const items = state.lifecycles.filter(item => environmentForStage(item.stage) === environment);
      return `<section class="environment-lane" data-environment-lane="${environment}"><header><div><small>${environment === "workspace" ? "BUILD" : environment === "sandbox" ? "VALIDATE" : "OPERATE"}</small><h3>${title}</h3><p>${description}</p></div><span>${items.length}</span></header><div class="environment-lane-dropzone">${items.map(item => `<article class="environment-widget record-selectable" draggable="true" data-lifecycle-widget="${escapeHtml(item.id)}" data-current-environment="${environment}" data-record-kind="lifecycle" data-record-id="${escapeHtml(item.id)}" role="button" tabindex="0"><div class="environment-widget-grip" aria-hidden="true">::</div><small>${escapeHtml(label(item.stage).toUpperCase())} · ${escapeHtml(item.status.toUpperCase())}</small><h4>${escapeHtml(item.title)}</h4><p>${item.evidence.length ? escapeHtml(item.evidence.at(-1).evidence || item.evidence.at(-1).reason || "Evidence recorded") : "No lifecycle evidence recorded yet."}</p><label>Move with override<select data-environment-move="${escapeHtml(item.id)}" aria-label="Move ${escapeHtml(item.title)} to another environment"><option value="${environment}">Current: ${title}</option>${lanes.filter(([value]) => value !== environment).map(([value, laneTitle]) => `<option value="${value}">${laneTitle}</option>`).join("")}</select></label><span class="record-open-hint">Drag to another lane or choose a destination</span></article>`).join("") || `<div class="environment-lane-empty">Drop an approved project here</div>`}</div></section>`;
    }).join("");
    board.querySelectorAll("[data-lifecycle-widget]").forEach(widget => widget.addEventListener("dragstart", event => {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", widget.dataset.lifecycleWidget);
      widget.classList.add("dragging");
    }));
    board.querySelectorAll("[data-lifecycle-widget]").forEach(widget => widget.addEventListener("dragend", () => widget.classList.remove("dragging")));
    board.querySelectorAll("[data-environment-lane]").forEach(lane => {
      lane.addEventListener("dragover", event => { event.preventDefault(); lane.classList.add("drag-over"); });
      lane.addEventListener("dragleave", () => lane.classList.remove("drag-over"));
      lane.addEventListener("drop", event => {
        event.preventDefault();
        lane.classList.remove("drag-over");
        const lifecycleId = event.dataTransfer.getData("text/plain");
        const widget = board.querySelector(`[data-lifecycle-widget="${CSS.escape(lifecycleId)}"]`);
        if (widget && widget.dataset.currentEnvironment !== lane.dataset.environmentLane) openEnvironmentOverride(lifecycleId, lane.dataset.environmentLane);
      });
    });
    board.querySelectorAll("[data-environment-move]").forEach(select => select.addEventListener("change", event => {
      event.stopPropagation();
      const widget = select.closest("[data-lifecycle-widget]");
      if (select.value !== widget.dataset.currentEnvironment) openEnvironmentOverride(select.dataset.environmentMove, select.value);
      select.value = widget.dataset.currentEnvironment;
    }));
  }

  function openEnvironmentOverride(lifecycleId, targetEnvironment) {
    const lifecycle = state.lifecycles.find(item => String(item.id) === String(lifecycleId));
    if (!lifecycle) return notify("Lifecycle record is unavailable.");
    const currentEnvironment = environmentForStage(lifecycle.stage);
    byId("environmentOverrideLifecycle").value = lifecycle.id;
    byId("environmentOverrideTarget").value = targetEnvironment;
    byId("environmentOverrideReason").value = "";
    byId("environmentOverrideTitle").textContent = `Move ${lifecycle.title}`;
    byId("environmentOverrideSummary").innerHTML = `<div><dt>From</dt><dd>${escapeHtml(label(currentEnvironment))}</dd></div><div><dt>To</dt><dd>${escapeHtml(label(targetEnvironment))}</dd></div><div><dt>Control</dt><dd>Six-digit user approval and audit event</dd></div>`;
    byId("environmentOverrideDialog").showModal();
  }

  async function submitEnvironmentOverride(event) {
    event.preventDefault();
    const lifecycleId = byId("environmentOverrideLifecycle").value;
    const target_environment = byId("environmentOverrideTarget").value;
    const reason = byId("environmentOverrideReason").value.trim();
    const payload = { target_environment, reason };
    try {
      const approvalId = await authorizeProtectedAction({ action: "lifecycle_override", purpose: `Override lifecycle environment to ${target_environment}`, target: lifecycleId, actor: "local-user", payload });
      if (!approvalId) return;
      await json(`/api/lifecycles/${lifecycleId}/override`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...payload, approval_id: approvalId }) });
      byId("environmentOverrideDialog").close();
      await refreshLifecycles();
      notify(`Project moved to ${target_environment}; override recorded.`);
    } catch (error) { notify(error.message); }
  }

  async function refreshLifecycles() {
    state.lifecycles = await json("/api/lifecycles");
    renderQa();
    renderLifecycles();
  }

  async function promoteLifecycle(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const id = form.dataset.lifecycleForm;
    const targetStage = form.dataset.targetStage;
    const evidence = form.elements.evidence.value.trim();
    const evidence_type = form.dataset.evidenceType;
    const payload = { target_stage: targetStage, evidence, evidence_type, task_id: form.elements.task_id.value || null, user_authorized: targetStage === "production", approval_id: null };
    try {
      if (targetStage === "production") {
        const approvalPayload = { target_stage: "production", evidence, evidence_type };
        const approval = await json("/api/approvals", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "production_promotion", purpose: `Promote lifecycle ${id} to Production`, target: id, actor: "local-user", payload: approvalPayload, ttl_minutes: 15 }) });
        const passcode = await requestPasscode("Authorize this one-time Production promotion. The approval expires in 15 minutes.", approval.challenge_code);
        if (!passcode) return;
        await json(`/api/approvals/${approval.id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: "approved", user_authorized: true, approval_passcode: passcode, reason: "Production promotion approved in Atlas Studio" }) });
        payload.approval_id = approval.id;
      }
      await json(`/api/lifecycles/${id}/transition`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      await Promise.all([refreshLifecycles(), refreshLifecycleGuide()]);
      notify(`Lifecycle promoted to ${targetStage}.`);
    } catch (error) { notify(error.message); }
  }

  function updateWorkspaceBreadcrumb(path = "") {
    const breadcrumb = byId("workspaceBreadcrumb");
    if (!breadcrumb) return;
    const parts = path ? path.split("/") : [];
    const nodes = [{ name: byId("workspaceRootName")?.textContent || "workspace", path: "" }];
    parts.forEach((part, index) => nodes.push({ name: part, path: parts.slice(0, index + 1).join("/") }));
    breadcrumb.innerHTML = nodes.map(node => `<button type="button" data-workspace-path="${escapeHtml(node.path)}">${escapeHtml(node.name)}</button>`).join("<span>/</span>");
    breadcrumb.querySelectorAll("[data-workspace-path]").forEach(button => button.addEventListener("click", () => revealFolder(button.dataset.workspacePath)));
  }

  function iconForFile(name) {
    const extension = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
    return ({ py: "PY", js: "JS", mjs: "JS", ts: "TS", tsx: "TS", jsx: "JS", html: "<> ", css: "#", json: "{}", md: "MD", yaml: "Y", yml: "Y", toml: "T", sql: "DB", ps1: "PS" })[extension] || "F";
  }

  async function loadFolder(path, target, nested = false) {
    target.innerHTML = `<p class="tree-loading">Loading...</p>`;
    try {
      const data = await json(`/api/workspace/tree?path=${encodeURIComponent(path)}`);
      if (!nested) {
        byId("workspaceRootName").textContent = data.root || "workspace";
        updateWorkspaceBreadcrumb(path);
      }
      const list = document.createElement("ul");
      list.setAttribute("role", "group");
      for (const entry of data.entries) {
        const item = document.createElement("li");
        item.dataset.path = entry.path;
        item.dataset.type = entry.type;
        const button = document.createElement("button");
        button.type = "button";
        button.className = entry.type === "directory" ? "tree-folder" : "tree-file";
        button.setAttribute("role", "treeitem");
        if (entry.type === "directory") button.setAttribute("aria-expanded", "false");
        button.dataset.path = entry.path;
        button.dataset.previewable = String(entry.previewable);
        const icon = document.createElement("i");
        icon.textContent = entry.type === "directory" ? ">" : iconForFile(entry.name);
        const name = document.createElement("span");
        name.textContent = entry.name;
        button.append(icon, name);
        button.addEventListener("click", () => entry.type === "directory" ? toggleFolder(item, entry.path, button) : openWorkspaceFile(entry.path, entry.previewable));
        item.appendChild(button);
        list.appendChild(item);
      }
      target.replaceChildren(list);
      if (!data.entries.length) target.insertAdjacentHTML("beforeend", '<p class="tree-loading">This folder is empty.</p>');
      if (data.truncated) target.insertAdjacentHTML("beforeend", '<p class="tree-loading">Directory limited to 500 entries.</p>');
      state.workspaceLoaded = true;
    } catch (error) {
      target.innerHTML = `<div class="tree-error"><strong>Workspace unavailable</strong><p>${escapeHtml(error.message)}</p></div>`;
    }
  }

  async function toggleFolder(item, path, button) {
    const existing = item.querySelector(":scope > .tree-children");
    if (existing) {
      existing.remove();
      item.classList.remove("expanded");
      state.openFolders.delete(path);
      button.setAttribute("aria-expanded", "false");
      return;
    }
    const children = document.createElement("div");
    children.className = "tree-children";
    item.appendChild(children);
    item.classList.add("expanded");
    state.openFolders.add(path);
    button.setAttribute("aria-expanded", "true");
    updateWorkspaceBreadcrumb(path);
    await loadFolder(path, children, true);
  }

  function revealFolder(path = "") {
    updateWorkspaceBreadcrumb(path);
    if (!path) {
      state.openFolders.clear();
      loadFolder("", byId("workspaceTree"));
      return;
    }
    const item = [...(byId("workspaceTree")?.querySelectorAll("li[data-path]") || [])].find(node => node.dataset.path === path);
    if (item && !item.classList.contains("expanded")) item.querySelector(":scope > button")?.click();
  }

  function appendHighlightedLine(target, text, language) {
    const line = document.createElement("div");
    line.className = "code-line";
    const number = document.createElement("span");
    number.className = "line-number";
    number.textContent = String(target.childElementCount + 1);
    const source = document.createElement("code");
    const keywords = language === "python"
      ? "and|as|async|await|break|class|continue|def|elif|else|except|False|finally|for|from|if|import|in|is|lambda|None|not|or|pass|raise|return|True|try|while|with|yield"
      : "async|await|break|case|catch|class|const|continue|default|delete|do|else|export|extends|false|finally|for|from|function|if|import|in|instanceof|let|new|null|return|static|super|switch|this|throw|true|try|typeof|undefined|var|while|yield";
    const comment = language === "python" || language === "shell" || language === "powershell" ? "#.*$" : "//.*$";
    const tokenPattern = new RegExp(`("(?:\\\\.|[^"\\\\])*"|'(?:\\\\.|[^'\\\\])*'|\\b(?:${keywords})\\b|\\b\\d+(?:\\.\\d+)?\\b|${comment})`, "g");
    let cursor = 0;
    for (const match of text.matchAll(tokenPattern)) {
      source.append(document.createTextNode(text.slice(cursor, match.index)));
      const token = document.createElement("span");
      token.textContent = match[0];
      token.className = match[0].startsWith("//") || match[0].startsWith("#") ? "syntax-comment" : /^['"]/.test(match[0]) ? "syntax-string" : /^\d/.test(match[0]) ? "syntax-number" : "syntax-keyword";
      source.appendChild(token);
      cursor = match.index + match[0].length;
    }
    source.append(document.createTextNode(text.slice(cursor) || " "));
    line.append(number, source);
    line.addEventListener("click", () => { byId("codePosition").textContent = `Ln ${number.textContent}, Col 1`; });
    target.appendChild(line);
  }

  async function openWorkspaceFile(path, previewable) {
    if (!previewable) return notify("This file is binary, sensitive, or too large for a safe preview.");
    try {
      const file = await json(`/api/workspace/file?path=${encodeURIComponent(path)}`);
      document.querySelector('.top-navigation button[data-view="codeView"]')?.click();
      byId("codeFileName").textContent = file.name;
      byId("codeLanguage").textContent = file.language.toUpperCase();
      byId("codeBreadcrumb").textContent = file.path;
      byId("codeStats").textContent = `${file.line_count} lines / ${file.size} bytes`;
      byId("codePosition").textContent = "Ln 1, Col 1";
      const viewer = byId("codeViewer");
      viewer.replaceChildren();
      file.content.split("\n").forEach(line => appendHighlightedLine(viewer, line, file.language));
      viewer.scrollTop = 0;
      byId("codeDiffName").textContent = "No change selected";
      byId("codeDiffState").textContent = "READ-ONLY";
      byId("codeDiffViewer").textContent = "Select a file from a Forge change set on the Implementation page to compare the current code with its proposed diff.";
    } catch (error) {
      notify(error.message);
    }
  }

  function refreshWorkspace() {
    state.openFolders.clear();
    state.workspaceLoaded = false;
    return loadFolder("", byId("workspaceTree"));
  }

  async function submitSourceRequest(event) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = Object.fromEntries(new FormData(form));
    for (const optional of ["jurisdiction", "version"]) if (!payload[optional]) payload[optional] = null;
    try {
      const result = await json("/api/sources/requests", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      byId("sourceRequestDialog").close();
      form.reset();
      notify(result.message);
    } catch (error) {
      notify(error.message);
    }
  }

  async function refreshTools() {
    try {
      state.tools = await json("/api/tool-library");
      populateSelect(byId("toolCategory"), [...new Set(state.tools.map(tool => tool.category))].sort(), "All categories");
      renderTools();
    } catch (error) {
      if (byId("toolDirectory")) byId("toolDirectory").innerHTML = `<div class="feature-empty"><strong>Tool registry unavailable</strong><p>${escapeHtml(error.message)}</p></div>`;
    }
  }

  function configureWorkerForm() {
    const action = byId("workerAction")?.value || "preview_write";
    const commandMode = action === "code_execute" || action === "test_execute";
    byId("workerContentField").hidden = commandMode;
    byId("workerCommandField").hidden = !commandMode;
    byId("workerPath").placeholder = commandMode ? ". or a workspace subdirectory" : "src/atlas_studio/example.py";
  }

  async function refreshWorker() {
    const status = byId("workerConnectionState");
    if (!status) return;
    const capable = state.agents.filter(agent => !agent.read_only && (agent.tools.includes("files_write") || agent.tools.includes("code_execute")));
    byId("workerAgent").innerHTML = capable.map(agent => `<option value="${escapeHtml(agent.id)}" ${agent.name === "Forge" ? "selected" : ""}>${escapeHtml(agent.name)} - ${escapeHtml(agent.role)}</option>`).join("");
    try {
      const health = await json("/api/worker/health");
      status.textContent = health.status === "ok" ? "CONNECTED" : "UNAVAILABLE";
      status.dataset.state = health.status === "ok" ? "ok" : "error";
    } catch (error) {
      status.textContent = "UNAVAILABLE";
      status.dataset.state = "error";
    }
  }

  function splitCommand(value) {
    return (value.match(/(?:[^\s"]+|"[^"]*")+/g) || []).map(part => part.replace(/^"|"$/g, ""));
  }

  async function runWorkerAction(event, forcePreview = false) {
    event?.preventDefault();
    if (!byId("workerAuthorized").checked) return notify("Check the authorization box before continuing.");
    const selectedAction = forcePreview ? "preview_write" : byId("workerAction").value;
    const target = byId("workerPath").value || ".";
    const summary = `${selectedAction.replaceAll("_", " ")} as ${byId("workerAgent").selectedOptions[0]?.textContent || "implementation agent"} on ${target}`;
    const workerPayload = {
      action: selectedAction,
      path: target,
      content: selectedAction === "preview_write" || selectedAction === "file_write" ? byId("workerContent").value : null,
      expected_sha256: null,
      command: selectedAction === "code_execute" || selectedAction === "test_execute" ? splitCommand(byId("workerCommand").value) : [],
      timeout_seconds: 60,
      workspace_id: byId("workerWorkspace").value,
    };
    const payload = {
      agent_id: byId("workerAgent").value,
      ...workerPayload,
      user_authorized: true,
      approval_passcode: "",
      approval_id: null,
    };
    const output = byId("workerResult"), resultState = byId("workerResultState");
    output.textContent = "Waiting for the isolated worker...";
    resultState.textContent = "RUNNING";
    try {
      if (selectedAction !== "preview_write") {
        const approval = await json("/api/approvals", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: selectedAction, purpose: summary, target, actor: byId("workerAgent").selectedOptions[0]?.textContent?.split(" - ")[0] || "Forge", payload: workerPayload, ttl_minutes: 15 }) });
        const passcode = await requestPasscode(`${summary}. Approval expires in 15 minutes and can be used once.`, approval.challenge_code);
        if (!passcode) { resultState.textContent = "AWAITING APPROVAL"; output.textContent = "The worker action was not authorized."; return; }
        await json(`/api/approvals/${approval.id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: "approved", user_authorized: true, approval_passcode: passcode, reason: "Approved in the Atlas implementation modal" }) });
        payload.approval_id = approval.id;
      }
      const result = await json("/api/worker/actions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      resultState.textContent = result.exit_code && result.exit_code !== 0 ? "NEEDS REVIEW" : "RECORDED";
      resultState.dataset.state = result.exit_code && result.exit_code !== 0 ? "error" : "ok";
      output.textContent = result.diff || [result.stdout, result.stderr].filter(Boolean).join("\n") || JSON.stringify(result, null, 2);
      json("/api/tasks").then(renderTasks).catch(() => {});
    } catch (error) {
      resultState.textContent = "BLOCKED";
      resultState.dataset.state = "error";
      output.textContent = error.message;
    }
  }

  function renderExternalApprovals() {
    const target = byId("externalApprovalList");
    if (!target) return;
    target.innerHTML = state.approvals.map(item => `<article><div><strong>${escapeHtml(item.query || item.action)}</strong><small>${escapeHtml(item.purpose)} · ${escapeHtml(item.status)} · expires ${new Date(item.expires_at).toLocaleTimeString()}</small></div><div>${item.status === "pending" ? `<button type="button" data-approve-egress="${item.id}">Review & approve</button>` : ""}${item.status === "approved" && item.action === "internet_search" ? `<button class="feature-primary" type="button" data-run-search="${item.id}">Run approved search</button>` : ""}</div></article>`).join("") || "<p>No external route requests. Internet access remains denied.</p>";
    target.querySelectorAll("[data-approve-egress]").forEach(button => button.addEventListener("click", () => approveExternal(button.dataset.approveEgress)));
    target.querySelectorAll("[data-run-search]").forEach(button => button.addEventListener("click", () => runApprovedSearch(button.dataset.runSearch)));
  }

  async function refreshExternalApprovals() {
    if (!byId("externalApprovalList")) return;
    try { state.approvals = await json("/api/external-approvals"); renderExternalApprovals(); }
    catch (error) { byId("externalApprovalList").textContent = error.message; }
  }

  async function authorizeProtectedAction({ action, purpose, target, actor, payload }) {
    const approval = await json("/api/approvals", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action, purpose, target, actor, payload, ttl_minutes: 15 }) });
    const passcode = await requestPasscode(`${purpose}. This exact approval expires in 15 minutes and can be used once.`, approval.challenge_code);
    if (!passcode) return null;
    await json(`/api/approvals/${approval.id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: "approved", user_authorized: true, approval_passcode: passcode, reason: "Approved in Atlas Studio" }) });
    return approval.id;
  }

  function forgeBranch(changeSet) {
    const slug = String(changeSet.title || "change").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 48) || "change";
    return `atlas/${String(changeSet.plan_id).slice(0, 8)}-${slug}`;
  }

  function changeSetApplyPayload(changeSet) {
    return {
      change_set_id: changeSet.id,
      workspace_id: changeSet.workspace_id,
      files: changeSet.files.map(file => ({ path: file.path, content: file.content, expected_sha256: file.expected_sha256 })),
    };
  }

  function renderChangeSets() {
    const target = byId("forgeChangeSets");
    if (!target) return;
    target.innerHTML = state.changeSets.map(changeSet => {
      const test = changeSet.test_result || {};
      const fileNames = changeSet.files.map(file => `<button type="button" data-change-open="${changeSet.id}" data-change-path="${escapeHtml(file.path)}">${escapeHtml(file.path)}</button>`).join("");
      const action = changeSet.status === "pending_review"
        ? `<button class="feature-primary" type="button" data-change-apply="${changeSet.id}">Review and approve write</button>`
        : changeSet.status === "applied"
          ? `<button class="feature-primary" type="button" data-change-test="${changeSet.id}">Approve test run</button>`
          : changeSet.status === "tests_passed"
            ? `<button class="feature-primary" type="button" data-change-commit="${changeSet.id}">Approve branch and commit</button>`
            : "";
      return `<article class="forge-change-card record-selectable" data-status="${escapeHtml(changeSet.status)}" data-record-kind="changeSet" data-record-id="${escapeHtml(changeSet.id)}" role="button" tabindex="0">
        <header><div><small>${escapeHtml(label(changeSet.status).toUpperCase())}</small><h4>${escapeHtml(changeSet.title)}</h4></div><span>${String(changeSet.id).slice(0, 8).toUpperCase()} · ${changeSet.files.length} FILE${changeSet.files.length === 1 ? "" : "S"}</span></header>
        <p>${escapeHtml(changeSet.summary)}</p>
        <div class="forge-file-list">${fileNames}</div>
        <details open><summary>Review combined diff</summary><pre>${escapeHtml(changeSet.combined_diff || "No textual diff was returned.")}</pre></details>
        ${Object.keys(test).length ? `<details><summary>Test evidence: exit ${escapeHtml(test.exit_code)}</summary><pre>${escapeHtml([test.stdout, test.stderr].filter(Boolean).join("\n") || "No test output")}</pre></details>` : ""}
        ${changeSet.commit ? `<div class="forge-commit-evidence"><span>Branch <b>${escapeHtml(changeSet.branch)}</b></span><span>Commit <b>${escapeHtml(changeSet.commit)}</b></span></div>` : ""}
        <footer><small>Plan ${escapeHtml(String(changeSet.plan_id).slice(0, 8))} · Workspace ${escapeHtml(String(changeSet.workspace_id).slice(0, 8))}</small><div class="forge-change-actions">${action}<button class="feature-danger" type="button" data-change-delete="${changeSet.id}">Delete implementation</button></div></footer>
      </article>`;
    }).join("") || `<div class="feature-empty"><strong>No Forge change set yet</strong><p>Create and approve a plan. Forge will inspect its isolated workspace and return a reviewable proposal.</p></div>`;
    target.querySelectorAll("[data-change-apply]").forEach(button => button.addEventListener("click", () => approveChangeSet(button.dataset.changeApply)));
    target.querySelectorAll("[data-change-test]").forEach(button => button.addEventListener("click", () => testChangeSet(button.dataset.changeTest)));
    target.querySelectorAll("[data-change-commit]").forEach(button => button.addEventListener("click", () => commitChangeSet(button.dataset.changeCommit)));
    target.querySelectorAll("[data-change-delete]").forEach(button => button.addEventListener("click", () => deleteChangeSet(button.dataset.changeDelete)));
    target.querySelectorAll("[data-change-open]").forEach(button => button.addEventListener("click", () => openChangeDiff(button.dataset.changeOpen, button.dataset.changePath)));
  }

  async function openChangeDiff(changeSetId, path) {
    try {
      const file = await json(`/api/change-sets/${changeSetId}/file?path=${encodeURIComponent(path)}`);
      document.querySelector('.top-navigation button[data-view="codeView"]')?.click();
      byId("codeFileName").textContent = file.path;
      byId("codeLanguage").textContent = (file.path.split(".").pop() || "text").toUpperCase();
      byId("codeBreadcrumb").textContent = `Forge proposal · ${file.path}`;
      byId("codeStats").textContent = `${file.current_content.split("\n").length} current lines · ${file.proposed_content.split("\n").length} proposed lines`;
      const viewer = byId("codeViewer"); viewer.replaceChildren();
      file.current_content.split("\n").forEach(line => appendHighlightedLine(viewer, line, "text"));
      byId("codeDiffName").textContent = file.path;
      byId("codeDiffState").textContent = label(file.status).toUpperCase();
      byId("codeDiffViewer").textContent = file.diff || "No textual change.";
    } catch (error) { notify(error.message); }
  }

  async function refreshChangeSets() {
    const target = byId("forgeChangeSets");
    if (!target) return;
    try { state.changeSets = await json("/api/change-sets"); renderChangeSets(); }
    catch (error) { target.innerHTML = `<div class="feature-empty"><strong>Forge proposals unavailable</strong><p>${escapeHtml(error.message)}</p></div>`; }
  }

  async function deleteChangeSet(id) {
    const changeSet = state.changeSets.find(item => item.id === id);
    if (!changeSet) return;
    const payload = { operation: "soft_delete", change_set_id: changeSet.id, plan_id: changeSet.plan_id, status: changeSet.status };
    try {
      const approvalId = await authorizeProtectedAction({ action: "change_set_delete", purpose: `Remove implementation from active work: ${changeSet.title}. This does not revert applied files or erase a Git commit`, target: changeSet.id, actor: "local-user", payload });
      if (!approvalId) return;
      const response = await fetch(`/api/change-sets/${id}?approval_id=${encodeURIComponent(approvalId)}`, { method: "DELETE" });
      if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `Request failed with HTTP ${response.status}`);
      await refreshChangeSets();
      notify("Implementation removed from active work; audit evidence was retained.");
    } catch (error) { notify(error.message); }
  }

  async function approveChangeSet(id) {
    const changeSet = state.changeSets.find(item => item.id === id);
    if (!changeSet) return;
    const payload = changeSetApplyPayload(changeSet);
    try {
      const approvalId = await authorizeProtectedAction({ action: "change_set_apply", purpose: `Apply Forge change set: ${changeSet.title}`, target: changeSet.id, actor: "Forge", payload });
      if (!approvalId) return;
      await json(`/api/change-sets/${id}/apply`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approval_id: approvalId, user_authorized: true }) });
      await refreshChangeSets();
      notify("The exact reviewed Forge change set was applied.");
    } catch (error) { notify(error.message); }
  }

  async function testChangeSet(id) {
    const changeSet = state.changeSets.find(item => item.id === id);
    if (!changeSet) return;
    const command = ["python", "-m", "pytest", "-q"], timeout_seconds = 180;
    const payload = { change_set_id: changeSet.id, workspace_id: changeSet.workspace_id, command, timeout_seconds };
    try {
      const approvalId = await authorizeProtectedAction({ action: "test_execute", purpose: `Run the standard test suite for: ${changeSet.title}`, target: changeSet.id, actor: "Forge", payload });
      if (!approvalId) return;
      await json(`/api/change-sets/${id}/test`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approval_id: approvalId, user_authorized: true, command, timeout_seconds }) });
      await refreshChangeSets();
      notify("Test evidence recorded for the Forge change set.");
    } catch (error) { notify(error.message); }
  }

  async function commitChangeSet(id) {
    const changeSet = state.changeSets.find(item => item.id === id);
    if (!changeSet) return;
    const branch = forgeBranch(changeSet);
    const message = `Atlas: ${changeSet.title} (${String(changeSet.plan_id).slice(0, 8)})`;
    const payload = { change_set_id: changeSet.id, workspace_id: changeSet.workspace_id, branch, message, paths: changeSet.files.map(file => file.path) };
    try {
      const approvalId = await authorizeProtectedAction({ action: "git_commit", purpose: `Create ${branch} and commit the tested Forge change set`, target: changeSet.id, actor: "Forge", payload });
      if (!approvalId) return;
      await json(`/api/change-sets/${id}/commit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approval_id: approvalId, user_authorized: true, branch, message }) });
      await refreshChangeSets();
      notify("Governed Forge commit created in the isolated workspace.");
    } catch (error) { notify(error.message); }
  }

  async function requestExternalApproval(event) {
    event.preventDefault();
    const domains = byId("externalSearchDomains").value.split(",").map(value => value.trim()).filter(Boolean);
    try {
      const approval = await json("/api/external-approvals", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: "internet_search", query: byId("externalSearchQuery").value, purpose: byId("externalSearchPurpose").value, allowed_domains: domains, ttl_minutes: 15 }) });
      const passcode = await requestPasscode(`Allow one internet search: ${byId("externalSearchQuery").value}`, approval.challenge_code);
      if (passcode) await json(`/api/external-approvals/${approval.id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: "approved", user_authorized: true, approval_passcode: passcode, reason: "Approved in Atlas Studio" }) });
      event.currentTarget.reset();
      await refreshExternalApprovals();
      notify("Internet search is waiting for your passcode approval.");
    } catch (error) { notify(error.message); }
  }

  async function approveExternal(id) {
    const item = state.approvals.find(approval => approval.id === id);
    try {
      const challenge = await json(`/api/approvals/${id}/challenge`, { method: "POST" });
      const passcode = await requestPasscode(`Allow one internet search: ${item?.query || id}`, challenge.challenge_code);
      if (!passcode) return;
      await json(`/api/external-approvals/${id}/decision`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ decision: "approved", user_authorized: true, approval_passcode: passcode, reason: "Approved in the Atlas settings modal" }) });
      await refreshExternalApprovals();
    } catch (error) { notify(error.message); }
  }

  async function runApprovedSearch(id) {
    try {
      const result = await json("/api/research/search", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ approval_id: id }) });
      byId("workerResult").textContent = JSON.stringify(result, null, 2);
      notify(`Approved search returned ${(result.results || []).length} results.`);
      await refreshExternalApprovals();
    } catch (error) { notify(error.message); }
  }

  async function initialize() {
    try {
      [state.agents, state.tasks, state.sources, state.plans, state.lifecycles, state.changeSets] = await Promise.all([json("/api/agents"), json("/api/tasks"), json("/api/sources"), json("/api/plans"), json("/api/lifecycles"), json("/api/change-sets")]);
      populateSelect(byId("knowledgeCategory"), [...new Set(state.sources.map(source => source.category))].sort(), "All source categories");
      renderSources();
      renderTasks();
      renderQa();
      renderPlans();
      renderLifecycles();
      renderChangeSets();
      await refreshLifecycleGuide();
    } catch (error) {
      notify(error.message);
    }
    await refreshTools();
    configureWorkerForm();
    await Promise.all([refreshWorker(), refreshExternalApprovals()]);
  }

  byId("toolSearch")?.addEventListener("input", renderTools);
  byId("toolCategory")?.addEventListener("change", renderTools);
  byId("knowledgeSearch")?.addEventListener("input", renderSources);
  byId("knowledgeCategory")?.addEventListener("change", renderSources);
  byId("runKnowledgeSearch")?.addEventListener("click", renderSources);
  byId("requestToolButton")?.addEventListener("click", requestTool);
  byId("requestSourceButton")?.addEventListener("click", () => {
    state.selectedSource = null;
    byId("sourceRequestForm").reset();
    byId("sourceRequestTitle").textContent = "Request a source";
    byId("sourceRequestDialog").showModal();
  });
  byId("requestSourceChange")?.addEventListener("click", requestSelectedSourceChange);
  document.querySelectorAll("[data-close-source-request]").forEach(button => button.addEventListener("click", () => byId("sourceRequestDialog").close()));
  byId("sourceRequestForm")?.addEventListener("submit", submitSourceRequest);
  byId("agentEditForm")?.addEventListener("submit", saveAgentEdit);
  document.querySelectorAll("[data-close-agent-edit]").forEach(button => button.addEventListener("click", () => byId("agentEditDialog").close()));
  byId("environmentOverrideForm")?.addEventListener("submit", submitEnvironmentOverride);
  document.querySelectorAll("[data-close-environment-override]").forEach(button => button.addEventListener("click", () => byId("environmentOverrideDialog").close()));
  byId("forgeRecommendationForm")?.addEventListener("submit", saveForgeRecommendation);
  document.querySelectorAll("[data-close-forge-recommendation]").forEach(button => button.addEventListener("click", () => byId("forgeRecommendationDialog").close()));
  byId("refreshLifecycleGuide")?.addEventListener("click", refreshLifecycleGuide);
  document.addEventListener("click", event => {
    const editButton = event.target.closest("[data-edit-agent]");
    if (editButton) {
      event.stopPropagation();
      openAgentEditor(editButton.dataset.editAgent);
    }
  });
  byId("refreshWorkspace")?.addEventListener("click", refreshWorkspace);
  byId("backToExplorer")?.addEventListener("click", () => document.querySelector('.top-navigation button[data-view="workspace"]')?.click());
  byId("workerAction")?.addEventListener("change", configureWorkerForm);
  byId("workerActionForm")?.addEventListener("submit", event => runWorkerAction(event, false));
  byId("previewWorkerAction")?.addEventListener("click", event => runWorkerAction(event, true));
  byId("externalApprovalForm")?.addEventListener("submit", requestExternalApproval);
  byId("planCreateForm")?.addEventListener("submit", createPlan);
  byId("taskCreateForm")?.addEventListener("submit", createTask);
  byId("refreshChangeSets")?.addEventListener("click", refreshChangeSets);
  document.addEventListener("click", event => {
    const record = event.target.closest("[data-record-kind][data-record-id]");
    if (!record || (event.target !== record && event.target.closest("button, a, input, select, textarea, summary, label, .tool"))) return;
    openRegisteredRecord(record);
  });
  document.addEventListener("keydown", event => {
    if (!['Enter', ' '].includes(event.key)) return;
    const record = event.target.closest("[data-record-kind][data-record-id]");
    if (!record || event.target !== record) return;
    event.preventDefault();
    openRegisteredRecord(record);
  });

  window.AtlasDeveloperFeatures = {
    refreshTools,
    refreshPlans,
    refreshChangeSets,
    refreshLifecycleGuide,
    renderTasks,
    syncAgents(items) { state.agents = items || []; },
    showAgentDetails(agentId) { openRecordDetail("agent", state.agents.find(agent => agent.id === agentId)); },
    authorizeProtectedAction,
    activate(view) {
      if (view === "tasksView" || view === "implementation") json("/api/tasks").then(renderTasks).catch(() => {});
      if (view === "projects") Promise.all([json("/api/plans"), json("/api/lifecycles")]).then(([plans, lifecycles]) => { state.plans = plans; state.lifecycles = lifecycles; renderProjects(); }).catch(() => {});
      if (view === "library") refreshLibrary();
      if (view === "plugins") refreshPlugins();
      if (view === "toolsView") refreshTools();
      if (view === "knowledge" || view === "sources") json("/api/sources").then(items => { state.sources = items; renderSources(); }).catch(() => {});
      if (view === "workspace" && !state.workspaceLoaded) refreshWorkspace();
      if (view === "implementation") { refreshWorker(); refreshChangeSets(); }
      if (view === "settings") refreshExternalApprovals();
      if (view === "plans" || view === "implementation") refreshPlans();
      if (view === "qa" || view === "sandbox" || view === "environments") Promise.all([refreshPlans(), refreshLifecycles(), refreshLifecycleGuide()]).catch(() => {});
      if (view === "lifecycleGuide") Promise.all([refreshPlans(), refreshLifecycles(), refreshLifecycleGuide()]).catch(() => {});
      if (view === "workflows") refreshLifecycleGovernance();
    },
  };
  initialize();
})();
