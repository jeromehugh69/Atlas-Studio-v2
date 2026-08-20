import { prepareSpeechText } from "./speech-text.js";

const stage = document.getElementById("stage");
const avatarState = document.getElementById("avatarState");
const micButton = document.getElementById("micButton");
const sessionHint = document.getElementById("sessionHint");
const transcript = document.getElementById("transcript");
const composer = document.getElementById("composer");
const textInput = document.getElementById("textInput");
const fileInput = document.getElementById("fileInput");
const codeInput = document.getElementById("codeInput");
const attachButton = document.getElementById("attachButton");
const codeButton = document.getElementById("codeButton");
const attachmentTray = document.getElementById("attachmentTray");
const clearButton = document.getElementById("clearButton");
const voiceElapsed = document.getElementById("voiceElapsed");
const voiceStatus = document.getElementById("voiceStatus");
const voiceSessionLabel = document.getElementById("voiceSessionLabel");
const muteButton = document.getElementById("muteButton");
const endVoiceButton = document.getElementById("endVoiceButton");
const contextMeter = document.getElementById("contextMeter");
const contextUsage = document.getElementById("contextUsage");
const contextStatus = document.getElementById("contextStatus");
const voiceReadyStatus = document.getElementById("voiceReadyStatus");
const atlasApprovalDialog = document.getElementById("atlasApprovalDialog");
const atlasApprovalForm = document.getElementById("atlasApprovalForm");
const atlasApprovalPurpose = document.getElementById("atlasApprovalPurpose");
const atlasApprovalChallenge = document.getElementById("atlasApprovalChallenge");
const atlasApprovalPasscode = document.getElementById("atlasApprovalPasscode");
const atlasApprovalError = document.getElementById("atlasApprovalError");

const TURN_SILENCE_MS = 650;
const MIN_SPEECH_FRAMES = 2;
const INPUT_THRESHOLD = 0.026;
const MAX_IDLE_RECORDING_MS = 30000;

let sessionActive = false;
let turnBusy = false;
let microphoneStream;
let inputContext;
let inputAnalyser;
let recorder;
let recorderChunks = [];
let vadTimer;
let heardSpeech = false;
let speechFrames = 0;
let lastVoiceAt = 0;
let recordingStartedAt = 0;
let playback;
let playbackContext;
let atlasAgentId;
let pendingFiles = [];
let sessionGeneration = 0;
let taskSocket;
let socketReconnectTimer;
let activeTaskId;
let activeSpeechStream;
let sessionStartedAt = 0;
let sessionClock;
let microphoneMuted = false;
let conversationTurns = [];
let pendingAtlasApproval;
const taskWaiters = new Map();
const parentOrigin = (() => {
  try { return document.referrer ? new URL(document.referrer).origin : location.origin; }
  catch (_) { return location.origin; }
})();

function setAvatarMode(mode, label, hint) {
  stage.classList.remove("listening", "hearing", "thinking", "speaking", "error");
  if (mode && mode !== "standby") stage.classList.add(mode);
  document.body.dataset.atlasState = mode || "standby";
  avatarState.lastChild.textContent = label;
  if (hint) sessionHint.textContent = hint;
  const voiceLabels = {
    standby: "Microphone standing by",
    listening: microphoneMuted ? "Microphone muted" : "Listening...",
    hearing: "Listening...",
    thinking: "Atlas is processing...",
    speaking: "Atlas is speaking...",
    error: "Voice worker unavailable",
  };
  voiceStatus.textContent = voiceLabels[mode || "standby"] || label;
  voiceSessionLabel.textContent = sessionActive ? "LIVE VOICE SESSION" : "VOICE READY";
  voiceReadyStatus.textContent = mode === "error" ? "Offline" : mode === "speaking" ? "Speaking" : sessionActive ? "Live" : "Ready";
  window.parent.postMessage({ type: "atlas:state", state: mode || "standby", label }, parentOrigin);
}

