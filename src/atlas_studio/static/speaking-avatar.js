import { TalkingHead } from "talkinghead";
import { HeadTTS } from "headtts";

let head;
let speech;
let ready = false;
let enabled = false;
let lastResponse = "Hello. I am Atlas, running locally inside Atlas Studio.";

const stage = document.querySelector(".worker-image-wrap");
const profile = document.querySelector(".worker-profile");
const canvas = document.getElementById("workerCanvas");

const host = document.createElement("div");
host.id = "speakingAvatar";
host.hidden = true;
stage.append(host);

const controls = document.createElement("div");
controls.className = "speech-controls";
controls.innerHTML = `<button id="enableSpeakingAvatar" type="button">Enable speaking avatar</button>
  <button id="speakAtlas" type="button" disabled>Speak latest response</button>
  <small id="speechStatus">CC0 MPFB rig · local Kokoro voice · Atlas photo customization pending</small>`;
profile.insertBefore(controls, document.getElementById("chatWithWorker"));

const status = document.getElementById("speechStatus");
const enableButton = document.getElementById("enableSpeakingAvatar");
const speakButton = document.getElementById("speakAtlas");

function wsEndpoint() {
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${location.hostname}:8882/`;
}

async function initialize() {
  if (ready) return;
  enableButton.disabled = true;
  status.textContent = "Loading the local rigged avatar…";
  host.hidden = false;
  canvas.style.opacity = "0";
  try {
    head = new TalkingHead(host, {
      ttsEndpoint: "N/A",
      lipsyncModules: [],
      cameraView: "full",
      cameraRotateEnable: true,
      modelFPS: 30,
      mixerGainSpeech: 2
    });
    await head.showAvatar({
      url: "/static/avatars/mpfb-speaking.glb",
      body: "F",
      avatarMood: "neutral",
      lipsyncLang: "en"
    }, event => {
      if (event.lengthComputable) status.textContent = `Loading speaking avatar ${Math.round(event.loaded / event.total * 100)}%`;
    });
    head.setView("full");
    speech = new HeadTTS({
      endpoints: [wsEndpoint()],
      languages: ["en-us"],
      voices: ["af_bella"],
      audioCtx: head.audioCtx,
      workerModule: "/static/vendor/headtts/modules/worker-tts.mjs",
      dictionaryURL: "/static/vendor/headtts/dictionaries/"
    });
    speech.onmessage = message => {
      if (message.type === "audio") head.speakAudio(message.data, { isRaw: true });
      if (message.type === "error") status.textContent = message.data?.error || "Local speech failed";
    };
    await speech.connect();
    await speech.setup({ voice: "af_bella", language: "en-us", speed: 1, audioEncoding: "wav" });
    ready = enabled = true;
    speakButton.disabled = false;
    enableButton.textContent = "Use static avatar";
    status.textContent = "Speaking avatar ready · local Kokoro + viseme lip-sync";
  } catch (error) {
    host.hidden = true;
    canvas.style.opacity = "1";
    enableButton.disabled = false;
    status.textContent = `Speaking avatar unavailable: ${error.message}`;
  }
}

enableButton.addEventListener("click", async () => {
  if (!ready) return initialize();
  enabled = !enabled;
  host.hidden = !enabled;
  canvas.style.opacity = enabled ? "0" : "1";
  enableButton.textContent = enabled ? "Use static avatar" : "Enable speaking avatar";
});

speakButton.addEventListener("click", async () => {
  if (!ready) return;
  status.textContent = "Atlas is synthesizing speech locally…";
  try {
    await speech.synthesize({ input: lastResponse.slice(0, 500) });
    status.textContent = "Speaking avatar ready · local Kokoro + viseme lip-sync";
  } catch (error) {
    status.textContent = `Local speech failed: ${error.message}`;
  }
});

window.addEventListener("atlas:response", event => {
  if (event.detail?.text) lastResponse = event.detail.text;
});

document.addEventListener("visibilitychange", () => {
  if (!head) return;
  document.visibilityState === "visible" ? head.start() : head.stop();
});
