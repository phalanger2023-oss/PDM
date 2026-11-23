// Partie "navigateur" : affiche le PDF et capte vos actions (surlignage, notes, texte, formes,
// édition du contenu natif), puis envoie le tout à Python (app.py) pour enregistrer ou télécharger.

pdfjsLib.GlobalWorkerOptions.workerSrc = window.PDFJS_WORKER || "/static/vendor/pdf.worker.min.js";

const $ = (id) => document.getElementById(id);
const NS = "http://www.w3.org/2000/svg";
const enc = encodeURIComponent;

// Si la connexion a expiré (le serveur répond « 401 »), on renvoie vers la page de connexion
const _fetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const res = await _fetch(...args);
  if (res.status === 401) location.href = "/login";
  return res;
};

// ====================== Préférences (thème, palette, couleurs, taille, zoom...) ======================
const APP_NAME = "Personal Document Modifier";
// Accents proposés : le graphite en premier (par défaut), puis des teintes douces dans l'esprit Notion
const ACCENTS = ["#37352f", "#c2693c", "#9f6b53", "#5a8f6a", "#8f6bb5", "#c4577b", "#4f7396"];
const HL_COLORS = ["#ffe000", "#69db7c", "#ff8fab", "#74c0fc", "#ffa94d"];
const ZOOM_STEPS = [0.75, 1, 1.25, 1.5, 1.75, 2, 2.5, 3];
const DEFAULT_PREFS = { theme: "auto", palette: "notion", accent: null, bg: null, surface: null, font: "notion", radius: null, css: "", ui: 1, hl: HL_COLORS[0], zoom: 1.5 };
let prefs = { ...DEFAULT_PREFS };
try { Object.assign(prefs, JSON.parse(localStorage.getItem("prefs") || "{}")); } catch (e) {}

let SCALE = prefs.zoom; // zoom d'affichage. Les annotations sont stockées à l'échelle 1 (= unités PDF).

function savePrefs() { try { localStorage.setItem("prefs", JSON.stringify(prefs)); } catch (e) {} }

function applyPrefs() {
  const root = document.documentElement;
  applyAppearance(prefs); // theme-init.js : palette, accent, fond et surfaces
  root.style.setProperty("--ui", prefs.ui);
  const key = PALETTES[prefs.palette] ? prefs.palette : "notion";
  document.querySelectorAll("#themeSeg [data-theme]").forEach((b) => b.classList.toggle("active", b.dataset.theme === prefs.theme));
  document.querySelectorAll("#paletteSeg [data-palette]").forEach((b) => b.classList.toggle("active", b.dataset.palette === key));
  document.querySelectorAll("[data-ui]").forEach((b) => b.classList.toggle("active", Number(b.dataset.ui) === prefs.ui));
  document.querySelectorAll("#fontSeg [data-font]").forEach((b) => b.classList.toggle("active", b.dataset.font === (prefs.font || "notion")));
  $("radius").value = prefs.radius ?? (parseFloat(getComputedStyle(root).getPropertyValue("--radius")) || 4);
  if (document.activeElement !== $("customCss")) $("customCss").value = prefs.css || "";
  // les sélecteurs de couleur montrent la couleur réellement utilisée
  const css = (v) => getComputedStyle(root).getPropertyValue(v).trim();
  const hex = (v, d) => (/^#[0-9a-f]{6}$/i.test(v) ? v : d);
  $("accent").value = hex(prefs.accent || css("--accent"), "#37352f");
  $("bgColor").value = hex(prefs.bg || css("--bg"), "#f7f6f3");
  $("surfaceColor").value = hex(prefs.surface || css("--surface"), "#ffffff");
  document.querySelectorAll("#accentSw .sw").forEach((b) => b.classList.toggle("active", b.dataset.color === prefs.accent));
  document.querySelectorAll("#hlSw .sw").forEach((b) => b.classList.toggle("active", b.dataset.color === prefs.hl));
}
matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applyPrefs()); // thème « Auto » : suit l'ordinateur

function makeSwatches(container, colors, onPick) {
  colors.forEach((c) => {
    const b = el("button", "sw");
    b.style.background = c; b.dataset.color = c; b.title = c;
    b.addEventListener("click", () => onPick(c));
    container.appendChild(b);
  });
}
makeSwatches($("accentSw"), ACCENTS, (c) => { prefs.accent = c; savePrefs(); applyPrefs(); });
makeSwatches($("hlSw"), HL_COLORS, (c) => {
  prefs.hl = c; savePrefs(); applyPrefs();
  if (selectedHl) { selectedHl.color = c; markDirty(); redraw(); } // un surlignage est sélectionné : on le recolore
  else updateBars();
});
$("accent").addEventListener("input", (e) => { prefs.accent = e.target.value; savePrefs(); applyPrefs(); });
$("bgColor").addEventListener("input", (e) => { prefs.bg = e.target.value; savePrefs(); applyPrefs(); });
$("surfaceColor").addEventListener("input", (e) => { prefs.surface = e.target.value; savePrefs(); applyPrefs(); });
document.querySelectorAll("#themeSeg [data-theme]").forEach((b) =>
  b.addEventListener("click", () => { prefs.theme = b.dataset.theme; savePrefs(); applyPrefs(); }));
document.querySelectorAll("#paletteSeg [data-palette]").forEach((b) =>
  b.addEventListener("click", () => { prefs.palette = b.dataset.palette; prefs.bg = null; prefs.surface = null; savePrefs(); applyPrefs(); }));
document.querySelectorAll("[data-ui]").forEach((b) =>
  b.addEventListener("click", () => { prefs.ui = Number(b.dataset.ui); savePrefs(); applyPrefs(); }));
document.querySelectorAll("#fontSeg [data-font]").forEach((b) =>
  b.addEventListener("click", () => { prefs.font = b.dataset.font; savePrefs(); applyPrefs(); }));
$("radius").addEventListener("input", (e) => { prefs.radius = Number(e.target.value); savePrefs(); applyPrefs(); });
$("customCss").addEventListener("input", (e) => { prefs.css = e.target.value; savePrefs(); applyPrefs(); });
$("resetPrefs").addEventListener("click", () => {
  prefs = { ...DEFAULT_PREFS }; savePrefs(); applyPrefs();
  if (pdfDoc) setZoom(prefs.zoom);
});
$("theme").addEventListener("click", () => { // bascule rapide clair <-> sombre
  prefs.theme = isDarkNow(prefs.theme) ? "light" : "dark"; savePrefs(); applyPrefs();
});

// ====================== État du document ======================
let pdfDoc = null;
let docName = null;      // nom du fichier dans « Mes documents », ex. "Cours.pdf"
let pages = [];          // pour chaque page : { div, canvas, hlLayer, shapeSvg, tbLayer, shUi, noteLayer }
let highlights = [];     // { page, rects: [[x0,y0,x1,y1], ...], color }
let notes = [];          // { page, x, y, text }
let textboxes = [];      // { page, x0,y0,x1,y1, paras, font, size, color, align, fill, border }
let shapes = [];         // { page, kind, x0,y0,x1,y1, stroke, width, fill }
let natives = null;      // paragraphes du PDF lui-même (chargés à la demande) : voir section 7
let nimages = null;      // images du PDF lui-même
let selectedHl = null;   // surlignage sélectionné
let undoStack = [], undoIdx = -1, commitTimer = null; // annuler / rétablir : voir section 9bis
let saveState = "idle";  // enregistrement automatique : idle | pending | saving | saved | error
let projRev = 0;         // version du brouillon connue du serveur (détecte une modification depuis un autre onglet)
let resumePage = null;   // page à laquelle reprendre, lue dans le brouillon
let view = "home";       // "home" (accueil) ou "doc" (un document est ouvert)
let loading = false;     // pendant le chargement, on ne marque rien comme « modifié »
let renderToken = 0;

const viewer = $("viewer");
const statusEl = $("status");
const undoBtn = $("undo");
const nameInput = $("docname");

const isUnsaved = () => saveState === "pending" || saveState === "saving" || saveState === "error";

function markDirty() { // appelé à chaque vrai changement
  if (loading) return;
  scheduleCommit();    // une étape d'annulation
  scheduleAutosave();  // et l'enregistrement automatique du brouillon sur le serveur
}

// Quitter le document (accueil, autre document, déconnexion) : on attend que le brouillon soit bien enregistré
async function leaveCurrentDoc() {
  if (!docName) return true;
  if (commitTimer) commitNow();
  if (isUnsaved()) await flushSave();
  if (saveState === "error") {
    return confirm("Les dernières modifications n'ont pas pu être enregistrées sur le serveur.\nQuitter quand même ?");
  }
  return true;
}

// Fermeture de la page : on tente un dernier envoi discret (« keepalive ») ; on ne prévient que s'il est impossible
window.addEventListener("beforeunload", (e) => {
  if (!docName || !isUnsaved()) return;
  if (!flushSave(true)) { e.preventDefault(); e.returnValue = ""; }
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden" && docName && isUnsaved()) flushSave(true);
});

// ====================== 1. Ouvrir un PDF ======================
["file", "file2"].forEach((id) =>
  $(id).addEventListener("change", (e) => {
    const f = e.target.files[0];
    e.target.value = ""; // permet de rouvrir le même fichier plus tard
    if (f) openUpload(f);
  }));

