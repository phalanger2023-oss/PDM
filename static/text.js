// Éditeur de texte (façon Word / Google Docs) : documents « .pdmdoc » (HTML simplifié) rangés comme les PDF.
// S'appuie sur app.js / home.js : setView, notify, fail, enc, el, goHome, renderHome, cwd, setRoute, svgIcon.

const txPaper = $("txPaper"), txName = $("txName"), txState = $("txState"), txTools = $("txTools");
let txDoc = null;          // nom du document texte ouvert (ex. « Cours.pdmdoc »)
let txDirty = false, txTimer = 0, txSaving = null, txLoaded = false;

// ---------- Ouvrir / créer / importer ----------
async function openText(name) {
  if (txDoc && txDirty) await txSave();
  const res = await fetch(`/api/texts/${enc(name)}`);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { fail(data.error || "Document introuvable"); setView("home"); if (typeof goHome === "function") goHome(true); return; }
  if (typeof closeDocState === "function") closeDocState();
  txDoc = data.name; txLoaded = false; txDirty = false;
  txPaper.innerHTML = data.html || "<p><br></p>";
  txName.value = stripPdf(data.name);
  setView("text");
  setRoute(data.name);
  document.title = stripPdf(data.name) + " · " + APP_NAME;
  setStatus("");
  txSetState("");
  txLoaded = true;
  txPaper.focus();
}

