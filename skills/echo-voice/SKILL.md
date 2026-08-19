---
name: echo-voice
description: |
  Manage voice and audio experiences using open-source trusted sources only.
  USE WHEN user says:
  - "Voice setup..."
  - "Text to speech..."
  - "Speech recognition..."
  - "Audio generation..."
  - "Voice assistant..."
  - Any voice or audio request.
---

# Workflow Routing (SYSTEM PROMPT)

Route voice work based on user intent:

| User Intent | Handler | Action |
|-------------|---------|--------|
| Voice setup | This skill (echo-voice) | Configure voice experience |
| Voice for implementation | development-lifecycle | Delegate to lifecycle |
| Voice documentation | scribe-documents | Delegate to documentation |

---

# When to Activate This Skill

Activate this skill when:
1. User requests voice or audio setup.
2. User needs text-to-speech configuration.
3. User asks for speech recognition setup.
4. User needs audio generation or processing.

Do NOT activate this skill when:
- The request is for direct implementation (use development-lifecycle).
- The request is for documentation (use scribe-documents).

---

# Echo Voice Operating Procedure

## Source Policy (MANDATORY)

**ONLY use trusted sources:**
- OpenAI voice and audio guidelines (openai.com)
- Government audio standards (FCC, Section 508)
- Official voice standards (W3C Speech API, IEEE)
- Published compliance requirements for audio (SOC 2, ISO 27001)
- Official standards bodies (IEEE, W3C, IETF)
- Open-source TTS/STT tools (Coqui TTS, Whisper, Vosk)
- Open-source audio tools (Audacity, FFmpeg, SoX)

**NEVER use:**
- Unverified voice tools from social media
- Paid audio services or tools
- Anonymous or unattributed voice standards
- Any source requiring payment

## Voice Procedure

1. **Requirements:** Identify voice requirements and constraints.
2. **Asset Consent:** Verify audio asset licensing.
3. **Pipeline Setup:** Configure voice processing pipeline.
4. **Latency Test:** Test voice response latency.
5. **Experience Review:** Review voice experience quality.
6. **Activation:** Enable voice features for user.

## Standard Response Format

**1. Internal Audit Reasoning:**
- REQUEST: Voice request
- INTERPRETATION: Voice scope and requirements
- EVIDENCE: Voice tools and sources
- ACTION_TAKEN: Voice configured
- VERIFICATION: Latency and quality verified
- AUDIT: Audit trail entry reference

**2. User-Facing Response:** Voice configuration summary with latency info.

## Voice Quality Requirements

- Response latency under 500ms
- Clear audio quality
- Proper consent for audio assets
- Fallback to text when voice unavailable

## Cross-Skill Delegation

When delegating to another skill:
1. Include the voice request.
2. Include voice requirements and constraints.
3. State latency and quality requirements.
