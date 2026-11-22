// Accueil : l'en-tête, « Reprendre où vous en étiez » et la galerie de vos documents.
// S'appuie sur app.js (openDoc, leaveCurrentDoc, notify, fail, APP_NAME...).

const grid = $("grid");

function svgIcon(name, cls = "ic") { // une icône de la page (définie dans index.html), créée sans HTML
  const s = document.createElementNS(NS, "svg");
  s.setAttribute("class", cls);
  const u = document.createElementNS(NS, "use");
  u.setAttribute("href", "#i-" + name);
  s.appendChild(u);
  return s;
}

// ---------- Adresse de la page : #/Nom.pdf = document ouvert, #/ = accueil ----------
// Recharger la page (ou la fermer et la rouvrir par son adresse) ramène donc sur le même document.
let suppressHash = false;
let cwd = "";          // dossier affiché à l'accueil ("" = l'accueil lui-même)
let folders = [];      // tous les dossiers : { path, name, parent, items }
function setRoute(name) {
  const h = name ? "#/" + encodeURIComponent(name) : cwd ? "#/" + encodeURIComponent("@/" + cwd) : "#/";
  if (location.hash !== h) { suppressHash = true; location.hash = h; }
}
async function route() {
  const name = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
  if (name.startsWith("@/")) { cwd = name.slice(2); await goHome(); }
  else if (name) await openDoc(name);
  else { cwd = ""; await goHome(); }
}
window.addEventListener("hashchange", () => {
  if (suppressHash) { suppressHash = false; return; }
  route();
});

// ---------- Aller à l'accueil ----------
async function goHome(skipLeave = false) {
  if (!skipLeave && docName && !(await leaveCurrentDoc())) return;
  closeDocState();
  setView("home");
  document.title = APP_NAME;
  setRoute(null);
  setStatus("");
  await renderHome();
}
$("homeBtn").addEventListener("click", () => goHome());

// ---------- Dates et textes ----------
const plural = (n, un, plus) => `${n} ${n > 1 ? plus : un}`;
const heure = (d) => d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" });

function ago(ts) { // « il y a 5 min »
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 45) return "à l'instant";
  if (s < 3600) return `il y a ${Math.round(s / 60)} min`;
  if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
  if (s < 172800) return "hier";
  if (s < 86400 * 30) return `il y a ${Math.round(s / 86400)} j`;
  return "";
}

function when(ts) { // « Aujourd'hui à 13:52 », « Hier à 09:10 », « 18 nov. à 13:52 »
  const d = new Date(ts * 1000), now = new Date(), y = new Date(now);
  y.setDate(now.getDate() - 1);
  if (d.toDateString() === now.toDateString()) return `Aujourd'hui à ${heure(d)}`;
  if (d.toDateString() === y.toDateString()) return `Hier à ${heure(d)}`;
  const o = { day: "numeric", month: "short" };
  if (d.getFullYear() !== now.getFullYear()) o.year = "numeric";
  return `${d.toLocaleDateString("fr-FR", o)} à ${heure(d)}`;
}
const whenLong = (ts) => new Date(ts * 1000).toLocaleString("fr-FR", { dateStyle: "full", timeStyle: "short" });

// ---------- Recherche et tri ----------
let docs = [];                                                      // liste reçue du serveur
let docSort = "recent";
try { docSort = localStorage.getItem("docSort") || "recent"; } catch (e) {}
const fold = (s) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase(); // sans accents ni majuscules

function visibleDocs() {
  const q = fold($("docSearch").value.trim());
  const list = docs.filter((d) => (q ? fold(stripPdf(d.name) + " " + (d.folder || "")).includes(q) : (d.folder || "") === cwd));
  const by = {
    recent: (a, b) => b.modified - a.modified,
    old: (a, b) => a.modified - b.modified,
    name: (a, b) => stripPdf(a.name).localeCompare(stripPdf(b.name), "fr", { sensitivity: "base" }),
    nameDesc: (a, b) => stripPdf(b.name).localeCompare(stripPdf(a.name), "fr", { sensitivity: "base" }),
  };
  return list.sort(by[docSort] || by.recent);
}