// Glisser-déposer un PDF n'importe où sur la page
["dragenter", "dragover"].forEach((t) => document.addEventListener(t, (e) => {
  if (e.dataTransfer && [...e.dataTransfer.types].includes("Files")) { e.preventDefault(); document.body.classList.add("dragging"); }
}));
["dragleave", "drop"].forEach((t) => document.addEventListener(t, () => document.body.classList.remove("dragging")));
document.addEventListener("drop", (e) => {
  const f = e.dataTransfer && e.dataTransfer.files[0];
  if (!f) return;
  e.preventDefault();
  if (f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf")) openUpload(f);
  else fail("Ce fichier n'est pas un PDF.");
});

async function openUpload(file) { // un PDF choisi sur l'ordinateur : il est copié dans Mes documents, puis ouvert
  if (!(await leaveCurrentDoc())) return;
  notify("Envoi du PDF…", "ok", 8000);
  const form = new FormData();
  form.append("file", file);
  if (typeof cwd === "string" && cwd) form.append("folder", cwd);
  const res = await fetch("/api/docs", { method: "POST", body: form });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { fail(data.error || "Erreur à l'envoi"); return; }
  await openDoc(data.name, data, true);
}

function setView(v) { view = v; document.body.dataset.view = v; }

// Ouvre un document de Mes documents, en reprenant son brouillon s'il en a un
async function openDoc(name, pre = null, force = false) {
  if (!force && view === "doc" && docName === name) return;
  if (!force && docName && !(await leaveCurrentDoc())) return;
  closeDocState();
  setView("doc");
  setStatus("Chargement…");
  try {
    const [ar, pr] = await Promise.all([
      pre ? Promise.resolve(null) : fetch(`/api/docs/${enc(name)}/annotations`),
      fetch(`/api/docs/${enc(name)}/project`),
    ]);
    let data = pre;
    if (ar) {
      data = await ar.json();
      if (!ar.ok) { fail(data.error || "Document introuvable"); setView("home"); if (typeof goHome === "function") goHome(true); return; }
    }
    const project = pr.ok ? (await pr.json()).project : null;
    await applyDocument(data, project);
    document.title = stripPdf(data.name) + " · " + APP_NAME;
    if (typeof setRoute === "function") setRoute(data.name);
  } catch (e) {
    fail("Impossible d'ouvrir ce document.");
    closeDocState(); setView("home");
    if (typeof goHome === "function") goHome(true);
  }
}

// Remet tout à zéro quand on quitte un document (retour à l'accueil ou ouverture d'un autre)
function closeDocState() {
  clearTimeout(autosaveTimer); clearTimeout(retryTimer); clearTimeout(commitTimer);
  autosaveTimer = retryTimer = commitTimer = null;
  pendingChange = false;
  teardownPages();
  docName = null; pdfDoc = null; pages = []; viewer.replaceChildren();
  highlights = []; notes = []; textboxes = []; shapes = []; natives = null; nimages = null;
  selected = null; selectedShape = null; selectedHl = null; selectedImage = null;
  boxEls.clear(); imgEls.clear();
  undoStack = []; undoIdx = -1; projRev = 0; resumePage = null; savedAt = null;
  setSaveState("idle");
  $("namebox").hidden = true;
  if (typeof onDocClosed === "function") onDocClosed();
  updateCounters();
}

// Le brouillon (s'il existe) l'emporte sur les annotations lues dans le PDF
async function applyDocument(data, project) {
  loading = true;
  docName = data.name;
  const st = project && project.state;
  projRev = project ? project.rev : 0;
  highlights = (st ? st.highlights : data.highlights) || [];
  notes = (st ? st.notes : data.notes) || [];
  textboxes = (st ? st.textboxes : data.textboxes) || [];
  shapes = (st ? st.shapes : data.shapes) || [];
  resumePage = st && Number(st.lastPage) > 0 ? Number(st.lastPage) : null;
  natives = null; nimages = null;
  nameInput.value = stripPdf(docName);
  fitName();
  $("namebox").hidden = false;
  pdfDoc = await pdfjsLib.getDocument(`/api/docs/${enc(docName)}/pdf?t=${Date.now()}`).promise;
  if (innerWidth < 900) { // petit écran : on ajuste d'emblée la page à la largeur disponible
    const p1 = await pdfDoc.getPage(1);
    SCALE = clamp((viewer.clientWidth - 24) / p1.getViewport({ scale: 1 }).width, 0.5, 3);
  }
  await renderPages(true);
  if (st && ((st.natives || []).length || (st.nimages || []).length)) { // modifications du contenu du PDF à retrouver
    await ensureNative();
    applyProjectNatives(st);
  }
  loading = false;
  setSaveState(project ? "saved" : "idle");
  resetUndo();
  updateCounters();
  if (currentMode() === "native") ensureNative();
}

// Retrouve les paragraphes et images du PDF modifiés dans le brouillon (par page et position d'origine)
function applyProjectNatives(st) {
  const near = (a, b) => a.length === b.length && a.every((v, i) => Math.abs(v - b[i]) < 0.6);
  let lost = 0;
  for (const s of st.natives || []) {
    const n = (natives || []).find((x) => x.page === s.page && near(x.orig, s.orig));
    if (!n) { lost++; continue; }
    Object.assign(n, {
      x0: s.bbox[0], y0: s.bbox[1], x1: s.bbox[2], y1: s.bbox[3], paras: s.paras, font: s.font, size: s.size,
      color: s.color, align: s.align, lh: s.lh ?? n.lh, base0: s.base0 ?? n.base0, changed: true, deleted: !!s.deleted,
    });
  }
  for (const s of st.nimages || []) {
    const m = (nimages || []).find((x) => x.page === s.page && x.xref === s.xref && (!s.kind || (x.kind || "image") === s.kind) && near(x.orig, s.orig));
    if (!m) { lost++; continue; }
    Object.assign(m, { x0: s.bbox[0], y0: s.bbox[1], x1: s.bbox[2], y1: s.bbox[3], changed: true, deleted: !!s.deleted });
  }
  if (lost) notify(`${lost} modification(s) du contenu du PDF n'ont pas pu être retrouvées.`, "error", 6000);
  redrawQuiet();
}

const stripPdf = (n) => n.replace(/\.(pdf|pdmdoc)$/i, "");
function fitName() { nameInput.style.width = Math.min(Math.max(nameInput.value.length + 2, 10), 40) + "ch"; }
nameInput.addEventListener("input", fitName);
nameInput.addEventListener("keydown", (e) => { if (e.key === "Enter") nameInput.blur(); });
nameInput.addEventListener("change", renameCurrent); // le document est renommé dès que vous validez le nom

// ====================== 2. Affichage des pages (et zoom) ======================
// Pour rester fluide même sur un PDF de 300 pages : on crée tout de suite le cadre de CHAQUE page (à sa bonne
// taille : le défilement et « aller à la page » marchent aussitôt), mais l'IMAGE d'une page n'est dessinée que
// si elle est proche de l'écran, et elle est libérée quand on s'en éloigne. Sans cela, chaque page garde ~4 Mo
// en mémoire et un long PDF finit par saturer le navigateur. Le texte des pages (recherche, surlignage) est
// préparé en arrière-plan, en commençant par les pages les plus proches.
const DPR = () => Math.min(window.devicePixelRatio || 1, 2); // netteté sur les écrans haute densité
const MAX_CANVAS = 16;                 // nombre maximum d'images de pages gardées en mémoire
let paintQueue = [], paintBusy = 0;
let renderDepth = 0, loadingBeforeRender = false; // affichages en cours (voir renderPages)
let textReady = Promise.resolve();     // se termine quand le texte de toutes les pages est prêt (recherche)

function distToView(p) { // distance (en pixels) entre une page et le milieu de l'écran
  const r = p.div.getBoundingClientRect(), mid = innerHeight / 2;
  return r.top <= mid && r.bottom >= mid ? 0 : Math.min(Math.abs(r.top - mid), Math.abs(r.bottom - mid));
}

async function paintCanvas(p, token) { // dessine l'image de la page
  if (p.canvasState !== "empty") return;
  p.canvasState = "rendering";
  try {
    const page = await pdfDoc.getPage(p.num);
    if (token !== renderToken || p.canvasState !== "rendering") return;
    const dpr = DPR(), cv = p.canvas;
    cv.width = Math.floor(p.vp.width * dpr);
    cv.height = Math.floor(p.vp.height * dpr);
    // annotationMode DISABLE : on ne dessine pas les annotations du PDF, c'est nous qui les affichons
    p.task = page.render({
      canvasContext: cv.getContext("2d"), viewport: p.vp,
      transform: dpr !== 1 ? [dpr, 0, 0, dpr, 0, 0] : undefined,
      annotationMode: pdfjsLib.AnnotationMode.DISABLE,
    });
    await p.task.promise;
    if (token !== renderToken || p.canvasState !== "rendering") return;
    p.canvasState = "ready";
    refreshCovers(p.num - 1);
    limitCanvases();
  } catch (e) {
    if (p.canvasState === "rendering") p.canvasState = "empty"; // annulé ou échoué : sera retenté au prochain passage
  }
}

function evictCanvas(p) { // libère la mémoire de l'image d'une page éloignée
  if (!p || p.canvasState === "empty") return;
  try { if (p.task) p.task.cancel(); } catch (e) {}
  p.canvas.width = 1; p.canvas.height = 1;
  p.canvasState = "empty";
  if (pdfDoc) pdfDoc.getPage(p.num).then((pg) => pg.cleanup()).catch(() => {});
}

function limitCanvases() { // garde-fou : jamais plus de MAX_CANVAS images en mémoire
  const ready = pages.filter((p) => p.canvasState === "ready");
  if (ready.length <= MAX_CANVAS) return;
  ready.sort((a, b) => distToView(b) - distToView(a)).slice(0, ready.length - MAX_CANVAS).forEach(evictCanvas);
}

async function paintText(p, token) { // prépare le texte sélectionnable de la page
  if (p.textState !== "empty") return;
  p.textState = "rendering";
  try {
    const page = await pdfDoc.getPage(p.num);
    const content = await page.getTextContent();
    if (token !== renderToken) return;
    await pdfjsLib.renderTextLayer({ textContentSource: content, container: p.textLayer, viewport: p.vp }).promise;
    p.textState = "ready";
  } catch (e) { p.textState = "empty"; }
}

function queuePaint(p, token) {
  if (!paintQueue.includes(p)) paintQueue.push(p);
  pumpPaint(token);
}
function pumpPaint(token) { // dessine 2 pages à la fois, les plus proches de l'écran d'abord
  while (paintBusy < 2 && paintQueue.length && token === renderToken) {
    paintQueue.sort((a, b) => distToView(a) - distToView(b));
    const p = paintQueue.shift();
    if (distToView(p) > innerHeight * 4) continue; // on s'est éloigné entre-temps : inutile
    paintBusy++;
    Promise.all([paintCanvas(p, token), paintText(p, token)]).finally(() => { paintBusy--; pumpPaint(token); });
  }
}

// Quelles pages dessiner ? Celles à moins d'un écran de la zone visible. Celles à plus de 3 écrans sont libérées.
// (Calcul simple à partir de la position de défilement : fiable partout, même quand le navigateur ne signale rien.)
function updateVisible() {
  if (!pages.length) return;
  const y0 = window.scrollY, y1 = y0 + innerHeight;
  const nearLo = y0 - innerHeight, nearHi = y1 + innerHeight;
  const farLo = y0 - innerHeight * 3, farHi = y1 + innerHeight * 3;
  for (const p of pages) {
    const top = p.div.offsetTop, bottom = top + p.div.offsetHeight;
    if (bottom >= nearLo && top <= nearHi) {
      if (p.canvasState === "empty" || p.textState === "empty") queuePaint(p, renderToken);
    } else if (bottom < farLo || top > farHi) evictCanvas(p);
  }
}
let visTimer = null;
function scheduleVisible() { clearTimeout(visTimer); visTimer = setTimeout(updateVisible, 50); }
window.addEventListener("scroll", scheduleVisible, { passive: true });
window.addEventListener("resize", scheduleVisible);

async function backgroundText(token) { // le texte de toutes les pages, en douceur, pour la recherche
  await new Promise((r) => setTimeout(r, 150));
  while (token === renderToken) {
    const next = pages.filter((p) => p.textState === "empty").sort((a, b) => distToView(a) - distToView(b))[0];
    if (!next) break;
    await paintText(next, token);
    await new Promise((r) => setTimeout(r, 0)); // laisse respirer l'interface
  }
  while (token === renderToken && pages.some((p) => p.textState === "rendering")) await new Promise((r) => setTimeout(r, 40));
}

function teardownPages() { // annule les dessins en cours et libère les anciennes pages
  paintQueue = []; paintBusy = 0;
  for (const p of pages) { try { if (p.task) p.task.cancel(); } catch (e) {} }
}

async function renderPages(initial = false) {
  if (!pdfDoc) return;
  const token = ++renderToken;
  // Plusieurs affichages peuvent se chevaucher (zoom rapide) : on retient l'état « chargement » du tout premier,
  // pour ne jamais rester bloqué en « chargement » (ce qui empêcherait l'enregistrement automatique).
  if (renderDepth === 0) loadingBeforeRender = loading;
  renderDepth++;
  loading = true;
  // Zoom : on garde la position de lecture. Ouverture d'un document : on repart du haut (le défilement
  // de la page d'accueil ne doit surtout pas être réutilisé).
  const ratio = initial ? 0 : window.scrollY / Math.max(1, document.documentElement.scrollHeight - innerHeight);
  teardownPages();
  viewer.innerHTML = "";
  pages = [];
  boxEls.clear();
  imgEls.clear();

  const total = pdfDoc.numPages;
  for (let n = 1; n <= total; n++) {
    const page = await pdfDoc.getPage(n);
    if (token !== renderToken) { renderDepth--; return; } // un autre affichage a pris le relais (zoom rapide)
    const vp = page.getViewport({ scale: SCALE });

    const div = el("div", "page");
    div.style.setProperty("--scale-factor", SCALE); // exigé par PDF.js pour dimensionner le texte
    div.style.width = vp.width + "px";
    div.style.height = vp.height + "px";

    const canvas = document.createElement("canvas"); // vide au départ : dessiné seulement quand la page approche
    canvas.width = 1; canvas.height = 1;
    canvas.style.width = vp.width + "px"; canvas.style.height = vp.height + "px";
    div.appendChild(canvas);

    const hlLayer = el("div", "hl-layer");
    const textLayer = el("div", "textLayer");
    const shapeSvg = document.createElementNS(NS, "svg");
    shapeSvg.setAttribute("class", "shape-layer");
    shapeSvg.setAttribute("width", vp.width);
    shapeSvg.setAttribute("height", vp.height);
    const tbLayer = el("div", "tb-layer");
    const shUi = el("div", "sh-ui");
    const noteLayer = el("div", "note-layer");
    div.append(hlLayer, textLayer, shapeSvg, tbLayer, shUi, noteLayer);
    viewer.appendChild(div);

    const p = { num: n, div, canvas, vp, hlLayer, textLayer, shapeSvg, tbLayer, shUi, noteLayer,
                canvasState: "empty", textState: "empty", task: null };
    pages.push(p);
    div.addEventListener("click", (ev) => onPageClick(ev, n - 1));
    div.addEventListener("mousedown", (ev) => { startTextBox(ev, n - 1); startShape(ev, n - 1); });
    if (n % 25 === 0) { setProgress(n, total); await new Promise((r) => setTimeout(r, 0)); }
  }
  redraw();
  window.scrollTo(0, ratio * Math.max(0, document.documentElement.scrollHeight - innerHeight));
  renderDepth--;
  loading = loadingBeforeRender;
  setProgress(0);
  updateCounters();

  updateVisible(); // dessine les pages visibles (et celles juste autour)
  textReady = backgroundText(token);
  if (typeof onPagesRendered === "function") onPagesRendered(initial); // navigation : miniatures, recherche...
}

function setZoom(v) {
  SCALE = v; prefs.zoom = v; savePrefs();
  return renderPages();
}
$("zoomIn").addEventListener("click", () => { const v = ZOOM_STEPS.find((z) => z > SCALE + 0.01); if (v) setZoom(v); });
$("zoomOut").addEventListener("click", () => { const v = [...ZOOM_STEPS].reverse().find((z) => z < SCALE - 0.01); if (v) setZoom(v); });

// ====================== 3. Surligner ======================
document.addEventListener("mouseup", () => {
  if (currentMode() !== "highlight") return;
  if (activeEditor()) return;
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || sel.rangeCount === 0) return;

  // Chaque ligne de texte sélectionnée donne un rectangle ; on le rattache à sa page.
  const perPage = {};
  for (const r of sel.getRangeAt(0).getClientRects()) {
    if (r.width < 1 || r.height < 1) continue;
    const cx = r.left + r.width / 2, cy = r.top + r.height / 2;
    const idx = pages.findIndex(({ div }) => {
      const b = div.getBoundingClientRect();
      return cx >= b.left && cx <= b.right && cy >= b.top && cy <= b.bottom;
    });
    if (idx < 0) continue;
    const b = pages[idx].div.getBoundingClientRect();
    (perPage[idx] ||= []).push([
      (r.left - b.left) / SCALE, (r.top - b.top) / SCALE,
      (r.right - b.left) / SCALE, (r.bottom - b.top) / SCALE,
    ]);
  }
  for (const [idx, rects] of Object.entries(perPage)) {
    const h = { page: Number(idx) + 1, rects, color: prefs.hl };
    highlights.push(h);
  }
  sel.removeAllRanges();
  markDirty();
  redraw();
});

