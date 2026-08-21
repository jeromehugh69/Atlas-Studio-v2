# Change 006 — Status Report Cards in Chat Feed

**Date:** 2026-08-21
**Status:** Completed

## Summary

Atlas status reports now render as a structured card inside the chat feed instead of a
plain paragraph: header ("PLATFORM STATUS" with pulsing indicator) plus one row per
labeled field, color-coded by health.

## Behavior

- Detection is automatic and frontend-only (`chat-format.js`): a message qualifies when
  every sentence/line matches `Label: value` and there are at least 3 fields. Any other
  prose renders as normal markdown.
- Works for both paragraph-style reports ("Health: ... . Tasks: ... .") and line-based lists.
- Row tone: green = healthy (stable/none/passing), amber = attention (pending/in
  progress/review), red = action (fail/critical/blocker/error/down/urgent).
- Renders during streaming too — the card fills in live as Atlas generates.

## Files

| File | Change |
|------|--------|
| `src/atlas_studio/static/chat-format.js` | `tryRenderStatusCard()` hooked at top of `formatAtlasMarkdown` |
| `src/atlas_studio/static/atlas-chat-panel.css` | `.chat-status-card` styles matching delegation-card look |

## Verification

- `node --check` passes; node smoke test: sample report → card with all three tones;
  normal prose and <3-field messages stay plain.
- To see it: hard-refresh the dashboard (Ctrl+Shift+R), ask Atlas
  "Give me a platform status report: overall health, active tasks, change sets,
  pending approvals, failures, urgent actions."