$("docSort").value = docSort;
$("docSort").addEventListener("change", () => {
  docSort = $("docSort").value;
  try { localStorage.setItem("docSort", docSort); } catch (e) {}
  renderGrid();
});
let searchTimer;
$("docSearch").addEventListener("input", () => { clearTimeout(searchTimer); searchTimer = setTimeout(renderGrid, 120); });

// ---------- L'accueil ----------
async function renderHome() {
  const [r1, r2] = await Promise.all([fetch("/api/docs"), fetch("/api/folders")]);
  if (!r1.ok) return;
  docs = await r1.json();
  folders = r2.ok ? await r2.json() : [];
  if (cwd && !folders.some((f) => f.path === cwd)) cwd = ""; // dossier supprimé ou renommé ailleurs
  $("homeEmpty").hidden = docs.length > 0;
  $("library").hidden = false;
  renderResume();
  renderGrid();
}

function renderResume() { // le document sur lequel vous avez travaillé en dernier
  const last = [...docs].sort((a, b) => b.modified - a.modified)[0];
  $("resume").hidden = !last;
  if (!last) return;
  const card = $("resumeCard");
  card.onclick = () => openDoc(last.name);
  card.setAttribute("aria-label", `Reprendre ${stripPdf(last.name)}`);
  $("resumeName").textContent = stripPdf(last.name);
  const rel = ago(last.modified);
  $("resumeDate").textContent = `Dernière modification : ${whenLong(last.modified)}` + (rel ? ` (${rel})` : "");
  $("resumeMeta").textContent = (last.pages ? plural(last.pages, "page", "pages") : "PDF") + (last.draft ? " · modifications en cours" : "");
  $("resumeImg").src = `/api/docs/${enc(last.name)}/thumb?v=${Math.round(last.modified)}`;
}

function visibleFolders() {
  const q = fold($("docSearch").value.trim());
  return folders.filter((f) => (q ? fold(f.name).includes(q) : f.parent === cwd)).sort((a, b) => a.name.localeCompare(b.name, "fr", { sensitivity: "base" }));
}

function goFolder(path) { cwd = path; $("docSearch").value = ""; setRoute(null); renderGrid(); window.scrollTo?.({ top: 0 }); }

function renderCrumbs() { // Accueil › Scolaire › 2026-2027 : chaque étape est cliquable et accepte un document ou un dossier lâché dessus
  const nav = $("crumbs"), parts = cwd ? cwd.split("/") : [];
  nav.replaceChildren();
  nav.hidden = !parts.length;
  const add = (label, path, last) => {
    const b = el("button", "crumb" + (last ? " here" : ""));
    b.type = "button"; b.textContent = label;
    if (!last) { b.addEventListener("click", () => goFolder(path)); dropTarget(b, path); }
    nav.appendChild(b);
    if (!last) nav.appendChild(Object.assign(el("span", "sep"), { textContent: "›" }));
  };
  add("Accueil", "", false);
  parts.forEach((p, i) => add(p, parts.slice(0, i + 1).join("/"), i === parts.length - 1));
}

function renderGrid() {
  const list = visibleDocs(), subs = visibleFolders(), searching = $("docSearch").value.trim() !== "";
  grid.replaceChildren();
  subs.forEach((f) => grid.appendChild(buildFolder(f, searching)));
  list.forEach((d) => grid.appendChild(buildCard(d)));
  renderCrumbs();
  $("noMatch").hidden = list.length > 0 || subs.length > 0 || (!searching && !cwd);
  $("noMatch").textContent = searching ? "Rien ne correspond à votre recherche." : "Ce dossier est vide. Glissez un PDF ici, ou utilisez « Ouvrir un PDF ».";
  $("docCount").textContent = searching ? `· ${list.length + subs.length} résultat(s)` : cwd ? `· ${cwd.split("/").pop()}` : docs.length ? `· ${docs.length}` : "";
}
$("newFolder").addEventListener("click", async () => {
  const name = prompt(cwd ? `Nom du nouveau dossier (dans « ${cwd.split("/").pop()} ») :` : "Nom du nouveau dossier :");
  if (!name || !name.trim()) return;
  const r = await fetch("/api/folders", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ parent: cwd, name: name.trim() }) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { fail(d.error || "Création impossible"); return; }
  notify("Dossier créé ✓", "ok", 1800);
  renderHome();
});

