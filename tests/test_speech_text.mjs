import assert from "node:assert/strict";
import { prepareSpeechText } from "../src/atlas_studio/static/speech-text.js";


const source = `**Completed** ✅
Open [Analytics](http://localhost:8080/analytics) for the report.
User → Atlas → Forge.
\`\`\`python
print({"secret": 1})
\`\`\`
Traceback (most recent call last):
File "app.py", line 10
ConnectionError: [Errno 111] connection refused
Task ID: 0dc43348-739a-4a44-9fd9-36dbdcbe99aa`;

const spoken = prepareSpeechText(source);
assert.match(spoken, /Completed/);
assert.match(spoken, /Open Analytics for the report/);
assert.match(spoken, /User then Atlas then Forge/);
for (const forbidden of ["http", "print", "Traceback", "ConnectionError", "Errno", "0dc43348", "✅", "→", "{"]) {
  assert.equal(spoken.includes(forbidden), false, `${forbidden} should not be spoken`);
}

assert.equal(prepareSpeechText("Local model unavailable: Ollama timed out.\nConnectionError: [Errno 111]"), "");
assert.equal(prepareSpeechText("Hello Jerome. Error: HTTP 500 Internal Server Error. Atlas is ready to continue."), "Hello Jerome. Atlas is ready to continue.");