async function newText() {
  const r = await fetch("/api/texts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ folder: cwd || "" }) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { fail(d.error || "Création impossible"); return; }
  await openText(d.name);
  txName.select();
}
$("newText").addEventListener("click", newText);
$("docxIn").addEventListener("change", async () => {
  const f = $("docxIn").files[0]; $("docxIn").value = "";
  if (!f) return;
  notify("Import du fichier Word…", "ok", 6000);
  const form = new FormData(); form.append("file", f); if (cwd) form.append("folder", cwd);
  const r = await fetch("/api/texts/import", { method: "POST", body: form });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { fail(d.error || "Import impossible"); return; }
  await openText(d.name);
});

function exportText(name, fmt) {
  const a = Object.assign(document.createElement("a"), { href: `/api/texts/${enc(name)}/export?fmt=${fmt}` });
  document.body.appendChild(a); a.click(); a.remove();
}

// ---------- Enregistrement automatique ----------
function txSetState(t, cls = "") { txState.textContent = t; txState.className = "savestate " + cls; }
function txChanged() {
  if (!txLoaded) return;
  txDirty = true; txSetState("Modifications non enregistrées");
  clearTimeout(txTimer); txTimer = setTimeout(txSave, 1200);
}
async function txSave() {
  clearTimeout(txTimer);
  if (!txDoc || !txDirty) return;
  if (txSaving) { await txSaving; if (!txDirty) return; }
  const name = txDoc, html = txPaper.innerHTML;
  txDirty = false; txSetState("Enregistrement…", "saving");
  txSaving = fetch(`/api/texts/${enc(name)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ html }), keepalive: html.length < 60000 })
    .then((r) => { if (!r.ok) throw new Error(); txSetState("Enregistré ✓"); })
    .catch(() => { txDirty = true; txSetState("Échec de l'enregistrement : nouvel essai…"); txTimer = setTimeout(txSave, 4000); })
    .finally(() => { txSaving = null; });
  await txSaving;
}
txPaper.addEventListener("input", txChanged);
document.addEventListener("keydown", (e) => { if (document.body.dataset.view === "text" && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); txSave(); } });
document.addEventListener("visibilitychange", () => { if (document.hidden && txDirty) txSave(); });
window.addEventListener("pagehide", () => { if (txDirty) txSave(); });

// Renommer depuis le titre
txName.addEventListener("change", async () => {
  const want = txName.value.trim();
  if (!want || want === stripPdf(txDoc)) { txName.value = stripPdf(txDoc); return; }
  await txSave();
  const r = await fetch(`/api/texts/${enc(txDoc)}/rename`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ newName: want }) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { fail(d.error || "Renommage impossible"); txName.value = stripPdf(txDoc); return; }
  txDoc = d.name; txName.value = stripPdf(d.name); setRoute(d.name); document.title = stripPdf(d.name) + " · " + APP_NAME;
});
txName.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); txPaper.focus(); } });

// Retour à l'accueil : on enregistre d'abord
const _goHomeBtn = $("homeBtn");
_goHomeBtn.addEventListener("click", () => { if (txDirty) txSave(); }, true);
window.addEventListener("hashchange", () => { if (txDirty) txSave(); });

// Menu Exporter
const txMenu = $("txExportMenu");
$("txExport").addEventListener("click", (e) => { e.stopPropagation(); txMenu.hidden = !txMenu.hidden; });
document.addEventListener("click", () => { txMenu.hidden = true; });
txMenu.addEventListener("click", async (e) => {
  const b = e.target.closest("[data-fmt]"); if (!b) return;
  txMenu.hidden = true; await txSave();
  if (b.dataset.fmt === "topdf") {
    const r = await fetch(`/api/texts/${enc(txDoc)}/to-pdf`, { method: "POST" });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { fail(d.error || "Création du PDF impossible"); return; }
    notify("PDF créé dans le même dossier ✓", "ok", 2500);
    openDoc(d.name);
  } else exportText(txDoc, b.dataset.fmt);
});

// ---------- Barre d'outils ----------
// Icônes de la barre (traits simples, comme le reste de l'application) — plus de flèches ni de symboles ambigus
const ICO = {
  undo: '<path d="M9 14L4 9l5-5"/><path d="M4 9h10a6 6 0 010 12h-3"/>', redo: '<path d="M15 14l5-5-5-5"/><path d="M20 9H10a6 6 0 000 12h3"/>',
  sup: '<path d="M4 19l8-9M12 19L4 10"/><path d="M16 8c0-2 1.2-3 2.6-3S21 6 21 7.3c0 1.2-1 2-2.2 2.9L16 12.5h5"/>', sub: '<path d="M4 15l8-9M12 15L4 6"/><path d="M16 20c0-2 1.2-3 2.6-3S21 18 21 19.3c0 1.2-1 2-2.2 2.9L16 24.5h5" transform="translate(0 -3)"/>',
  left: '<path d="M4 6h16M4 10h10M4 14h16M4 18h10"/>', center: '<path d="M4 6h16M7 10h10M4 14h16M7 18h10"/>', right: '<path d="M4 6h16M10 10h10M4 14h16M10 18h10"/>', justify: '<path d="M4 6h16M4 10h16M4 14h16M4 18h16"/>',
  ul: '<circle cx="5" cy="7" r="1"/><circle cx="5" cy="12" r="1"/><circle cx="5" cy="17" r="1"/><path d="M10 7h10M10 12h10M10 17h10"/>', ol: '<path d="M10 7h10M10 12h10M10 17h10"/><path d="M4 5.5l1.5-1v4M4 14.5c0-1 2.5-1 2.5.3 0 1-2.5 2-2.5 2.7h2.7"/>',
  indent: '<path d="M4 6h16M12 10h8M12 14h8M4 18h16"/><path d="M4 9.5l3 2.5-3 2.5z"/>', outdent: '<path d="M4 6h16M12 10h8M12 14h8M4 18h16"/><path d="M7 9.5L4 12l3 2.5z"/>',
  link: '<path d="M10 14a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 00-5.7 0l-3 3a4 4 0 005.7 5.7l1-1"/>',
  image: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="M4 18l5-5 4 4 3-3 4 4"/>',
  table: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M3.5 10h17M3.5 15h17M10 4.5v15"/>', hr: '<path d="M4 12h16"/><path d="M8 7h8M8 17h8" opacity=".35"/>',
  clear: '<path d="M5 6h10M10 6l-3 12M8 18h5"/><path d="M15 14l5 5M20 14l-5 5"/>',
  rowAdd: '<rect x="3.5" y="4.5" width="17" height="8" rx="1.5"/><path d="M12 15v6M9 18h6"/>', colAdd: '<rect x="3.5" y="4.5" width="8" height="15" rx="1.5"/><path d="M17 8v8M13 12h8"/>',
  rowDel: '<rect x="3.5" y="4.5" width="17" height="8" rx="1.5"/><path d="M9 18h6"/>', colDel: '<rect x="3.5" y="4.5" width="8" height="15" rx="1.5"/><path d="M13 12h8"/>', tblDel: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M8 9l8 6M16 9l-8 6"/>',
};
const ic = (n) => `<svg class="ic" viewBox="0 0 24 24" aria-hidden="true">${ICO[n]}</svg>`;
const FONTS = ["Arial", "Georgia", "Times New Roman", "Courier New", "Verdana", "Trebuchet MS", "Comic Sans MS"];
const SIZES = [8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48];
const tbtn = (label, title, fn, cls = "") => {
  const b = el("button", "tx-btn " + cls); b.type = "button"; b.innerHTML = label; b.title = title; b.setAttribute("aria-label", title);
  b.addEventListener("mousedown", (e) => e.preventDefault()); // garde la sélection dans le texte
  b.addEventListener("click", () => { txPaper.focus(); fn(); txChanged(); });
  txTools.appendChild(b); return b;
};
const tsel = (title, options, fn, width) => {
  const s = el("select", "tx-sel"); s.title = title; s.setAttribute("aria-label", title); if (width) s.style.width = width;
  options.forEach(([v, l]) => s.appendChild(Object.assign(document.createElement("option"), { value: v, textContent: l })));
  let saved = null;
  s.addEventListener("mousedown", () => { const sel = getSelection(); saved = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null; });
  s.addEventListener("change", () => { txPaper.focus(); if (saved) { const sel = getSelection(); sel.removeAllRanges(); sel.addRange(saved); } fn(s.value); s.selectedIndex = 0; txChanged(); });
  txTools.appendChild(s); return s;
};
const tsep = () => txTools.appendChild(el("span", "tx-sep"));
const cmd = (c, v = null) => document.execCommand(c, false, v);

function inEditor() { const n = getSelection().anchorNode; return n && txPaper.contains(n.nodeType === 3 ? n.parentNode : n); }
function closest(sel) { const n = getSelection().anchorNode; const e = n && (n.nodeType === 3 ? n.parentNode : n); const r = e?.closest?.(sel); return r && txPaper.contains(r) ? r : null; }

function setFontSize(pt) { // taille en points : execCommand ne sait faire que 1 à 7, on remplace ensuite ces balises par un style précis
  cmd("styleWithCSS", false); cmd("fontSize", "7");
  txPaper.querySelectorAll("font[size='7']").forEach((f) => { const s = el("span", ""); s.style.fontSize = pt + "pt"; while (f.firstChild) s.appendChild(f.firstChild); f.replaceWith(s); });
}
function colorInput(title, label, command) {
  const wrap = el("label", "tx-btn tx-color"); wrap.title = title; wrap.innerHTML = label;
  const inp = document.createElement("input"); inp.type = "color"; inp.value = command === "hiliteColor" ? "#ffff00" : "#d32f2f";
  let saved = null;
  inp.addEventListener("mousedown", () => { const sel = getSelection(); saved = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null; });
  inp.addEventListener("input", () => { txPaper.focus(); if (saved) { const sel = getSelection(); sel.removeAllRanges(); sel.addRange(saved); } cmd("styleWithCSS", true); cmd(command, inp.value); txChanged(); });
  wrap.appendChild(inp); txTools.appendChild(wrap);
}

tbtn(ic("undo"), "Annuler (Ctrl+Z)", () => cmd("undo")); tbtn(ic("redo"), "Rétablir (Ctrl+Y)", () => cmd("redo")); tsep();
tsel("Style de paragraphe", [["", "Style"], ["p", "Texte normal"], ["h1", "Titre 1"], ["h2", "Titre 2"], ["h3", "Titre 3"], ["blockquote", "Citation"]], (v) => v && cmd("formatBlock", v), "108px");
tsel("Police", [["", "Police"], ...FONTS.map((f) => [f, f])], (v) => { if (v) { cmd("styleWithCSS", true); cmd("fontName", v); } }, "104px");
tsel("Taille du texte", [["", "Taille"], ...SIZES.map((n) => [n, n + " pt"])], (v) => v && setFontSize(v), "74px"); tsep();
const B_ = {}; const sb = (st, b) => { B_[st] = b; return b; };
sb("bold", tbtn("<b>G</b>", "Gras (Ctrl+B)", () => cmd("bold"))); sb("italic", tbtn("<i>I</i>", "Italique (Ctrl+I)", () => cmd("italic")));
sb("underline", tbtn("<u>S</u>", "Souligné (Ctrl+U)", () => cmd("underline"))); sb("strikeThrough", tbtn("<s>B</s>", "Barré", () => cmd("strikeThrough")));
sb("superscript", tbtn(ic("sup"), "Exposant (x²)", () => cmd("superscript"))); sb("subscript", tbtn(ic("sub"), "Indice (x₂)", () => cmd("subscript")));
colorInput("Couleur du texte", "<b style='color:#d32f2f'>A</b>", "foreColor"); colorInput("Surligner", "<b style='background:#ff0;padding:0 3px'>A</b>", "hiliteColor"); tsep();
sb("justifyLeft", tbtn(ic("left"), "Aligner à gauche", () => cmd("justifyLeft"))); sb("justifyCenter", tbtn(ic("center"), "Centrer", () => cmd("justifyCenter"))); sb("justifyRight", tbtn(ic("right"), "Aligner à droite", () => cmd("justifyRight"))); sb("justifyFull", tbtn(ic("justify"), "Justifier", () => cmd("justifyFull"))); tsep();
sb("insertUnorderedList", tbtn(ic("ul"), "Liste à puces", () => cmd("insertUnorderedList"))); sb("insertOrderedList", tbtn(ic("ol"), "Liste numérotée", () => cmd("insertOrderedList")));
tbtn(ic("indent"), "Augmenter le retrait", () => cmd("indent")); tbtn(ic("outdent"), "Diminuer le retrait", () => cmd("outdent")); tsep();
tbtn(ic("link"), "Insérer un lien", () => {
  const sel = getSelection(); const saved = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
  const url = prompt("Adresse du lien (https://…) :", "https://"); if (!url || !/^(https?:\/\/|mailto:)/i.test(url.trim())) { if (url) fail("L'adresse doit commencer par https://"); return; }
  if (saved) { sel.removeAllRanges(); sel.addRange(saved); }
  if (sel.isCollapsed) cmd("insertHTML", `<a href="${url.trim().replace(/"/g, "%22")}">${url.trim().replace(/</g, "&lt;")}</a>`); else cmd("createLink", url.trim());
});
tbtn(ic("image"), "Insérer une image", () => $("txImg").click());
tbtn(ic("table"), "Insérer un tableau", () => {
  const v = prompt("Tableau : lignes × colonnes (ex. 3x4)", "3x3"); const m = /^(\d{1,2})\s*[x×*]\s*(\d{1,2})$/i.exec((v || "").trim()); if (!m) return;
  const r = +m[1], c = +m[2]; let h = '<table style="width:100%"><tbody>';
  for (let i = 0; i < r; i++) { h += "<tr>"; for (let j = 0; j < c; j++) h += i === 0 ? "<th><br></th>" : "<td><br></td>"; h += "</tr>"; }
  cmd("insertHTML", h + "</tbody></table><p><br></p>");
});
tbtn(ic("hr"), "Ligne de séparation", () => cmd("insertHorizontalRule"));
tbtn(ic("clear"), "Effacer la mise en forme", () => { cmd("removeFormat"); cmd("formatBlock", "p"); }); tsep();
// outils de tableau (visibles quand le curseur est dans un tableau)
const tbl = [];
const tt = (label, title, fn) => { const b = tbtn(label, title, fn, "tx-tbl"); b.hidden = true; tbl.push(b); };
const rowOf = () => closest("tr"), cellOf = () => closest("td,th");
tt(ic("rowAdd"), "Ajouter une ligne dessous", () => { const r = rowOf(); if (!r) return; const n = r.cloneNode(true); n.querySelectorAll("td,th").forEach((c) => { c.innerHTML = "<br>"; }); r.after(n); });
tt(ic("colAdd"), "Ajouter une colonne à droite", () => { const c = cellOf(); if (!c) return; const i = [...c.parentNode.children].indexOf(c); c.closest("table").querySelectorAll("tr").forEach((r) => { const x = r.children[i]; if (x) { const n = document.createElement(x.tagName); n.innerHTML = "<br>"; x.after(n); } }); });
tt(ic("rowDel"), "Supprimer la ligne", () => { const r = rowOf(); if (!r) return; const t = r.closest("table"); if (t.querySelectorAll("tr").length <= 1) t.remove(); else r.remove(); });
tt(ic("colDel"), "Supprimer la colonne", () => { const c = cellOf(); if (!c) return; const i = [...c.parentNode.children].indexOf(c), t = c.closest("table"); if (c.parentNode.children.length <= 1) { t.remove(); return; } t.querySelectorAll("tr").forEach((r) => r.children[i]?.remove()); });
tt(ic("tblDel"), "Supprimer le tableau", () => closest("table")?.remove());
document.addEventListener("selectionchange", () => { if (document.body.dataset.view !== "text") return;
  if (inEditor()) for (const [st, b] of Object.entries(B_)) { let on = false; try { on = document.queryCommandState(st); } catch (e) {} b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on)); } // l'outil actif est surligné
  const on = !!closest("td,th"); tbl.forEach((b) => { b.hidden = !on; }); });

