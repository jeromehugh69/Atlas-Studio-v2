"""Add the shared Atlas conversation launcher to the upstream Gradio shell."""

import os
from pathlib import Path


demo = Path(os.getenv("ATLAS_OPEN_AVATAR_DEMO", "/opt/open-avatar-chat/src/demo.py"))
source = demo.read_text(encoding="utf-8")
needle = "with gr.Blocks(css=css) as gradio_block:"
replacement = '''with gr.Blocks(
        css=css,
        head="""
        <link rel="stylesheet" href="http://localhost:8081/static/atlas-widget.css">
        <script defer src="http://localhost:8081/static/atlas-widget.js"></script>
        """,
    ) as gradio_block:'''

if replacement not in source:
    if needle not in source:
        raise RuntimeError("OpenAvatarChat Gradio shell changed; Atlas widget injection target was not found")
    demo.write_text(source.replace(needle, replacement, 1), encoding="utf-8")
