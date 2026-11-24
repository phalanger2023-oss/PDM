// Navigation et confort : page courante, miniatures, recherche, dernière page lue, raccourcis, aide.
// S'appuie sur app.js (variables et fonctions partagées : pdfDoc, pages, SCALE, docName, notify...).

// ---------- Hauteur de la barre du haut (sert à aligner les pages et les miniatures) ----------
const topbar = document.querySelector(".topbar");
const setTopbarH = () => document.documentElement.style.setProperty("--topbar-h", topbar.offsetHeight + "px");
new ResizeObserver(setTopbarH).observe(topbar);
setTopbarH();

// ---------- Réglages du document : pages épinglées et numéro de la première page (affichage seulement) ----------
let docMeta = { pins: [], firstPage: 1 };
const pageLabel = (n) => n + docMeta.firstPage - 1;       // numéro affiché pour la page n du PDF
const pageFromLabel = (l) => l - docMeta.firstPage + 1;   // numéro dans le PDF pour un numéro affiché
let metaTimer;
function saveMeta() {
  clearTimeout(metaTimer);
  const name = docName;
  metaTimer = setTimeout(() => {
    fetch(`/api/docs/${enc(name)}/meta`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(docMeta) }).catch(() => {});
  }, 300);
}
async function loadMeta() {
  docMeta = { pins: [], firstPage: 1 };
  try {
    const r = await fetch(`/api/docs/${enc(docName)}/meta`);
    if (r.ok) { const d = await r.json(); docMeta = { pins: d.pins || [], firstPage: d.firstPage ?? 1 }; }
  } catch (e) {}
}

// ---------- Page courante ----------
let curPage = 1;
let restoring = false; // vrai pendant le retour à la dernière page lue

function pageAtViewport() { // la page qui occupe le milieu de la zone visible
  const mid = topbar.offsetHeight + (innerHeight - topbar.offsetHeight) / 2;
  let best = 1, bestD = Infinity;
  pages.forEach((p, i) => {
    const r = p.div.getBoundingClientRect();
    const d = r.top <= mid && r.bottom >= mid ? 0 : Math.min(Math.abs(r.top - mid), Math.abs(r.bottom - mid));
    if (d < bestD) { bestD = d; best = i + 1; }
  });
  return best;
}

function updatePager() {
  if (!pages.length) return;
  curPage = pageAtViewport();
  if (document.activeElement !== $("pageNum")) $("pageNum").value = pageLabel(curPage);
  markThumb();
  if (!restoring) rememberPage();
}
let scrollTimer;
window.addEventListener("scroll", () => { clearTimeout(scrollTimer); scrollTimer = setTimeout(updatePager, 80); }, { passive: true });

function goToPage(n, isLabel = false) {
  if (!pages.length) return;
  n = Math.round(Number(n) || 1);
  if (isLabel) n = pageFromLabel(n);
  n = clamp(n, 1, pages.length);
  pages[n - 1].div.scrollIntoView({ block: "start" });
  updateVisible(); // les pages d'arrivée se dessinent tout de suite
  setTimeout(updatePager, 60);
}
$("pageNum").addEventListener("change", () => goToPage($("pageNum").value, true));
$("pageNum").addEventListener("keydown", (e) => { if (e.key === "Enter") { goToPage($("pageNum").value, true); e.target.blur(); } });

// ---------- Se souvenir de la dernière page lue (par document, dans ce navigateur) ----------
const lastPageKey = () => "lastpage:" + docName;
let rememberTimer;
function rememberPage() {
  clearTimeout(rememberTimer);
  rememberTimer = setTimeout(() => { try { localStorage.setItem(lastPageKey(), String(curPage)); } catch (e) {} }, 500);
}
function restoreLastPage() {
  let n = 0;
  try { n = Number(localStorage.getItem(lastPageKey())) || 0; } catch (e) {} // la plus récente, dans ce navigateur
  if (!n && resumePage) n = resumePage;                                      // sinon celle du brouillon (autre appareil)
  resumePage = null;
  if (n <= 1 || n > pages.length) return;
  restoring = true;
  setTimeout(() => { goToPage(n); notify(`Reprise à la page ${pageLabel(n)}`, "ok", 2500); setTimeout(() => { restoring = false; }, 400); }, 120);
}

// ---------- Miniatures ----------
let thumbObserver = null;

