"""Documents texte (façon Word / Google Docs) : nettoyage du HTML, export PDF et Word, import Word.

Un document texte est un fichier « NOM.pdmdoc » (du HTML simplifié) rangé dans Mes documents, comme un PDF.
Rien ici ne dépend de Flask : app.py s'occupe des adresses (routes) et des dossiers.
"""
import base64
import io
import re
from html.parser import HTMLParser

import pymupdf

# ------------------------------------------------------------------ Nettoyage (liste blanche) : ce qui n'est pas prévu est retiré
TAGS = {"p", "br", "h1", "h2", "h3", "strong", "b", "em", "i", "u", "s", "strike", "sub", "sup", "ul", "ol", "li", "a", "img", "table",
        "thead", "tbody", "tr", "td", "th", "hr", "blockquote", "span", "div", "pre", "code", "colgroup", "col"}
VOID = {"br", "img", "hr", "col"}
STYLE_OK = {"color", "background-color", "text-align", "font-size", "font-family", "font-weight", "font-style", "text-decoration",
            "width", "height", "margin-left", "line-height", "vertical-align"}
VAL = re.compile(r"^[\w\s#%.,'\"()+-]{1,80}$")      # pas de « ; » « : » « / » « url( » dans une valeur
IMG_SRC = re.compile(r"^data:image/(png|jpeg|gif|webp);base64,[A-Za-z0-9+/=]+$")


def _clean_style(style):
    out = []
    for part in (style or "").split(";"):
        if ":" not in part:
            continue
        k, v = (x.strip() for x in part.split(":", 1))
        if k.lower() in STYLE_OK and VAL.match(v) and "url(" not in v.lower() and "expression" not in v.lower():
            out.append(f"{k.lower()}:{v}")
    return ";".join(out)


class _Clean(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "iframe", "object", "embed", "svg", "math", "form", "textarea", "select", "button", "input"):
            self.skip += 1
            return
        if self.skip or tag not in TAGS:
            return
        a = dict(attrs)
        keep = []
        st = _clean_style(a.get("style"))
        if st:
            keep.append(f'style="{st}"')
        if tag == "a":
            href = (a.get("href") or "").strip()
            if re.match(r"^(https?://|mailto:)", href, re.I):
                keep.append(f'href="{_esc(href)}" target="_blank" rel="noopener noreferrer"')
        elif tag == "img":
            src = (a.get("src") or "").strip()
            if not IMG_SRC.match(src):
                return
            keep.append(f'src="{src}"')
            if a.get("alt"):
                keep.append(f'alt="{_esc(a["alt"][:200])}"')
        elif tag in ("td", "th"):
            for k in ("colspan", "rowspan"):
                if (a.get(k) or "").isdigit() and 1 <= int(a[k]) <= 50:
                    keep.append(f'{k}="{a[k]}"')
        elif tag == "ol" and (a.get("start") or "").isdigit():
            keep.append(f'start="{int(a["start"])}"')
        self.out.append(f"<{tag}{(' ' + ' '.join(keep)) if keep else ''}>")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "iframe", "object", "embed", "svg", "math", "form", "textarea", "select", "button", "input"):
            self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in TAGS and tag not in VOID:
            self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(_esc(data))


def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def sanitize_html(html):
    p = _Clean()
    p.feed(str(html or "")[:30_000_000])
    p.close()
    return "".join(p.out)


# ------------------------------------------------------------------ Export PDF (PyMuPDF Story)
CSS = """
body { font-family: sans-serif; font-size: 11pt; line-height: 1.4; }
h1 { font-size: 22pt; margin: 14pt 0 6pt; } h2 { font-size: 16pt; margin: 12pt 0 5pt; } h3 { font-size: 13pt; margin: 10pt 0 4pt; }
p { margin: 0 0 7pt; } blockquote { margin: 6pt 0 6pt 14pt; color: #555; } pre, code { font-family: monospace; }
table { border-collapse: collapse; } td, th { border: 1px solid #999; padding: 3pt 5pt; } th { background-color: #eee; }
a { color: #1a56c4; } hr { border: 0; border-top: 1px solid #999; }
"""


def html_to_pdf(html, title=""):
    images = pymupdf.Archive()
    n = [0]

    def keep_img(m):  # Story lit les images dans une « archive » : les images intégrées y sont déposées
        n[0] += 1
        name = f"img{n[0]}.{'jpg' if m.group(1) == 'jpeg' else m.group(1)}"
        images.add(base64.b64decode(m.group(2)), name)
        return f'src="{name}"'

    body = re.sub(r'src="data:image/(\w+);base64,([^"]+)"', keep_img, sanitize_html(html))
    story = pymupdf.Story(html=f"<html><body>{body or '<p></p>'}</body></html>", user_css=CSS, archive=images)
    buf = io.BytesIO()
    writer = pymupdf.DocumentWriter(buf)
    media = pymupdf.paper_rect("a4")
    where = media + (56, 56, -56, -56)
    more = 1
    while more:
        dev = writer.begin_page(media)
        more, _ = story.place(where)
        story.draw(dev)
        writer.end_page()
    writer.close()
    doc = pymupdf.open("pdf", buf.getvalue())
    if title:
        doc.set_metadata({"title": title})
    out = doc.tobytes(garbage=3, deflate=True)
    doc.close()
    return out


