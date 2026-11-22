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
function setRoute(name) {
  const h = name ? "#/" + encodeURIComponent(name) : "#/";
  if (location.hash !== h) { suppressHash = true; location.hash = h; }
}
async function route() {
  const name = decodeURIComponent(location.hash.replace(/^#\/?/, ""));
  if (name) await openDoc(name);
  else await goHome();
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
  const list = docs.filter((d) => !q || fold(stripPdf(d.name)).includes(q));
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
  const res = await fetch("/api/docs");
  if (!res.ok) return;
  docs = await res.json();
  const has = docs.length > 0;
  $("homeEmpty").hidden = has;
  $("library").hidden = !has;
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

function renderGrid() {
  const list = visibleDocs();
  grid.replaceChildren();
  list.forEach((d) => grid.appendChild(buildCard(d)));
  $("noMatch").hidden = list.length > 0 || docs.length === 0;
  $("docCount").textContent = docs.length ? `· ${list.length === docs.length ? docs.length : `${list.length} sur ${docs.length}`}` : "";
}

function buildCard(d) {
  const title = stripPdf(d.name);
  const card = el("div", "card");

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
  main.append(tw, ct, cd, cp);
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