// ---------- Glisser-déposer (souris) : un document ou un dossier lâché sur un dossier ou sur le fil d'Ariane y est rangé. Au doigt : menu « Déplacer vers… ». ----------
function dropTarget(node, path) {
  node.addEventListener("dragover", (e) => { if ([...e.dataTransfer.types].some((t) => t === "text/pdm-doc" || t === "text/pdm-folder")) { e.preventDefault(); node.classList.add("drop-over"); } });
  node.addEventListener("dragleave", () => node.classList.remove("drop-over"));
  node.addEventListener("drop", async (e) => {
    node.classList.remove("drop-over");
    const doc = e.dataTransfer.getData("text/pdm-doc"), fol = e.dataTransfer.getData("text/pdm-folder");
    if (!doc && !fol) return;
    e.preventDefault(); e.stopPropagation();
    if (doc) await moveDoc(doc, path); else await moveFolder(fol, path);
  });
}
async function moveDoc(name, to) {
  const r = await fetch(`/api/docs/${enc(name)}/move`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ folder: to }) });
  if (!r.ok) { fail((await r.json().catch(() => ({}))).error || "Déplacement impossible"); return; }
  notify("Document déplacé ✓", "ok", 1800);
  renderHome();
}
async function moveFolder(path, to) {
  const r = await fetch("/api/folders/move", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path, to }) });
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { fail(d.error || "Déplacement impossible"); return; }
  if (cwd === path || cwd.startsWith(path + "/")) cwd = d.path + cwd.slice(path.length);
  notify("Dossier déplacé ✓", "ok", 1800);
  renderHome();
}
function pickFolder(title, exclude) { // fenêtre « Déplacer vers… » : liste des dossiers en arborescence ; renvoie le chemin choisi, "" = Accueil, null = annulé
  return new Promise((resolve) => {
    const dlg = $("pickDlg"), list = $("pickList");
    $("pickTitle").textContent = title;
    list.replaceChildren();
    const row = (label, path, depth) => {
      const b = el("button", "pick-row"); b.type = "button"; b.style.paddingLeft = `${12 + depth * 18}px`;
      b.append(svgIcon("folder"), Object.assign(document.createElement("span"), { textContent: label }));
      b.addEventListener("click", () => { dlg.close(); resolve(path); });
      list.appendChild(b);
    };
    row("Accueil", "", 0);
    folders.filter((f) => !exclude || !(f.path === exclude || f.path.startsWith(exclude + "/")))
      .sort((a, b) => a.path.localeCompare(b.path, "fr", { sensitivity: "base" })).forEach((f) => row(f.name, f.path, f.path.split("/").length));
    $("pickCancel").onclick = () => { dlg.close(); resolve(null); };
    dlg.addEventListener("close", () => resolve(null), { once: true });
    dlg.showModal();
  });
}