function buildThumbs() {
  const box = $("thumbs");
  box.replaceChildren();
  if (thumbObserver) thumbObserver.disconnect();
  thumbObserver = new IntersectionObserver((entries) => {
    for (const en of entries) if (en.isIntersecting) { thumbObserver.unobserve(en.target); drawThumb(en.target); }
  }, { root: box, rootMargin: "300px" });
  // en-tête : numéro de la première page + épingles
  const head = el("div", "thumbhead");
  const first = el("button", "thumbfirst");
  first.id = "firstPageBtn";
  first.title = "Numéro de la première page (documents en plusieurs parties). Le PDF n'est pas modifié.";
  first.addEventListener("click", askFirstPage);
  const pins = el("div", "thumbpins");
  pins.id = "thumbPins";
  head.append(first, pins);
  box.appendChild(head);
  for (let n = 1; n <= pdfDoc.numPages; n++) {
    const w = el("div", "thumbw");
    const b = el("button", "thumb");
    b.dataset.n = n;
    const cv = document.createElement("canvas");
    cv.width = 90; cv.height = 120;
    const lab = el("span", "");
    b.append(cv, lab);
    b.addEventListener("click", () => goToPage(n));
    const pin = el("button", "thumbpin");
    pin.dataset.n = n;
    pin.addEventListener("click", (e) => { e.stopPropagation(); togglePin(n); });
    w.append(b, pin);
    box.appendChild(w);
    thumbObserver.observe(b);
  }
  refreshThumbLabels();
  markThumb();
}

function refreshThumbLabels() { // numéros affichés, épingles, bouton « première page »
  document.querySelectorAll(".thumb").forEach((b) => {
    const n = Number(b.dataset.n), l = pageLabel(n);
    b.querySelector("span").textContent = l;
    b.title = "Page " + l;
    b.setAttribute("aria-label", "Aller à la page " + l);
  });
  document.querySelectorAll(".thumbpin").forEach((p) => {
    const on = docMeta.pins.includes(Number(p.dataset.n));
    p.classList.toggle("on", on);
    p.textContent = on ? "★" : "☆";
    p.title = on ? "Retirer l'épingle" : "Épingler cette page";
    p.setAttribute("aria-label", p.title);
    p.setAttribute("aria-pressed", String(on));
  });
  const fb = $("firstPageBtn");
  if (fb) fb.textContent = "1ʳᵉ page : " + docMeta.firstPage;
  const box = $("thumbPins");
  if (box) {
    box.replaceChildren();
    for (const n of docMeta.pins) {
      if (n > pages.length) continue;
      const c = el("button", "pinchip");
      c.textContent = "★ " + pageLabel(n);
      c.title = "Aller à la page épinglée " + pageLabel(n);
      c.addEventListener("click", () => goToPage(n));
      box.appendChild(c);
    }
  }
  const pg = $("pageNum");
  if (pg) { pg.min = pageLabel(1); pg.max = pageLabel(pages.length); if (document.activeElement !== pg) pg.value = pageLabel(curPage); }
  const pc = $("pageCount"); if (pc) pc.textContent = pageLabel(pages.length);
}

function togglePin(n) {
  const i = docMeta.pins.indexOf(n);
  if (i >= 0) docMeta.pins.splice(i, 1); else docMeta.pins.push(n);
  docMeta.pins.sort((a, b) => a - b);
  refreshThumbLabels(); saveMeta();
}

function askFirstPage() {
  const v = prompt("Numéro de la première page de ce document (ex. 101 si ce document commence à la page 101). Cela change seulement l'affichage, pas le PDF.", String(docMeta.firstPage));
  if (v === null) return;
  const n = Math.round(Number(v));
  if (!Number.isFinite(n) || n < -9999 || n > 99999) { notify("Numéro invalide", "err", 2500); return; }
  docMeta.firstPage = n;
  refreshThumbLabels(); saveMeta();
}

async function drawThumb(btn) { // dessin à la demande : seulement les miniatures visibles
  const doc = pdfDoc;
  try {
    const page = await doc.getPage(Number(btn.dataset.n));
    const vp = page.getViewport({ scale: 110 / page.getViewport({ scale: 1 }).width });
    const cv = btn.querySelector("canvas");
    cv.width = Math.ceil(vp.width); cv.height = Math.ceil(vp.height);
    await page.render({ canvasContext: cv.getContext("2d"), viewport: vp, annotationMode: pdfjsLib.AnnotationMode.DISABLE }).promise;
  } catch (e) { /* miniature ignorée : le document a changé entre-temps */ }
}

