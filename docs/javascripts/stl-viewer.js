// Interactive STL viewer for the 3D-printed parts page.
// A thumbnail with class `stl-thumb` (data-stl = STL url, data-title = name)
// opens a modal three.js viewer on click. One WebGL context at a time; the
// context is created on open and disposed on close. Uses a delegated click
// listener so it survives Material's instant navigation.
import * as THREE from "three";
import { STLLoader } from "three/addons/loaders/STLLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

let active = null;

function close() {
  if (!active) return;
  active.dispose();
  active.el.remove();
  active = null;
  document.removeEventListener("keydown", onKey);
}

function onKey(e) {
  if (e.key === "Escape") close();
}

function open(url, title) {
  close();

  const el = document.createElement("div");
  el.className = "stlv-overlay";
  el.innerHTML = `
    <div class="stlv-dialog" role="dialog" aria-modal="true">
      <div class="stlv-bar">
        <span class="stlv-title"></span>
        <button class="stlv-close" aria-label="Close">&times;</button>
      </div>
      <div class="stlv-canvas"><div class="stlv-spinner">Loading&nbsp;3D&nbsp;model…</div></div>
      <div class="stlv-hint">Drag to rotate · scroll to zoom · <a class="stlv-dl" download>download STL</a></div>
    </div>`;
  el.querySelector(".stlv-title").textContent = title || "STL preview";
  el.querySelector(".stlv-dl").href = url;
  document.body.appendChild(el);
  el.addEventListener("click", (e) => {
    if (e.target === el) close();
  });
  el.querySelector(".stlv-close").addEventListener("click", close);
  document.addEventListener("keydown", onKey);

  const host = el.querySelector(".stlv-canvas");

  // Defer one frame so the flex layout has real dimensions.
  requestAnimationFrame(() => {
    const w = host.clientWidth || 640;
    const h = host.clientHeight || 420;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, w / h, 0.1, 100000);
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(w, h);
    host.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;

    scene.add(new THREE.AmbientLight(0xffffff, 0.65));
    const key = new THREE.DirectionalLight(0xffffff, 0.9);
    key.position.set(1, 1, 1.5);
    scene.add(key);
    const fill = new THREE.DirectionalLight(0xffffff, 0.35);
    fill.position.set(-1, -0.6, -1);
    scene.add(fill);

    let mesh = null;
    let raf = 0;

    new STLLoader().load(
      url,
      (geo) => {
        geo.center();
        geo.computeVertexNormals();
        const mat = new THREE.MeshStandardMaterial({
          color: 0x4d8db8,
          metalness: 0.1,
          roughness: 0.65,
        });
        mesh = new THREE.Mesh(geo, mat);
        scene.add(mesh);

        geo.computeBoundingSphere();
        const r = geo.boundingSphere.radius || 1;
        const dist = (r / Math.sin((camera.fov * Math.PI) / 360)) * 1.3;
        camera.position.set(dist, dist * 0.55, dist);
        camera.near = r / 100;
        camera.far = r * 100;
        camera.updateProjectionMatrix();
        controls.target.set(0, 0, 0);
        controls.update();

        const sp = host.querySelector(".stlv-spinner");
        if (sp) sp.remove();
      },
      undefined,
      () => {
        host.innerHTML = '<div class="stlv-error">Could not load this STL file.</div>';
      }
    );

    function resize() {
      const w = host.clientWidth || 640;
      const h = host.clientHeight || 420;
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
      renderer.setSize(w, h);
    }
    window.addEventListener("resize", resize);

    (function animate() {
      raf = requestAnimationFrame(animate);
      controls.update();
      renderer.render(scene, camera);
    })();

    active.dispose = () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      controls.dispose();
      if (mesh) {
        mesh.geometry.dispose();
        mesh.material.dispose();
      }
      renderer.dispose();
      if (renderer.forceContextLoss) renderer.forceContextLoss();
    };
  });

  active = { el, dispose() {} };
}

document.addEventListener("click", (e) => {
  const t = e.target.closest ? e.target.closest(".stl-thumb") : null;
  if (!t) return;
  e.preventDefault();
  open(t.getAttribute("data-stl"), t.getAttribute("data-title"));
});
