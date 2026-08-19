(() => {
  if (document.querySelector(".atlas-widget-root")) return;

  const widgetScript = document.currentScript;
  const assetOrigin = widgetScript?.src ? new URL(widgetScript.src, location.href).origin : location.origin;
  const assetUrl = path => `${assetOrigin}${path}`;

  const root = document.createElement("div");
  root.className = "atlas-widget-root";
  root.dataset.state = "standby";
  root.innerHTML = `
    <button class="atlas-widget-backdrop" type="button" tabindex="-1" aria-label="Close Atlas conversation"></button>
    <aside class="atlas-widget-drawer" role="dialog" aria-modal="false" aria-label="Atlas conversation" aria-hidden="true">
      <button class="atlas-widget-close" type="button" aria-label="Close Atlas conversation">&times;</button>
      <iframe title="Atlas conversation" allow="microphone; autoplay" data-src="${assetUrl("/static/atlas-chat-panel.html")}"></iframe>
    </aside>
    <button class="atlas-widget-launcher" type="button" aria-label="Open Atlas conversation" aria-expanded="false">
      <img src="${assetUrl("/static/avatars/references/atlas_portrait.png")}" alt="Atlas">
      <span class="atlas-widget-status" aria-hidden="true"></span>
      <span class="atlas-widget-label">Talk with Atlas</span>
    </button>`;
  document.body.appendChild(root);
  document.body.classList.add("atlas-widget-enabled");

  const launcher = root.querySelector(".atlas-widget-launcher");
  const drawer = root.querySelector(".atlas-widget-drawer");
  const frame = root.querySelector("iframe");
  const closeButton = root.querySelector(".atlas-widget-close");
  const backdrop = root.querySelector(".atlas-widget-backdrop");
  const voiceLaunchers = [...document.querySelectorAll("[data-open-atlas-voice]")];
  let panelReady = false;
  let pendingVoiceActivation = false;

  const postVoiceActivation = () => {
    if (!panelReady || !frame.contentWindow) return;
    try {
      if (frame.contentWindow.AtlasVoice?.activate) {
        pendingVoiceActivation = false;
        frame.contentWindow.AtlasVoice.activate();
        return;
      }
    } catch (_) {
      // Cross-origin surfaces use the postMessage fallback below.
    }
    pendingVoiceActivation = false;
    frame.contentWindow.postMessage({ type: "atlas:activate", source: "command-dashboard" }, assetOrigin);
  };

  frame.addEventListener("load", () => {
    panelReady = true;
    if (pendingVoiceActivation) postVoiceActivation();
  });

  const open = () => {
    if (!frame.src) frame.src = frame.dataset.src;
    root.classList.add("is-open");
    launcher.setAttribute("aria-expanded", "true");
    drawer.setAttribute("aria-hidden", "false");
    closeButton.focus({ preventScroll: true });
  };

  const close = () => {
    pendingVoiceActivation = false;
    frame.contentWindow?.postMessage({ type: "atlas:deactivate" }, assetOrigin);
    root.classList.remove("is-open");
    launcher.setAttribute("aria-expanded", "false");
    drawer.setAttribute("aria-hidden", "true");
    launcher.focus({ preventScroll: true });
  };

  const toggle = () => root.classList.contains("is-open") ? close() : open();
  const openVoice = () => {
    pendingVoiceActivation = true;
    open();
    if (panelReady) postVoiceActivation();
  };
  launcher.addEventListener("click", toggle);
  closeButton.addEventListener("click", close);
  backdrop.addEventListener("click", close);
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && root.classList.contains("is-open")) close();
  });
  window.addEventListener("message", event => {
    if (event.origin !== assetOrigin || event.source !== frame.contentWindow) return;
    if (event.data?.type === "atlas:state") {
      root.dataset.state = event.data.state || "standby";
      launcher.title = event.data.label ? `Atlas: ${event.data.label.toLowerCase()}` : "Talk with Atlas";
      const voiceActive = ["listening", "hearing", "thinking", "speaking"].includes(event.data.state);
      voiceLaunchers.forEach(button => {
        button.classList.toggle("is-live", voiceActive);
        const label = button.querySelector("[data-voice-label]");
        if (label) label.textContent = event.data.state === "speaking" ? "Atlas is speaking" : voiceActive ? "Voice session active" : event.data.state === "error" ? "Microphone needs attention" : "Talk to Atlas";
      });
    }
    if (event.data?.type === "atlas:close") close();
    if (event.data?.type === "atlas:approval-completed") {
      window.AtlasDeveloperFeatures?.refreshLifecycleGuide?.();
      window.AtlasDeveloperFeatures?.refreshPlans?.();
    }
  });

  window.AtlasChat = { open, openVoice, close, toggle };
  document.querySelectorAll("[data-open-atlas-chat]").forEach(button => button.addEventListener("click", open));
  voiceLaunchers.forEach(button => button.addEventListener("click", openVoice));
  const workerChatButton = document.getElementById("chatWithWorker");
  if (workerChatButton) workerChatButton.onclick = open;

  const preloadPanel = () => {
    if (document.body.classList.contains("command-active")) return;
    if (!frame.src) frame.src = frame.dataset.src;
  };
  if (document.readyState === "complete") window.setTimeout(preloadPanel, 350);
  else window.addEventListener("load", () => window.setTimeout(preloadPanel, 350), { once: true });
})();