function addMessage(role, text, pending = false) {
  const article = document.createElement("article");
  article.className = `message ${role === "user" ? "user-message" : role === "system" ? "system-message" : "atlas-message"}${pending ? " pending-message" : ""}`;
  if (role !== "system") {
    const header = document.createElement("header");
    header.className = "message-meta";
    const avatar = document.createElement("span");
    avatar.className = "message-avatar";
    avatar.textContent = role === "user" ? "Y" : "A";
    const identity = document.createElement("span");
    const name = document.createElement("strong");
    name.textContent = role === "user" ? "YOU" : "ATLAS";
    const time = document.createElement("time");
    time.textContent = new Intl.DateTimeFormat([], { hour: "2-digit", minute: "2-digit" }).format(new Date());
    identity.append(name, time);
    const state = document.createElement("span");
    state.className = "message-state";
    state.textContent = role === "user" ? "ENGINEER INPUT" : pending ? "PROCESSING" : "LOCAL RESPONSE";
    header.append(avatar, identity, state);
    article.appendChild(header);
  }
  const body = document.createElement("div");
  body.className = "message-body";
  if (role === "atlas" && window.AtlasFormat) {
    body.innerHTML = AtlasFormat.render(text);
  } else {
    body.textContent = text;
  }
  article.appendChild(body);
  if (role === "atlas") {
    const tools = document.createElement("footer");
    tools.className = "message-tools";
    for (const label of ["LOCAL MODEL", "WORKSPACE", "READ-ONLY"]) {
      const tag = document.createElement("span");
      tag.textContent = label;
      tools.appendChild(tag);
    }
    const details = document.createElement("details");
    details.className = "response-context";
    const summary = document.createElement("summary");
    summary.textContent = "View response context";
    const context = document.createElement("p");
    context.textContent = "Context includes permitted local workspace information, attached files, and read-only tools. Private model reasoning is not displayed.";
    details.append(summary, context);
    article.append(tools, details);
  }
  transcript.appendChild(article);
  transcript.scrollTop = transcript.scrollHeight;
  return article;
}

function setPendingMessage(node, text, complete = false) {
  if (complete) node.classList.remove("pending-message");
  const body = node.querySelector(".message-body");
  const isAtlas = node.classList.contains("atlas-message");
  if (isAtlas && window.AtlasFormat) {
    body.innerHTML = AtlasFormat.render(text);
  } else {
    body.textContent = text;
  }
  const state = node.querySelector(".message-state");
  if (state) state.textContent = complete ? "LOCAL RESPONSE" : "STREAMING";
  transcript.scrollTop = transcript.scrollHeight;
}

function formatElapsed(milliseconds) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

function startSessionClock() {
  window.clearInterval(sessionClock);
  sessionStartedAt = Date.now();
  voiceElapsed.textContent = "00:00";
  sessionClock = window.setInterval(() => {
    voiceElapsed.textContent = formatElapsed(Date.now() - sessionStartedAt);
  }, 1000);
}

function stopSessionClock() {
  window.clearInterval(sessionClock);
  sessionClock = undefined;
  sessionStartedAt = 0;
  voiceElapsed.textContent = "00:00";
}

