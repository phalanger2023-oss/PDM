// Notes de version : fenêtre ouverte depuis l'accueil. Le contenu vient de /api/releases (releases.py).
(() => {
  const dlg = document.getElementById("relDlg"), btn = document.getElementById("relBtn"), body = document.getElementById("relBody");
  if (!dlg || !btn) return;
  const SECTIONS = [["nouveautes", "Nouveautés"], ["ameliorations", "Améliorations"], ["corrections", "Corrections"]];
  const fmt = (d) => (d ? new Date(d + "T12:00:00").toLocaleDateString("fr-FR", { dateStyle: "long" }) : "");
  const mk = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text) e.textContent = text; return e; };
  let loaded = false;
  const credits = mk("div", "credits"); credits.hidden = true;
  const cbtn = mk("button", "rel-link", "Crédits"); cbtn.type = "button";
  cbtn.addEventListener("click", async () => {
    if (!credits.hidden) { credits.hidden = true; body.hidden = false; cbtn.textContent = "Crédits"; return; }
    credits.replaceChildren();
    try {
      const c = await (await fetch("/api/credits")).json();
      (c.lines || []).forEach((l) => { const p = mk("p", "credit-line"); if (l.label) p.append(mk("span", "muted", l.label + " ")); p.append(mk("b", "", l.value)); credits.append(p); });
      if (c.quote) { const q = mk("blockquote", "credit-quote", "« " + c.quote + " »"); if (c.quote_author) q.append(mk("footer", "muted", "— " + c.quote_author)); credits.append(q); }
      if (!credits.children.length) credits.append(mk("p", "muted", "Aucun crédit renseigné pour l'instant (à remplir dans DeepWell → Notes de version → Crédits)."));
    } catch { credits.append(mk("p", "muted", "Impossible de charger les crédits.")); }
    credits.hidden = false; body.hidden = true; cbtn.textContent = "← Notes de version";
  });
  body.before(credits); document.getElementById("relClose").before(cbtn);

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
