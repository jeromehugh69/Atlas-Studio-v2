"""Generate Atlas Studio's redistributable stylized worker GLB."""
import json, math, struct
from pathlib import Path

import numpy as np

buffers = bytearray()
views, accessors, meshes, materials, nodes = [], [], [], [], []


def material(name, color):
    materials.append({"name": name, "pbrMetallicRoughness": {"baseColorFactor": [*color, 1], "metallicFactor": 0.0, "roughnessFactor": 0.72}})
    return len(materials) - 1


SKIN = material("warm skin", [0.72, 0.46, 0.34])
WHITE = material("white blouse", [0.92, 0.93, 0.96])
BLACK = material("charcoal skirt and shoes", [0.035, 0.038, 0.055])
HAIR = material("dark brunette hair", [0.055, 0.025, 0.018])
IRIS = material("blue grey eyes", [0.18, 0.34, 0.38])
LIP = material("natural lip", [0.48, 0.18, 0.16])
ACCENT = material("Atlas accent", [0.95, 0.40, 0.18])


def add_blob(data, target=None):
    while len(buffers) % 4: buffers.append(0)
    offset = len(buffers); buffers.extend(data)
    view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
    if target: view["target"] = target
    views.append(view)
    return len(views) - 1


def accessor(arr, component_type, kind, target=None):
    arr = np.ascontiguousarray(arr)
    view = add_blob(arr.tobytes(), target)
    count = len(arr); item = arr.reshape(count, -1)
    acc = {"bufferView": view, "componentType": component_type, "count": count, "type": kind}
    if kind == "VEC3":
        acc["min"] = item.min(axis=0).astype(float).tolist(); acc["max"] = item.max(axis=0).astype(float).tolist()
    accessors.append(acc)
    return len(accessors) - 1


def add_mesh(name, positions, normals, indices, mat):
    p = accessor(np.array(positions, np.float32), 5126, "VEC3", 34962)
    n = accessor(np.array(normals, np.float32), 5126, "VEC3", 34962)
    i = accessor(np.array(indices, np.uint16), 5123, "SCALAR", 34963)
    meshes.append({"name": name, "primitives": [{"attributes": {"POSITION": p, "NORMAL": n}, "indices": i, "material": mat}]})
    return len(meshes) - 1


def cube(mat):
    pos=[]; norm=[]; ind=[]
    faces=[((1,0,0),[(1,-1,-1),(1,1,-1),(1,1,1),(1,-1,1)]),((-1,0,0),[(-1,-1,1),(-1,1,1),(-1,1,-1),(-1,-1,-1)]),((0,1,0),[(-1,1,-1),(-1,1,1),(1,1,1),(1,1,-1)]),((0,-1,0),[(-1,-1,1),(-1,-1,-1),(1,-1,-1),(1,-1,1)]),((0,0,1),[(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)]),((0,0,-1),[(1,-1,-1),(-1,-1,-1),(-1,1,-1),(1,1,-1)])]
    for normal,verts in faces:
        base=len(pos);pos.extend(verts);norm.extend([normal]*4);ind.extend([base,base+1,base+2,base,base+2,base+3])
    return add_mesh("box",pos,norm,ind,mat)


def sphere(mat, rings=12, seg=18):
    pos=[];norm=[];ind=[]
    for r in range(rings+1):
        phi=math.pi*r/rings
        for s in range(seg+1):
            th=2*math.pi*s/seg;x=math.sin(phi)*math.cos(th);y=math.cos(phi);z=math.sin(phi)*math.sin(th)
            pos.append((x,y,z));norm.append((x,y,z))
    for r in range(rings):
        for s in range(seg):
            a=r*(seg+1)+s;b=a+seg+1;ind.extend([a,b,a+1,b,b+1,a+1])
    return add_mesh("sphere",pos,norm,ind,mat)


def cylinder(mat, seg=18):
    pos=[];norm=[];ind=[]
    for y in (-1,1):
        for s in range(seg):
            a=2*math.pi*s/seg;x=math.cos(a);z=math.sin(a);pos.append((x,y,z));norm.append((x,0,z))
    for s in range(seg):
        n=(s+1)%seg;ind.extend([s,seg+s,n, n,seg+s,seg+n])
    for y,ny in ((-1,-1),(1,1)):
        c=len(pos);pos.append((0,y,0));norm.append((0,ny,0))
        base=len(pos)
        for s in range(seg):
            a=2*math.pi*s/seg;pos.append((math.cos(a),y,math.sin(a)));norm.append((0,ny,0))
        for s in range(seg):
            n=(s+1)%seg;ind.extend([c,base+n,base+s] if ny<0 else [c,base+s,base+n])
    return add_mesh("cylinder",pos,norm,ind,mat)


mesh_cache={}
def primitive(shape, mat):
    key=(shape,mat)
    if key not in mesh_cache: mesh_cache[key]={"sphere":sphere,"box":cube,"cylinder":cylinder}[shape](mat)
    return mesh_cache[key]


def node(name, shape, mat, translation, scale):
    nodes.append({"name":name,"mesh":primitive(shape,mat),"translation":translation,"scale":scale})


# Stylized worker based on the supplied studio references.
node("head","sphere",SKIN,[0,2.30,0],[.33,.43,.31])
node("hair cap","sphere",HAIR,[0,2.56,-.02],[.37,.30,.33])
node("hair bun","sphere",HAIR,[0,2.86,-.08],[.22,.22,.20])
node("neck","cylinder",SKIN,[0,1.90,0],[.12,.18,.12])
node("blouse","box",WHITE,[0,1.38,0],[.48,.55,.22])
node("waist","box",BLACK,[0,.91,0],[.43,.13,.23])
node("skirt","box",BLACK,[0,.56,0],[.47,.37,.24])
for x in (-.58,.58): node("sleeve","cylinder",WHITE,[x,1.40,0],[.105,.55,.105])
for x in (-.58,.58): node("hand","sphere",SKIN,[x,.78,0],[.105,.17,.09])
for x in (-.22,.22): node("leg","cylinder",SKIN,[x,-.14,0],[.12,.67,.12])
for x in (-.22,.22): node("shoe","box",BLACK,[x,-.86,.05],[.15,.11,.28])
for x in (-.13,.13): node("eye","sphere",IRIS,[x,2.38,.285],[.045,.035,.022])
node("mouth","box",LIP,[0,2.16,.305],[.095,.018,.012])
node("badge","box",ACCENT,[.25,1.59,.235],[.055,.055,.015])

doc={"asset":{"version":"2.0","generator":"Atlas Studio GLB generator"},"scene":0,"scenes":[{"name":"Atlas Worker","nodes":list(range(len(nodes)))}],"nodes":nodes,"meshes":meshes,"materials":materials,"buffers":[{"byteLength":len(buffers)}],"bufferViews":views,"accessors":accessors}
raw=json.dumps(doc,separators=(",",":")).encode();raw+=b" "*((4-len(raw)%4)%4)
while len(buffers)%4:buffers.append(0)
total=12+8+len(raw)+8+len(buffers)
glb=struct.pack("<4sII",b"glTF",2,total)+struct.pack("<I4s",len(raw),b"JSON")+raw+struct.pack("<I4s",len(buffers),b"BIN\0")+buffers
out=Path(__file__).parents[1]/"src"/"atlas_studio"/"static"/"avatars"/"atlas_worker_stylized.glb"
out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(glb)
print(f"Generated {out} ({len(glb):,} bytes)")
