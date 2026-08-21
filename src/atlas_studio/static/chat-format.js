(() => {
  function escapeHtml(str) {
    return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  function formatAtlasMarkdown(text) {
    if (!text) return "";
    const statusCard = tryRenderStatusCard(text);
    if (statusCard) return statusCard;
    const lines = text.split("\n");
    let html = "";
    let inCodeBlock = false;
    let codeBuffer = [];
    let codeLang = "";
    let inTable = false;
    let tableRows = [];
    let inList = false;
    let listType = "";
    let listItems = [];

    function flushList() {
      if (!inList || !listItems.length) { inList = false; return; }
      const tag = listType === "ol" ? "ol" : "ul";
      html += `<${tag} class="chat-list">${listItems.join("")}</${tag}>`;
      listItems = [];
      inList = false;
    }

    function flushTable() {
      if (!inTable || !tableRows.length) { inTable = false; return; }
      const header = tableRows[0];
      const body = tableRows.slice(2);
      html += '<div class="chat-table-wrap"><table class="chat-table"><thead><tr>';
      header.forEach(cell => { html += `<th>${inlineFormat(cell.trim())}</th>`; });
      html += "</tr></thead><tbody>";
      body.forEach(row => {
        html += "<tr>";
        row.forEach(cell => { html += `<td>${inlineFormat(cell.trim())}</td>`; });
        html += "</tr>";
      });
      html += "</tbody></table></div>";
      tableRows = [];
      inTable = false;
    }

    function inlineFormat(s) {
      s = s.replace(/`([^`]+)`/g, '<code class="chat-inline-code">$1</code>');
      s = s.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
      s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
      s = s.replace(/\*(.+?)\*/g, "<em>$1</em>");
      s = s.replace(/~~(.+?)~~/g, "<del>$1</del>");
      s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a class="chat-link" href="$2" target="_blank" rel="noopener">$1</a>');
      return s;
    }

    function tryRenderStatusCard(t) {
      if (t.length > 2500 || t.includes("```")) return null;
      const pair = /^([A-Za-z][\w /()&+'-]{1,40}):\s*(.+?)\.?\s*$/;
      const rows = [];
      for (const chunk of t.split(/\.\s+(?=[A-Z])|\n+/)) {
        const m = pair.exec(chunk.trim());
        if (!m) return null;
        rows.push([m[1].trim(), m[2].trim()]);
      }
      if (rows.length < 3) return null;
      let html = '<div class="chat-status-card"><div class="chat-status-head"><span class="dot"></span>PLATFORM STATUS</div>';
      for (const [k, v] of rows) {
        const s = v.toLowerCase();
        const tone = /fail|critical|blocker|error|down|urgent/.test(s) ? "bad"
          : /pending|in progress|awaiting|queued|review/.test(s) ? "warn" : "ok";
        html += `<div class="chat-status-row"><span class="k">${escapeHtml(k)}</span><span class="v ${tone}">${inlineFormat(escapeHtml(v))}</span></div>`;
      }
      return html + "</div>";
    }

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];

      if (line.startsWith("```")) {
        if (inCodeBlock) {
          html += `<pre class="chat-code-block"><code>${escapeHtml(codeBuffer.join("\n"))}</code></pre>`;
          codeBuffer = [];
          inCodeBlock = false;
        } else {
          flushList(); flushTable();
          inCodeBlock = true;
          codeLang = line.slice(3).trim();
        }
        continue;
      }
      if (inCodeBlock) { codeBuffer.push(line); continue; }

      if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
        flushList();
        const cells = line.trim().slice(1, -1).split("|");
        if (!inTable) { inTable = true; tableRows = []; }
        tableRows.push(cells);
        continue;
      } else if (inTable) {
        flushTable();
      }

      const headingMatch = line.match(/^(#{1,6})\s+(.*)/);
      if (headingMatch) {
        flushList();
        const level = headingMatch[1].length;
        html += `<h${level} class="chat-heading chat-h${level}">${inlineFormat(escapeHtml(headingMatch[2]))}</h${level}>`;
        continue;
      }

      if (/^(-{3,}|\*{3,}|_{3,})\s*$/.test(line.trim())) {
        flushList();
        html += '<hr class="chat-divider">';
        continue;
      }

      const bulletMatch = line.match(/^(\s*)([-*+])\s+(.*)/);
      if (bulletMatch) {
        if (!inList || listType !== "ul") { flushList(); inList = true; listType = "ul"; }
        listItems.push(`<li>${inlineFormat(escapeHtml(bulletMatch[3]))}</li>`);
        continue;
      }

      const olMatch = line.match(/^(\s*)(\d+[.)]\s+)(.*)/);
      if (olMatch) {
        if (!inList || listType !== "ol") { flushList(); inList = true; listType = "ol"; }
        listItems.push(`<li>${inlineFormat(escapeHtml(olMatch[3]))}</li>`);
        continue;
      }

      const quoteMatch = line.match(/^>\s*(.*)/);
      if (quoteMatch) {
        flushList();
        html += `<blockquote class="chat-blockquote">${inlineFormat(escapeHtml(quoteMatch[1]))}</blockquote>`;
        continue;
      }

      if (line.trim() === "") {
        flushList();
        html += '<div class="chat-spacer"></div>';
        continue;
      }

      flushList();
      html += `<p class="chat-para">${inlineFormat(escapeHtml(line))}</p>`;
    }

    flushList();
    flushTable();
    if (inCodeBlock && codeBuffer.length) {
      html += `<pre class="chat-code-block"><code>${escapeHtml(codeBuffer.join("\n"))}</code></pre>`;
    }

    return html;
  }

  window.AtlasFormat = { render: formatAtlasMarkdown };
})();