// ====================== 4. Notes ======================
function onPageClick(ev, pageIndex) {
  const mode = currentMode();
  const b = pages[pageIndex].div.getBoundingClientRect();
  // Un clic (sans glisser) sur un surlignage le sélectionne : on peut alors le recolorer ou le supprimer
  if ((mode === "select" || mode === "highlight") && window.getSelection().isCollapsed &&
      !ev.target.closest(".tb, .note, .ni, .hit, .sh-handle")) {
    selectHl(hlAt(pageIndex, (ev.clientX - b.left) / SCALE, (ev.clientY - b.top) / SCALE));
    return;
  }
  if (mode !== "note" || ev.target.closest(".note") || ev.target.closest(".tb")) return;
  const text = prompt("Texte de la note :");
  if (!text) return;
  const note = {
    page: pageIndex + 1,
    x: (ev.clientX - b.left) / SCALE,
    y: (ev.clientY - b.top) / SCALE,
    text,
  };
  notes.push(note);
  markDirty();
  redraw();
}

// ---- Surlignages existants : sélectionner, recolorer, supprimer ----
function hlAt(pi, x, y) { // surlignage sous le point (x, y), en unités du PDF
  for (let i = highlights.length - 1; i >= 0; i--) {
    const h = highlights[i];
    if (h.page === pi + 1 && h.rects.some((r) => x >= r[0] - 1 && x <= r[2] + 1 && y >= r[1] - 1 && y <= r[3] + 1)) return h;
  }
  return null;
}
function selectHl(h) {
  selectedHl = h;
  if (h) { // un seul élément sélectionné à la fois
    if (selected) select(null);
    if (selectedShape) setSelectedShape(null);
    if (selectedImage) selectImage(null);
  }
  drawHlSelection();
  updateBars();
}
function drawHlSelection() { // contour du surlignage sélectionné
  document.querySelectorAll(".hl-sel").forEach((d) => d.remove());
  if (!selectedHl) return;
  for (const [x0, y0, x1, y1] of selectedHl.rects) {
    const d = el("div", "hl-sel");
    Object.assign(d.style, {
      left: x0 * SCALE + "px", top: y0 * SCALE + "px",
      width: (x1 - x0) * SCALE + "px", height: (y1 - y0) * SCALE + "px",
    });
    pages[selectedHl.page - 1]?.hlLayer.appendChild(d);
  }
}
function deleteSelectedHl() {
  if (!selectedHl) return;
  highlights = highlights.filter((h) => h !== selectedHl);
  selectedHl = null;
  markDirty();
  redraw();
}
function updateBars() { // la barre des surlignages s'affiche en mode Surligner, ou quand un surlignage est sélectionné
  $("hlbar").hidden = !(currentMode() === "highlight" || selectedHl);
  $("hDelete").disabled = !selectedHl;
  const cur = selectedHl ? selectedHl.color : prefs.hl;
  document.querySelectorAll("#hlSw .sw").forEach((b) => b.classList.toggle("active", b.dataset.color === cur));
}
$("hDelete").addEventListener("click", deleteSelectedHl);