// ---------- Images (réduites avant d'être intégrées au document) ----------
async function insertImageFile(file) {
  if (!/^image\/(png|jpeg|gif|webp)$/.test(file.type)) { fail("Image non prise en charge (PNG, JPEG, GIF ou WebP)."); return; }
  const url = URL.createObjectURL(file);
  try {
    const img = await new Promise((ok, ko) => { const i = new Image(); i.onload = () => ok(i); i.onerror = ko; i.src = url; });
    const max = 1400, k = Math.min(1, max / Math.max(img.width, img.height));
    let data;
    if (k < 1 || file.size > 700_000) {
      const c = document.createElement("canvas"); c.width = Math.round(img.width * k); c.height = Math.round(img.height * k);
      const g = c.getContext("2d"); if (file.type !== "image/png") { g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height); } g.drawImage(img, 0, 0, c.width, c.height);
      data = c.toDataURL(file.type === "image/png" ? "image/png" : "image/jpeg", 0.85);
    } else data = await new Promise((ok) => { const r = new FileReader(); r.onload = () => ok(r.result); r.readAsDataURL(file); });
    txPaper.focus(); cmd("insertHTML", `<img src="${data}" style="width:${Math.min(img.width * k, 560)}px">`); txChanged();
  } catch (e) { fail("Image illisible."); } finally { URL.revokeObjectURL(url); }
}
$("txImg").addEventListener("change", () => { const f = $("txImg").files[0]; $("txImg").value = ""; if (f) insertImageFile(f); });

