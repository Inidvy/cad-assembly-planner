"""3D step-by-step assembly animation, rendered as a self-contained HTML file.

Each part flies in along its insertion direction in plan order; fasteners also
rotate about their axis as they drive in. This is the visual validation tool the
design calls for — you watch the plan and catch a bad ordering or interpenetration
by eye. three.js is loaded from a CDN (needs internet on first open).
"""

from __future__ import annotations

import json
from pathlib import Path

from asmplan.emit.tessellate import tessellate
from asmplan.geometry import LoadedAssembly
from asmplan.schema import Plan, Screw, Translate

# Distinct-ish palette for generic parts; fasteners get a fixed gold.
_PALETTE = ["#4e79a7", "#59a14f", "#af7aa1", "#76b7b2", "#edc948", "#ff9da7"]
_FASTENER_COLOR = "#b08d37"


def _part_payload(plan: Plan, assembly: LoadedAssembly) -> list[dict]:
    step_by_id = {s.part_id: s for s in plan.steps}
    parts = []
    color_i = 0
    for lp in assembly.parts:
        step = step_by_id.get(lp.part_id)
        if step is None:
            continue
        verts, tris = tessellate(lp.shape)
        cx, cy, cz = lp.centroid
        # centre geometry on the part centroid so we can rotate about it
        flat_v = []
        for (x, y, z) in verts:
            flat_v += [x - cx, y - cy, z - cz]
        flat_t = [i for t in tris for i in t]

        kind, direction, backoff, turns = "none", [0, 0, 1], 10.0, 0.0
        m = step.motion
        if isinstance(m, Translate):
            kind = "translate"
            direction = list(m.direction)
            backoff = float(m.distance_mm)
        elif isinstance(m, Screw):
            kind = "screw"
            direction = list(m.axis)
            turns = float(m.turns)
            backoff = max(turns * m.pitch_mm, 8.0)

        is_fast = step.part_class.is_fastener
        color = _FASTENER_COLOR if is_fast else _PALETTE[color_i % len(_PALETTE)]
        if not is_fast:
            color_i += 1

        parts.append({
            "id": lp.part_id,
            "name": lp.name or lp.part_id,
            "color": color,
            "verts": flat_v,
            "tris": flat_t,
            "centroid": [cx, cy, cz],
            "order": step.order_index,
            "kind": kind,
            "dir": direction,
            "backoff": backoff,
            "turns": turns,
            "subgoal": step.subgoal_text or f"Place {lp.name or lp.part_id}",
        })
    return parts


def _scene_meta(assembly: LoadedAssembly) -> dict:
    xs = [c for p in assembly.parts for c in (p.bbox_min[0], p.bbox_max[0])]
    ys = [c for p in assembly.parts for c in (p.bbox_min[1], p.bbox_max[1])]
    zs = [c for p in assembly.parts for c in (p.bbox_min[2], p.bbox_max[2])]
    center = [(min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, (min(zs) + max(zs)) / 2]
    radius = max(max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), 1.0)
    return {"center": center, "radius": radius}


def render_animation(plan: Plan, assembly: LoadedAssembly) -> str:
    data = {"parts": _part_payload(plan, assembly), "meta": _scene_meta(assembly)}
    return _TEMPLATE.replace("__DATA__", json.dumps(data))


def write_animation(plan: Plan, assembly: LoadedAssembly, path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_animation(plan, assembly), encoding="utf-8")
    return path


