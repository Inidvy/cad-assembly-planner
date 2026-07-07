"""Static multi-part inspection viewer — render a chosen subset of an assembly's
parts (distinct colors, toggleable, orbit camera). Used to eyeball an interlock
the sequencer couldn't resolve.
"""

from __future__ import annotations

import json
from pathlib import Path

from asmplan.emit.tessellate import tessellate
from asmplan.geometry import LoadedAssembly

_PALETTE = ["#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#b07aa1", "#76b7b2",
            "#edc948", "#ff9da7", "#9c755f", "#bab0ac"]


def render_inspection(assembly: LoadedAssembly, part_ids: list[str] | None = None,
                      title: str = "asmplan — inspection") -> str:
    ids = part_ids or [p.part_id for p in assembly.parts]
    parts = []
    for i, pid in enumerate(ids):
        lp = assembly.by_id(pid)
        verts, tris = tessellate(lp.shape)
        cx, cy, cz = lp.centroid
        flat_v = [c for (x, y, z) in verts for c in (x - cx, y - cy, z - cz)]
        parts.append({
            "id": pid, "name": lp.name or pid,
            "color": _PALETTE[i % len(_PALETTE)],
            "verts": flat_v, "tris": [i for t in tris for i in t],
            "centroid": [cx, cy, cz],
            "size": [round(s, 1) for s in lp.bbox_size],
        })
    xs = [c for p in assembly.parts if p.part_id in ids
          for c in (p.bbox_min[0], p.bbox_max[0])]
    ys = [c for p in assembly.parts if p.part_id in ids
          for c in (p.bbox_min[1], p.bbox_max[1])]
    zs = [c for p in assembly.parts if p.part_id in ids
          for c in (p.bbox_min[2], p.bbox_max[2])]
    meta = {"center": [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                       (min(zs) + max(zs)) / 2],
            "radius": max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1.0)}
    return _TEMPLATE.replace("__DATA__", json.dumps({"parts": parts, "meta": meta})) \
                    .replace("__TITLE__", title)


def write_inspection(assembly: LoadedAssembly, path, part_ids=None,
                     title="asmplan — inspection") -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_inspection(assembly, part_ids, title), encoding="utf-8")
    return path


_TEMPLATE = r"""<!doctype html><html><head><meta charset="utf-8"/><title>__TITLE__</title>
<style>
 html,body{margin:0;height:100%;background:#1b1e24;color:#e6e6e6;font-family:system-ui,sans-serif;overflow:hidden}
 #legend{position:fixed;top:10px;left:10px;z-index:10;background:#20242c;padding:10px 12px;border-radius:8px;font-size:13px;max-height:85%;overflow:auto}
 #legend h3{margin:0 0 8px;font-size:13px;color:#9aa4b2}
 .row{display:flex;align-items:center;gap:8px;margin:3px 0;cursor:pointer}
 .sw{width:14px;height:14px;border-radius:3px;flex:none}
 .row.off{opacity:.35}
 .tag{color:#8892a0;font-size:11px}
</style></head><body>
<div id="legend"><h3>__TITLE__</h3><div id="rows"></div>
<div class="tag" style="margin-top:8px">click a row to toggle · drag to orbit · scroll to zoom</div></div>
<script type="importmap">{ "imports": {
 "three":"https://unpkg.com/three@0.160.0/build/three.module.js",
 "three/addons/":"https://unpkg.com/three@0.160.0/examples/jsm/" }}</script>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
const D=__DATA__, parts=D.parts, M=D.meta;
const r=new THREE.WebGLRenderer({antialias:true});r.setSize(innerWidth,innerHeight);r.setPixelRatio(devicePixelRatio);document.body.appendChild(r.domElement);
const scene=new THREE.Scene();scene.background=new THREE.Color(0x1b1e24);
const cam=new THREE.PerspectiveCamera(45,innerWidth/innerHeight,0.1,1e6);
const R=M.radius,C=M.center;cam.position.set(C[0]+R*1.6,C[1]-R*2,C[2]+R*1.4);
const ctl=new OrbitControls(cam,r.domElement);ctl.target.set(C[0],C[1],C[2]);ctl.update();
scene.add(new THREE.AmbientLight(0xffffff,.6));const dl=new THREE.DirectionalLight(0xffffff,.9);dl.position.set(R,-R,2*R);scene.add(dl);
const rows=document.getElementById('rows');
const meshes=parts.map((p,i)=>{
 const g=new THREE.BufferGeometry();
 g.setAttribute('position',new THREE.Float32BufferAttribute(p.verts,3));g.setIndex(p.tris);g.computeVertexNormals();
 const mesh=new THREE.Mesh(g,new THREE.MeshStandardMaterial({color:p.color,metalness:.2,roughness:.6,side:THREE.DoubleSide}));
 mesh.position.set(p.centroid[0],p.centroid[1],p.centroid[2]);scene.add(mesh);
 const row=document.createElement('div');row.className='row';
 row.innerHTML=`<span class="sw" style="background:${p.color}"></span><span>${p.id} · ${p.name}</span><span class="tag">${p.size.join('×')}</span>`;
 row.onclick=()=>{mesh.visible=!mesh.visible;row.classList.toggle('off',!mesh.visible);};
 rows.appendChild(row);return mesh;});
addEventListener('resize',()=>{cam.aspect=innerWidth/innerHeight;cam.updateProjectionMatrix();r.setSize(innerWidth,innerHeight);});
(function loop(){requestAnimationFrame(loop);ctl.update();r.render(scene,cam);})();
</script></body></html>
"""
