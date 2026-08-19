"""Headless Blender cleanup for locally reconstructed worker avatars."""
import argparse
import math
import sys
import traceback

import bpy


def arguments():
    parser = argparse.ArgumentParser()
    args = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args(args)


def main():
    args = arguments()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if hasattr(bpy.ops.wm, "ply_import"):
        bpy.ops.wm.ply_import(filepath=args.input)
    elif hasattr(bpy.ops.import_mesh, "ply"):
        bpy.ops.import_mesh.ply(filepath=args.input)
    else:
        raise RuntimeError("this Blender build has no PLY importer")
    meshes = [item for item in bpy.context.scene.objects if item.type == "MESH"]
    if not meshes:
        raise RuntimeError("reconstruction contains no mesh")

    for item in list(bpy.context.scene.objects):
        if item.type in {"CAMERA", "LIGHT"}:
            bpy.data.objects.remove(item, do_unlink=True)

    bpy.ops.object.select_all(action="DESELECT")
    for item in meshes:
        item.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    avatar = bpy.context.active_object
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    dimensions = avatar.dimensions
    height = max(dimensions.z, 0.001)
    shallow = min(dimensions.x, dimensions.y) / height < 0.035
    if shallow:
        modifier = avatar.modifiers.new("Minimum body depth", "SOLIDIFY")
        modifier.thickness = height * 0.04
        modifier.offset = 0.0

    smooth = avatar.modifiers.new("Surface smoothing", "SMOOTH")
    smooth.factor = 0.15
    smooth.iterations = 2
    polygons = len(avatar.data.polygons)
    if polygons > 120000:
        decimate = avatar.modifiers.new("Web optimization", "DECIMATE")
        decimate.ratio = max(0.2, 120000 / polygons)

    # Apply modifiers explicitly. This works across the Blender 3.x versions
    # shipped by Debian and avoids exporter-version-specific apply flags.
    bpy.context.view_layer.objects.active = avatar
    avatar.select_set(True)
    for modifier in list(avatar.modifiers):
        bpy.ops.object.modifier_apply(modifier=modifier.name)

    # Blender/PLY is Z-up while the Atlas WebGL runtime is Y-up. Bake the
    # conversion into vertex coordinates before the cleaned mesh leaves
    # Blender so downstream exporters cannot reinterpret the scene axes.
    avatar.rotation_euler[0] = math.radians(-90.0)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)

    for polygon in avatar.data.polygons:
        polygon.use_smooth = True
    avatar["atlas_pipeline"] = "triposr+blender"
    avatar["review_required"] = True
    if hasattr(bpy.ops.wm, "ply_export"):
        bpy.ops.wm.ply_export(filepath=args.output, export_colors="SRGB")
    elif hasattr(bpy.ops.export_mesh, "ply"):
        bpy.ops.export_mesh.ply(filepath=args.output, use_mesh_modifiers=True, use_colors=True)
    else:
        raise RuntimeError("this Blender build has no PLY exporter")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        # Blender otherwise may exit zero after a Python exception, which
        # makes the worker believe an output was produced.
        sys.exit(1)