function markThumb() {
  document.querySelectorAll(".thumb").forEach((b) => {
    const cur = Number(b.dataset.n) === curPage;
    b.classList.toggle("current", cur);
    if (cur && !$("thumbs").hidden) b.scrollIntoView({ block: "nearest" });
  });
}

function toggleThumbs(force) {
  if (!pdfDoc) return;
  const open = force ?? $("thumbs").hidden;
  $("thumbs").hidden = !open;
  document.body.classList.toggle("has-thumbs", open);
  $("thumbsBtn").setAttribute("aria-pressed", String(open));
  prefs.thumbs = open; savePrefs();
  if (open) markThumb();
}
$("thumbsBtn").addEventListener("click", () => toggleThumbs());

// ---------- Ajuster à la largeur ----------
async function fitWidthNow() {
  if (!pdfDoc) return;
  const p = await pdfDoc.getPage(clamp(curPage, 1, pdfDoc.numPages));
  setZoom(clamp((viewer.clientWidth - 40) / p.getViewport({ scale: 1 }).width, 0.5, 4));
}
$("fitWidth").addEventListener("click", fitWidthNow);

// ---------- Recherche dans le PDF ----------
// Insensible aux majuscules et aux accents ; on garde la correspondance avec le texte d'origine.
function norm(s) {
  let out = "";
  const map = [];
  for (let i = 0; i < s.length; i++) {
    const c = s[i].normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
    for (const ch of c) { out += ch; map.push(i); }
  }
  return { out, map };
}
let hits = [], hitIdx = -1;

function addFindLayers() {
  pages.forEach((p) => {
    if (!p.findLayer) {
      p.findLayer = el("div", "find-layer");
      p.div.insertBefore(p.findLayer, p.div.querySelector(".textLayer"));
    }
  });
}

function locate(offs, pos) { // dernier morceau de texte qui commence avant pos
  let lo = 0, hi = offs.length - 1;
  while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (offs[mid] <= pos) lo = mid; else hi = mid - 1; }
  return lo;
}

function clearFind() {
  pages.forEach((p) => p.findLayer?.replaceChildren());
  hits = []; hitIdx = -1;
}

let searchRun = 0; // numéro de la recherche en cours : une plus récente annule la précédente
async function runSearch(keep = false) {
  const my = ++searchRun;
  const prev = keep ? hitIdx : -1;
  clearFind();
  const q = norm($("findInput").value.trim()).out;
  if (!q) { $("findCount").textContent = ""; return; }
  // Le texte des pages est préparé en arrière-plan (voir app.js) : on l'attend avant de chercher
  for (let i = 0; i < 900 && pages.some((p) => p.textState !== "ready"); i++) {
    $("findCount").textContent = "Préparation du texte…";
    await Promise.race([textReady, new Promise((r) => setTimeout(r, 120))]);
    await new Promise((r) => setTimeout(r, 40));
    if (my !== searchRun || !pages.length) return;
  }
  if (my !== searchRun) return;
  pages.forEach((p, pi) => {
    const spans = [...p.div.querySelectorAll(".textLayer span")].filter((s) => s.children.length === 0 && s.firstChild && s.firstChild.nodeType === 3);
    if (!spans.length) return;
    let full = "";
    const offs = [];
    spans.forEach((s) => { offs.push(full.length); full += s.textContent + " "; }); // une espace entre deux morceaux
    const { out, map } = norm(full);
    const pr = p.div.getBoundingClientRect();
    for (let idx = out.indexOf(q); idx !== -1; idx = out.indexOf(q, idx + Math.max(1, q.length))) {
      const a = map[idx], b = map[idx + q.length - 1] + 1;
      const sa = locate(offs, a), sb = locate(offs, b - 1);
      try {
        const r = document.createRange();
        r.setStart(spans[sa].firstChild, Math.min(a - offs[sa], spans[sa].firstChild.length));
        r.setEnd(spans[sb].firstChild, Math.min(b - offs[sb], spans[sb].firstChild.length));
        const rects = [...r.getClientRects()].filter((x) => x.width > 0.5)
          .map((x) => [(x.left - pr.left) / SCALE, (x.top - pr.top) / SCALE, x.width / SCALE, x.height / SCALE]);
        if (rects.length) hits.push({ page: pi, rects });
      } catch (e) { /* correspondance impossible à localiser : ignorée */ }
    }
  });
  for (const h of hits) {
    h.els = h.rects.map(([x, y, w, hh]) => {
      const d = el("div", "find-hit");
      Object.assign(d.style, { left: x * SCALE + "px", top: y * SCALE + "px", width: w * SCALE + "px", height: hh * SCALE + "px" });
      pages[h.page].findLayer.appendChild(d);
      return d;
    });
  }
  if (!hits.length) { $("findCount").textContent = "Aucun résultat"; return; }
  const firstFromHere = hits.findIndex((h) => h.page + 1 >= curPage);
  gotoHit(prev >= 0 && prev < hits.length ? prev : Math.max(0, firstFromHere), prev < 0);
}

