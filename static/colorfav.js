/* Couleurs favorites : à côté de chaque sélecteur de couleur, ★ = garder la couleur actuelle, ▾ = retrouver ses favorites.
   Elles sont gardées dans le navigateur : elles suivent d'un document à l'autre (et se retrouvent à la réouverture). */
(() => {
  const KEY = "pdm_fav_colors", MAX = 24;
  const load = () => { try { const a = JSON.parse(localStorage.getItem(KEY) || "[]"); return Array.isArray(a) ? a.filter((c) => /^#[0-9a-f]{6}$/.test(c)) : []; } catch (e) { return []; } };
  const save = (a) => { try { localStorage.setItem(KEY, JSON.stringify(a.slice(0, MAX))); } catch (e) {} };
  let pop = null, popFor = null;
  const closePop = () => { if (pop) { pop.remove(); pop = null; popFor = null; } };
  const apply = (input, c) => { input.value = c; input.dispatchEvent(new Event("input", { bubbles: true })); input.dispatchEvent(new Event("change", { bubbles: true })); refreshStars(); };
  function refreshStars() {
    const favs = load();
    document.querySelectorAll(".colfav-star").forEach((b) => {
      const on = favs.includes(b._input.value.toLowerCase());
      const t = on ? "★" : "☆"; if (b.textContent !== t) b.textContent = t; // pas d'écriture inutile : l'observateur ci-dessous ne doit pas se relancer sans fin
      b.classList.toggle("on", on);
      const ti = on ? "Cette couleur est dans tes favorites (clic : la retirer)" : "Mettre cette couleur en favorite"; if (b.title !== ti) b.title = ti;
    });
  }
  function openPop(input, anchor) {
    if (popFor === input) return closePop();
    closePop(); popFor = input;
    pop = document.createElement("div"); pop.className = "colfav-pop";
    const draw = () => {
      pop.textContent = "";
      const favs = load(), head = document.createElement("div"); head.className = "colfav-head"; head.textContent = "Mes couleurs favorites"; pop.append(head);
      if (!favs.length) { const e = document.createElement("div"); e.className = "colfav-empty"; e.textContent = "Aucune pour l'instant : choisis une couleur, puis clique sur ☆."; pop.append(e); return; }
      const grid = document.createElement("div"); grid.className = "colfav-grid";
      favs.forEach((c) => {
        const cell = document.createElement("span"); cell.className = "colfav-cell";
        const b = document.createElement("button"); b.type = "button"; b.className = "sw"; b.style.background = c; b.title = c; b.setAttribute("aria-label", "Couleur " + c);
        b.addEventListener("click", () => { apply(input, c); closePop(); });
        const x = document.createElement("button"); x.type = "button"; x.className = "colfav-x"; x.textContent = "×"; x.title = "Retirer des favorites";
        x.addEventListener("click", (e) => { e.stopPropagation(); save(load().filter((v) => v !== c)); draw(); refreshStars(); });
        cell.append(b, x); grid.append(cell);
      });
      pop.append(grid);
    };
    draw(); document.body.append(pop);
    const r = anchor.getBoundingClientRect(), w = pop.offsetWidth;
    pop.style.left = Math.max(8, Math.min(r.left, innerWidth - w - 8)) + "px"; pop.style.top = Math.min(r.bottom + 6, innerHeight - pop.offsetHeight - 8) + "px";
  }
  function enhance(input) {
    if (input._fav) return; input._fav = true;
    const star = document.createElement("button"), open = document.createElement("button");
    star.type = open.type = "button"; star._input = input;
    star.className = "colfav-btn colfav-star"; open.className = "colfav-btn colfav-open"; open.textContent = "▾"; open.title = "Mes couleurs favorites";
    star.addEventListener("click", () => {
      const c = input.value.toLowerCase(), favs = load();
      save(favs.includes(c) ? favs.filter((v) => v !== c) : [c, ...favs]); refreshStars();
      if (popFor) { const i = popFor; closePop(); openPop(i, open); }
    });
    open.addEventListener("click", (e) => { e.stopPropagation(); openPop(input, open); });
    input.after(star, open);
    input.addEventListener("input", refreshStars); input.addEventListener("change", refreshStars);
  }
  document.addEventListener("click", (e) => { if (pop && !e.target.closest(".colfav-pop")) closePop(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closePop(); });
  window.addEventListener("storage", refreshStars);
  const run = () => { const fresh = [...document.querySelectorAll('input[type="color"]')].filter((i) => !i._fav); if (!fresh.length) return; fresh.forEach(enhance); refreshStars(); };
  run(); new MutationObserver(run).observe(document.body, { childList: true, subtree: true });
  window.pdmFavColors = { load, add: (c) => { save([c.toLowerCase(), ...load().filter((v) => v !== c.toLowerCase())]); refreshStars(); } };
})();
