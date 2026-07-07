"""Play back a guided disassembly (parts move OUT along the specified motions,
including reposition-to-unlock steps) as a self-contained HTML/three.js viewer.
Lets a human confirm the sequence they specified actually comes apart cleanly.
"""

from __future__ import annotations

import json
from pathlib import Path

from asmplan.emit.tessellate import tessellate
from asmplan.guided import GRotate, GTranslate, GuidedOp
from asmplan.geometry import LoadedAssembly

_PALETTE = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1", "#76b7b2",
            "#edc948", "#ff9da7", "#9c755f", "#bab0ac"]


def _seg_json(seg) -> dict:
    if isinstance(seg, GTranslate):
        return {"kind": "translate", "dir": list(seg.direction), "dist": seg.distance}
    if isinstance(seg, GRotate):
        return {"kind": "rotate", "axis": list(seg.axis), "center": list(seg.center),
                "angle": seg.angle_deg}
    raise TypeError(seg)


def render_guided_animation(assembly: LoadedAssembly, ops: list[GuidedOp],
                            title: str = "asmplan — guided disassembly") -> str:
    involved = [op.part_id for op in ops]
    ids = list(dict.fromkeys(involved))  # unique, order-preserving
    # include any other present parts as static context
    for p in assembly.parts:
        if p.part_id not in ids:
            ids.append(p.part_id)

    color_of = {pid: _PALETTE[i % len(_PALETTE)] for i, pid in enumerate(involved)}
    parts = []
    for pid in ids:
        lp = assembly.by_id(pid)
        verts, tris = tessellate(lp.shape)
        parts.append({
            "id": pid, "name": lp.name or pid,
            "color": color_of.get(pid, "#5b616b"),
            "moving": pid in involved,
            "verts": [c for (x, y, z) in verts for c in (x, y, z)],
            "tris": [i for t in tris for i in t],
        })

    ops_json = [{"part": op.part_id, "removes": op.removes,
                 "label": op.label or ("remove " if op.removes else "reposition ") + op.part_id,
                 "segments": [_seg_json(s) for s in op.segments]} for op in ops]

    xs = [c for p in assembly.parts for c in (p.bbox_min[0], p.bbox_max[0])]
    ys = [c for p in assembly.parts for c in (p.bbox_min[1], p.bbox_max[1])]
    zs = [c for p in assembly.parts for c in (p.bbox_min[2], p.bbox_max[2])]
    meta = {"center": [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                       (min(zs) + max(zs)) / 2],
            "radius": max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1.0)}

    data = {"parts": parts, "ops": ops_json, "meta": meta}
    return _TEMPLATE.replace("__DATA__", json.dumps(data)).replace("__TITLE__", title)


def write_guided_animation(assembly, ops, path, title="asmplan — guided disassembly"):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_guided_animation(assembly, ops, title), encoding="utf-8")
    return path


_TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8"/><title>__TITLE__</title>
<style>
 html,body{margin:0;height:100%;background:#1b1e24;color:#e6e6e6;font-family:system-ui,sans-serif;overflow:hidden}
 #hud{position:fixed;top:12px;left:12px;z-index:10}#step{font-size:15px;margin:0 0 6px}
 #controls{position:fixed;bottom:14px;left:12px;right:12px;z-index:10;display:flex;gap:10px;align-items:center}
 button{background:#2c313a;color:#e6e6e6;border:1px solid #444;border-radius:6px;padding:6px 12px;cursor:pointer}
 button:hover{background:#3a414d}#slider{flex:1}.tag{color:#9aa4b2;font-size:12px}
</style></head><body>
<div id="hud"><p id="step">—</p><span class="tag" id="counter"></span></div>
<div id="controls"><button id="play">▶ Play</button><button id="prev">⟨</button>
<button id="next">⟩</button><input id="slider" type="range" min="0" max="1" step="0.001" value="0"/></div>
<script type="importmap">{ "imports": {
 "three":"https://unpkg.com/three@0.160.0/build/three.module.js",
 "three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/" }}</script>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
const D=__DATA__, parts=D.parts, ops=D.ops, M=D.meta, NOP=ops.length;
const r=new THREE.WebGLRenderer({antialias:true});r.setSize(innerWidth,innerHeight);r.setPixelRatio(devicePixelRatio);document.body.appendChild(r.domElement);
const scene=new THREE.Scene();scene.background=new THREE.Color(0x1b1e24);
const cam=new THREE.PerspectiveCamera(45,innerWidth/innerHeight,0.1,1e6);const R=M.radius,C=M.center;
cam.position.set(C[0]+R*1.7,C[1]-R*2.1,C[2]+R*1.5);
const ctl=new OrbitControls(cam,r.domElement);ctl.target.set(C[0],C[1],C[2]);ctl.update();
scene.add(new THREE.AmbientLight(0xffffff,.6));const dl=new THREE.DirectionalLight(0xffffff,.9);dl.position.set(R,-R,2*R);scene.add(dl);
const meshOf={};
for(const p of parts){
 const g=new THREE.BufferGeometry();
 g.setAttribute('position',new THREE.Float32BufferAttribute(p.verts,3));g.setIndex(p.tris);g.computeVertexNormals();
 const m=new THREE.Mesh(g,new THREE.MeshStandardMaterial({color:p.color,metalness:.2,roughness:.6,side:THREE.DoubleSide,
   transparent:!p.moving,opacity:p.moving?1:0.25}));
 m.matrixAutoUpdate=false;scene.add(m);meshOf[p.id]=m;
}
function segMat(seg,t){
 if(seg.kind==='translate'){const d=new THREE.Vector3(...seg.dir);if(d.length()>0)d.normalize();
   return new THREE.Matrix4().makeTranslation(d.x*seg.dist*t,d.y*seg.dist*t,d.z*seg.dist*t);}
 // rotate about axis through center by angle*t
 const c=new THREE.Vector3(...seg.center),ax=new THREE.Vector3(...seg.axis).normalize();
 const R=new THREE.Matrix4().makeRotationAxis(ax,THREE.MathUtils.degToRad(seg.angle*t));
 const T1=new THREE.Matrix4().makeTranslation(c.x,c.y,c.z),T0=new THREE.Matrix4().makeTranslation(-c.x,-c.y,-c.z);
 return T1.multiply(R).multiply(T0);
}
function applyOp(m,op,f){ // compose op's segments up to fraction f (0..1) onto m
 const ns=op.segments.length; const span=1/ns;
 for(let i=0;i<ns;i++){const lo=i*span; if(f<=lo)break; const local=Math.min(1,(f-lo)/span);
   m.premultiply(segMat(op.segments[i],local));}
 return m;
}
function poseAt(pid,P){ // cumulative disassembly transform of part pid at progress P
 let m=new THREE.Matrix4();
 for(let j=0;j<NOP;j++){ if(ops[j].part!==pid)continue;
   if(P>=j+1) applyOp(m,ops[j],1); else if(P>j) applyOp(m,ops[j],P-j); }
 return m;
}
function apply(P){
 for(const p of parts) meshOf[p.id].matrix.copy(poseAt(p.id,P));
 const j=Math.min(NOP-1,Math.max(0,Math.ceil(P)-1));
 document.getElementById('step').textContent = P<=0?'Ready — press Play':((j+1)+'. '+ops[j].label);
 document.getElementById('counter').textContent='step '+Math.min(NOP,Math.max(0,Math.ceil(P)))+' / '+NOP;
}
const slider=document.getElementById('slider');slider.max=NOP;let P=0,playing=false;
const play=document.getElementById('play');
slider.oninput=()=>{P=parseFloat(slider.value);playing=false;play.textContent='▶ Play';apply(P);};
play.onclick=()=>{if(P>=NOP)P=0;playing=!playing;play.textContent=playing?'❚❚ Pause':'▶ Play';};
document.getElementById('next').onclick=()=>{playing=false;play.textContent='▶ Play';P=Math.min(NOP,Math.floor(P)+1);slider.value=P;apply(P);};
document.getElementById('prev').onclick=()=>{playing=false;play.textContent='▶ Play';P=Math.max(0,Math.ceil(P)-1);slider.value=P;apply(P);};
let last=performance.now();
(function loop(now){const dt=(now-last)/1000;last=now;
 if(playing){P=Math.min(NOP,P+dt*0.6);slider.value=P;apply(P);if(P>=NOP){playing=false;play.textContent='▶ Play';}}
 ctl.update();r.render(scene,cam);requestAnimationFrame(loop);})(last);
addEventListener('resize',()=>{cam.aspect=innerWidth/innerHeight;cam.updateProjectionMatrix();r.setSize(innerWidth,innerHeight);});
apply(0);
</script></body></html>
"""
