"""Moteur de texte riche et d'édition du contenu natif d'un PDF.

Deux usages :
  - écrire une zone de texte en annotation (gras, italique, souligné, barré mélangés)
  - lire / réécrire les paragraphes et les images du PDF lui-même

Format du texte riche (le même côté navigateur et côté Python) :
  paras = liste de paragraphes ; un paragraphe = liste de "runs"
  run   = {"t": "texte", "b": 1, "i": 1, "u": 1, "s": 1}   (b, i, u, s facultatifs)
"""
import io
import os
import re
import statistics

import pymupdf

# ---------------------------------------------------------------- polices
# famille -> (normal, gras, italique, gras+italique)
BASE14 = {
    "helv": ("helv", "hebo", "heit", "hebi"),
    "tiro": ("tiro", "tibo", "tiit", "tibi"),
    "cour": ("cour", "cobo", "coit", "cobi"),
}
PS_NAME = {
    "helv": "Helvetica", "hebo": "Helvetica-Bold", "heit": "Helvetica-Oblique", "hebi": "Helvetica-BoldOblique",
    "tiro": "Times-Roman", "tibo": "Times-Bold", "tiit": "Times-Italic", "tibi": "Times-BoldItalic",
    "cour": "Courier", "cobo": "Courier-Bold", "coit": "Courier-Oblique", "cobi": "Courier-BoldOblique",
}
_metric = {}


def metric(key):
    if key not in _metric:
        _metric[key] = pymupdf.Font(key)
    return _metric[key]


class Spec:
    """Une police utilisable : standard (key) ou intégrée au PDF (buf)."""

    def __init__(self, key=None, buf=None, tag=None):
        self.key, self.buf = key, buf
        self.font = pymupdf.Font(fontbuffer=buf) if buf else metric(key)
        self.name = tag if buf else key

    def length(self, text, size):
        if self.buf and " " in text and not self.font.has_glyph(32):  # police réduite aux lettres utilisées : pas d'espace dans le fichier
            return self.font.text_length(text.replace(" ", ""), fontsize=size) + 0.26 * size * text.count(" ")
        return self.font.text_length(text, fontsize=size)

    def has(self, text):
        return all(c.isspace() or self.font.has_glyph(ord(c)) for c in text)


def make_resolver(family, embedded=None, tagprefix="EF"):
    """Choisit la police d'un run : celle d'origine si elle a toutes les lettres, sinon la plus proche."""
    family = family if family in BASE14 else "helv"
    cache = {}

    def resolve(run):
        b, i = bool(run.get("b")), bool(run.get("i"))
        text = run.get("t", "")
        buf = (embedded or {}).get((b, i))
        if buf is not None:
            sp = cache.get(("e", b, i))
            if sp is None:
                try:
                    sp = Spec(buf=buf, tag=f"{tagprefix}{int(b)}{int(i)}")
                except Exception:
                    sp = False
                cache[("e", b, i)] = sp
            if sp and sp.has(text):
                return sp
        key = BASE14[family][int(b) + 2 * int(i)]
        if ("s", key) not in cache:
            cache[("s", key)] = Spec(key=key)
        return cache[("s", key)]

    return resolve


# ---------------------------------------------------------------- mise en page
def normalize_paras(item):
    """Accepte {"paras": [...]} ou {"text": "..."} et renvoie toujours des paragraphes de runs."""
    paras = item.get("paras")
    if not paras:
        paras = [[{"t": line}] for line in str(item.get("text", "")).split("\n")]
    out = []
    for p in paras:
        runs = [{**r, "t": str(r.get("t", ""))} for r in p if isinstance(r, dict)]
        out.append(runs)
    return out


def plain_text(paras):
    return "\n".join("".join(r["t"] for r in p) for p in paras)


def layout(paras, width, size, resolve):
    """Découpe en lignes : chaque ligne = (liste de segments, largeur)."""
    lines = []
    for para in paras:
        toks = []
        for run in para:
            for w in re.findall(r"\s+|\S+", run.get("t", "")):
                toks.append((w, run))
        state = {"cur": [], "w": 0.0}

        def push():
            while state["cur"] and state["cur"][-1][0].isspace():
                state["w"] -= state["cur"][-1][2]
                state["cur"].pop()
            lines.append((state["cur"], state["w"]))
            state["cur"], state["w"] = [], 0.0

        for w, run in toks:
            sp = resolve({**run, "t": w})
            wl = sp.length(w, size)
            if w.isspace():
                if state["cur"]:
                    state["cur"].append((w, run, wl, sp)); state["w"] += wl
                continue
            if state["cur"] and state["w"] + wl > width + 0.01:
                push()
            if wl > width:  # mot plus long que la ligne : on le coupe
                for ch in w:
                    cw = sp.length(ch, size)
                    if state["cur"] and state["w"] + cw > width:
                        push()
                    state["cur"].append((ch, run, cw, sp)); state["w"] += cw
            else:
                state["cur"].append((w, run, wl, sp)); state["w"] += wl
        push()  # un paragraphe vide donne une ligne vide
    return lines