// ---------- Coller : on garde le texte et la mise en forme utile, sans le reste ----------
const OK_TAGS = new Set(["P", "BR", "H1", "H2", "H3", "STRONG", "B", "EM", "I", "U", "S", "STRIKE", "SUB", "SUP", "UL", "OL", "LI", "A", "TABLE", "THEAD", "TBODY", "TR", "TD", "TH", "HR", "BLOCKQUOTE", "SPAN", "DIV", "PRE", "CODE"]);
function cleanNode(n) {
  [...n.childNodes].forEach((c) => {
    if (c.nodeType === 8) { c.remove(); return; }
    if (c.nodeType !== 1) return;
    if (["SCRIPT", "STYLE", "META", "LINK", "IFRAME", "OBJECT", "SVG", "IMG"].includes(c.tagName)) { c.remove(); return; }
    cleanNode(c);
    if (!OK_TAGS.has(c.tagName)) { c.replaceWith(...c.childNodes); return; }
    const keep = {}; if (c.tagName === "A" && /^(https?:|mailto:)/i.test(c.getAttribute("href") || "")) keep.href = c.getAttribute("href");
    const st = c.style, css = [];
    for (const p of ["color", "background-color", "font-weight", "font-style", "text-decoration", "text-align", "font-size"]) if (st[p]) css.push(`${p}:${st[p]}`);
    [...c.attributes].forEach((a) => c.removeAttribute(a.name));
    Object.entries(keep).forEach(([k, v]) => c.setAttribute(k, v)); if (css.length) c.setAttribute("style", css.join(";"));
  });
}
txPaper.addEventListener("paste", (e) => {
  const cd = e.clipboardData; if (!cd) return;
  const img = [...cd.files].find((f) => f.type.startsWith("image/"));
  if (img) { e.preventDefault(); insertImageFile(img); return; }
  const html = cd.getData("text/html");
  e.preventDefault();
  if (html) { const d = new DOMParser().parseFromString(html, "text/html"); cleanNode(d.body); cmd("insertHTML", d.body.innerHTML); }
  else cmd("insertText", cd.getData("text/plain"));
  txChanged();
});
// Tab dans une liste = retrait
txPaper.addEventListener("keydown", (e) => { if (e.key === "Tab" && closest("li")) { e.preventDefault(); cmd(e.shiftKey ? "outdent" : "indent"); txChanged(); } });