// ====================== 5. Texte riche (gras, italique, souligné, barré) ======================
// Le texte d'une zone est une liste de paragraphes ; un paragraphe est une liste de « runs » :
//   { t: "texte", b: 1, i: 1, u: 1, s: 1 }  (b gras, i italique, u souligné, s barré)
// C'est le même format côté Python.
const escHtml = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function parasToHtml(paras) {
  let html = "";
  paras.forEach((p, pi) => {
    if (pi) html += "<br>";
    for (const r of p) {
      let t = escHtml(r.t);
      if (r.c && /^#[0-9a-fA-F]{6}$/.test(r.c)) t = `<span style="color:${r.c}">${t}</span>`; // couleur propre à ce morceau (lue dans le PDF)
      if (r.b) t = `<b>${t}</b>`;
      if (r.i) t = `<i>${t}</i>`;
      if (r.u) t = `<u>${t}</u>`;
      if (r.s) t = `<s>${t}</s>`;
      html += t;
    }
  });
  if (paras.length && !paras[paras.length - 1].length) html += "<br>"; // ligne vide finale : il faut un 2e <br>
  return html;
}

// Relit le contenu de l'éditeur : fonctionne même si une extension (QuillBot...) a modifié le HTML.
function readParas(ed) {
  const paras = [[]];
  let needNl = false, started = false, lastBr = false;
  const nl = () => paras.push([]);
  const push = (t, f) => {
    if (needNl) { nl(); needNl = false; }
    const run = { t };
    for (const k of ["b", "i", "u", "s"]) if (f[k]) run[k] = 1;
    if (f.c) run.c = f.c;
    const cur = paras[paras.length - 1], prev = cur[cur.length - 1];
    if (prev && ["b", "i", "u", "s"].every((k) => (prev[k] || 0) === (run[k] || 0)) && (prev.c || "") === (run.c || "")) prev.t += t;
    else cur.push(run);
    started = true; lastBr = false;
  };
  const walk = (node, fmt) => {
    for (const n of node.childNodes) {
      if (n.nodeType === 3) {
        const parts = n.nodeValue.replace(/ /g, " ").replace(/\r/g, "").split("\n");
        parts.forEach((part, i) => { if (i) { nl(); lastBr = false; } if (part) push(part, fmt); });
      } else if (n.nodeType === 1) {
        const tag = n.tagName;
        if (tag === "BR") {
          if (needNl) { nl(); needNl = false; } else nl();
          started = true; lastBr = true;
          continue;
        }
        const cs = getComputedStyle(n), f = { ...fmt }, td = cs.textDecorationLine || "";
        if (tag === "B" || tag === "STRONG" || parseInt(cs.fontWeight, 10) >= 600) f.b = 1;
        if (tag === "I" || tag === "EM" || cs.fontStyle === "italic") f.i = 1;
        if (tag === "U" || td.includes("underline")) f.u = 1;
        if (tag === "S" || tag === "STRIKE" || tag === "DEL" || td.includes("line-through")) f.s = 1;
        if (n.style && n.style.color) { const m = /rgba?\((\d+),\s*(\d+),\s*(\d+)/.exec(cs.color); if (m) f.c = "#" + [m[1], m[2], m[3]].map((v) => Number(v).toString(16).padStart(2, "0")).join(""); }
        const block = tag === "DIV" || tag === "P";
        if (block && started) needNl = true;
        walk(n, f);
        if (block) needNl = true;
      }
    }
  };
  walk(ed, {});
  if (lastBr && paras.length > 1 && !paras[paras.length - 1].length) paras.pop(); // le <br> « de remplissage » final
  return paras;
}

function plainOf(paras) { return paras.map((p) => p.map((r) => r.t).join("")).join("\n"); }

function activeEditor() {
  const a = document.activeElement;
  return a && a.classList && a.classList.contains("ed") ? a : null;
}

// Boutons G / I / S / barré : agissent sur le texte sélectionné dans la zone en cours d'édition
try { document.execCommand("styleWithCSS", false, false); } catch (e) {}
document.querySelectorAll(".fmt").forEach((b) => {
  b.addEventListener("mousedown", (e) => e.preventDefault()); // garde la sélection dans la zone
  b.addEventListener("click", () => { if (activeEditor()) document.execCommand(b.dataset.cmd); });
});
document.addEventListener("selectionchange", () => {
  const ed = activeEditor();
  document.querySelectorAll(".fmt").forEach((b) => {
    let on = false;
    try { on = !!ed && document.queryCommandState(b.dataset.cmd); } catch (e) {}
    b.classList.toggle("active", on);
  });
});

// ====================== 6. Zones de texte (annotations) ======================
const defaults = { font: "helv", size: 14, color: "#000000", align: 0, fill: null, border: false, lh: 1.2 };
const FONT_CSS = {
  helv: "Helvetica, Arial, sans-serif",
  tiro: '"Times New Roman", Times, serif',
  cour: '"Courier New", Courier, monospace',
  carl: 'Carlito, Calibri, sans-serif', cala: 'Caladea, Cambria, serif', card: 'Cardo, Georgia, serif',
  crim: '"Crimson Text", Georgia, serif', deja: '"DejaVu Sans", Verdana, sans-serif',
  comi: '"Comic Relief", "Comic Sans MS", cursive', anto: 'Anton, Impact, sans-serif',
};
const ALIGN_CSS = ["left", "center", "right"];
const boxEls = new Map(); // zone de texte (ou paragraphe natif) -> son élément HTML
let selected = null;      // zone de texte (ou paragraphe natif) sélectionné

// ---- Calques : « z » ordonne zones de texte et formes entre elles (le plus grand est au-dessus) ----
function nextZ() { return Math.max(0, ...textboxes.map((t) => t.z || 0), ...shapes.map((t) => t.z || 0)) + 1; }
function ensureZ() { // anciens brouillons : pas de z. Ordre d'avant : zones de texte puis formes
  let z = Math.max(0, ...textboxes.map((t) => t.z || 0), ...shapes.map((t) => t.z || 0));
  for (const it of [...textboxes, ...shapes]) if (!it.z) it.z = ++z;
}
function layerItem() { return selectedShape || (selected && !selected.native && textboxes.includes(selected) ? selected : null); }
function moveLayer(how) {
  const it = layerItem();
  if (!it) return;
  const same = [...textboxes, ...shapes].filter((x) => x.page === it.page).sort((a, b) => a.z - b.z);
  const i = same.indexOf(it);
  if (how === "front") it.z = nextZ();
  else if (how === "back") it.z = Math.min(...same.map((x) => x.z)) - 1;
  else {
    const o = same[i + (how === "forward" ? 1 : -1)];
    if (!o) return;
    [it.z, o.z] = [o.z, it.z];
  }
  markDirty();
  if (it === selectedShape) renderShapes(it.page - 1); else redraw();
}
document.querySelectorAll("[data-layer]").forEach((b) => {
  b.addEventListener("mousedown", (e) => e.preventDefault());
  b.addEventListener("click", () => moveLayer(b.dataset.layer));
});

// Créer : mode « Texte », puis cliquer-glisser pour tracer le rectangle.
function startTextBox(ev, pageIndex) {
  if (currentMode() !== "text" || ev.button !== 0) return;
  if (ev.target.closest(".tb") || ev.target.closest(".note")) return;
  ev.preventDefault();

  const pageDiv = pages[pageIndex].div;
  const b = pageDiv.getBoundingClientRect();
  const x0 = ev.clientX - b.left, y0 = ev.clientY - b.top;
  const band = el("div", "rubber");
  pageDiv.appendChild(band);

  const rect = (e) => {
    const x1 = Math.min(Math.max(e.clientX - b.left, 0), b.width);
    const y1 = Math.min(Math.max(e.clientY - b.top, 0), b.height);
    return [Math.min(x0, x1), Math.min(y0, y1), Math.max(x0, x1), Math.max(y0, y1)];
  };
  const move = (e) => {
    const [a, c, d, f] = rect(e);
    Object.assign(band.style, { left: a + "px", top: c + "px", width: d - a + "px", height: f - c + "px" });
  };
  const up = (e) => {
    window.removeEventListener("mousemove", move);
    window.removeEventListener("mouseup", up);
    band.remove();
    let [a, c, d, f] = rect(e);
    // simple clic sans tracer : zone par défaut de 200 points de large, deux lignes de haut
    if (d - a < 20 || f - c < 20) { d = a + 200 * SCALE; f = c + defaults.size * 2.4 * SCALE; }
    const tb = {
      page: pageIndex + 1, x0: a / SCALE, y0: c / SCALE, x1: d / SCALE, y1: f / SCALE,
      paras: [[]], ...defaults, z: nextZ(),
    };
    textboxes.push(tb);
    selected = tb;
    markDirty();
    redraw();
    boxEls.get(tb).querySelector(".ed").focus();
  };
  window.addEventListener("mousemove", move);
  window.addEventListener("mouseup", up);
}

// Construit l'élément HTML d'une zone de texte (ou d'un paragraphe natif ; idle = pas encore touché)
function buildBox(tb, idle = false) {
  const box = el("div", "tb" + (tb.native ? " native" : "") + (idle ? " idle" : "") + (tb.nowrap ? " nowrap" : ""));
  // Un éditeur de texte standard (contenteditable) : les correcteurs (QuillBot, Grammarly, correcteur du
  // navigateur) le reconnaissent et peuvent y corriger le texte.
  const ed = el("div", "ed");
  ed.contentEditable = idle ? "false" : "true";
  ed.spellcheck = false;   // le correcteur ne s'active que dans la zone sélectionnée (voir select)
  ed.lang = "fr";
  ed.setAttribute("role", "textbox");
  ed.setAttribute("aria-multiline", "true");
  ed.setAttribute("aria-label", tb.native ? "Texte du PDF" : "Texte de la zone");
  ed.innerHTML = parasToHtml(tb.paras);
  box._base = JSON.stringify(readParas(ed));  // forme « normalisée » de départ : sert à détecter une vraie modification
  const grip = el("div", "tb-grip"); grip.textContent = "✥"; grip.title = "Déplacer";
  const rz = el("div", "tb-resize"); rz.title = "Redimensionner";
  box.append(ed, grip);
  let edgeL, edgeR, topH;
  if (tb.native) box.append(rz);
  else { // zone de texte : barres latérales = largeur du texte, poignée du haut = taille du texte
    edgeL = el("div", "tb-edge l"); edgeL.title = "Largeur de la zone";
    edgeR = el("div", "tb-edge r"); edgeR.title = "Largeur de la zone";
    topH = el("div", "tb-top"); topH.title = "Glisser vers le haut / le bas : agrandir / réduire le texte";
    box.append(edgeL, edgeR, topH);
  }
  boxEls.set(tb, box);
  styleBox(tb);

  if (idle) { // paragraphe du PDF pas encore touché : un clic l'active
    box.addEventListener("mousedown", (ev) => { ev.preventDefault(); activateNative(tb, ev.clientX, ev.clientY); });
  } else {
    box.addEventListener("mousedown", () => select(tb));
    ed.addEventListener("focus", () => select(tb));
    ed.addEventListener("keydown", (e) => { // Entrée = saut de ligne simple (pas de <div> imbriqués)
      if (e.key === "Enter") { e.preventDefault(); document.execCommand("insertLineBreak"); }
    });
    ed.addEventListener("paste", (e) => { // on colle toujours du texte brut
      e.preventDefault();
      const t = ((e.clipboardData || window.clipboardData).getData("text/plain") || "").replace(/\r/g, "");
      t.split("\n").forEach((ln, i) => {
        if (i) document.execCommand("insertLineBreak");
        if (ln) document.execCommand("insertText", false, ln);
      });
    });
    // Une extension peut modifier le texte sans frappe : on relit à chaque événement utile
    ["input", "blur"].forEach((evn) => ed.addEventListener(evn, () => { syncBox(tb, box); fitBox(tb); updateCounters(); }));
    dragHandle(grip, tb, "move");
    if (tb.native) dragHandle(rz, tb, "resize");
    else { dragHandle(edgeL, tb, "left"); dragHandle(edgeR, tb, "right"); dragHandle(topH, tb, "scale"); }
  }
  pages[tb.page - 1].tbLayer.appendChild(box);
  fitBox(tb);
}

// Recopie le texte affiché dans le modèle, seulement s'il a vraiment changé
function syncBox(tb, box) {
  const ed = box.querySelector(".ed");
  const p = readParas(ed), s = JSON.stringify(p);
  if (s === box._base) return;
  box._base = s;
  tb.paras = p;
  if (tb.native) tb.changed = true;
  markDirty();
}
function syncTextFromDom() {
  boxEls.forEach((box, tb) => { if (!box.classList.contains("idle")) syncBox(tb, box); });
}

// Applique position, taille et mise en page à l'élément d'une zone
function styleBox(tb) {
  const box = boxEls.get(tb);
  if (!box) return;
  const nat = !!tb.native;
  Object.assign(box.style, {
    left: tb.x0 * SCALE + "px", top: tb.y0 * SCALE + "px",
    width: (tb.x1 - tb.x0) * SCALE + "px",
    height: "auto",   // la zone grandit avec son texte (Entrée ajoute une ligne)
    minHeight: nat ? (tb.y1 - tb.y0) * SCALE + "px" : "",
    background: tb.fill || "transparent",
    border: tb.border ? `${SCALE}px solid ${tb.color}` : "none",
  });
  const lh = tb.lh || 1.2;
  if (!nat) box.style.zIndex = String(tb.z || 1);
  // Paragraphe natif : on place la 1re ligne de base comme dans le PDF d'origine
  const padTop = nat ? Math.max(0, (tb.base0 - tb.size * (lh / 2 + 0.3465)) * SCALE) : 2 * SCALE;
  Object.assign(box.querySelector(".ed").style, {
    fontFamily: FONT_CSS[tb.font] || FONT_CSS.helv,
    fontSize: tb.size * SCALE + "px",
    lineHeight: String(lh),
    color: tb.color,
    textAlign: ALIGN_CSS[tb.align] || "left",
    padding: nat ? `${padTop}px 0 0 0` : 2 * SCALE + "px",
  });
  if (!nat) fitBox(tb);
}

// La hauteur d'une zone de texte = celle de son texte : on la relit après chaque changement
function fitBox(tb) {
  const box = boxEls.get(tb);
  if (!box || tb.native) return;
  const h = box.offsetHeight;
  if (h > 0) tb.y1 = tb.y0 + h / SCALE;
}
if (document.fonts && document.fonts.ready) document.fonts.ready.then(() => boxEls.forEach((b, t) => fitBox(t)));

// Déplacer (poignée ✥) ou redimensionner (poignée en bas à droite) à la souris
function dragHandle(handle, tb, kind) {
  handle.addEventListener("pointerdown", (ev) => {
    ev.preventDefault(); ev.stopPropagation();
    select(tb);
    handle.setPointerCapture(ev.pointerId);
    const sx = ev.clientX, sy = ev.clientY;
    const o = { x0: tb.x0, y0: tb.y0, x1: tb.x1, y1: tb.y1, size: tb.size };
    const move = (e) => {
      const dx = (e.clientX - sx) / SCALE, dy = (e.clientY - sy) / SCALE;
      if (kind === "move") {
        tb.x0 = o.x0 + dx; tb.x1 = o.x1 + dx; tb.y0 = o.y0 + dy; tb.y1 = o.y1 + dy;
      } else if (kind === "right") {
        tb.x1 = Math.max(o.x1 + dx, o.x0 + 20);
      } else if (kind === "left") {
        tb.x0 = Math.min(o.x0 + dx, o.x1 - 20);
      } else if (kind === "scale") { // glisser vers le haut : texte plus grand (même largeur de zone)
        const h0 = Math.max(o.y1 - o.y0, 10);
        tb.size = Math.round(Math.min(Math.max(o.size * (1 - dy / (h0 + 30)), 6), 200) * 2) / 2;
        fSize.value = tb.size;
      } else {
        tb.x1 = Math.max(o.x1 + dx, o.x0 + 20); tb.y1 = Math.max(o.y1 + dy, o.y0 + 14);
      }
      styleBox(tb);
    };
    const up = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", up);
      if (tb.native) tb.changed = true;
      fitBox(tb);
      markDirty();
      updateSelectionButtons();
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
  });
}

// Sélection d'une zone : la barre de mise en page reflète alors ses réglages
function select(tb) {
  const prev = selected;
  if (prev && prev !== tb && !prev.native && textboxes.includes(prev) && !plainOf(prev.paras || []).trim()) {
    textboxes = textboxes.filter((x) => x !== prev); // zone vide qu'on quitte : elle disparaît
    const pe_ = boxEls.get(prev); if (pe_) { pe_.remove(); boxEls.delete(prev); }
    markDirty();
  }
  selected = tb;
  if (tb && selectedHl) selectHl(null);
  if (tb && selectedImage) { selectedImage = null; imgEls.forEach((b) => b.classList.remove("selected")); }
  boxEls.forEach((box, t) => {
    box.classList.toggle("selected", t === tb);
    const ed = box.querySelector(".ed");
    if (ed) ed.spellcheck = t === tb && !box.classList.contains("idle"); // correcteur : seulement la zone choisie
  });
  updateSelectionButtons();
  syncControls(tb || defaults);
}

function updateSelectionButtons() {
  $("fDelete").disabled = !(selected || selectedImage);
  const s = selected, im = selectedImage;
  $("fReset").disabled = !((s && s.native && (s.changed || s.deleted || s.active)) || (im && (im.changed || im.deleted)));
}

// Barre de mise en page du texte
const fFont = $("fFont"), fSize = $("fSize"), fColor = $("fColor");
const fFillOn = $("fFillOn"), fFill = $("fFill"), fBorder = $("fBorder"), fLh = $("fLh");
const alignBtns = document.querySelectorAll("[data-align]");

function syncControls(s) {
  fFont.value = s.font; fSize.value = s.size; fColor.value = s.color; fLh.value = s.lh || 1.2;
  fFillOn.setAttribute("aria-pressed", String(!!s.fill)); if (s.fill) fFill.value = s.fill;
  fBorder.setAttribute("aria-pressed", String(!!s.border));
  alignBtns.forEach((b) => b.classList.toggle("active", Number(b.dataset.align) === s.align));
}

// Un réglage change : on l'applique à la zone sélectionnée (sinon aux prochaines zones)
function applyStyle(patch) {
  if (selected && selected.native) { // paragraphe du PDF : on ne touche pas aux réglages des futures zones
    Object.assign(selected, patch);
    if (patch.color && selected.paras) { // choisir une couleur pour tout le paragraphe efface les couleurs propres à certains morceaux
      selected.paras.forEach((p) => p.forEach((r) => { delete r.c; }));
      const bx = boxEls.get(selected), ed = bx && bx.querySelector(".ed");
      if (ed) { ed.querySelectorAll("span[style]").forEach((sp) => { sp.style.removeProperty("color"); }); bx._base = JSON.stringify(readParas(ed)); }
    }
    selected.changed = true;
    styleBox(selected); markDirty(); updateSelectionButtons(); syncControls(selected);
    return;
  }
  Object.assign(defaults, patch);
  if (selected) { Object.assign(selected, patch); styleBox(selected); markDirty(); }
  syncControls(selected || defaults);
}
const pressed = (b) => b.getAttribute("aria-pressed") === "true";
fFont.addEventListener("change", () => applyStyle({ font: fFont.value }));
fSize.addEventListener("input", () => applyStyle({ size: Math.min(Math.max(Number(fSize.value) || 14, 6), 120) }));
fColor.addEventListener("input", () => applyStyle({ color: fColor.value }));
fLh.addEventListener("input", () => { const v = Number(fLh.value); if (v >= 0.8 && v <= 3) applyStyle({ lh: Math.round(v * 100) / 100 }); });
fFillOn.addEventListener("click", () => applyStyle({ fill: pressed(fFillOn) ? null : fFill.value }));
fFill.addEventListener("input", () => applyStyle({ fill: fFill.value }));
fBorder.addEventListener("click", () => applyStyle({ border: !pressed(fBorder) }));
alignBtns.forEach((b) => b.addEventListener("click", () => applyStyle({ align: Number(b.dataset.align) })));

function deleteSelectedBox() {
  if (!selected) return;
  const t = selected;
  if (t.native) { t.deleted = true; t.changed = true; t.active = false; }
  else {
    textboxes = textboxes.filter((x) => x !== t);
  }
  selected = null;
  markDirty();
  redraw();
}
function deleteSelected() { if (selectedImage) deleteImage(); else deleteSelectedBox(); }
$("fDelete").addEventListener("click", deleteSelected);
$("fReset").addEventListener("click", () => {
  if (selectedImage) resetImage(selectedImage);
  else if (selected && selected.native) resetNative(selected);
});

// ====================== 7. Contenu natif du PDF : texte et images ======================
// Mode « Éditer le PDF » : Python lit les paragraphes et les images du PDF. Quand on en modifie un,
// l'original est effacé à l'enregistrement et le nouveau contenu est écrit à la place.
let selectedImage = null;
const imgEls = new Map();
let nativeLoading = null;

async function ensureNative() {
  if (natives || !docName) return;
  if (nativeLoading) return nativeLoading;
  setStatus("Analyse du PDF…");
  nativeLoading = (async () => {
    const res = await fetch(`/api/docs/${enc(docName)}/content`);
    natives = []; nimages = [];
    if (!res.ok) { fail("Impossible d'analyser ce PDF."); return; }
    const data = await res.json();
    data.pages.forEach((p, pi) => {
      for (const b of p.blocks) {
        if (b.locked) continue;
        natives.push({
          native: true, page: pi + 1, orig: [...b.bbox],
          x0: b.bbox[0], y0: b.bbox[1], x1: b.bbox[2], y1: b.bbox[3],
          paras: b.paras, font: b.font, size: b.size, color: b.color, align: b.align, lh: b.lh, base0: b.base0,
          locked: false, nowrap: !!b.oneline, changed: false, deleted: false, active: false, _locked: !!b.locked,
          origPatch: { paras: b.paras, font: b.font, size: b.size, color: b.color, align: b.align },
        });
      }
      for (const im of p.images) {
        nimages.push({
          page: pi + 1, xref: im.xref, orig: [...im.bbox],
          x0: im.bbox[0], y0: im.bbox[1], x1: im.bbox[2], y1: im.bbox[3],
          kind: im.kind || "image", changed: false, deleted: false,
        });
      }
    });
    // Morceaux « figés » (formules, traits, cadres, tableaux) : ajoutés APRÈS toutes les images pour ne rien décaler
    data.pages.forEach((p, pi) => {
      for (const b of p.blocks) {
        if (!b.locked) continue;
        nimages.push({
          page: pi + 1, xref: 0, orig: [...b.bbox], x0: b.bbox[0], y0: b.bbox[1], x1: b.bbox[2], y1: b.bbox[3],
          kind: "text", changed: false, deleted: false,
        });
      }
      for (const g of p.graphics || []) {
        nimages.push({
          page: pi + 1, xref: 0, orig: [...g.bbox], x0: g.bbox[0], y0: g.bbox[1], x1: g.bbox[2], y1: g.bbox[3],
          kind: "graphic", changed: false, deleted: false,
        });
      }
    });
  })();
  await nativeLoading;
  nativeLoading = null;
  const was = loading; loading = true; redraw(); loading = was;
  updateCounters();
}

// Couleur de fond autour d'une zone (lue sur l'image de la page) pour masquer l'original.
// Si la page n'est pas dessinée pour l'instant : blanc, puis corrigé par refreshCovers() dès qu'elle l'est.
function sampleBg(pi, r) {
  const p = pages[pi];
  if (!p || p.canvasState !== "ready") return "#fff";
  try {
    const k = p.canvas.width / p.vp.width; // finesse de l'image (écrans haute densité)
    const x = Math.max(0, Math.floor((r[0] * SCALE - 2) * k)), y = Math.max(0, Math.floor((r[1] * SCALE - 2) * k));
    const d = p.canvas.getContext("2d").getImageData(x, y, 1, 1).data;
    return d[3] ? `rgb(${d[0]},${d[1]},${d[2]})` : "#fff";
  } catch (e) { return "#fff"; }
}
function addCover(pi, r, restUrl) {
  if (!pages[pi]) return;
  const c = el("div", "cover");
  if (restUrl) c.classList.add("rest");
  c._rect = r;
  Object.assign(c.style, {
    left: (r[0] - 1) * SCALE + "px", top: (r[1] - 1) * SCALE + "px",
    width: (r[2] - r[0] + 2) * SCALE + "px", height: (r[3] - r[1] + 2) * SCALE + "px",
    ...(restUrl ? { background: `url("${restUrl}") center/100% 100% no-repeat` } : { background: sampleBg(pi, r) }),
  });
  pages[pi].hlLayer.appendChild(c);
}
function refreshCovers(pi) { // une page vient d'être dessinée : on met à jour la couleur de ses caches
  const p = pages[pi];
  if (p) p.hlLayer.querySelectorAll(".cover").forEach((c) => { if (c._rect && !c.classList.contains("rest")) c.style.background = sampleBg(pi, c._rect); });
}

function buildLocked(nb) {
  const d = el("div", "nb-locked");
  d.title = "Non modifiable (" + nb.reason + ")";
  Object.assign(d.style, {
    left: nb.x0 * SCALE + "px", top: nb.y0 * SCALE + "px",
    width: (nb.x1 - nb.x0) * SCALE + "px", height: (nb.y1 - nb.y0) * SCALE + "px",
  });
  pages[nb.page - 1]?.tbLayer.appendChild(d);
}

// Un clic sur un paragraphe du PDF l'ouvre en édition
function activateNative(nb, cx, cy) {
  if (selected && selected !== nb && selected.native && !selected.changed) selected.active = false;
  nb.active = true;
  selected = nb;
  selectedImage = null;
  redraw();
  const ed = boxEls.get(nb)?.querySelector(".ed");
  if (!ed) return;
  ed.focus();
  try { // le curseur se place là où vous avez cliqué
    const r = document.caretRangeFromPoint(cx, cy);
    if (r && ed.contains(r.startContainer)) { const s = getSelection(); s.removeAllRanges(); s.addRange(r); }
  } catch (e) {}
}

function resetNative(nb) {
  nb.x0 = nb.orig[0]; nb.y0 = nb.orig[1]; nb.x1 = nb.orig[2]; nb.y1 = nb.orig[3];
  Object.assign(nb, JSON.parse(JSON.stringify(nb.origPatch)));
  nb.changed = false; nb.deleted = false; nb.active = false;
  selected = null;
  markDirty();
  redraw();
}

// --- Images ---
function buildImage(im) {
  const box = el("div", "ni k-" + (im.kind || "image"));
  if (im.kind === "text") box.title = "Formule ou symbole : déplaçable, mais pas modifiable";
  else if (im.kind === "graphic") box.title = "Traits / cadre / tableau : déplaçable";
  if (im.changed && !im.deleted) {
    const img = document.createElement("img");
    img.src = pieceUrl(im, im.kind);
    img.draggable = false;
    box.appendChild(img);
  }
  const rz = el("div", "ni-resize"); rz.title = "Redimensionner";
  box.appendChild(rz);
  imgEls.set(im, box);
  styleImg(im);
  if (selectedImage === im) box.classList.add("selected");
  {
    box.addEventListener("pointerdown", (ev) => { if (!ev.target.closest(".ni-resize")) startImageDrag(ev, im, "move"); });
    rz.addEventListener("pointerdown", (ev) => startImageDrag(ev, im, "resize"));
  }
  pages[im.page - 1]?.tbLayer.appendChild(box);
}
function pieceUrl(im, kind) {
  if (!im.kind || im.kind === "image") return `/api/docs/${enc(docName)}/image/${im.xref}`;
  const o = im.orig.map((v) => v.toFixed(2)).join("/");
  return `/api/docs/${enc(docName)}/clip/${kind}/${im.page}/${o}.png`;
}
function styleImg(im) {
  const b = imgEls.get(im);
  if (!b) return;
  Object.assign(b.style, {
    left: im.x0 * SCALE + "px", top: im.y0 * SCALE + "px",
    width: (im.x1 - im.x0) * SCALE + "px", height: (im.y1 - im.y0) * SCALE + "px",
  });
}
function selectImage(im) {
  selectedImage = im;
  if (im && selectedHl) selectHl(null);
  if (im && selected) select(null);
  imgEls.forEach((b, i) => b.classList.toggle("selected", i === im));
  updateSelectionButtons();
}
function startImageDrag(ev, im, kind) {
  if (ev.button !== 0) return;
  ev.preventDefault(); ev.stopPropagation();
  selectImage(im);
  const sx = ev.clientX, sy = ev.clientY, o = { x0: im.x0, y0: im.y0, x1: im.x1, y1: im.y1 };
  let moved = false;
  const move = (e) => {
    const dx = (e.clientX - sx) / SCALE, dy = (e.clientY - sy) / SCALE;
    if (!moved) {
      if (Math.hypot(dx, dy) * SCALE < 3) return;
      moved = true;
      if (!im.changed) { im.changed = true; redraw(); } // l'original est masqué, l'image devient mobile
    }
    if (kind === "move") { im.x0 = o.x0 + dx; im.x1 = o.x1 + dx; im.y0 = o.y0 + dy; im.y1 = o.y1 + dy; }
    else { // on garde les proportions de l'image
      const w = Math.max(10, o.x1 - o.x0 + dx), ratio = (o.y1 - o.y0) / (o.x1 - o.x0);
      im.x1 = o.x0 + w; im.y1 = o.y0 + w * ratio;
    }
    styleImg(im);
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    if (moved) { markDirty(); updateSelectionButtons(); }
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
}
function deleteImage() {
  const im = selectedImage;
  if (!im) return;
  im.deleted = true; im.changed = true; selectedImage = null;
  markDirty();
  redraw();
}
function resetImage(im) {
  im.x0 = im.orig[0]; im.y0 = im.orig[1]; im.x1 = im.orig[2]; im.y1 = im.orig[3];
  im.changed = false; im.deleted = false;
  markDirty();
  redraw();
}

// ====================== 8. Formes ======================
const BOX_KINDS = ["rect", "ellipse", "triangle"];
const isBoxKind = (k) => BOX_KINDS.includes(k);
const shapeDefaults = { kind: "rect", stroke: "#e03131", width: 2, fill: null };
let selectedShape = null;

function sv(tag, attrs = {}) {
  const e = document.createElementNS(NS, tag);
  for (const k in attrs) e.setAttribute(k, attrs[k]);
  return e;
}
const clamp = (v, a, b) => Math.min(Math.max(v, a), b);
function normShape(s) { // rectangle, ellipse, triangle : coins rangés (x0 < x1, y0 < y1)
  if (!isBoxKind(s.kind)) return;
  [s.x0, s.x1] = [Math.min(s.x0, s.x1), Math.max(s.x0, s.x1)];
  [s.y0, s.y1] = [Math.min(s.y0, s.y1), Math.max(s.y0, s.y1)];
}

// Le dessin de base d'une forme (sans style)
function shapeGeom(s) {
  const [x0, y0, x1, y1] = [s.x0, s.y0, s.x1, s.y1].map((v) => v * SCALE);
  const bx = Math.min(x0, x1), by = Math.min(y0, y1), bw = Math.abs(x1 - x0), bh = Math.abs(y1 - y0);
  switch (s.kind) {
    case "rect": return sv("rect", { x: bx, y: by, width: bw, height: bh });
    case "ellipse": return sv("ellipse", { cx: bx + bw / 2, cy: by + bh / 2, rx: bw / 2, ry: bh / 2 });
    case "triangle": return sv("polygon", { points: `${bx + bw / 2},${by} ${bx + bw},${by + bh} ${bx},${by + bh}` });
    default: return sv("line", { x1: x0, y1: y0, x2: x1, y2: y1 });
  }
}

function arrowHead(s) { // petit triangle plein au bout de la flèche
  const [x0, y0, x1, y1] = [s.x0, s.y0, s.x1, s.y1].map((v) => v * SCALE);
  const a = Math.atan2(y1 - y0, x1 - x0), len = 7 * s.width * SCALE, half = 3.2 * s.width * SCALE;
  const bx = x1 - Math.cos(a) * len, by = y1 - Math.sin(a) * len;
  const px = -Math.sin(a) * half, py = Math.cos(a) * half;
  return sv("polygon", { points: `${x1},${y1} ${bx + px},${by + py} ${bx - px},${by - py}` });
}

function renderShapes(pi) {
  const p = pages[pi];
  if (!p) return;
  p.shapeSvg.replaceChildren();
  p.tbLayer.querySelectorAll(":scope > .shape-layer").forEach((e) => e.remove());
  p.shUi.replaceChildren();
  for (const s of shapes) {
    if (s.page !== pi + 1) continue;
    const g = sv("svg", { class: "shape-layer" });
    g.style.zIndex = String(s.z || 1);
    const vis = shapeGeom(s);
    vis.setAttribute("class", "vis");
    vis.setAttribute("stroke", s.stroke);
    vis.setAttribute("stroke-width", s.width * SCALE);
    vis.setAttribute("stroke-linejoin", "round");
    vis.setAttribute("stroke-linecap", "round");
    vis.setAttribute("fill", isBoxKind(s.kind) && s.fill ? s.fill : "none");
    g.appendChild(vis);
    if (s.kind === "arrow") {
      const head = arrowHead(s);
      head.setAttribute("class", "vis");
      head.setAttribute("fill", s.stroke); head.setAttribute("stroke", s.stroke);
      head.setAttribute("stroke-linejoin", "round");
      g.appendChild(head);
    }
    // Zone cliquable plus large que le trait, pour pouvoir attraper la forme facilement
    const hit = shapeGeom(s);
    hit.setAttribute("class", "hit");
    hit.setAttribute("stroke", "rgba(0,0,0,0)");
    hit.setAttribute("stroke-width", Math.max(s.width * SCALE, 12));
    hit.setAttribute("fill", isBoxKind(s.kind) && s.fill ? "rgba(0,0,0,0)" : "none");
    hit.addEventListener("pointerdown", (ev) => startShapeMove(ev, s));
    g.appendChild(hit);
    p.tbLayer.appendChild(g);
  }
  if (selectedShape && selectedShape.page === pi + 1 && shapes.includes(selectedShape)) drawShapeUi(selectedShape, p);
}
function renderAllShapes() { pages.forEach((_, i) => renderShapes(i)); }

// Cadre pointillé et poignées de la forme sélectionnée
function drawShapeUi(s, p) {
  const handle = (kx, ky, cls) => {
    const h = el("div", "sh-handle " + cls);
    h.style.left = s[kx] * SCALE + "px"; h.style.top = s[ky] * SCALE + "px";
    h.addEventListener("pointerdown", (ev) => startHandleDrag(ev, s, kx, ky));
    p.shUi.appendChild(h);
  };
  if (isBoxKind(s.kind)) {
    const box = el("div", "sh-box");
    Object.assign(box.style, {
      left: Math.min(s.x0, s.x1) * SCALE + "px", top: Math.min(s.y0, s.y1) * SCALE + "px",
      width: Math.abs(s.x1 - s.x0) * SCALE + "px", height: Math.abs(s.y1 - s.y0) * SCALE + "px",
    });
    p.shUi.appendChild(box);
    handle("x0", "y0", ""); handle("x1", "y0", "nesw"); handle("x0", "y1", "nesw"); handle("x1", "y1", "");
  } else {
    handle("x0", "y0", "pt"); handle("x1", "y1", "pt"); // une ligne : une poignée à chaque bout
  }
}

function setSelectedShape(s) {
  const prev = selectedShape;
  selectedShape = s;
  if (s && selectedHl) selectHl(null);
  if (prev && prev !== s) renderShapes(prev.page - 1);
  if (s) { renderShapes(s.page - 1); if (selected) select(null); }
  $("sDelete").disabled = !s;
  syncShapeControls(s || shapeDefaults);
}

// Dessiner : mode « Forme », puis cliquer-glisser
function startShape(ev, pi) {
  if (currentMode() !== "shape" || ev.button !== 0) return;
  if (ev.target.closest(".tb") || ev.target.closest(".note") || ev.target.closest(".hit") || ev.target.closest(".sh-handle")) return;
  ev.preventDefault();
  const b = pages[pi].div.getBoundingClientRect();
  const pt = (e) => [clamp((e.clientX - b.left) / SCALE, 0, b.width / SCALE), clamp((e.clientY - b.top) / SCALE, 0, b.height / SCALE)];
  const [sx, sy] = pt(ev);
  const s = {
    page: pi + 1, kind: shapeDefaults.kind, x0: sx, y0: sy, x1: sx, y1: sy,
    stroke: shapeDefaults.stroke, width: shapeDefaults.width,
    fill: isBoxKind(shapeDefaults.kind) ? shapeDefaults.fill : null, z: nextZ(),
  };
  shapes.push(s);
  const move = (e) => { [s.x1, s.y1] = pt(e); renderShapes(pi); };
  const up = (e) => {
    window.removeEventListener("mousemove", move);
    window.removeEventListener("mouseup", up);
    [s.x1, s.y1] = pt(e);
    if (Math.hypot(s.x1 - s.x0, s.y1 - s.y0) < 6) { // simple clic : on ne crée rien
      shapes = shapes.filter((x) => x !== s);
      renderShapes(pi);
      return;
    }
    normShape(s);
    setSelectedShape(s);
    markDirty();
    updateCounters();
  };
  window.addEventListener("mousemove", move);
  window.addEventListener("mouseup", up);
}

// Déplacer une forme en la faisant glisser
function startShapeMove(ev, s) {
  if (ev.button !== 0) return;
  ev.preventDefault(); ev.stopPropagation();
  setSelectedShape(s);
  const sx = ev.clientX, sy = ev.clientY;
  const o = { x0: s.x0, y0: s.y0, x1: s.x1, y1: s.y1 };
  let moved = false;
  const move = (e) => {
    const dx = (e.clientX - sx) / SCALE, dy = (e.clientY - sy) / SCALE;
    if (Math.abs(dx) + Math.abs(dy) > 0.5) moved = true;
    s.x0 = o.x0 + dx; s.x1 = o.x1 + dx; s.y0 = o.y0 + dy; s.y1 = o.y1 + dy;
    renderShapes(s.page - 1);
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    if (moved) markDirty();
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
}

// Étirer une forme avec une poignée
function startHandleDrag(ev, s, kx, ky) {
  ev.preventDefault(); ev.stopPropagation();
  const sx = ev.clientX, sy = ev.clientY, ox = s[kx], oy = s[ky];
  const move = (e) => {
    s[kx] = ox + (e.clientX - sx) / SCALE;
    s[ky] = oy + (e.clientY - sy) / SCALE;
    renderShapes(s.page - 1);
  };
  const up = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", up);
    normShape(s);
    renderShapes(s.page - 1);
    markDirty();
  };
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", up);
}

// Barre des formes
const sStroke = $("sStroke"), sWidth = $("sWidth"), sFillOn = $("sFillOn"), sFill = $("sFill");
const kindBtns = document.querySelectorAll("[data-kind]");

function syncShapeControls(s) {
  kindBtns.forEach((b) => b.classList.toggle("active", b.dataset.kind === shapeDefaults.kind)); // l'outil choisi
  sStroke.value = s.stroke; sWidth.value = s.width;
  sFillOn.setAttribute("aria-pressed", String(!!s.fill)); if (s.fill) sFill.value = s.fill;
  const canFill = isBoxKind(s.kind);
  sFillOn.disabled = !canFill; sFill.disabled = !canFill;
}

function applyShapeStyle(patch) {
  Object.assign(shapeDefaults, patch);
  const s = selectedShape;
  if (s && !("kind" in patch)) { // trait, épaisseur, remplissage : on modifie la forme sélectionnée
    Object.assign(s, patch);
    if (!isBoxKind(s.kind)) s.fill = null;
    renderShapes(s.page - 1);
    markDirty();
  }
  syncShapeControls(s || shapeDefaults);
}
// Choisir un type de forme prépare le PROCHAIN dessin (la forme sélectionnée n'est pas modifiée)
kindBtns.forEach((b) => b.addEventListener("click", () => {
  setSelectedShape(null);
  applyShapeStyle({ kind: b.dataset.kind });
}));
sStroke.addEventListener("input", () => applyShapeStyle({ stroke: sStroke.value }));
sWidth.addEventListener("input", () => applyShapeStyle({ width: clamp(Number(sWidth.value) || 2, 1, 20) }));
sFillOn.addEventListener("click", () => applyShapeStyle({ fill: pressed(sFillOn) ? null : sFill.value }));
sFill.addEventListener("input", () => applyShapeStyle({ fill: sFill.value }));

function deleteSelectedShape() {
  if (!selectedShape) return;
  const s = selectedShape;
  shapes = shapes.filter((x) => x !== s);
  selectedShape = null;
  renderShapes(s.page - 1);
  setSelectedShape(null);
  markDirty();
  updateCounters();
}
$("sDelete").addEventListener("click", deleteSelectedShape);

// ====================== 9. Affichage de toutes les annotations ======================
function redraw() {
  syncTextFromDom();
  ensureZ();
  boxEls.clear();
  imgEls.clear();
  pages.forEach(({ hlLayer, tbLayer, noteLayer }) => {
    hlLayer.innerHTML = ""; tbLayer.innerHTML = ""; noteLayer.innerHTML = "";
  });
  const mode = currentMode();

  // Contenu natif modifié : on masque l'original (puis on affiche le nouveau contenu)
  for (const nb of natives || []) if (nb.changed || nb.deleted || nb.active) addCover(nb.page - 1, nb.orig);
  for (const im of nimages || []) if (im.changed || im.deleted) addCover(im.page - 1, im.orig, im.kind === "graphic" ? pieceUrl(im, "graphic_rest") : null);

  for (const h of highlights) {
    for (const [x0, y0, x1, y1] of h.rects) {
      const d = el("div", "hl");
      Object.assign(d.style, {
        left: x0 * SCALE + "px", top: y0 * SCALE + "px",
        width: (x1 - x0) * SCALE + "px", height: (y1 - y0) * SCALE + "px",
        background: h.color || HL_COLORS[0],
      });
      pages[h.page - 1]?.hlLayer.appendChild(d);
    }
  }

  // Images natives d'abord (les textes passent au-dessus), puis paragraphes natifs, puis zones de texte
  for (const im of nimages || []) {
    if (im.deleted || !pages[im.page - 1]) continue;
    if (mode === "native" || im.changed) buildImage(im);
  }
  for (const nb of natives || []) {
    if (nb.deleted || !pages[nb.page - 1]) continue;
    if (nb.changed || nb.active) buildBox(nb);
    else if (mode === "native") buildBox(nb, true);
  }
  for (const tb of textboxes) if (pages[tb.page - 1]) buildBox(tb);

  for (const n of notes) {
    if (!pages[n.page - 1]) continue;
    const d = el("div", "note");
    d.textContent = "✎";
    d.title = n.text + "\n(clic : modifier ou supprimer)";
    d.style.left = n.x * SCALE + "px";
    d.style.top = n.y * SCALE + "px";
    d.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const t = prompt("Modifier la note (laisser vide pour la supprimer) :", n.text);
      if (t === null) return;
      if (t === "") {
        notes = notes.filter((x) => x !== n);
      } else n.text = t;
      markDirty();
      redraw();
    });
    pages[n.page - 1].noteLayer.appendChild(d);
  }

  if (selected && !(textboxes.includes(selected) || (natives && natives.includes(selected) && !selected.deleted))) selected = null;
  if (selectedShape && !shapes.includes(selectedShape)) selectedShape = null;
  if (selectedImage && (selectedImage.deleted || !(nimages || []).includes(selectedImage))) selectedImage = null;
  if (selectedHl && !highlights.includes(selectedHl)) selectedHl = null;
  drawHlSelection();
  updateBars();
  select(selected);
  imgEls.forEach((b, i) => b.classList.toggle("selected", i === selectedImage));
  renderAllShapes();
  updateCounters();
}

function updateCounters() {
  const has = !!pdfDoc;
  undoBtn.disabled = undoIdx <= 0;
  $("redo").disabled = undoIdx >= undoStack.length - 1;
  ["download", "zoomIn", "zoomOut"].forEach((id) => { $(id).disabled = !has; });
  $("zoomLabel").textContent = Math.round((SCALE / 1.5) * 100) + "%";
  updateSelectionButtons();
  if (has) {
    const nat = (natives || []).filter((n) => n.changed || n.deleted).length + (nimages || []).filter((i) => i.changed || i.deleted).length;
    setStatus(`${highlights.length} surlignage(s) · ${notes.length} note(s) · ${textboxes.length} texte(s) · ${shapes.length} forme(s)` +
      (nat ? ` · ${nat} élément(s) du PDF modifié(s)` : ""));
  }
}

// ====================== 9bis. Annuler / rétablir (tout) ======================
// À chaque changement, on garde une « photo » de l'état : surlignages, notes, textes, formes, et le contenu
// du PDF modifié (paragraphes et images). Annuler / Rétablir passent d'une photo à l'autre.
// Plusieurs frappes rapprochées ne forment qu'une seule étape.
const NAT_KEYS = ["x0", "y0", "x1", "y1", "paras", "font", "size", "color", "align", "changed", "deleted"];
const IMG_KEYS = ["x0", "y0", "x1", "y1", "changed", "deleted"];
const pick = (o, keys) => Object.fromEntries(keys.map((k) => [k, o[k]]));

function snapshot() {
  return JSON.stringify({
    h: highlights, n: notes, t: textboxes, s: shapes,
    nat: (natives || []).map((n, i) => (n.changed || n.deleted ? [i, pick(n, NAT_KEYS)] : null)).filter(Boolean),
    img: (nimages || []).map((m, i) => (m.changed || m.deleted ? [i, pick(m, IMG_KEYS)] : null)).filter(Boolean),
  });
}
function resetUndo() { // nouveau point de départ (ouverture d'un document, enregistrement qui change le PDF)
  clearTimeout(commitTimer); commitTimer = null;
  undoStack = [snapshot()]; undoIdx = 0;
  updateCounters();
}
function scheduleCommit() { clearTimeout(commitTimer); commitTimer = setTimeout(commitNow, 350); }
function commitNow() {
  clearTimeout(commitTimer); commitTimer = null;
  if (undoIdx < 0) return;
  const s = snapshot();
  if (s === undoStack[undoIdx]) return;
  undoStack.length = undoIdx + 1; // un nouveau changement efface ce qu'on pouvait « rétablir »
  undoStack.push(s);
  if (undoStack.length > 100) undoStack.shift();
  undoIdx = undoStack.length - 1;
  updateCounters();
}
function resetNativeState(nb) { // paragraphe du PDF remis à l'original (sans toucher à l'affichage)
  nb.x0 = nb.orig[0]; nb.y0 = nb.orig[1]; nb.x1 = nb.orig[2]; nb.y1 = nb.orig[3];
  Object.assign(nb, JSON.parse(JSON.stringify(nb.origPatch)));
  nb.changed = false; nb.deleted = false; nb.active = false;
}
function resetImageState(im) {
  im.x0 = im.orig[0]; im.y0 = im.orig[1]; im.x1 = im.orig[2]; im.y1 = im.orig[3];
  im.changed = false; im.deleted = false;
}
function restore(snap) {
  const o = JSON.parse(snap);
  highlights = o.h; notes = o.n; textboxes = o.t; shapes = o.s;
  selected = null; selectedShape = null; selectedImage = null; selectedHl = null;
  const nat = new Map(o.nat), img = new Map(o.img);
  (natives || []).forEach((n, i) => { if (nat.has(i)) Object.assign(n, nat.get(i), { active: false }); else resetNativeState(n); });
  (nimages || []).forEach((m, i) => { if (img.has(i)) Object.assign(m, img.get(i)); else resetImageState(m); });
  redrawQuiet();
  scheduleAutosave(); // annuler / rétablir est aussi un changement à enregistrer
}
function undo() {
  if (commitTimer) commitNow(); // on prend d'abord en compte le dernier changement en attente
  if (undoIdx <= 0) return;
  restore(undoStack[--undoIdx]);
}
function redo() {
  if (commitTimer) commitNow();
  if (undoIdx >= undoStack.length - 1) return;
  restore(undoStack[++undoIdx]);
}
undoBtn.addEventListener("click", undo);
$("redo").addEventListener("click", redo);

// ====================== 10. Enregistrer / télécharger ======================
function payload() {
  syncTextFromDom();
  const box = (n) => ({ page: n.page, orig: n.orig, bbox: [n.x0, n.y0, n.x1, n.y1] });
  return {
    newName: nameInput.value.trim(), highlights, notes, textboxes, shapes,
    natives: (natives || []).filter((n) => n.changed || n.deleted).map((n) => ({
      ...box(n), paras: n.paras, font: n.font, size: n.size, color: n.color, align: n.align, lh: n.lh, base0: n.base0, nowrap: !!n.nowrap, deleted: !!n.deleted,
    })),
    nimages: (nimages || []).filter((i) => i.changed || i.deleted).map((i) => ({ ...box(i), xref: i.xref, kind: i.kind || "image", deleted: !!i.deleted })),
  };
}

// ---- Enregistrement automatique (comme Canva) ----
// Chaque changement est envoyé au serveur dans un « brouillon », 1 seconde après la dernière modification.
// Le PDF d'origine n'est jamais touché ; le PDF final n'est créé que par « Télécharger ».
let autosaveTimer = null, retryTimer = null, saving = false, pendingChange = false, savedAt = null;
const hhmm = (t) => new Date(t).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

function setSaveState(s) { saveState = s; renderSaveState(); }
function renderSaveState() {
  const e = $("saveState");
  const texts = {
    idle: "", pending: "Enregistrement…", saving: "Enregistrement…",
    saved: savedAt ? "Enregistré à " + hhmm(savedAt) : "Enregistré", error: "⚠ Non enregistré",
  };
  e.textContent = texts[saveState] || "";
  e.className = "savestate " + saveState;
  e.title = saveState === "error"
    ? "Le serveur n'a pas pu enregistrer vos modifications. Cliquez pour réessayer."
    : "Vos modifications sont enregistrées automatiquement sur le serveur : vous pouvez fermer la page et reprendre plus tard.";
}
$("saveState").addEventListener("click", () => { if (saveState === "error") flushSave(); });

function scheduleAutosave() {
  if (!docName || loading) return;
  pendingChange = true;
  if (saveState !== "saving") setSaveState("pending");
  clearTimeout(autosaveTimer);
  autosaveTimer = setTimeout(() => flushSave(), 1000);
}

function projectState() { // tout ce qui permet de retrouver votre travail
  const p = payload();
  delete p.newName;
  p.lastPage = typeof curPage === "number" ? curPage : 1;
  return p;
}

// Envoie le brouillon. keepalive = dernier envoi pendant la fermeture de la page (limité à ~64 Ko).
// Renvoie true si l'envoi est parti.
function flushSave(keepalive = false) {
  clearTimeout(autosaveTimer); clearTimeout(retryTimer);
  if (!docName) return false;
  if (saving) { pendingChange = true; return keepalive ? false : Promise.resolve(false); }
  const name = docName;
  const body = JSON.stringify({ baseRev: projRev, state: projectState() });
  if (keepalive && body.length > 60000) return false;
  const run = async () => {
    saving = true; pendingChange = false;
    setSaveState("saving");
    try {
      const res = await fetch(`/api/docs/${enc(name)}/project`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body, keepalive,
      });
      if (name !== docName) return true; // on a changé de document pendant l'envoi
      if (res.status === 409) { saving = false; await handleConflict(await res.json().catch(() => ({}))); return false; }
      if (!res.ok) throw new Error("HTTP " + res.status);
      const d = await res.json();
      projRev = d.rev; savedAt = d.saved * 1000;
      setSaveState(pendingChange ? "pending" : "saved");
      return true;
    } catch (e) {
      if (name === docName) { setSaveState("error"); retryTimer = setTimeout(() => flushSave(), 6000); }
      return false;
    } finally {
      saving = false;
      if (pendingChange && name === docName && saveState !== "error") scheduleAutosave();
    }
  };
  const p = run();
  return keepalive ? true : p;
}