def pdf_first_page_png(pdf_bytes, width=360):
    doc = pymupdf.open("pdf", pdf_bytes)
    try:
        page = doc[0]
        z = width / page.rect.width
        return page.get_pixmap(matrix=pymupdf.Matrix(z, z), alpha=False).tobytes("png")
    finally:
        doc.close()


# ------------------------------------------------------------------ Export Word (.docx)
def _rgb(css):
    css = (css or "").strip().lower()
    m = re.match(r"^#([0-9a-f]{6})$", css) or re.match(r"^#([0-9a-f])([0-9a-f])([0-9a-f])$", css)
    if m:
        g = m.groups()
        return "".join(g) if len(g) == 1 else "".join(c * 2 for c in g)
    m = re.match(r"^rgba?\((\d+),\s*(\d+),\s*(\d+)", css)
    return "%02x%02x%02x" % tuple(min(255, int(x)) for x in m.groups()) if m else None


def _styles(attrs):
    st = {}
    for part in (dict(attrs).get("style") or "").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            st[k.strip()] = v.strip()
    return st


def html_to_docx(html):
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    doc = Document()
    ALIGN = {"left": WD_ALIGN_PARAGRAPH.LEFT, "center": WD_ALIGN_PARAGRAPH.CENTER, "right": WD_ALIGN_PARAGRAPH.RIGHT, "justify": WD_ALIGN_PARAGRAPH.JUSTIFY}

    class B(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.par = None          # paragraphe en cours
            self.fmt = []            # pile de mises en forme
            self.lists = []          # pile ('ul'|'ol')
            self.tables = []         # pile de {"t": table, "row": n, "col": n}
            self.cell = None

        # ---- utilitaires
        def container(self):
            return self.cell if self.cell is not None else doc

        def new_par(self, style=None, align=None):
            p = self.container().add_paragraph(style=style)
            if align in ALIGN:
                p.alignment = ALIGN[align]
            self.par = p
            return p

        def cur(self):
            return self.par or self.new_par()

        def cur_fmt(self):
            f = {}
            for x in self.fmt:
                f.update(x)
            return f

        def handle_starttag(self, tag, attrs):
            a, st = dict(attrs), _styles(attrs)
            if getattr(self, "in_cell", False) and tag in ("p", "div", "blockquote", "pre", "h1", "h2", "h3", "li"):
                self.fmt.append({"bold": True} if tag in ("h1", "h2", "h3") else {})
            elif tag in ("p", "div", "blockquote", "pre"):
                self.new_par(align=st.get("text-align"))
                self.fmt.append({})
            elif tag in ("h1", "h2", "h3"):
                self.new_par(style=f"Heading {tag[1]}", align=st.get("text-align"))
                self.fmt.append({})
            elif tag in ("ul", "ol"):
                self.lists.append(tag)
                self.par = None
            elif tag == "li":
                kind = "List Bullet" if (self.lists[-1:] or ["ul"])[0] == "ul" else "List Number"
                depth = max(0, len(self.lists) - 1)
                self.new_par(style=kind if depth == 0 else f"{kind} {min(depth + 1, 3)}", align=st.get("text-align"))
                self.fmt.append({})
            elif tag == "br":
                self.cur().add_run().add_break()
            elif tag == "hr":
                p = self.new_par()
                b = OxmlElement("w:pBdr")
                bottom = OxmlElement("w:bottom")
                for k, v in (("w:val", "single"), ("w:sz", "6"), ("w:space", "1"), ("w:color", "999999")):
                    bottom.set(qn(k), v)
                b.append(bottom)
                p._p.get_or_add_pPr().append(b)
                self.par = None
            elif tag == "table":
                self.tables.append({"t": None, "r": -1, "c": -1, "rows": []})
                self.tbl_rows = []
            elif tag == "tr":
                self.tables[-1]["r"] += 1
                self.tables[-1]["c"] = -1
                self.tables[-1]["rows"].append([])
            elif tag in ("td", "th"):
                self.tables[-1]["rows"][-1].append({"parts": [], "bold": tag == "th"})
                self.tables[-1]["c"] += 1
                self.cell_buf = self.tables[-1]["rows"][-1][-1]
                self.cell_buf["_events"] = []
                self.in_cell = True
            elif tag == "img" and a.get("src", "").startswith("data:image"):
                data = base64.b64decode(a["src"].split(",", 1)[1])
                if getattr(self, "in_cell", False):
                    self.cell_buf["_events"].append(("img", data))
                else:
                    try:
                        from docx.shared import Cm
                        self.cur().add_run().add_picture(io.BytesIO(data), width=Cm(12))
                    except Exception:
                        pass
            elif tag == "a":
                self.fmt.append({"link": a.get("href", ""), "color": "1a56c4", "underline": True})
            else:
                f = {}
                if tag in ("strong", "b"):
                    f["bold"] = True
                if tag in ("em", "i"):
                    f["italic"] = True
                if tag == "u":
                    f["underline"] = True
                if tag in ("s", "strike"):
                    f["strike"] = True
                if tag == "sub":
                    f["sub"] = True
                if tag == "sup":
                    f["sup"] = True
                if tag in ("code", "pre"):
                    f["mono"] = True
                self.fmt.append(f)
            if tag in ("span", "p", "div", "h1", "h2", "h3", "li", "td", "th", "strong", "b", "em", "i", "u", "s", "strike", "sub", "sup", "a", "code", "blockquote"):
                f = self.fmt[-1] if self.fmt else {}
                if st.get("color") and _rgb(st["color"]):
                    f["color"] = _rgb(st["color"])
                if st.get("background-color") and _rgb(st["background-color"]):
                    f["shade"] = _rgb(st["background-color"])
                if st.get("font-weight") in ("bold", "700", "600"):
                    f["bold"] = True
                if st.get("font-style") == "italic":
                    f["italic"] = True
                if "underline" in st.get("text-decoration", ""):
                    f["underline"] = True
                m = re.match(r"^(\d+(?:\.\d+)?)(pt|px)$", st.get("font-size", ""))
                if m:
                    f["size"] = float(m.group(1)) * (0.75 if m.group(2) == "px" else 1)
                if st.get("font-family"):
                    f["font"] = st["font-family"].split(",")[0].strip(" '\"")

        def handle_endtag(self, tag):
            if tag in ("ul", "ol"):
                if self.lists:
                    self.lists.pop()
                self.par = None
                return
            if tag == "table":
                self.flush_table()
                return
            if tag in ("td", "th"):
                self.in_cell = False
                if self.fmt:
                    self.fmt.pop()
                return
            if tag in ("tr", "hr", "br", "img", "thead", "tbody", "colgroup", "col"):
                return
            if self.fmt and tag in ("p", "div", "blockquote", "pre", "h1", "h2", "h3", "li", "span", "strong", "b", "em", "i", "u", "s", "strike", "sub", "sup", "a", "code"):
                self.fmt.pop()
            if tag in ("p", "div", "blockquote", "pre", "h1", "h2", "h3", "li") and not getattr(self, "in_cell", False):
                self.par = None

        def handle_data(self, data):
            if getattr(self, "in_cell", False):
                self.cell_buf["_events"].append(("text", data, self.cur_fmt()))
                return
            if not data.strip() and self.par is None:
                return
            self.run(self.cur(), data, self.cur_fmt())

        def run(self, p, text, f):
            r = p.add_run(text)
            r.bold = f.get("bold") or None
            r.italic = f.get("italic") or None
            r.underline = f.get("underline") or None
            r.font.strike = f.get("strike") or None
            r.font.subscript = f.get("sub") or None
            r.font.superscript = f.get("sup") or None
            if f.get("color"):
                r.font.color.rgb = RGBColor.from_string(f["color"].upper())
            if f.get("size"):
                r.font.size = Pt(f["size"])
            if f.get("font") or f.get("mono"):
                r.font.name = f.get("font") or "Courier New"
            if f.get("shade"):
                shd = OxmlElement("w:shd")
                shd.set(qn("w:val"), "clear")
                shd.set(qn("w:fill"), f["shade"].upper())
                r._r.get_or_add_rPr().append(shd)

        def flush_table(self):
            t = self.tables.pop()
            rows = t["rows"]
            if not rows:
                return
            ncol = max(len(r) for r in rows)
            table = self.container().add_table(rows=len(rows), cols=max(1, ncol))
            table.style = "Table Grid"
            for i, r in enumerate(rows):
                for j, c in enumerate(r):
                    cell = table.cell(i, j)
                    p = cell.paragraphs[0]
                    for ev in c.get("_events", []):
                        if ev[0] == "text":
                            f = dict(ev[2])
                            if c["bold"]:
                                f["bold"] = True
                            self.run(p, ev[1], f)
                        elif ev[0] == "img":
                            try:
                                from docx.shared import Cm
                                p.add_run().add_picture(io.BytesIO(ev[1]), width=Cm(5))
                            except Exception:
                                pass
            self.par = None

    b = B()
    b.feed(sanitize_html(html))
    b.close()
    out = io.BytesIO()
    doc.save(out)
    return out.getvalue()


# ------------------------------------------------------------------ Import Word (.docx)
def docx_to_html(data):
    import mammoth
    res = mammoth.convert_to_html(io.BytesIO(data))
    return sanitize_html(res.value)