function gotoHit(i, scroll = true) {
  if (!hits.length) return;
  hitIdx = (i + hits.length) % hits.length;
  hits.forEach((h, k) => h.els.forEach((d) => d.classList.toggle("cur", k === hitIdx)));
  $("findCount").textContent = `${hitIdx + 1} / ${hits.length}`;
  if (scroll) { hits[hitIdx].els[0].scrollIntoView({ block: "center", inline: "nearest" }); updateVisible(); }
}

function openFind() {
  if (!pdfDoc) return;
  $("findbar").hidden = false;
  $("findInput").focus();
  $("findInput").select();
  if ($("findInput").value) runSearch();
}
function closeFind() {
  $("findbar").hidden = true;
  clearFind();
  $("findCount").textContent = "";
}
let findTimer;
$("findInput").addEventListener("input", () => { clearTimeout(findTimer); findTimer = setTimeout(() => runSearch(), 200); });
$("findInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); gotoHit(hitIdx + (e.shiftKey ? -1 : 1)); }
});
$("findNext").addEventListener("click", () => gotoHit(hitIdx + 1));
$("findPrev").addEventListener("click", () => gotoHit(hitIdx - 1));
$("findClose").addEventListener("click", closeFind);
$("findBtn").addEventListener("click", () => ($("findbar").hidden ? openFind() : closeFind()));

// ---------- Appelé par app.js quand on quitte un document (retour à l'accueil) ----------
function onDocClosed() {
  if (thumbObserver) { thumbObserver.disconnect(); thumbObserver = null; }
  $("thumbs").replaceChildren();
  $("thumbs").hidden = true;
  document.body.classList.remove("has-thumbs");
  $("thumbsBtn").setAttribute("aria-pressed", "false");
  closeFind();
  $("pager").hidden = true;
  curPage = 1;
  ["thumbsBtn", "findBtn", "fitWidth"].forEach((id) => { $(id).disabled = true; });
}

// ---------- Appelé par app.js à chaque affichage des pages ----------
function onPagesRendered(initial) {
  const has = pages.length > 0;
  ["thumbsBtn", "findBtn", "fitWidth"].forEach((id) => { $(id).disabled = !has; });
  $("pager").hidden = !has;
  $("pageCount").textContent = pageLabel(pages.length);
  addFindLayers();
  if (initial) {
    const meta = loadMeta();
    buildThumbs();
    meta.then(() => { refreshThumbLabels(); updatePager(); });
    closeFind();
    toggleThumbs(!!prefs.thumbs && innerWidth >= 900); // le panneau reste ouvert ou fermé comme vous l'aviez laissé
    restoreLastPage();
  }
  if (!$("findbar").hidden && $("findInput").value) runSearch(true); // après un changement de zoom
  setTimeout(updatePager, 50);
}

// ---------- Raccourcis clavier et aide ----------
function setMode(m) {
  const r = document.querySelector(`input[name="mode"][value="${m}"]`);
  if (!r) return;
  r.checked = true;
  r.dispatchEvent(new Event("change", { bubbles: true }));
}
function toggleHelp(force) {
  const h = $("help"), open = force ?? h.hidden;
  closePopovers();
  h.hidden = !open;
}
$("helpBtn").addEventListener("click", () => toggleHelp());

document.addEventListener("keydown", (e) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(e.target.tagName) || e.target.isContentEditable;
  const ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && e.key.toLowerCase() === "f") { if (pdfDoc) { e.preventDefault(); openFind(); } return; }
  if (e.key === "Escape") {
    if (!$("findbar").hidden) closeFind();
    else if (!typing && currentMode() !== "select") setMode("select"); // Échap : retour à l'outil Sélection
    return;
  }
  if (typing || ctrl || e.altKey) return;
  const tools = { v: "select", h: "highlight", d: "draw", n: "note", t: "text", f: "shape", x: "erase", e: "native" };
  const k = e.key.toLowerCase();
  if (tools[k]) { e.preventDefault(); setMode(tools[k]); }
  else if (k === "p") toggleThumbs();
  else if (k === "w") fitWidthNow();
  else if (e.key === "?") toggleHelp();
});