// Le brouillon a été modifié ailleurs (autre onglet) : on ne l'écrase jamais sans votre accord
async function handleConflict(info) {
  setSaveState("error");
  const keep = confirm("Ce document a été modifié ailleurs (dans un autre onglet ou une autre fenêtre).\n\n" +
    "OK : garder la version de CET onglet (l'autre sera remplacée).\nAnnuler : recharger la version enregistrée.");
  if (keep) { projRev = info.rev ?? projRev; await flushSave(); }
  else { await openDoc(docName, null, true); }
}

async function forceSave() { // Ctrl+S : le brouillon est déjà enregistré tout seul ; on l'envoie sans attendre
  if (!docName) return;
  if (commitTimer) commitNow();
  const ok = await flushSave();
  if (ok) notify("Enregistré automatiquement ✓", "ok", 2000);
}

// Renommer le document : il est renommé tout de suite sur le serveur (avec son brouillon)
async function renameCurrent() {
  const want = nameInput.value.trim();
  if (!docName || !want || want === stripPdf(docName)) { if (docName) { nameInput.value = stripPdf(docName); fitName(); } return; }
  await flushSave();
  const res = await fetch(`/api/docs/${enc(docName)}/rename`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ newName: want }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { fail(data.error || "Renommage impossible"); nameInput.value = stripPdf(docName); fitName(); return; }
  docName = data.name;
  nameInput.value = stripPdf(docName); fitName();
  document.title = stripPdf(docName) + " · " + APP_NAME;
  if (typeof setRoute === "function") setRoute(docName);
  notify("Document renommé ✓", "ok", 2000);
}