function taskSocketUrl() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.host}/api/ws`;
}

function settleTaskWaiter(taskId, task, error) {
  const waiter = taskWaiters.get(taskId);
  if (!waiter) return;
  taskWaiters.delete(taskId);
  window.clearTimeout(waiter.timeout);
  window.clearTimeout(waiter.pollTimer);
  if (error) waiter.reject(error);
  else waiter.resolve(task);
}

function handleTaskEvent(event) {
  const waiter = taskWaiters.get(event.task_id);
  if (!waiter) return;
  if (event.type === "task.delta") {
    waiter.onUpdate(event.text || "");
    return;
  }
  if (event.type === "task.progress" && !["queued", "running"].includes(event.status)) {
    if (event.status === "completed") waiter.onUpdate(event.message || "");
    settleTaskWaiter(event.task_id, {
      id: event.task_id,
      status: event.status,
      output: event.message || "",
    });
  }
}

function connectTaskSocket() {
  window.clearTimeout(socketReconnectTimer);
  if (taskSocket && [WebSocket.OPEN, WebSocket.CONNECTING].includes(taskSocket.readyState)) return;
  taskSocket = new WebSocket(taskSocketUrl());
  taskSocket.onmessage = message => {
    try {
      handleTaskEvent(JSON.parse(message.data));
    } catch (_) {
      // Ignore malformed local events and allow the polling fallback to recover.
    }
  };
  taskSocket.onclose = () => {
    socketReconnectTimer = window.setTimeout(connectTaskSocket, 800);
  };
  taskSocket.onerror = () => taskSocket.close();
}

function bestRecorderOptions() {
  const candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"];
  const mimeType = candidates.find(type => window.MediaRecorder?.isTypeSupported(type));
  return mimeType ? { mimeType } : undefined;
}

async function unlockPlayback() {
  playbackContext ||= new AudioContext();
  if (playbackContext.state === "suspended") await playbackContext.resume();
}

async function activateSession() {
  if (sessionActive) return;
  try {
    await unlockPlayback();
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      throw new Error("This browser does not provide microphone recording.");
    }
    microphoneStream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    inputContext = new AudioContext();
    const source = inputContext.createMediaStreamSource(microphoneStream);
    inputAnalyser = inputContext.createAnalyser();
    inputAnalyser.fftSize = 1024;
    inputAnalyser.smoothingTimeConstant = 0.32;
    source.connect(inputAnalyser);
    sessionGeneration += 1;
    sessionActive = true;
    document.body.classList.add("session-active");
    stage.classList.add("active");
    stage.setAttribute("aria-pressed", "true");
    micButton.classList.add("active");
    micButton.querySelector("strong").textContent = "Voice Test Live";
    muteButton.disabled = false;
    endVoiceButton.disabled = false;
    startSessionClock();
    await beginListening(sessionGeneration);
  } catch (error) {
    setAvatarMode("error", "MICROPHONE BLOCKED", error.message || "Allow microphone access in the browser, then click Atlas again.");
  }
}

function stopRecorder(discard = false) {
  clearInterval(vadTimer);
  vadTimer = undefined;
  if (!recorder || recorder.state === "inactive") return;
  if (discard) recorder.onstop = null;
  recorder.stop();
}

function deactivateSession() {
  sessionGeneration += 1;
  sessionActive = false;
  turnBusy = false;
  activeSpeechStream?.cancel();
  if (activeTaskId) {
    void fetch(`/api/tasks/${activeTaskId}/cancel`, { method: "POST" }).catch(() => {});
  }
  stopRecorder(true);
  microphoneStream?.getTracks().forEach(track => track.stop());
  microphoneStream = undefined;
  microphoneMuted = false;
  inputContext?.close().catch(() => {});
  inputContext = undefined;
  inputAnalyser = undefined;
  if (playback) {
    playback.pause();
    playback.onended?.();
  }
  playback = undefined;
  document.body.classList.remove("session-active");
  stage.classList.remove("active", "listening", "hearing", "thinking", "speaking", "error");
  stage.style.setProperty("--input", "0");
  stage.setAttribute("aria-pressed", "false");
  micButton.classList.remove("active");
  micButton.querySelector("strong").textContent = "Start Voice Test";
  muteButton.disabled = true;
  muteButton.textContent = "Mute";
  endVoiceButton.disabled = true;
  document.body.classList.remove("voice-muted");
  stopSessionClock();
  setAvatarMode("standby", "AI ONLINE", "Click Atlas or the microphone to begin another conversation.");
}

function toggleMute() {
  if (!sessionActive || !microphoneStream) return;
  microphoneMuted = !microphoneMuted;
  microphoneStream.getAudioTracks().forEach(track => { track.enabled = !microphoneMuted; });
  muteButton.textContent = microphoneMuted ? "Unmute" : "Mute";
  document.body.classList.toggle("voice-muted", microphoneMuted);
  setAvatarMode(
    microphoneMuted ? "standby" : "listening",
    microphoneMuted ? "MIC MUTED" : "LISTENING",
    microphoneMuted ? "Atlas will pause listening until you unmute the microphone." : "Speak naturally. Atlas will respond after you pause.",
  );
}

async function beginListening(generation = sessionGeneration) {
  if (!sessionActive || turnBusy || generation !== sessionGeneration || !microphoneStream || !inputAnalyser) return;
  recorderChunks = [];
  heardSpeech = false;
  speechFrames = 0;
  lastVoiceAt = 0;
  recordingStartedAt = performance.now();
  recorder = new MediaRecorder(microphoneStream, bestRecorderOptions());
  recorder.ondataavailable = event => { if (event.data.size) recorderChunks.push(event.data); };
  recorder.onstop = async () => {
    clearInterval(vadTimer);
    if (!sessionActive || generation !== sessionGeneration) return;
    if (!heardSpeech || recorderChunks.length === 0) {
      window.setTimeout(() => beginListening(generation), 120);
      return;
    }
    const blob = new Blob(recorderChunks, { type: recorder.mimeType || "audio/webm" });
    await processVoiceTurn(blob, generation);
  };
  recorder.start(250);
  setAvatarMode("listening", "LISTENING", "Speak naturally. Atlas will respond after you pause.");

  const samples = new Uint8Array(inputAnalyser.fftSize);
  vadTimer = window.setInterval(() => {
    if (!sessionActive || generation !== sessionGeneration || !inputAnalyser) return;
    inputAnalyser.getByteTimeDomainData(samples);
    let energy = 0;
    for (const value of samples) {
      const normalized = (value - 128) / 128;
      energy += normalized * normalized;
    }
    const rms = Math.sqrt(energy / samples.length);
    const visualLevel = Math.min(1, rms * 9);
    stage.style.setProperty("--input", visualLevel.toFixed(3));
    const now = performance.now();
    if (rms >= INPUT_THRESHOLD) {
      speechFrames += 1;
      if (speechFrames >= MIN_SPEECH_FRAMES) {
        heardSpeech = true;
        lastVoiceAt = now;
        stage.classList.add("hearing");
        avatarState.lastChild.textContent = "ATLAS · HEARING YOU";
      }
    } else {
      speechFrames = 0;
      stage.classList.remove("hearing");
      if (heardSpeech && now - lastVoiceAt >= TURN_SILENCE_MS) stopRecorder();
      if (!heardSpeech && now - recordingStartedAt >= MAX_IDLE_RECORDING_MS) stopRecorder();
    }
  }, 90);
}

async function transcribe(blob) {
  const suffix = blob.type.includes("ogg") ? "ogg" : "webm";
  const data = new FormData();
  data.append("audio", blob, `atlas-turn.${suffix}`);
  const response = await fetch("/api/speech/transcribe", { method: "POST", body: data });
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Local transcription failed.");
  return (await response.json()).text?.trim() || "";
}

async function getAtlasAgent() {
  if (atlasAgentId) return atlasAgentId;
  const response = await fetch("/api/agents");
  if (!response.ok) throw new Error("Atlas is unavailable.");
  const agents = await response.json();
  const atlas = agents.find(agent => agent.name === "Atlas");
  if (!atlas) throw new Error("Atlas is not configured.");
  atlasAgentId = atlas.id;
  return atlasAgentId;
}

async function uploadPendingFiles() {
  if (!pendingFiles.length) return [];
  const uploads = [];
  for (const file of pendingFiles) {
    const data = new FormData();
    data.append("file", file);
    const response = await fetch("/api/artifacts", { method: "POST", body: data });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || `Could not upload ${file.name}.`);
    uploads.push(await response.json());
  }
  pendingFiles = [];
  renderAttachments();
  return uploads;
}

function showAtlasApproval(approval) {
  pendingAtlasApproval = approval;
  atlasApprovalPurpose.textContent = approval.purpose;
  atlasApprovalChallenge.textContent = approval.challenge_code;
  atlasApprovalPasscode.value = "";
  atlasApprovalError.textContent = "";
  atlasApprovalDialog.showModal();
  window.setTimeout(() => atlasApprovalPasscode.focus(), 40);
}

function closeAtlasApproval() {
  if (pendingAtlasApproval?.delegation && pendingAtlasApproval?.reject) {
    pendingAtlasApproval.resolve(false);
  }
  pendingAtlasApproval = undefined;
  if (atlasApprovalDialog.open) atlasApprovalDialog.close();
}

atlasApprovalForm.addEventListener("submit", async event => {
  event.preventDefault();
  if (!pendingAtlasApproval) return;
  atlasApprovalError.textContent = "";
  const approval = pendingAtlasApproval;

  if (approval.delegation) {
    if (atlasApprovalPasscode.value !== approval.challenge_code) {
      atlasApprovalError.textContent = "Incorrect passcode. Try again.";
      atlasApprovalPasscode.select();
      return;
    }
    closeAtlasApproval();
    approval.resolve(true);
    return;
  }

  try {
    const decision = await fetch(`/api/approvals/${approval.id}/decision`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decision: "approved", user_authorized: true, approval_passcode: atlasApprovalPasscode.value, reason: "Approved directly from the Atlas request popup" }),
    });
    if (!decision.ok) throw new Error((await decision.json().catch(() => ({}))).detail || "The approval code was not accepted.");
    const response = await fetch(`/api/atlas/intake/${approval.id}/approve`, { method: "POST" });
    if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "The governed request could not be created.");
    const plan = await response.json();
    closeAtlasApproval();
    addMessage("atlas", `Approved. I created the governed change request “${plan.title}” and sent it to Forge and the required review agents. You will receive the next-step notification here in Atlas Studio.`);
    window.parent.postMessage({ type: "atlas:approval-completed", planId: plan.id }, parentOrigin);
  } catch (error) {
    atlasApprovalError.textContent = error.message || "Approval failed safely. Check the code and retry.";
    atlasApprovalPasscode.select();
  }
});
document.getElementById("deferAtlasApproval").addEventListener("click", closeAtlasApproval);
document.getElementById("closeAtlasApproval").addEventListener("click", closeAtlasApproval);

function waitForTask(taskId, generation, onUpdate) {
  return new Promise((resolve, reject) => {
    const waiter = {
      resolve,
      reject,
      onUpdate,
      pollTimer: undefined,
      timeout: window.setTimeout(
        () => settleTaskWaiter(taskId, null, new Error("Atlas is still working; this turn timed out.")),
        15 * 60 * 1000,
      ),
    };
    taskWaiters.set(taskId, waiter);

    const poll = async () => {
      if (!taskWaiters.has(taskId)) return;
      if (generation !== sessionGeneration) {
        settleTaskWaiter(taskId, null, new Error("Voice conversation ended."));
        return;
      }
      try {
        const response = await fetch("/api/tasks");
        if (!response.ok) throw new Error("Atlas task status is unavailable.");
        const task = (await response.json()).find(item => item.id === taskId);
        if (task?.output && !["failed", "cancelled"].includes(task.status)) onUpdate(task.output);
        if (task && !["queued", "running"].includes(task.status)) {
          settleTaskWaiter(taskId, task);
          return;
        }
      } catch (error) {
        if (!taskSocket || taskSocket.readyState !== WebSocket.OPEN) {
          settleTaskWaiter(taskId, null, error);
          return;
        }
      }
      waiter.pollTimer = window.setTimeout(poll, 1200);
    };
    void poll();
  });
}

function readFilesAsText(files) {
  return Promise.all(
    Array.from(files).map(
      file =>
        new Promise((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => resolve({ name: file.name, content: reader.result || "" });
          reader.onerror = () => resolve({ name: file.name, content: "[unreadable]" });
          reader.readAsText(file);
        }),
    ),
  );
}

async function requestAtlas(text, generation = sessionGeneration, onUpdate = () => {}) {
  let attachmentContext = "";
  if (pendingFiles.length) {
    const files = await readFilesAsText(pendingFiles);
    attachmentContext = files.map(f => `--- ${f.name} ---\n${f.content}`).join("\n\n");
    if (attachmentContext.length > 32_000) attachmentContext = `${attachmentContext.slice(0, 32_000)}\n\n[Attachment context truncated.]`;
    pendingFiles = [];
    renderAttachments();
  }

  let userContent = text;
  if (attachmentContext) userContent += `\n\nLocal attachment context:\n${attachmentContext}`;

  const history = conversationTurns.map(turn => ({ role: turn.role === "user" ? "user" : "assistant", content: turn.text }));

  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: userContent, history }),
  });
  if (!response.ok) throw new Error(`Chat endpoint returned ${response.status}.`);
  const data = await response.json();
  return { id: data.task_id || "direct", status: "completed", output: data.response };
}

function createSentenceSpeaker(generation, onSpokenText) {
  let receivedText = "";
  let pendingText = "";
  let spokenText = "";
  let queue = Promise.resolve();
  let cancelled = false;
  let failure;

  const enqueue = sentence => {
    const clean = prepareSpeechText(sentence);
    if (!clean) return;
    queue = queue
      .then(async () => {
        if (cancelled) return;
        const prefix = spokenText ? `${spokenText} ` : "";
        await speak(clean, generation, partial => onSpokenText(`${prefix}${partial}`.trim()));
        spokenText = `${prefix}${clean}`.trim();
        onSpokenText(spokenText);
        await new Promise(resolve => window.setTimeout(resolve, clean.length < 70 ? 90 : 135));
      })
      .catch(error => {
        failure ||= error;
        cancelled = true;
      });
  };

  const drain = final => {
    while (pendingText.trim()) {
      const sentence = pendingText.match(/^([\s\S]*?[.!?](?:["')\]]*))(?:\s+|$)/);
      if (sentence) {
        enqueue(sentence[1]);
        pendingText = pendingText.slice(sentence[0].length);
        continue;
      }
      if (!final && pendingText.length >= 180) {
        const windowText = pendingText.slice(0, 180);
        const punctuation = Math.max(windowText.lastIndexOf(","), windowText.lastIndexOf(";"), windowText.lastIndexOf(":"));
        const whitespace = windowText.lastIndexOf(" ");
        const splitAt = punctuation >= 80 ? punctuation + 1 : whitespace >= 100 ? whitespace : 180;
        enqueue(pendingText.slice(0, splitAt));
        pendingText = pendingText.slice(splitAt);
        continue;
      }
      if (final) {
        enqueue(pendingText);
        pendingText = "";
      }
      break;
    }
  };

  const update = fullText => {
    if (!fullText || fullText === receivedText || receivedText.startsWith(fullText)) return;
    if (!fullText.startsWith(receivedText)) {
      receivedText = fullText;
      return;
    }
    pendingText += fullText.slice(receivedText.length);
    receivedText = fullText;
    drain(false);
  };

  return {
    update,
    async finish(fullText) {
      update(fullText);
      drain(true);
      await queue;
      if (failure) throw failure;
    },
    cancel() {
      cancelled = true;
      pendingText = "";
      if (playback) {
        playback.pause();
        playback.onended?.();
      }
    },
  };
}

async function speak(text, generation, onProgress = () => {}) {
  if (generation !== sessionGeneration) throw new Error("Voice conversation ended.");
  const spokenText = prepareSpeechText(text);
  if (!spokenText) return;
  setAvatarMode("speaking", "PREPARING VOICE", "Atlas is preparing her local voice.");
  const response = await fetch("/api/speech/synthesize", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: spokenText.slice(0, 4000) }),
  });
  if (!response.ok) throw new Error((await response.json().catch(() => ({}))).detail || "Atlas voice is unavailable.");
  const audioUrl = URL.createObjectURL(await response.blob());
  playback?.pause();
  playback = new Audio(audioUrl);
  playback.onplay = () => setAvatarMode("speaking", "SPEAKING", "Atlas is speaking. Listening resumes automatically afterward.");
  await new Promise((resolve, reject) => {
    const words = [...spokenText.matchAll(/\S+/g)];
    let frame;
    const showSpokenWords = () => {
      if (generation !== sessionGeneration) return;
      const duration = Number.isFinite(playback.duration) && playback.duration > 0 ? playback.duration : 0;
      const ratio = duration ? Math.min(1, playback.currentTime / duration) : 0;
      const count = playback.currentTime > 0 ? Math.max(1, Math.floor(ratio * words.length)) : 0;
      const lastWord = words[Math.min(count, words.length) - 1];
      if (lastWord) onProgress(spokenText.slice(0, lastWord.index + lastWord[0].length));
      if (!playback.ended && !playback.paused) frame = window.requestAnimationFrame(showSpokenWords);
    };
    const cleanup = () => window.cancelAnimationFrame(frame);
    playback.onended = () => {
      cleanup();
      if (generation === sessionGeneration) onProgress(spokenText);
      resolve();
    };
    playback.onerror = () => {
      cleanup();
      reject(new Error("Atlas audio playback failed."));
    };
    playback.ontimeupdate = showSpokenWords;
    playback.play().catch(reject);
  });
  URL.revokeObjectURL(audioUrl);
}

async function delegateToAgent(delegation, originalPrompt) {
  return new Promise((resolve, reject) => {
    const purpose = `Atlas recommends delegating to ${delegation.agent}: "${delegation.task}"`;
    pendingAtlasApproval = {
      purpose,
      challenge_code: String(Math.floor(100000 + Math.random() * 900000)),
      delegation,
      originalPrompt,
      resolve,
      reject,
    };
    atlasApprovalPurpose.textContent = purpose;
    atlasApprovalChallenge.textContent = pendingAtlasApproval.challenge_code;
    atlasApprovalPasscode.value = "";
    atlasApprovalError.textContent = "";
    atlasApprovalDialog.showModal();
    window.setTimeout(() => atlasApprovalPasscode.focus(), 40);
  });
}

async function runTurn(text, generation = sessionGeneration, resumeAfter = sessionActive) {
  if (!text.trim() || turnBusy) return;
  turnBusy = true;
  stopRecorder(true);
  addMessage("user", text.trim());
  let pending;
  const ensurePending = () => {
    pending ||= addMessage("atlas", "", true);
    return pending;
  };
  const sentenceSpeaker = createSentenceSpeaker(generation, spokenText => {
    if (spokenText) setPendingMessage(ensurePending(), spokenText, false);
  });
  activeSpeechStream = sentenceSpeaker;
  let streamedAnswer = "";
  setAvatarMode("thinking", "THINKING", "Atlas is thinking...");
  try {
    const task = await requestAtlas(text.trim(), generation, fullText => {
      if (!fullText) return;
      streamedAnswer = fullText;
      setPendingMessage(ensurePending(), fullText, false);
      sentenceSpeaker.update(fullText);
    });

    if (task.status === "delegation" && task.delegation) {
      const explanation = task.output || `I recommend delegating this to ${task.delegation.agent}.`;
      setPendingMessage(ensurePending(), explanation, true);
      conversationTurns.push({ role: "user", text: text.trim() }, { role: "atlas", text: explanation });
      conversationTurns = conversationTurns.slice(-8);

      addMessage("system", `Atlas recommends delegating to ${task.delegation.agent}. Approving delegation...`);
      setAvatarMode("thinking", "DELEGATING", `${task.delegation.agent} is processing through the governed lifecycle.`);

      try {
        const delegateResponse = await fetch("/api/chat/delegate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ agent_name: task.delegation.agent, prompt: task.delegation.task }),
        });
        if (!delegateResponse.ok) throw new Error((await delegateResponse.json().catch(() => ({}))).detail || "Delegation failed.");
        const createdTask = await delegateResponse.json();
        activeTaskId = createdTask.id;
        const result = await waitForTask(createdTask.id, generation, fullText => {
          if (fullText) setPendingMessage(ensurePending(), fullText, false);
        });
        const answer = result.output || `Task ${result.status}.`;
        setPendingMessage(ensurePending(), answer, true);
        conversationTurns.push({ role: "atlas", text: answer });
        conversationTurns = conversationTurns.slice(-8);
      } catch (delegateError) {
        setPendingMessage(ensurePending(), `Delegation failed: ${delegateError.message}`, true);
      }
    } else {
      const answer = task.output || streamedAnswer || `The local task ended with status ${task.status}.`;
      if (task.status !== "completed") {
        setPendingMessage(ensurePending(), answer, true);
        throw new Error(answer);
      }
      conversationTurns.push({ role: "user", text: text.trim() }, { role: "atlas", text: answer });
      conversationTurns = conversationTurns.slice(-8);
      try {
        await sentenceSpeaker.finish(answer);
        setPendingMessage(ensurePending(), answer, true);
      } catch (speechError) {
        setPendingMessage(ensurePending(), answer, true);
        setAvatarMode("error", "VOICE OFFLINE", speechError.message || "The response is available in the transcript while the local voice recovers.");
      }
    }
  } catch (error) {
    sentenceSpeaker.cancel();
    setPendingMessage(ensurePending(), error.message || "The local conversation turn failed.", true);
    setAvatarMode("error", "CONNECTION ISSUE", "Check the local speech and model services, then try again.");
  } finally {
    if (activeSpeechStream === sentenceSpeaker) activeSpeechStream = undefined;
    turnBusy = false;
    if (resumeAfter && sessionActive && generation === sessionGeneration) {
      await new Promise(resolve => window.setTimeout(resolve, 450));
      await beginListening(generation);
    } else if (!sessionActive) {
      setAvatarMode("standby", "STANDBY", "Type another message or start a voice conversation.");
    }
  }
}

async function processVoiceTurn(blob, generation) {
  if (!sessionActive || generation !== sessionGeneration) return;
  turnBusy = true;
  setAvatarMode("thinking", "TRANSCRIBING", "Whisper is transcribing your turn locally.");
  try {
    const text = await transcribe(blob);
    turnBusy = false;
    if (!text) {
      setAvatarMode("listening", "LISTENING", "I didn’t catch that. Keep speaking when you’re ready.");
      await beginListening(generation);
      return;
    }
    await runTurn(text, generation, true);
  } catch (error) {
    turnBusy = false;
    setAvatarMode("error", "SPEECH OFFLINE", error.message || "The local speech worker is unavailable.");
    if (sessionActive && generation === sessionGeneration) {
      await new Promise(resolve => window.setTimeout(resolve, 900));
      await beginListening(generation);
    }
  }
}

function toggleSession() {
  if (sessionActive) deactivateSession();
  else activateSession();
}

function renderAttachments() {
  attachmentTray.innerHTML = "";
  attachmentTray.hidden = pendingFiles.length === 0;
  pendingFiles.forEach((file, index) => {
    const chip = document.createElement("span");
    chip.className = "attachment-chip";
    const name = document.createElement("span");
    name.textContent = file.name;
    name.title = file.name;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.setAttribute("aria-label", `Remove ${file.name}`);
    remove.textContent = "×";
    remove.addEventListener("click", () => {
      pendingFiles.splice(index, 1);
      fileInput.value = "";
      codeInput.value = "";
      renderAttachments();
    });
    chip.append(name, remove);
    attachmentTray.appendChild(chip);
  });
  const context = Math.min(92, 42 + (pendingFiles.length * 8));
  contextMeter.style.width = `${context}%`;
  contextUsage.textContent = `${context}%`;
  contextStatus.textContent = `${context}%`;
}

function mergePendingFiles(fileList) {
  pendingFiles = [...pendingFiles, ...fileList].filter(
    (file, index, files) => files.findIndex(candidate => candidate.name === file.name && candidate.size === file.size) === index,
  );
  renderAttachments();
}

stage.addEventListener("click", toggleSession);
micButton.addEventListener("click", toggleSession);
attachButton.addEventListener("click", () => fileInput.click());
codeButton.addEventListener("click", () => codeInput.click());
fileInput.addEventListener("change", () => mergePendingFiles(fileInput.files));
codeInput.addEventListener("change", () => mergePendingFiles(codeInput.files));
muteButton.addEventListener("click", toggleMute);
endVoiceButton.addEventListener("click", deactivateSession);
textInput.addEventListener("keydown", event => {
  if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    composer.requestSubmit();
  }
});
composer.addEventListener("submit", async event => {
  event.preventDefault();
  const text = textInput.value.trim() || (pendingFiles.length ? "Analyze the attached files and explain the relevant findings and next actions." : "");
  if (!text) return;
  textInput.value = "";
  await unlockPlayback();
  await runTurn(text, sessionGeneration, sessionActive);
});
clearButton.addEventListener("click", () => {
  transcript.innerHTML = "";
  conversationTurns = [];
});
window.addEventListener("beforeunload", deactivateSession);
window.addEventListener("message", event => {
  if (![location.origin, parentOrigin, "http://localhost:8080"].includes(event.origin)) return;
  if (event.data?.type === "atlas:activate" && !sessionActive) activateSession();
  if (event.data?.type === "atlas:deactivate" && sessionActive) deactivateSession();
});
window.AtlasVoice = { activate: activateSession, deactivate: deactivateSession };
connectTaskSocket();
renderAttachments();
window.setInterval(() => {
  if (taskSocket?.readyState === WebSocket.OPEN) taskSocket.send("ping");
}, 20000);
