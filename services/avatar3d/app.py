import asyncio
import logging
import os
import subprocess
import traceback
from pathlib import Path
from threading import Lock
from uuid import uuid4

import rembg
import numpy as np
import torch
import trimesh
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from tsr.system import TSR
from tsr.utils import remove_background, resize_foreground

app = FastAPI(title="Atlas Studio Local Avatar Worker", docs_url=None, redoc_url=None)
logger = logging.getLogger("atlas.avatar3d")
root = Path("/data/jobs")
root.mkdir(parents=True, exist_ok=True)
jobs: dict[str, dict] = {}
model = None
background_session = None
load_lock = Lock()


def get_pipeline():
    global model, background_session
    with load_lock:
        if model is None:
            model = TSR.from_pretrained("stabilityai/TripoSR", config_name="config.yaml", weight_name="model.ckpt")
            model.renderer.set_chunk_size(8192)
            model.to(os.getenv("AVATAR_DEVICE", "cpu"))
            background_session = rembg.new_session()
    return model, background_session


def generate(job_id: str, source: Path):
    job = jobs[job_id]
    try:
        job.update(status="running", progress=10, message="Loading local open-source model")
        pipeline, session = get_pipeline()
        job.update(progress=30, message="Preparing image locally")
        # Follow TripoSR's reference preprocessing exactly: rembg returns RGBA,
        # then alpha-composite the foreground over the model's expected gray
        # RGB background. Passing RGBA directly causes a 4-vs-3 tensor error.
        image = resize_foreground(remove_background(Image.open(source), session), 0.85)
        rgba = np.array(image).astype(np.float32) / 255.0
        rgb = rgba[:, :, :3] * rgba[:, :, 3:4] + (1.0 - rgba[:, :, 3:4]) * 0.5
        image = Image.fromarray((rgb * 255.0).astype(np.uint8), mode="RGB")
        job.update(progress=45, message="Reconstructing 3D geometry locally")
        device = os.getenv("AVATAR_DEVICE", "cpu")
        with torch.no_grad():
            scene_codes = pipeline([image], device=device)
        job.update(progress=78, message="Baking texture and exporting reconstruction")
        mesh = pipeline.extract_mesh(scene_codes, True)[0]
        # Use PLY for the internal handoff. Importing the intermediate GLB
        # invokes Blender's glTF importer, which is broken in some Debian
        # package combinations. The final reviewed artifact remains GLB.
        raw = root / job_id / "reconstruction.ply"
        mesh.export(raw)
        job.update(progress=86, message="Blender is cleaning and optimizing the mesh")
        cleaned = root / job_id / "cleaned.ply"
        blender = subprocess.run([
            "blender", "--background", "--python", "/opt/avatar-worker/blender_cleanup.py", "--",
            "--input", str(raw), "--output", str(cleaned),
        ], check=False, timeout=600, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        if blender.returncode != 0 or not cleaned.is_file():
            details = "\n".join(blender.stdout.splitlines()[-12:])
            logger.error("Blender cleanup failed for %s:\n%s", job_id, details)
            reason = f"exit {blender.returncode}" if blender.returncode else "no cleaned mesh was exported"
            raise RuntimeError(f"Blender cleanup failed ({reason})")
        job.update(progress=94, message="Packaging Blender output as a web GLB")
        output = root / job_id / "avatar.glb"
        final_mesh = trimesh.load(cleaned, force="mesh", process=False)
        output.write_bytes(trimesh.exchange.gltf.export_glb(trimesh.Scene(final_mesh), include_normals=True))
        if output.read_bytes()[:4] != b"glTF":
            raise RuntimeError("export did not produce a binary GLB")
        job.update(status="success", progress=100, message="Blender preview ready for review", artifact_url=f"/jobs/{job_id}/model")
    except Exception as exc:
        logger.error("Local generation failed for %s: %s\n%s", job_id, exc, traceback.format_exc())
        job.update(status="failed", message=f"Local generation failed during {job.get('message', 'processing')}: {exc}")


@app.get("/health")
async def health():
    return {"status": "ok", "provider": "triposr+blender-local", "device": os.getenv("AVATAR_DEVICE", "cpu"), "blender": True}


@app.post("/jobs", status_code=202)
async def create_job(image: UploadFile = File(...), left: UploadFile | None = File(None), right: UploadFile | None = File(None), rear: UploadFile | None = File(None)):
    if image.content_type not in ("image/png", "image/jpeg"):
        raise HTTPException(422, "PNG or JPEG required")
    content = await image.read(10 * 1024 * 1024 + 1)
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(422, "image exceeds 10 MB")
    job_id = str(uuid4()); folder = root / job_id; folder.mkdir(parents=True)
    source = folder / ("source.png" if image.content_type == "image/png" else "source.jpg")
    source.write_bytes(content)
    references = []
    for label, upload in (("left", left), ("right", right), ("rear", rear)):
        if upload is None:
            continue
        if upload.content_type not in ("image/png", "image/jpeg"):
            raise HTTPException(422, f"{label} reference must be PNG or JPEG")
        reference_content = await upload.read(10 * 1024 * 1024 + 1)
        if len(reference_content) > 10 * 1024 * 1024:
            raise HTTPException(422, f"{label} reference exceeds 10 MB")
        reference = folder / f"reference-{label}{'.png' if upload.content_type == 'image/png' else '.jpg'}"
        reference.write_bytes(reference_content)
        references.append(label)
    jobs[job_id] = {"id": job_id, "status": "queued", "progress": 0, "message": "Queued on local worker", "references": references}
    asyncio.create_task(asyncio.to_thread(generate, job_id, source))
    return jobs[job_id]


@app.get("/jobs/{job_id}")
async def job_status(job_id: str):
    if job_id not in jobs: raise HTTPException(404, "job not found")
    return jobs[job_id]


@app.get("/jobs/{job_id}/model")
async def job_model(job_id: str):
    output = root / job_id / "avatar.glb"
    if not output.exists(): raise HTTPException(404, "model not ready")
    return FileResponse(output, media_type="model/gltf-binary", filename=f"atlas-avatar-{job_id}.glb")