function buildFolder(f, searching) {
  const card = el("div", "card foldercard");
  card.draggable = true;
  card.addEventListener("dragstart", (e) => { e.dataTransfer.setData("text/pdm-folder", f.path); e.dataTransfer.effectAllowed = "move"; });
  dropTarget(card, f.path);
  const main = el("button", "cardmain");
  main.setAttribute("aria-label", `Ouvrir le dossier ${f.name}`);
  const tw = el("div", "thumbwrap foldertile");
  tw.appendChild(svgIcon("folder", "ic xl"));
  const ct = el("div", "ct"); ct.textContent = f.name; ct.title = f.path;
  const cs = el("div", "cs"); cs.textContent = f.items ? plural(f.items, "élément", "éléments") : "Vide";
  main.append(tw, ct, cs);
  if (searching && f.parent) { const cf = el("div", "cs cfolder"); cf.textContent = "📁 " + f.parent; main.append(cf); }
  main.addEventListener("click", () => goFolder(f.path));
  const mb = el("button", "tool menu-btn");
  mb.title = "Actions"; mb.setAttribute("aria-label", `Actions pour le dossier ${f.name}`); mb.setAttribute("aria-haspopup", "menu");
  mb.appendChild(svgIcon("more"));
  const menu = el("div", "cardmenu"); menu.hidden = true; menu.setAttribute("role", "menu");
  const item = (icon, label, cls, fn) => {
    const b = el("button", "mi " + cls); b.setAttribute("role", "menuitem"); b.append(svgIcon(icon), label);
    b.addEventListener("click", (ev) => { ev.stopPropagation(); closeCardMenus(); fn(); }); menu.appendChild(b);
  };
  item("folder", "Ouvrir", "", () => goFolder(f.path));
  item("pencil", "Renommer", "", async () => {
    const want = prompt("Nouveau nom du dossier :", f.name);
    if (want === null || !want.trim() || want.trim() === f.name) return;
    const r = await fetch("/api/folders/rename", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: f.path, newName: want.trim() }) });
    const d = await r.json().catch(() => ({}));
    if (!r.ok) { fail(d.error || "Renommage impossible"); return; }
    if (cwd === f.path || cwd.startsWith(f.path + "/")) cwd = d.path + cwd.slice(f.path.length);
    renderHome();
  });
  item("folder", "Déplacer vers…", "", async () => { const to = await pickFolder(`Déplacer « ${f.name} » vers`, f.path); if (to !== null) await moveFolder(f.path, to); });
  item("trash", "Supprimer le dossier", "danger", async () => {
    if (!confirm(`Supprimer le dossier « ${f.name} » ?\n\nSes documents et sous-dossiers ne sont PAS supprimés : ils remontent d'un niveau.`)) return;
    const r = await fetch("/api/folders/delete", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: f.path }) });
    if (!r.ok) { fail("Suppression impossible"); return; }
    if (cwd === f.path || cwd.startsWith(f.path + "/")) cwd = f.parent;
    notify("Dossier supprimé (contenu conservé)", "ok", 2500);
    renderHome();
  });
  mb.addEventListener("click", (ev) => { ev.stopPropagation(); const open = menu.hidden; closeCardMenus(); menu.hidden = !open; card.classList.toggle("menu-open", open); });
  card.append(main, mb, menu);
  return card;
}

function buildCard(d) {
  const title = stripPdf(d.name);
  const card = el("div", "card");
  card.draggable = true;
  card.addEventListener("dragstart", (e) => { e.dataTransfer.setData("text/pdm-doc", d.name); e.dataTransfer.effectAllowed = "move"; });

  const main = el("button", "cardmain");
  main.setAttribute("aria-label", `Ouvrir ${title}`);
  const tw = el("div", "thumbwrap");
  const img = document.createElement("img");
  img.loading = "lazy";
  img.alt = "";
  img.src = `/api/docs/${enc(d.name)}/thumb?v=${Math.round(d.modified)}`; // v : la miniature se rafraîchit quand le document change
  img.addEventListener("error", () => { img.remove(); tw.prepend(svgIcon("file", "ic xl")); });
  tw.appendChild(img);
  if (d.draft) { const b = el("span", "badge"); b.textContent = "Modifié"; tw.appendChild(b); }
  // Titre centré, puis la date de dernière modification et le nombre de pages
  const ct = el("div", "ct"); ct.textContent = title; ct.title = title;
  const cd = el("div", "cs"); cd.textContent = `Modifié · ${when(d.modified)}`; cd.title = whenLong(d.modified);
  const cp = el("div", "cs"); cp.textContent = d.pages ? plural(d.pages, "page", "pages") : "PDF";
  main.append(tw, ct);
  if (d.folder && $("docSearch").value.trim()) { const cf = el("div", "cs cfolder"); cf.textContent = "📁 " + d.folder; cf.title = d.folder; main.append(cf); }
  main.append(cd, cp);
  main.addEventListener("click", () => openDoc(d.name));

  const mb = el("button", "tool menu-btn");
  mb.title = "Actions"; mb.setAttribute("aria-label", `Actions pour ${title}`); mb.setAttribute("aria-haspopup", "menu");
  mb.appendChild(svgIcon("more"));
  const menu = el("div", "cardmenu");
  menu.hidden = true; menu.setAttribute("role", "menu");
  const item = (icon, label, cls, fn) => {
    const b = el("button", "mi " + cls);
    b.setAttribute("role", "menuitem");
    b.append(svgIcon(icon), label);
    b.addEventListener("click", (ev) => { ev.stopPropagation(); closeCardMenus(); fn(); });
    menu.appendChild(b);
  };
  item("folder", "Ouvrir", "", () => openDoc(d.name));
  item("pencil", "Renommer", "", () => renameFromHome(d));
  item("folder", "Déplacer vers…", "", async () => { const to = await pickFolder(`Déplacer « ${title} » vers`); if (to !== null) await moveDoc(d.name, to); });
  item("download", "Télécharger le PDF", "", () => downloadFromHome(d));
  if (d.draft) item("undo", "Revenir à l'original", "", () => resetFromHome(d));
  item("trash", "Supprimer", "danger", () => deleteFromHome(d));
  mb.addEventListener("click", (ev) => {
    ev.stopPropagation();
    const open = menu.hidden;
    closeCardMenus();
    menu.hidden = !open;
    card.classList.toggle("menu-open", open);
  });
  card.append(main, mb, menu);
  return card;
}