async function download() {
  if (!docName) return;
  setStatus("Création du PDF annoté…");
  const res = await fetch(`/api/docs/${enc(docName)}/download`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload()),
  });
  if (!res.ok) { fail("Erreur pendant l'export"); return; }
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: (nameInput.value.trim() || stripPdf(docName)) + ".pdf" });
  a.click();
  URL.revokeObjectURL(url);
  toast("Copie téléchargée ✓");
}
$("download").addEventListener("click", download);

function toast(msg, ms = 2500) { setStatus(msg); notify(msg, "ok", Math.max(ms, 2500)); setTimeout(updateCounters, ms); }
function fail(msg) { setStatus(msg); notify(msg, "error", 6000); }

// Petit message en bas de l'écran (succès ou erreur)
let notifyTimer = null;
function notify(msg, kind = "ok", ms = 3500) {
  const t = $("toast");
  t.textContent = msg;
  t.className = "toast " + kind;
  t.hidden = false;
  clearTimeout(notifyTimer);
  notifyTimer = setTimeout(() => { t.hidden = true; }, ms);
}
// Barre de progression pendant l'affichage des pages (n pages sur total ; 0 = terminé)
function setProgress(n, total) {
  const bar = $("progress");
  if (!n) { bar.hidden = true; return; }
  bar.hidden = false;
  bar.firstElementChild.style.width = Math.round((n / total) * 100) + "%";
  setStatus(`Affichage des pages… ${n}/${total}`);
}

