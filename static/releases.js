// Notes de version : fenêtre ouverte depuis l'accueil. Le contenu vient de /api/releases (releases.py).
(() => {
  const dlg = document.getElementById("relDlg"), btn = document.getElementById("relBtn"), body = document.getElementById("relBody");
  if (!dlg || !btn) return;
  const SECTIONS = [["nouveautes", "Nouveautés"], ["ameliorations", "Améliorations"], ["corrections", "Corrections"]];
  const fmt = (d) => (d ? new Date(d + "T12:00:00").toLocaleDateString("fr-FR", { dateStyle: "long" }) : "");
  const mk = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; };
  let loaded = false;

  fetch("/api/releases").then((r) => (r.ok ? r.json() : null)).then((d) => { if (d) btn.textContent = "alpha " + d.version; }).catch(() => {});

  async function load() {
    if (loaded) return;
    const r = await fetch("/api/releases");
    if (!r.ok) { body.textContent = "Impossible de charger les notes de version."; return; }
    const { releases } = await r.json();
    releases.forEach((rel, i) => {
      const det = mk("details", "rel");
      det.open = i === 0;
      const sum = mk("summary", "rel-head");
      sum.append(mk("h3", "", "Alpha " + rel.version));
      if (i === 0) sum.append(mk("span", "rel-tag", "Dernière version"));
      if (rel.date) sum.append(mk("span", "rel-date", fmt(rel.date)));
      det.append(sum);
      for (const [k, label] of SECTIONS) {
        if (!(rel[k] || []).length) continue;
        const blk = mk("div", "rel-block");
        blk.append(mk("h4", "", label));
        const ul = mk("ul");
        rel[k].forEach((t) => ul.append(mk("li", "", t)));
        blk.append(ul); det.append(blk);
      }
      body.append(det);
    });
    loaded = true;
  }
  btn.addEventListener("click", async () => { await load(); dlg.showModal(); });
  document.getElementById("relClose").addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
})();