function closeCardMenus() {
  document.querySelectorAll(".cardmenu").forEach((m) => { m.hidden = true; });
  document.querySelectorAll(".card.menu-open").forEach((c) => c.classList.remove("menu-open"));
}
document.addEventListener("mousedown", (e) => { if (!e.target.closest(".cardmenu, .menu-btn")) closeCardMenus(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeCardMenus(); });

// ---------- Actions sur une carte ----------
async function renameFromHome(d) {
  const cur = stripPdf(d.name);
  const want = prompt("Nouveau nom du document :", cur);
  if (want === null || !want.trim() || want.trim() === cur) return;
  const res = await fetch(`/api/docs/${enc(d.name)}/rename`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ newName: want.trim() }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { fail(data.error || "Renommage impossible"); return; }
  notify("Document renommé ✓", "ok", 2000);
  renderHome();
}

function downloadFromHome(d) { // le PDF final = l'original + votre brouillon, fabriqué par le serveur
  const a = Object.assign(document.createElement("a"), { href: `/api/docs/${enc(d.name)}/export`, download: d.name });
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function resetFromHome(d) {
  if (!confirm(`Revenir à l'original pour « ${stripPdf(d.name)} » ?\n\nToutes vos modifications de ce document seront supprimées.`)) return;
  await fetch(`/api/docs/${enc(d.name)}/project`, { method: "DELETE" });
  notify("Document remis à l'original", "ok", 2500);
  renderHome();
}

async function deleteFromHome(d) {
  if (!confirm(`Supprimer « ${stripPdf(d.name)} » ?\n\nLe document et ses modifications seront supprimés de Mes documents.\nVotre fichier d'origine sur l'ordinateur n'est pas touché.`)) return;
  await fetch(`/api/docs/${enc(d.name)}`, { method: "DELETE" });
  notify("Document supprimé", "ok", 2500);
  renderHome();
}

// ---------- Démarrage : on reprend là où on était ----------
route();


// ---------- Lien avec DeepWell : la clé secrète à recopier dans DeepWell ----------
$("linkShow").addEventListener("click", async () => {
  const r = await fetch("/api/integration/key");
  if (!r.ok) return;
  $("linkKey").value = (await r.json()).key;
  $("linkCopy").hidden = false;
  $("linkKey").select();
});
$("linkCopy").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("linkKey").value); $("linkCopy").textContent = "Copié ✓"; setTimeout(() => { $("linkCopy").textContent = "Copier"; }, 1500); } catch (e) { $("linkKey").select(); }
});
$("linkRenew").addEventListener("click", async () => {
  if (!confirm("Créer une nouvelle clé ? L'ancienne cessera de fonctionner : il faudra recopier la nouvelle dans DeepWell.")) return;
  const r = await fetch("/api/integration/key/renew", { method: "POST" });
  if (!r.ok) return;
  $("linkKey").value = (await r.json()).key;
  $("linkCopy").hidden = false;
});