def place(lines, width, size, lh, align, base0):
    """Positions (dans la zone, y vers le bas) des morceaux de texte et des traits."""
    items = []
    for k, (segs, lw) in enumerate(lines):
        y = base0 + k * size * lh
        x = {0: 0.0, 1: (width - lw) / 2, 2: width - lw}.get(align, 0.0)
        merged = []
        for text, run, wl, sp in segs:
            if merged and merged[-1]["run"] is run and merged[-1]["sp"] is sp:
                merged[-1]["t"] += text; merged[-1]["w"] += wl
            else:
                merged.append({"t": text, "run": run, "sp": sp, "w": wl})
        for m in merged:
            if m["t"].strip():
                items.append(("t", x, y, m["t"], m["sp"], size, m["run"].get("c")))
            th = max(0.5, size * 0.06)
            if m["run"].get("u"):
                items.append(("l", x, y + 0.13 * size, x + m["w"], y + 0.13 * size, th, m["run"].get("c")))
            if m["run"].get("s"):
                items.append(("l", x, y - 0.30 * size, x + m["w"], y - 0.30 * size, th, m["run"].get("c")))
            x += m["w"]
    return items


# ---------------------------------------------------------------- annotation FreeText avec apparence maison
def _esc(text):
    b = text.encode("cp1252", "replace")
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def _rgb_str(hexcolor):
    if not isinstance(hexcolor, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", hexcolor):
        return None
    r, g, b = hex_to_rgb(hexcolor)
    return f"{r:.3f} {g:.3f} {b:.3f}"


def ap_stream(items, W, H, color, fill, border_w, pad):
    r, g, b = color
    col = f"{r:.3f} {g:.3f} {b:.3f}"
    out = [b"q"]
    if fill:
        out.append(f"{fill[0]:.3f} {fill[1]:.3f} {fill[2]:.3f} rg 0 0 {W:.3f} {H:.3f} re f".encode())
    if border_w:
        out.append(f"{border_w:.2f} w {col} RG {border_w / 2:.3f} {border_w / 2:.3f} {W - border_w:.3f} {H - border_w:.3f} re S".encode())
    out.append(f"{border_w:.2f} {border_w:.2f} {W - 2 * border_w:.3f} {H - 2 * border_w:.3f} re W n".encode())
    used = set()
    for it in items:
        rc = _rgb_str(it[-1]) or col  # couleur propre au morceau de texte, sinon celle de la zone
        if it[0] == "t":
            _, x, y, text, sp, size, _c = it
            used.add(sp.key)
            out.append(f"BT /F{sp.key} {size:.2f} Tf {rc} rg {x + pad:.2f} {H - y:.2f} Td (".encode() + _esc(text) + b") Tj ET")
        else:
            _, x1, y1, x2, y2, th, _c = it
            out.append(f"{th:.2f} w {rc} RG {x1 + pad:.2f} {H - y1:.2f} m {x2 + pad:.2f} {H - y2:.2f} l S".encode())
    out.append(b"Q")
    return b"\n".join(out), used


def _font_obj(doc, ctx, key):
    fonts = ctx.setdefault("fonts", {})
    if key not in fonts:
        xref = doc.get_new_xref()
        doc.update_object(xref, f"<</Type/Font/Subtype/Type1/BaseFont/{PS_NAME[key]}/Encoding/WinAnsiEncoding>>")
        fonts[key] = xref
    return fonts[key]


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def write_text_annot(doc, page, rect, paras, style, ctx):
    """Crée la zone de texte (FreeText) et remplace son apparence par la nôtre."""
    plain = plain_text(paras)
    size = style["size"]
    a = page.add_freetext_annot(
        rect, plain, fontsize=size, fontname=style["font"],
        text_color=hex_to_rgb(style["color"]),
        fill_color=hex_to_rgb(style["fill"]) if style["fill"] else None,
        border_width=1 if style["border"] else 0, align=style["align"])
    a.set_rect(rect)
    pad, bw = 2.0, (1.0 if style["border"] else 0.0)
    W, H = rect.width, rect.height
    resolve = make_resolver(style["font"])
    lines = layout(paras, W - 2 * pad, size, resolve)
    items = place(lines, W - 2 * pad, size, 1.2, style["align"], pad + 0.946 * size)
    stream, used = ap_stream(items, W, H, hex_to_rgb(style["color"]),
                             hex_to_rgb(style["fill"]) if style["fill"] else None, bw, pad)
    # Attention : MuPDF régénère l'apparence des annotations quand on en ajoute une autre. On ne pose donc
    # la nôtre qu'à la fin, avec finalize_aps(), une fois toutes les annotations créées.
    ctx.setdefault("pending", []).append((a.xref, W, H, stream, used))
    return a


def finalize_aps(doc, ctx):
    for xref, W, H, stream, used in ctx.get("pending", []):
        kind, val = doc.xref_get_key(xref, "AP/N")
        if kind != "xref":
            continue
        n = int(val.split()[0])
        fonts = "".join(f"/F{k} {_font_obj(doc, ctx, k)} 0 R " for k in sorted(used))
        doc.xref_set_key(n, "Resources", f"<</Font<<{fonts}>>>>")
        doc.xref_set_key(n, "BBox", f"[0 0 {W:.3f} {H:.3f}]")
        doc.xref_set_key(n, "Matrix", "[1 0 0 1 0 0]")
        doc.update_stream(n, stream)


# ---------------------------------------------------------------- contenu natif : lecture
MATH_FONT = re.compile(r"^(?:[A-Z]{6}\+)?(CMMI|CMSY|CMEX|MSBM|MSAM|Symbol|.*Math|Wingdings|STIX|LMMath|Cambria Math)", re.I)
SANS_RE = re.compile(r"arial|helvet|calibri|verdana|sans|tahoma|segoe|roboto|open|lato|gothic|cmss|nimbus.?sans", re.I)
SERIF_RE = re.compile(r"times|serif|roman|georgia|garamond|palatino|book|cambria|minion|century|cmr|cmbx|cmti|libertin|charter", re.I)
MONO_RE = re.compile(r"courier|mono|consol|menlo|typewriter|cmtt", re.I)
TEXT_FLAGS = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_IMAGES


def _strip(name):
    return re.sub(r"^[A-Z]{6}\+", "", name or "")


def _norm(name):
    n = re.sub(r"[^a-z0-9]", "", _strip(name).lower())
    return re.sub(r"(regular|roman|normal|bold|italic|oblique|mt|psmt|ps)+$", "", n)


def is_bold(s):
    return bool(s["flags"] & 16 or re.search(r"bold|black|heavy|semibold|cmbx", s["font"], re.I))


def is_italic(s):
    return bool(s["flags"] & 2 or re.search(r"italic|oblique|cmti|cmsl", s["font"], re.I))


def _char_ok(c):
    o = ord(c)
    return c in " \t\n " or 0x20 <= o < 0x180 or c in "–—‘’“”‚„…•€‰′″‐‑"


# Ligatures des polices TeX : codes de contrôle dans le texte extrait (encodages OT1 et T1)
LIGATURES = {0x0b: "ff", 0x0c: "fi", 0x0d: "fl", 0x0e: "ffi", 0x0f: "ffl",
             0x1b: "ff", 0x1c: "fi", 0x1d: "fl", 0x1e: "ffi", 0x1f: "ffl"}


def fix_text(s):
    return s.translate(LIGATURES)


def family_of(span, is_type3):
    n, f = span["font"], span["flags"]
    if MONO_RE.search(n) or f & 8:
        return "cour"
    if SANS_RE.search(n):
        return "helv"
    if SERIF_RE.search(n) or f & 4:
        return "tiro"
    return "tiro" if is_type3 else "helv"


def _merge(runs):
    out = []
    for r in runs:
        if out and all(out[-1].get(k) == r.get(k) for k in ("b", "i", "c")):
            out[-1]["t"] += r["t"]
        else:
            out.append(dict(r))
    return out


def read_blocks(page):
    """Les paragraphes (blocs de texte) de la page, prêts à être modifiés."""
    types = {_strip(f[3]): f[2] for f in page.get_fonts(full=True)}
    types.update({f[4]: f[2] for f in page.get_fonts(full=True)})
    d = page.get_text("dict", flags=TEXT_FLAGS)
    blocks = []
    for b in d["blocks"]:
        if b["type"] != 0 or not b.get("lines"):
            continue
        spans = [s for l in b["lines"] for s in l["spans"] if s["text"].strip()]
        if not spans:
            continue
        x0, y0, x1, y1 = b["bbox"]
        bw = max(x1 - x0, 1)
        dom = max(spans, key=lambda s: len(s["text"].strip()))
        block_color = "#%06x" % dom["color"]
        locked, reason = False, ""
        for s in spans:
            if MATH_FONT.match(s["font"]) or not all(_char_ok(c) for c in fix_text(s["text"])):
                locked, reason = True, "formules ou symboles"
                break
        # Des morceaux posés côte à côte sur la même ligne de base (numéro + titre, par exemple) forment UNE seule
        # ligne visuelle : sinon ils seraient remis l'un sous l'autre à l'édition.
        vlines = []
        for l in b["lines"]:
            if not l["spans"]:
                continue
            oy, sz = l["spans"][0]["origin"][1], max(l["spans"][0]["size"], 1)
            if vlines and abs(vlines[-1]["oy"] - oy) < 0.35 * sz and l["bbox"][0] >= vlines[-1]["bbox"][0] - 1:
                v = vlines[-1]
                v["spans"] = sorted(v["spans"] + l["spans"], key=lambda sp: sp["bbox"][0])
                v["bbox"] = (min(v["bbox"][0], l["bbox"][0]), min(v["bbox"][1], l["bbox"][1]), max(v["bbox"][2], l["bbox"][2]), max(v["bbox"][3], l["bbox"][3]))
            else:
                vlines.append({"spans": list(l["spans"]), "bbox": tuple(l["bbox"]), "oy": oy})
        # lignes -> paragraphes : une ligne nettement plus courte que le bloc termine un paragraphe
        paras, cur = [], []
        for li, line in enumerate(vlines):
            runs, prev = [], None
            for s in line["spans"]:
                if s["text"] == "":
                    continue
                gap = (s["bbox"][0] - prev["bbox"][2]) if prev else 0
                if prev and gap > 1.6 * max(s["size"], 1) * 0.28 and not prev["text"].endswith(" ") and not s["text"].startswith(" "):
                    # grand écart entre deux morceaux (numéro puis titre, tabulation...) : on le garde avec des espaces
                    runs.append({"t": " " * min(40, max(2, round(gap / (max(s["size"], 1) * 0.28)))),
                                 **({"b": 1} if is_bold(s) else {}), **({"i": 1} if is_italic(s) else {})})
                col = "#%06x" % s["color"]
                runs.append({"t": fix_text(s["text"]), **({"b": 1} if is_bold(s) else {}), **({"i": 1} if is_italic(s) else {}),
                             **({"c": col} if col != block_color else {})})  # couleur propre à ce morceau (mot en rouge dans un texte noir…)
                prev = s
            cur.extend(runs)
            last = li == len(vlines) - 1
            short = (x1 - line["bbox"][2]) > 0.12 * bw
            if last or short:
                paras.append(_merge(cur)); cur = []
            elif cur and not cur[-1]["t"].endswith((" ", "-")):
                cur.append({"t": " "})
        for p in paras:
            if p:
                p[0]["t"] = p[0]["t"].lstrip()
                p[-1]["t"] = p[-1]["t"].rstrip()
        origins = [l["oy"] for l in vlines]
        deltas = [origins[k + 1] - origins[k] for k in range(len(origins) - 1) if origins[k + 1] > origins[k]]
        size = round(dom["size"], 1)
        lh = round(min(max(statistics.median(deltas) / size, 1.0), 2.2), 3) if deltas and size else 1.2
        blocks.append({
            "bbox": [x0, y0, x1, y1], "paras": paras, "font": family_of(dom, types.get(dom["font"]) == "Type3"),
            "size": size, "color": "#%06x" % dom["color"], "align": 0, "lh": lh,
            "base0": round(vlines[0]["oy"] - y0, 3), "locked": locked, "reason": reason,
            "oneline": len(vlines) == 1,
        })
    return blocks


def image_usage(doc):
    """Combien de fois chaque image est utilisée dans tout le document (page par page)."""
    usage = {}
    for page in doc:
        for i in page.get_image_info(xrefs=True):
            usage[i["xref"]] = usage.get(i["xref"], 0) + 1
    return usage


def read_images(page, usage=None):
    """Images de la page. kind : « image » (utilisée une seule fois : modifiable à part entière),
    « shared » (même image utilisée à plusieurs endroits) ou « inline » (intégrée dans la page) :
    ces deux-là se déplacent comme un morceau de page, sans toucher aux autres emplacements."""
    pw, ph = page.rect.width, page.rect.height
    infos = page.get_image_info(xrefs=True)
    counts = usage or {}
    if not usage:
        for i in infos:
            counts[i["xref"]] = counts.get(i["xref"], 0) + 1
    out = []
    for i in infos:
        r = pymupdf.Rect(i["bbox"])
        if r.is_empty or r.width * r.height > 0.85 * pw * ph:
            continue  # arrière-plans pleine page : on ne les propose pas
        kind = "inline" if i["xref"] == 0 else ("shared" if counts.get(i["xref"], 1) > 1 else "image")
        out.append({"xref": i["xref"], "bbox": list(r), "kind": kind, "locked": False, "reason": ""})
    return out


# ---------------------------------------------------------------- dessins vectoriels (traits, cadres, tableaux, formes)
def _group_rects(rects, gap):
    """Regroupe les rectangles qui se touchent (ou presque) : une pièce = un ensemble de traits liés."""
    n = len(rects)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    order = sorted(range(n), key=lambda k: rects[k].x0)
    for ai, a in enumerate(order):
        ra = rects[a]
        for b in order[ai + 1:]:
            rb = rects[b]
            if rb.x0 > ra.x1 + gap:
                break
            if rb.y0 <= ra.y1 + gap and rb.y1 >= ra.y0 - gap:
                parent[find(a)] = find(b)
    groups = {}
    for k in range(n):
        groups.setdefault(find(k), []).append(k)
    return list(groups.values())


def read_graphics(page, blocks=None):
    """Les ensembles de traits / cadres / formes de la page, déplaçables comme des morceaux."""
    pw, ph = page.rect.width, page.rect.height
    try:
        drawings = [d for d in page.get_drawings() if d.get("type") in ("f", "s", "fs") and d.get("items")]
    except Exception:
        return []
    if not drawings or len(drawings) > 6000:
        return []
    rects = []
    for d in drawings:
        r = pymupdf.Rect(d["rect"])
        w = d.get("width") or 0
        rects.append(pymupdf.Rect(r.x0 - w / 2, r.y0 - w / 2, r.x1 + w / 2, r.y1 + w / 2))
    text_boxes = [pymupdf.Rect(b["bbox"]) for b in (blocks or [])]
    out = []
    for grp in _group_rects(rects, 3.0):
        r = pymupdf.Rect(rects[grp[0]])
        for k in grp[1:]:
            r |= rects[k]
        area = r.width * r.height
        if r.is_empty and r.width < 0.5 and r.height < 0.5:
            continue
        if area > 0.85 * pw * ph:
            continue  # fond de page
        thin = min(r.width, r.height) < 3.0
        if thin and max(r.width, r.height) < 25:
            continue  # petit trait isolé (point, soulignement court...)
        if thin:  # trait fin : on ignore les soulignements, c'est-à-dire ceux qui longent un bloc de texte
            near = pymupdf.Rect(r.x0 - 2, r.y0 - 3, r.x1 + 2, r.y1 + 3)
            if any(near.intersects(t) and (near & t).width > 0.5 * r.width for t in text_boxes):
                continue
        elif max(r.width, r.height) < 8:
            continue
        out.append({"bbox": [r.x0, r.y0, r.x1, r.y1], "kind": "graphic", "count": len(grp)})
    out.sort(key=lambda g: -((g["bbox"][2] - g["bbox"][0]) * (g["bbox"][3] - g["bbox"][1])))
    return out[:60]


def image_png(doc, xref):
    return _pixmap(doc, xref).tobytes("png")


# ---------------------------------------------------------------- contenu natif : écriture
def _trace_maps(page, rect):
    """Pour chaque style (gras, italique) de la zone : {code Unicode: numéro de glyphe} lu dans le PDF lui-même."""
    maps = {}
    try:
        trace = page.get_texttrace()
    except Exception:
        return maps
    for sp in trace:
        if not pymupdf.Rect(sp["bbox"]).intersects(rect):
            continue
        st = {"flags": sp.get("flags", 0), "font": sp.get("font", "")}
        m = maps.setdefault((is_bold(st), is_italic(st)), {})
        for ch in sp["chars"]:
            if 0 < ch[0] <= 0xFFFF and ch[1] >= 0:
                m[ch[0]] = ch[1]
    return maps


def _with_cmap(buf, charmap):
    """Police réduite d'un PDF (souvent codée par numéros de glyphes, sans table Unicode) + table Unicode reconstruite à partir du texte
    existant : elle devient utilisable pour réécrire du texte avec les mêmes lettres. Renvoie None si ce n'est pas possible."""
    from fontTools.ttLib import TTFont, newTable
    from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
    f = TTFont(io.BytesIO(buf))
    order = f.getGlyphOrder()
    cm = dict(f.getBestCmap() or {}) if "cmap" in f else {}
    for u, g in charmap.items():
        if g < len(order):
            cm[u] = order[g]
    if not cm:
        return None
    st = CmapSubtable.newSubtable(4)
    st.platformID, st.platEncID, st.language, st.cmap = 3, 1, 0, cm
    cmap = newTable("cmap")
    cmap.tableVersion, cmap.tables = 0, [st]
    f["cmap"] = cmap
    out = io.BytesIO()
    f.save(out)
    return out.getvalue()


def collect_embedded(doc, page, rect):
    """Polices réellement intégrées dans le PDF et utilisées dans cette zone : {(gras, italique): octets}."""
    d = page.get_text("dict", clip=rect, flags=TEXT_FLAGS)
    names = {}
    for b in d["blocks"]:
        if b["type"] != 0:
            continue
        for l in b["lines"]:
            for s in l["spans"]:
                names.setdefault((is_bold(s), is_italic(s)), s["font"])
    fonts = page.get_fonts(full=True)
    table = {}
    for f in fonts:
        table[_strip(f[3])] = f
        table[f[4]] = f

    def find(name):
        f = table.get(name) or table.get(_strip(name))
        if f:
            return f
        n = _norm(name)  # "Calibri" (texte) <-> "Calibri Regular" (fichier de police)
        for g in fonts:
            m = _norm(g[3])
            if n and m and (n == m or m.startswith(n) or n.startswith(m)):
                return g
        return None

    out = {}
    for key, name in names.items():
        f = find(name)
        if not f or f[2] == "Type3" or f[1] in ("n/a", ""):
            continue
        try:
            buf = doc.extract_font(f[0])[3]
        except Exception:
            continue
        if buf and len(buf) < 2_500_000:  # une police entière alourdirait trop le fichier
            out[key] = bytes(buf)
    if out:
        maps = _trace_maps(page, rect)
        for key in list(out):
            cm = maps.get(key)
            try:
                probe = pymupdf.Font(fontbuffer=out[key])
                if cm and not all(probe.has_glyph(u) for u in cm):
                    patched = _with_cmap(out[key], cm)
                    if patched and all(pymupdf.Font(fontbuffer=patched).has_glyph(u) for u in cm):
                        out[key] = patched
                    else:
                        del out[key]
                elif not cm and not probe.has_glyph(ord("e")):
                    del out[key]
            except Exception:
                out.pop(key, None)
    return out


def _run_color(rc, default):
    if isinstance(rc, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", rc):
        return hex_to_rgb(rc)
    return default


def _consistent_fonts(embedded, paras):
    """Garde une police d'origine seulement si elle a TOUTES les lettres du texte de ce style (gras / italique) :
    sinon une même ligne mélangerait deux polices différentes ; on prend alors la police standard pour ce style."""
    if not embedded:
        return embedded
    need = {}
    for p in paras:
        for r in p:
            key = (bool(r.get("b")), bool(r.get("i")))
            need[key] = need.get(key, "") + r.get("t", "")
    out = {}
    for key, buf in embedded.items():
        try:
            f = pymupdf.Font(fontbuffer=buf)
        except Exception:
            continue
        if all(c.isspace() or f.has_glyph(ord(c)) for c in need.get(key, "")):
            out[key] = buf
    return out


def write_block(page, n, embedded, report):
    rect = pymupdf.Rect(n["bbox"])
    size = min(max(float(n.get("size", 12)), 4), 200)
    family = n.get("font") if n.get("font") in BASE14 else "helv"
    color = hex_to_rgb(n.get("color") or "#000000")
    paras = normalize_paras(n)
    report["blocks"] = report.get("blocks", 0) + 1
    tag = f"EF{report['blocks']}_"
    embedded = _consistent_fonts(embedded, paras)
    resolve = make_resolver(family, embedded, tag)
    # Un bloc qui n'avait qu'une ligne (titre, numéro + titre...) ne passe jamais à la ligne : la police de
    # remplacement est souvent un peu plus large, et le texte déborderait sinon sur une 2e ligne.
    wrap_w = 100000.0 if n.get("nowrap") else max(rect.width, 5)
    lines = layout(paras, wrap_w, size, resolve)
    items = place(lines, max(rect.width, 5) if n.get("nowrap") else wrap_w, size, float(n.get("lh", 1.2)), n.get("align", 0), float(n.get("base0", size)))
    inserted = set()
    used_original = False
    for it in items:
        if it[0] == "t":
            _, x, y, text, sp, sz, rc = it
            if sp.buf and sp.name not in inserted:
                page.insert_font(fontname=sp.name, fontbuffer=sp.buf)
                inserted.add(sp.name)
            used_original = used_original or bool(sp.buf)
            page.insert_text((rect.x0 + x, rect.y0 + y), text, fontname=sp.name, fontsize=sz, color=_run_color(rc, color))
        else:
            _, x1, y1, x2, y2, th, rc = it
            page.draw_line((rect.x0 + x1, rect.y0 + y1), (rect.x0 + x2, rect.y0 + y2), color=_run_color(rc, color), width=th)
    if used_original:
        report["original_font"] = report.get("original_font", 0) + 1


PIECE_KINDS = ("shared", "inline", "text", "graphic")


def _redraw(page, src_page, orig, new):
    """Redessine les traits / formes de `orig` (page d'origine) à la position `new` (déplacement + échelle)."""
    sx = new.width / orig.width if orig.width else 1.0
    sy = new.height / orig.height if orig.height else 1.0
    area = pymupdf.Rect(orig.x0 - 1.5, orig.y0 - 1.5, orig.x1 + 1.5, orig.y1 + 1.5)

    def pt(p):
        return pymupdf.Point(new.x0 + (p.x - orig.x0) * sx, new.y0 + (p.y - orig.y0) * sy)

    def rc(r):
        a, b = pt(pymupdf.Point(r.x0, r.y0)), pt(pymupdf.Point(r.x1, r.y1))
        return pymupdf.Rect(a, b)

    count = 0
    for d in src_page.get_drawings():
        if d.get("type") not in ("f", "s", "fs") or not d.get("items") or pymupdf.Rect(d["rect"]) not in area:
            continue
        shape = page.new_shape()
        try:
            for it in d["items"]:
                k = it[0]
                if k == "l":
                    shape.draw_line(pt(it[1]), pt(it[2]))
                elif k == "re":
                    shape.draw_rect(rc(it[1]))
                elif k == "qu":
                    q = it[1]
                    shape.draw_quad(pymupdf.Quad(pt(q.ul), pt(q.ur), pt(q.ll), pt(q.lr)))
                elif k == "c":
                    shape.draw_bezier(pt(it[1]), pt(it[2]), pt(it[3]), pt(it[4]))
            cap = d.get("lineCap")
            kw = dict(color=d.get("color"), fill=d.get("fill"), width=(d.get("width") or 1) * min(sx, sy),
                      closePath=bool(d.get("closePath")), even_odd=bool(d.get("even_odd")),
                      lineCap=int(cap[0]) if isinstance(cap, (tuple, list)) and cap else 0,
                      lineJoin=int(d.get("lineJoin") or 0))
            if d.get("dashes") and d["dashes"] not in ("[] 0", "[] 0.0"):
                kw["dashes"] = d["dashes"]
            if d.get("stroke_opacity") is not None:
                kw["stroke_opacity"] = d["stroke_opacity"]
            if d.get("fill_opacity") is not None:
                kw["fill_opacity"] = d["fill_opacity"]
            if d["type"] == "f":
                kw["color"] = None
            if d["type"] == "s":
                kw["fill"] = None
            shape.finish(**kw)
            shape.commit()
            count += 1
        except Exception:
            continue
    return count


def clip_png(pdf_bytes, pno, kind, bbox, dpi=170):
    """Aperçu (PNG) d'un morceau de page : pour montrer le contenu pendant qu'on le déplace."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        src = doc[pno - 1]
        r = pymupdf.Rect(bbox)
        if kind == "graphic":  # seulement les traits, sans le texte qui se trouve dedans
            tmp = pymupdf.open()
            page = tmp.new_page(width=src.rect.width, height=src.rect.height)
            _redraw(page, src, r, r)
            pix = page.get_pixmap(clip=r, dpi=dpi, alpha=True)
            tmp.close()
        elif kind == "graphic_rest":  # ce qui reste à l'endroit d'origine quand on enlève les traits (texte, images)
            src.add_redact_annot(pymupdf.Rect(r.x0 - 1.5, r.y0 - 1.5, r.x1 + 1.5, r.y1 + 1.5), fill=False)
            src.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED, text=pymupdf.PDF_REDACT_TEXT_NONE)
            pix = src.get_pixmap(clip=r, dpi=dpi, alpha=False)
        else:
            pix = src.get_pixmap(clip=r, dpi=dpi, alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()


def apply_native(doc, natives, nimages):
    """Applique les modifications du contenu natif. Renvoie un petit rapport."""
    report = {}
    src = None
    if any(im.get("kind") in PIECE_KINDS and (im.get("changed", True) or im.get("deleted")) for im in nimages):
        src = pymupdf.open(stream=doc.tobytes(), filetype="pdf")  # le PDF d'origine, intact, pour recopier les morceaux
    pages = {}
    for n in natives:
        pages.setdefault(int(n["page"]), {"t": [], "i": []})["t"].append(n)
    for im in nimages:
        pages.setdefault(int(im["page"]), {"t": [], "i": []})["i"].append(im)
    for pno, items in pages.items():
        if not 1 <= pno <= len(doc):
            continue
        page = doc[pno - 1]
        pieces = [im for im in items["i"] if im.get("kind") in PIECE_KINDS]
        items["i"] = [im for im in items["i"] if im.get("kind") not in PIECE_KINDS]
        # 1. on garde les images à déplacer AVANT de les effacer
        kept = []
        for im in items["i"]:
            if not im.get("deleted"):
                try:
                    kept.append((im, _pixmap(doc, int(im["xref"]))))
                except Exception:
                    report["errors"] = report.get("errors", 0) + 1
        # 2. Polices : on utilise toujours la police standard la plus proche (Helvetica, Times, Courier).
        #    Polices : on réutilise celles du PDF quand elles contiennent toutes les lettres du texte (même rendu qu'à l'origine) ;
        #    sinon (police absente ou réduite aux lettres déjà utilisées) la standard la plus proche. PDM_ORIGINAL_FONTS=0 désactive.
        use_orig = os.environ.get("PDM_ORIGINAL_FONTS", "1") != "0"
        prepared = []
        for n in items["t"]:
            emb = {}
            if use_orig and not n.get("deleted"):
                try:
                    emb = collect_embedded(doc, page, pymupdf.Rect(n["orig"]))
                except Exception:
                    emb = {}
            prepared.append((n, emb))
        # 3. on efface le texte d'origine
        for n in items["t"]:
            r = pymupdf.Rect(n["orig"])
            r = pymupdf.Rect(r.x0 + 0.3, r.y0 + 0.8, r.x1 - 0.3, r.y1 - 0.8)
            if not r.is_empty:
                page.add_redact_annot(r, fill=False)
        if items["t"]:
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        # 3bis. on efface l'original des morceaux de page (sans toucher aux autres emplacements ni au texte voisin)
        if src is not None and pieces:
            for flags, kinds in (
                (dict(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED, text=pymupdf.PDF_REDACT_TEXT_REMOVE), ("text",)),
                (dict(images=pymupdf.PDF_REDACT_IMAGE_REMOVE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE, text=pymupdf.PDF_REDACT_TEXT_NONE), ("shared", "inline")),
                (dict(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED, text=pymupdf.PDF_REDACT_TEXT_NONE), ("graphic",)),
            ):
                group = [pc for pc in pieces if pc.get("kind") in kinds]
                for pc in group:
                    o = pymupdf.Rect(pc["orig"])
                    if pc["kind"] == "text":
                        o = pymupdf.Rect(o.x0 + 0.3, o.y0 + 0.8, o.x1 - 0.3, o.y1 - 0.8)
                    elif pc["kind"] == "graphic":
                        o = pymupdf.Rect(o.x0 - 1.5, o.y0 - 1.5, o.x1 + 1.5, o.y1 + 1.5)
                    else:
                        o = pymupdf.Rect(o.x0 + 0.5, o.y0 + 0.5, o.x1 - 0.5, o.y1 - 0.5)
                    if not o.is_empty:
                        page.add_redact_annot(o, fill=False)
                if group:
                    page.apply_redactions(**flags)
        # 4. on efface les images modifiées
        for im in items["i"]:
            page.delete_image(int(im["xref"]))
        # 5. on écrit les nouveaux textes
        for n, emb in prepared:
            if not n.get("deleted"):
                write_block(page, n, emb, report)
        # 6. on remet les images à leur nouvelle place
        for im, pix in kept:
            page.insert_image(pymupdf.Rect(im["bbox"]), pixmap=pix, keep_proportion=False)
        # 7. on recopie les morceaux de page à leur nouvelle place
        for pc in pieces:
            if pc.get("deleted") or src is None:
                continue
            orig, new = pymupdf.Rect(pc["orig"]), pymupdf.Rect(pc["bbox"])
            try:
                if pc["kind"] == "text":
                    page.show_pdf_page(new, src, pno - 1, clip=orig)  # copie vectorielle : reste nette
                elif pc["kind"] == "graphic":
                    _redraw(page, src[pno - 1], orig, new)
                else:
                    pix = None
                    if int(pc.get("xref") or 0) > 0:
                        try:
                            pix = _pixmap(doc, int(pc["xref"]))
                        except Exception:
                            pix = None
                    if pix is None:
                        pix = src[pno - 1].get_pixmap(clip=orig, dpi=300)
                    page.insert_image(new, pixmap=pix, keep_proportion=False)
            except Exception:
                report["errors"] = report.get("errors", 0) + 1
        report["images"] = report.get("images", 0) + len(items["i"]) + len(pieces)
    if src is not None:
        src.close()
    return report


def _pixmap(doc, xref):
    pix = pymupdf.Pixmap(doc, xref)
    ex = doc.extract_image(xref)
    if ex and ex.get("smask"):
        pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(doc, ex["smask"]))
    elif pix.colorspace and pix.colorspace.n > 3:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    return pix
