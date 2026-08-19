"""Atlas Studio command-center portal.

The portal keeps port 8080 as the public entry point while embedding the main
Atlas application served by the app container on the host's port 8081.
"""

from __future__ import annotations

import os

import gradio as gr


CSS = """
html, body, .gradio-container { margin: 0 !important; min-height: 100% !important; background: #05090f !important; }
.gradio-container { max-width: none !important; padding: 0 !important; }
.gradio-container > .main { padding: 0 !important; }
#atlas-command-shell { margin: 0 !important; padding: 0 !important; border: 0 !important; }
#atlas-command-shell > div { padding: 0 !important; }
#atlas-command-frame { display: block; width: 100%; height: 100vh; min-height: 760px; border: 0; background: #05090f; }
footer { display: none !important; }
"""

COMMAND_CENTER_URL = os.getenv("ATLAS_STUDIO_PORTAL_TARGET_URL", "http://localhost:8080/")


with gr.Blocks() as demo:
    gr.HTML(
        f"""
        <iframe
          id="atlas-command-frame"
          src="{COMMAND_CENTER_URL}"
          title="Atlas AI Engineering Command Center"
          allow="microphone; autoplay"
        ></iframe>
        """,
        elem_id="atlas-command-shell",
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("ATLAS_STUDIO_PORTAL_PORT", "8080")),
        css=CSS,
    )