_TEMPLATE = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>asmplan — assembly animation</title>
<style>
  html,body{margin:0;height:100%;background:#1b1e24;color:#e6e6e6;
    font-family:system-ui,sans-serif;overflow:hidden}
  #hud{position:fixed;top:12px;left:12px;z-index:10;max-width:60%}
  #step{font-size:15px;margin:0 0 8px;line-height:1.4}
  #controls{position:fixed;bottom:14px;left:12px;right:12px;z-index:10;
    display:flex;gap:10px;align-items:center}
  button{background:#2c313a;color:#e6e6e6;border:1px solid #444;border-radius:6px;
    padding:6px 12px;cursor:pointer;font-size:13px}
  button:hover{background:#3a414d}
  #slider{flex:1}
  .tag{color:#9aa4b2;font-size:12px}
</style>
</head>
<body>
<div id="hud"><p id="step">—</p><span class="tag" id="counter"></span></div>
<div id="controls">
  <button id="playBtn">▶ Play</button>
  <button id="prevBtn">⟨ Prev</button>
  <button id="nextBtn">Next ⟩</button>
  <input id="slider" type="range" min="0" max="1" step="0.001" value="0"/>
</div>
<script type="importmap">
{ "imports": {
  "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
  "three/addons/": "https://unpkg.com/three@0.160.0/examples/jsm/"
}}
</script>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const DATA = __DATA__;
const parts = DATA.parts, meta = DATA.meta;
const N = parts.length;

const renderer = new THREE.WebGLRenderer({antialias:true});
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(devicePixelRatio);
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x1b1e24);
const cam = new THREE.PerspectiveCamera(45, innerWidth/innerHeight, 0.1, 100000);
const R = meta.radius, C = meta.center;
cam.position.set(C[0]+R*1.6, C[1]-R*2.0, C[2]+R*1.4);
const controls = new OrbitControls(cam, renderer.domElement);
controls.target.set(C[0], C[1], C[2]);
controls.update();

scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const dl = new THREE.DirectionalLight(0xffffff, 0.9);
dl.position.set(R, -R, 2*R); scene.add(dl);
const grid = new THREE.GridHelper(R*6, 24, 0x333a44, 0x2a2f38);
grid.rotation.x = Math.PI/2; grid.position.set(C[0],C[1],C[2]-R); scene.add(grid);

const groups = parts.map(p => {
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(p.verts, 3));
  g.setIndex(p.tris);
  g.computeVertexNormals();
  const mat = new THREE.MeshStandardMaterial({color:p.color, metalness:0.2,
    roughness:0.6, side:THREE.DoubleSide});
  const mesh = new THREE.Mesh(g, mat);
  const grp = new THREE.Group();
  grp.add(mesh);
  scene.add(grp);
  return grp;
});

function norm(v){const n=Math.hypot(v[0],v[1],v[2])||1;return [v[0]/n,v[1]/n,v[2]/n];}

function apply(progress){
  for(let i=0;i<N;i++){
    const p = parts[i], grp = groups[i], k = p.order;
    let f; // 0=fully backed off, 1=seated
    if(progress <= k){ grp.visible = false; continue; }
    grp.visible = true;
    f = Math.min(1, progress - k);
    const d = norm(p.dir), back = (1-f)*p.backoff;
    grp.position.set(
      p.centroid[0] - d[0]*back,
      p.centroid[1] - d[1]*back,
      p.centroid[2] - d[2]*back);
    if(p.kind === 'screw' && p.turns>0){
      const axis = new THREE.Vector3(d[0],d[1],d[2]).normalize();
      grp.quaternion.setFromAxisAngle(axis, -(1-f)*p.turns*2*Math.PI);
    } else { grp.quaternion.identity(); }
  }
  const active = Math.min(N-1, Math.floor(progress - 1e-6));
  const idx = Math.max(0, Math.min(N-1, Math.ceil(progress)-1));
  document.getElementById('step').textContent =
    progress<=0 ? 'Ready — press Play' : (idx+1)+'. '+parts[idx].subgoal;
  document.getElementById('counter').textContent = 'step '+
    Math.min(N, Math.max(0,Math.ceil(progress)))+' / '+N;
}

const slider = document.getElementById('slider');
slider.max = N;
let progress = 0, playing = false;
slider.addEventListener('input', ()=>{ progress = parseFloat(slider.value);
  playing=false; playBtn.textContent='▶ Play'; apply(progress); });
const playBtn=document.getElementById('playBtn');
playBtn.onclick=()=>{ if(progress>=N) progress=0; playing=!playing;
  playBtn.textContent = playing?'❚❚ Pause':'▶ Play'; };
document.getElementById('nextBtn').onclick=()=>{ playing=false;
  playBtn.textContent='▶ Play'; progress=Math.min(N,Math.floor(progress)+1);
  slider.value=progress; apply(progress); };
document.getElementById('prevBtn').onclick=()=>{ playing=false;
  playBtn.textContent='▶ Play'; progress=Math.max(0,Math.ceil(progress)-1);
  slider.value=progress; apply(progress); };

let last=performance.now();
function loop(now){
  const dt=(now-last)/1000; last=now;
  if(playing){ progress=Math.min(N, progress + dt*0.8);
    slider.value=progress; apply(progress);
    if(progress>=N){ playing=false; playBtn.textContent='▶ Play'; } }
  controls.update();
  renderer.render(scene, cam);
  requestAnimationFrame(loop);
}
addEventListener('resize', ()=>{ cam.aspect=innerWidth/innerHeight;
  cam.updateProjectionMatrix(); renderer.setSize(innerWidth,innerHeight); });
apply(0);
requestAnimationFrame(loop);
</script>
</body>
</html>
"""
