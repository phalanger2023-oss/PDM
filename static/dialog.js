/* Petites fenêtres de PDM, à la place des boîtes du navigateur (prompt / confirm).
   askText({ title, label, value, multiline, ok, placeholder }) -> Promise<string|null>
   askConfirm({ title, message, ok, danger }) -> Promise<boolean> */
(function () {
  function build(title) {
    const back = document.createElement("div");
    back.className = "dlg-back";
    const box = document.createElement("div");
    box.className = "dlg";
    box.setAttribute("role", "dialog");
    box.setAttribute("aria-modal", "true");
    const h = document.createElement("div");
    h.className = "dlg-title";
    h.textContent = title || "";
    box.appendChild(h);
    back.appendChild(box);
    return { back, box };
  }
  function open(title, fill) {
    return new Promise((resolve) => {
      const { back, box } = build(title);
      const prevFocus = document.activeElement;
      const close = (v) => { back.remove(); document.removeEventListener("keydown", onKey, true); if (prevFocus && prevFocus.focus) { try { prevFocus.focus({ preventScroll: true }); } catch (e) {} } resolve(v); };
      let getValue = () => true;
      const onKey = (e) => {
        if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(null); }
        else if (e.key === "Enter" && !(e.target.tagName === "TEXTAREA" && !e.ctrlKey) && e.target.tagName !== "BUTTON") { e.preventDefault(); e.stopPropagation(); close(getValue()); }
      };
      const api = { box, close, setValue: (fn) => { getValue = fn; } };
      fill(api);
      document.addEventListener("keydown", onKey, true);
      back.addEventListener("mousedown", (e) => { if (e.target === back) close(null); });
      document.body.appendChild(back);
      const f = box.querySelector("input, textarea, .dlg-ok");
      if (f) { f.focus({ preventScroll: true }); if (f.select && f.tagName !== "BUTTON") f.select(); }
    });
  }
  function buttons(api, okLabel, danger, cancelLabel) {
    const row = document.createElement("div");
    row.className = "dlg-btns";
    const no = document.createElement("button");
    no.type = "button"; no.className = "dlg-cancel"; no.textContent = cancelLabel || "Annuler";
    no.addEventListener("click", () => api.close(null));
    const ok = document.createElement("button");
    ok.type = "button"; ok.className = "dlg-ok" + (danger ? " danger" : ""); ok.textContent = okLabel || "OK";
    ok.addEventListener("click", () => api.close(api.get()));
    row.append(no, ok);
    api.box.appendChild(row);
  }
  window.askText = function ({ title, label, value = "", multiline = false, ok = "OK", placeholder = "" } = {}) {
    return open(title, (api) => {
      if (label) { const l = document.createElement("div"); l.className = "dlg-label"; l.textContent = label; api.box.appendChild(l); }
      const inp = document.createElement(multiline ? "textarea" : "input");
      if (!multiline) inp.type = "text";
      inp.className = "dlg-input"; inp.value = value; inp.placeholder = placeholder;
      if (multiline) inp.rows = 4;
      inp.spellcheck = true; inp.lang = "fr";
      api.box.appendChild(inp);
      api.get = () => inp.value; api.setValue(api.get);
      buttons(api, ok);
    });
  };
  window.askConfirm = function ({ title = "Confirmer", message = "", ok = "OK", danger = false } = {}) {
    return open(title, (api) => {
      const m = document.createElement("div");
      m.className = "dlg-msg"; m.textContent = message;
      api.box.appendChild(m);
      api.get = () => true; api.setValue(api.get);
      buttons(api, ok, danger);
    }).then((v) => v === true);
  };
})();
