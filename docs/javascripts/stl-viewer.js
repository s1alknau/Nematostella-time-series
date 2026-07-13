// Interactive STL viewer + client-side thumbnails for the 3D-printed parts page.
//
// Each `.stl-thumb` (data-stl = STL url, data-title = name) is rendered to a
// small preview <canvas> in the browser and, on click, opens a full modal
// three.js viewer (rotate/zoom). All rendering reuses a single WebGL context,
// so a 20-part page stays well within the browser's context limit. A delegated
// click listener + document$ subscription keep it working across Material's
// instant navigation.
import * as THREE from "three";
import { STLLoader } from "three/addons/loaders/STLLoader.js";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

const PART_COLOR = 0x4d8db8;

function fitCamera(camera, radius, yaw = 1, pitch = 0.55) {
  const dist = (radius / Math.sin((camera.fov * Math.PI) / 360)) * 1.3;
  camera.position.set(dist * yaw, dist * pitch, dist);
  camera.near = radius / 100;
  camera.far = radius * 100;
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();
}

function addLights(scene) {
  scene.add(new THREE.AmbientLight(0xffffff, 0.65));
  const key = new THREE.DirectionalLight(0xffffff, 0.9);
  key.position.set(1, 1, 1.5);
  scene.add(key);
  const fill = new THREE.DirectionalLight(0xffffff, 0.35);
  fill.position.set(-1, -0.6, -1);
  scene.add(fill);
}

// ---- Thumbnails --------------------------------------------------------
const THUMB_W = 340;
const THUMB_H = 240;
let thumbRenderer = null;
const geoCache = new Map();
const queue = [];
let processing = false;

function getThumbRenderer() {
  if (thumbRenderer) return thumbRenderer;
  thumbRenderer = new THREE.WebGLRenderer({
    antialias: true,
    alpha: true,
    preserveDrawingBuffer: true,
  });
  thumbRenderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  thumbRenderer.setSize(THUMB_W, THUMB_H, false);
  return thumbRenderer;
}

function loadGeometry(url) {
  if (geoCache.has(url)) return Promise.resolve(geoCache.get(url));
  return new Promise((resolve, reject) => {
    new STLLoader().load(
      url,
      (geo) => {
        geo.center();
        geo.computeVertexNormals();
        geo.computeBoundingSphere();
        geoCache.set(url, geo);
        resolve(geo);
      },
      undefined,
      reject
    );
  });
}

async function renderThumb(el) {
  const url = el.getAttribute("data-stl");
  const canvas = el.querySelector("canvas.stl-thumb-canvas");
  if (!canvas || !url) return;
  const geo = await loadGeometry(url);

  const renderer = getThumbRenderer();
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(35, THUMB_W / THUMB_H, 0.1, 100000);
  addLights(scene);
  const mesh = new THREE.Mesh(
    geo,
    new THREE.MeshStandardMaterial({ color: PART_COLOR, metalness: 0.1, roughness: 0.65 })
  );
  scene.add(mesh);
  fitCamera(camera, geo.boundingSphere.radius || 1);
  renderer.render(scene, camera);

  const src = renderer.domElement;
  canvas.width = src.width;
  canvas.height = src.height;
  canvas.getContext("2d").drawImage(src, 0, 0);
  el.classList.add("stl-thumb--ready");

  mesh.material.dispose();
  scene.clear();
}

async function processQueue() {
  if (processing) return;
  processing = true;
  while (queue.length) {
    const el = queue.shift();
    try {
      await renderThumb(el);
    } catch (e) {
      el.dataset.thumbDone = ""; // allow a later retry
    }
  }
  processing = false;
}

function enqueueThumb(el) {
  if (el.dataset.thumbDone) return;
  el.dataset.thumbDone = "1";
  queue.push(el);
  processQueue();
}

const io =
  "IntersectionObserver" in window
    ? new IntersectionObserver(
        (entries, obs) => {
          for (const e of entries) {
            if (e.isIntersecting) {
              obs.unobserve(e.target);
              enqueueThumb(e.target);
            }
          }
        },
        { rootMargin: "300px" }
      )
    : null;

function scanThumbs() {
  document.querySelectorAll(".stl-thumb").forEach((el) => {
    if (el.dataset.observed) return;
    el.dataset.observed = "1";
    if (io) io.observe(el);
    else enqueueThumb(el);
  });
}

// ---- Modal viewer ------------------------------------------------------
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
  active = { el, dispose() {} };

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
    addLights(scene);

    let mesh = null;
    let raf = 0;
    loadGeometry(url).then(
      (geo) => {
        mesh = new THREE.Mesh(
          geo,
          new THREE.MeshStandardMaterial({ color: PART_COLOR, metalness: 0.1, roughness: 0.65 })
        );
        scene.add(mesh);
        fitCamera(camera, geo.boundingSphere.radius || 1);
        controls.target.set(0, 0, 0);
        controls.update();
        const sp = host.querySelector(".stlv-spinner");
        if (sp) sp.remove();
      },
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
      if (mesh) mesh.material.dispose();
      renderer.dispose();
      if (renderer.forceContextLoss) renderer.forceContextLoss();
    };
  });
}

document.addEventListener("click", (e) => {
  const t = e.target.closest ? e.target.closest(".stl-thumb") : null;
  if (!t) return;
  e.preventDefault();
  open(t.getAttribute("data-stl"), t.getAttribute("data-title"));
});

// Run on first load and after every Material instant navigation.
if (window.document$ && typeof window.document$.subscribe === "function") {
  window.document$.subscribe(() => scanThumbs());
} else {
  scanThumbs();
  document.addEventListener("DOMContentLoaded", scanThumbs);
}