// ====================== 11. Fenêtres : réglages et aide ======================
const settings = $("settings");
function closePopovers() { settings.hidden = true; const h = $("help"); if (h) h.hidden = true; const m = $("more"); if (m) m.hidden = true; }
$("moreBtn").addEventListener("click", () => { const open = $("more").hidden; closePopovers(); $("more").hidden = !open; });
$("settingsBtn").addEventListener("click", () => { const open = settings.hidden; closePopovers(); settings.hidden = !open; });

// ====================== 12. Modes, clavier, petits outils ======================
function el(tag, cls) { const e = document.createElement(tag); e.className = cls; return e; }
function setStatus(t) { statusEl.textContent = t; }
function currentMode() { return document.querySelector('input[name="mode"]:checked').value; }

function applyMode() {
  const m = currentMode();
  document.body.dataset.mode = m;
  updateBars();                                // chaque barre n'apparaît que dans son mode
  $("formatbar").hidden = !(m === "text" || m === "native");
  $("shapebar").hidden = m !== "shape";
  $("fTitle").textContent = m === "native" ? "Contenu du PDF" : "Texte";
  // en quittant le mode « Éditer le PDF », les paragraphes non touchés redeviennent le PDF tout simple
  if (selected && selected.native && !selected.changed) selected.active = false;
  if (m === "native") ensureNative();
  redrawQuiet();
}
function redrawQuiet() { const was = loading; loading = true; redraw(); loading = was; }
document.querySelectorAll('input[name="mode"]').forEach((r) => r.addEventListener("change", applyMode));

