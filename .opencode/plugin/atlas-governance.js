// Mirrors OpenCode terminal activity into Atlas governance.
// First user message per session -> POST /api/atlas/intake (governed Plan approval).
// Permission asks/replies, tool results, idle summaries -> POST /api/opencode/mirror (audit trail).
// Best-effort only: Atlas outages never block OpenCode.

const ATLAS_URL = (process.env.ATLAS_URL || "http://127.0.0.1:8080").replace(/\/$/, "");
const seenSessions = new Set();
const userMessages = new Set();

async function post(path, body) {
  try {
    const response = await fetch(`${ATLAS_URL}${path}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) console.log(`[atlas-governance] ${path} -> HTTP ${response.status}`);
  } catch (error) {
    console.log(`[atlas-governance] ${path} unreachable: ${error.message}`);
  }
}

function trimText(value, limit) {
  if (value === undefined || value === null) return "";
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
}

function pick(source, keys) {
  const detail = {};
  for (const key of keys) {
    const value = source[key];
    if (value !== undefined && value !== null && value !== "") detail[key] = trimText(value, 400);
  }
  return detail;
}

function sessionIdOf(properties) {
  return properties.sessionID || properties.part?.sessionID || properties.info?.sessionID || "";
}

export const AtlasGovernance = async () => ({
  event: async ({ event }) => {
    const type = event.type || "";
    const props = event.properties || {};

    if (type === "message.updated") {
      const info = props.info || {};
      if (info.role === "user" && info.sessionID) userMessages.add(info.id);
      return;
    }

    if (type === "message.part.updated") {
      const part = props.part || {};
      if (part.type !== "text") return;
      const sessionID = sessionIdOf(props);
      if (!sessionID || seenSessions.has(sessionID)) return;
      const messageID = part.messageID || "";
      if (messageID && !userMessages.has(messageID)) return;
      seenSessions.add(sessionID);
      const raw = trimText(part.text ?? "", 20000);
      const text = raw.replace(/^"+/, "").replace(/"+$/, "").replace(/\\n/g, "\n").trim();
      if (text.length < 5) return;
      await post("/api/atlas/intake", { title: trimText(text, 180), prompt: text });
      return;
    }

    let kind = null;
    if (type === "permission.asked") kind = "permission_asked";
    else if (type === "permission.replied") kind = "permission_replied";
    else if (type === "session.tool.success" || type.startsWith("tool.success")) kind = "tool_success";
    else if (type === "session.tool.failed" || type.startsWith("tool.failed")) kind = "tool_failed";
    else if (type === "session.idle") kind = "session_idle";
    if (!kind) return;

    const sessionID = sessionIdOf(props);
    if (!sessionID) return;
    const title =
      trimText(props.title ?? props.permission?.title ?? props.tool ?? props.callID ?? type, 280) || undefined;
    await post("/api/opencode/mirror", {
      session_id: sessionID,
      kind,
      title,
      detail: pick(props, ["type", "pattern", "permissionID", "callID", "tool", "response"]),
    });
  },
});
