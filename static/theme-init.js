// Apparence : palettes, accent et couleurs personnalisées.
// Ce fichier est chargé en tout premier (page principale ET page de connexion) pour que les bonnes couleurs
// soient là dès l'affichage, sans clignotement. Il est séparé de la page pour rester compatible avec une
// politique de sécurité stricte (CSP).
//
// Principe : on ne choisit que 4 couleurs de base (fond, surfaces, texte, accent). Les bordures, survols et
// textes discrets sont déduits dans style.css. Les couleurs par défaut (style « Notion ») sont dans style.css.

const PALETTES = {
  notion:  { label: "Notion",  light: { bg: "#f7f6f3", surface: "#ffffff", text: "#37352f" }, dark: { bg: "#191919", surface: "#252525", text: "#e6e6e4" } },
  papier:  { label: "Papier",  light: { bg: "#f3ecda", surface: "#fbf8ef", text: "#43392a" }, dark: { bg: "#1c1913", surface: "#26221a", text: "#eadfc8" } },
  ardoise: { label: "Ardoise", light: { bg: "#eef1f4", surface: "#ffffff", text: "#2a3138" }, dark: { bg: "#13171b", surface: "#1c2127", text: "#e2e6ea" } },
  foret:   { label: "Forêt",   light: { bg: "#eff3ed", surface: "#fcfdfb", text: "#2b392c" }, dark: { bg: "#131913", surface: "#1b221b", text: "#e0e9de" } },
};

function luminance(hex) { // 0 = noir, 1 = blanc
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function contrastOn(hex) { // texte noir ou blanc, selon la luminosité de la couleur
  return luminance(hex) > 0.55 ? "#111111" : "#ffffff";
}
const isHex = (v) => typeof v === "string" && /^#[0-9a-f]{6}$/i.test(v);

function isDarkNow(theme) {
  return theme === "dark" || theme === "black" || (theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
}

// Applique les préférences (theme, palette, accent, bg, surface) à la page
function applyAppearance(p) {
  const root = document.documentElement;
  const theme = ["light", "dark", "black"].includes(p.theme) ? p.theme : "auto";
  if (theme === "auto") delete root.dataset.theme; else root.dataset.theme = theme;
  const dark = isDarkNow(theme);

  const key = PALETTES[p.palette] ? p.palette : "notion";
  const base = (dark ? PALETTES[key].dark : PALETTES[key].light);
  const black = theme === "black"; // « Noir profond » : vrai noir, les palettes ne changent pas ses fonds
  const bg = isHex(p.bg) ? p.bg : (black ? "#000000" : base.bg);
  const surface = isHex(p.surface) ? p.surface : (black ? "#141414" : base.surface);
  const customBase = (!black && key !== "notion") || isHex(p.bg) || isHex(p.surface);

  const set = (k, v) => (v ? root.style.setProperty(k, v) : root.style.removeProperty(k));
  // Palette « Notion » sans personnalisation : on laisse les couleurs de style.css (une seule source)
  set("--bg", customBase ? bg : null);
  set("--surface", customBase ? surface : null);
  set("--text", key !== "notion" ? base.text : null);

  // Accent : celui choisi, sinon la couleur du texte de la palette (monochrome, comme Notion)
  let accent = null;
  if (isHex(p.accent)) accent = p.accent;
  else if (key !== "notion") accent = base.text;
  set("--accent", accent);
  set("--accent-contrast", accent ? contrastOn(accent) : null);

  // Couleur des contours sur la page PDF (toujours blanche) : l'accent s'il est assez foncé, sinon une couleur sûre
  const accentEff = accent || (dark ? "#ebebe9" : "#37352f");
  const sel = luminance(accentEff) <= 0.62 ? accentEff : (dark ? "#e07b39" : "#37352f");
  set("--sel", accent || key !== "notion" ? sel : null);

  // Police, arrondi des coins et CSS personnalisé (mêmes réglages que DeepWell)
  const FONTS = {
    notion: 'ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, "Apple Color Emoji", Arial, sans-serif',
    sans: 'Arial, Helvetica, sans-serif',
    serif: 'Georgia, "Times New Roman", serif',
    mono: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
  };
  set("--font", FONTS[p.font] && p.font !== "notion" ? FONTS[p.font] : null);
  const rad = Number(p.radius);
  set("--radius", p.radius !== null && p.radius !== undefined && p.radius !== "" && rad >= 0 && rad <= 16 ? rad + "px" : null);
  let st = document.getElementById("custom-css");
  if (!st) { st = document.createElement("style"); st.id = "custom-css"; document.head.appendChild(st); }
  st.textContent = typeof p.css === "string" ? p.css : "";
}

try {
  applyAppearance({ theme: "auto", palette: "notion", ...JSON.parse(localStorage.getItem("prefs") || "{}") });
} catch (e) {}