// ---- Copier / coller / dupliquer une zone de texte ou une forme ----
let elClip = null; // { kind: "t" | "s", data }
function copyElement() {
  const it = layerItem();
  if (!it) return false;
  syncTextFromDom();
  elClip = { kind: it === selectedShape ? "s" : "t", data: JSON.parse(JSON.stringify(it)) };
  try { if (elClip.kind === "t") navigator.clipboard.writeText(plainOf(it.paras)); } catch (e) {}
  notify("Élément copié", "ok", 1500);
  return true;
}
function pasteElement(offset = 14) {
  if (!elClip) return false;
  const c = JSON.parse(JSON.stringify(elClip.data));
  const cur = Math.min(Math.max(typeof curPage === "number" ? curPage : c.page, 1), pages.length);
  const samePage = c.page === cur;
  const dx = samePage ? offset : 0, dy = samePage ? offset : 0;
  c.page = cur; c.x0 += dx; c.x1 += dx; c.y0 += dy; c.y1 += dy; c.z = nextZ();
  if (elClip.kind === "t") { textboxes.push(c); markDirty(); selected = c; redraw(); }
  else { shapes.push(c); markDirty(); renderShapes(cur - 1); setSelectedShape(c); }
  elClip.data = JSON.parse(JSON.stringify(c)); // le collage suivant se décale encore
  return true;
}
function duplicateElement() { if (!copyElement()) return false; return pasteElement(); }
$("fCopy").addEventListener("click", copyElement);
$("fPaste").addEventListener("click", () => pasteElement());
$("fDup").addEventListener("click", duplicateElement);
$("sCopy").addEventListener("click", copyElement);
$("sPaste").addEventListener("click", () => pasteElement());
$("sDup").addEventListener("click", duplicateElement);

// ---- Zoom : pincement au doigt, pincement du pavé tactile (Ctrl + molette), Ctrl + molette ----
let zoomTarget = null, zoomTimer = null;
function zoomBy(factor) {
  zoomTarget = clamp((zoomTarget || SCALE) * factor, 0.4, 4);
  clearTimeout(zoomTimer);
  zoomTimer = setTimeout(async () => {
    const v = Math.round(zoomTarget * 100) / 100; zoomTarget = null;
    if (Math.abs(v - SCALE) < 0.01) return;
    const doc = document.documentElement, ratio = (window.scrollY + innerHeight / 2) / Math.max(doc.scrollHeight, 1);
    await setZoom(v);
    window.scrollTo(window.scrollX, ratio * doc.scrollHeight - innerHeight / 2);
  }, 140);
}
window.addEventListener("wheel", (e) => {
  if (!e.ctrlKey || document.body.dataset.view !== "doc") return;
  e.preventDefault(); // sinon le navigateur zoome toute la page
  zoomBy(Math.exp(-e.deltaY * (e.deltaMode ? 0.05 : 0.01)));
}, { passive: false });
let pinch = null;
const tdist = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
document.addEventListener("touchstart", (e) => { if (e.touches.length === 2 && document.body.dataset.view === "doc") pinch = tdist(e.touches); }, { passive: true });
document.addEventListener("touchmove", (e) => {
  if (!pinch || e.touches.length !== 2) return;
  e.preventDefault();
  const d = tdist(e.touches);
  zoomBy(d / pinch);
  pinch = d;
}, { passive: false });
document.addEventListener("touchend", (e) => { if (e.touches.length < 2) pinch = null; }, { passive: true });

// Clic ailleurs : on désélectionne et on ferme les fenêtres
document.addEventListener("mousedown", (ev) => {
  const t = ev.target;
  if (!t.closest(".tb") && !t.closest(".ctxbar") && !t.closest(".ni") && selected) {
    const was = selected;
    select(null);
    if (was.native && was.active && !was.changed) { was.active = false; redrawQuiet(); } // pas touché : on revient à l'original
  }
  if (!t.closest(".ni") && !t.closest(".ctxbar") && selectedImage) selectImage(null);
  if (!t.closest(".hit") && !t.closest(".sh-handle") && !t.closest(".ctxbar") && selectedShape) setSelectedShape(null);
  if (!t.closest(".page") && !t.closest(".ctxbar") && selectedHl) selectHl(null);
  if (!t.closest(".popwrap")) closePopovers();
});

document.addEventListener("keydown", (e) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable;
  const ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && e.key.toLowerCase() === "s") { e.preventDefault(); forceSave(); }
  else if (ctrl && e.key.toLowerCase() === "o") { e.preventDefault(); $("file").click(); }
  else if (ctrl && e.key.toLowerCase() === "z" && !typing) { e.preventDefault(); e.shiftKey ? redo() : undo(); }
  else if (ctrl && e.key.toLowerCase() === "y" && !typing) { e.preventDefault(); redo(); }
  else if (ctrl && e.key.toLowerCase() === "d" && layerItem()) { e.preventDefault(); duplicateElement(); }
  else if (ctrl && e.key.toLowerCase() === "c" && layerItem() && (!typing || (activeEditor() && window.getSelection().isCollapsed))) { e.preventDefault(); copyElement(); }
  else if (ctrl && e.key.toLowerCase() === "v" && elClip && !typing) { e.preventDefault(); pasteElement(); }
  else if (e.key === "Delete" && !typing) { selectedShape ? deleteSelectedShape() : selectedHl ? deleteSelectedHl() : deleteSelected(); }
  else if (e.key === "Escape") { closePopovers(); setSelectedShape(null); selectHl(null); }
});

// Bouton « Se déconnecter » : visible seulement si le site demande une connexion
fetch("/api/me").then((r) => r.json()).then((m) => { $("logout").hidden = !(m.auth && m.logged); document.querySelector(".menu-title.menu-account").hidden = $("logout").hidden; }).catch(() => {});
$("logout").addEventListener("click", async () => {
  if (!(await leaveCurrentDoc())) return; // le brouillon est enregistré avant de se déconnecter
  await _fetch("/api/logout", { method: "POST" });
  location.href = "/login";
});

applyPrefs();
applyMode();
syncControls(defaults);
syncShapeControls(shapeDefaults);
updateCounters();
