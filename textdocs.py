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
def _docx_run_html(run, W):
    """Un morceau de texte Word -> HTML avec sa mise en forme (gras, italique, souligné, barré, couleur, taille, police, surlignage)."""
    t = _esc(run.text or "").replace("\t", "&emsp;")
    if not t:
        return ""
    f, css = run.font, []
    try:
        if f.color is not None and f.color.type is not None and f.color.rgb is not None and str(f.color.rgb) not in ("000000", "auto"):
            css.append(f"color:#{f.color.rgb}")
    except Exception:
        pass
    if f.size:
        css.append(f"font-size:{round(f.size.pt)}pt")
    if f.name and re.fullmatch(r"[\w .-]{2,40}", f.name):
        css.append(f"font-family:{f.name}")
    try:
        hl = {"YELLOW": "#ffff00", "BRIGHT_GREEN": "#00ff00", "TURQUOISE": "#00ffff", "PINK": "#ff00ff", "BLUE": "#0000ff", "RED": "#ff0000",
              "GRAY_25": "#c0c0c0", "GRAY_50": "#808080", "DARK_YELLOW": "#808000", "GREEN": "#008000"}.get(f.highlight_color.name) if f.highlight_color else None
    except Exception:
        hl = None
    if hl:
        css.append(f"background-color:{hl}")
    if css:
        t = f'<span style="{";".join(css)}">{t}</span>'
    if f.bold:
        t = f"<strong>{t}</strong>"
    if f.italic:
        t = f"<em>{t}</em>"
    if f.underline:
        t = f"<u>{t}</u>"
    if f.strike:
        t = f"<s>{t}</s>"
    if f.subscript:
        t = f"<sub>{t}</sub>"
    if f.superscript:
        t = f"<sup>{t}</sup>"
    return t


def _docx_images(par, doc):
    """Images en ligne d'un paragraphe Word, en data:image."""
    out = []
    for blip in par._p.xpath(".//a:blip"):
        rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
        try:
            part = doc.part.related_parts[rid]
            ct = part.content_type
            if ct in ("image/png", "image/jpeg", "image/gif", "image/webp"):
                out.append(f'<img src="data:{ct};base64,{base64.b64encode(part.blob).decode()}">')
        except Exception:
            pass
    return "".join(out)


def docx_to_html(data):
    """Word -> HTML : titres, listes, tableaux, images, alignement, couleurs, tailles, polices.
    Si le fichier résiste à notre lecture, on retombe sur mammoth (plus simple, moins fidèle)."""
    try:
        return sanitize_html(_docx_to_html_rich(data))
    except Exception:
        import mammoth
        return sanitize_html(mammoth.convert_to_html(io.BytesIO(data)).value)


def _docx_to_html_rich(data):
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(io.BytesIO(data))
    ALIGN = {0: "left", 1: "center", 2: "right", 3: "justify"}

    def para_html(par):
        name = (par.style.name or "") if par.style is not None else ""
        inner = "".join(_docx_run_html(r, doc) for r in par.runs) + _docx_images(par, doc)
        for h in par._p.xpath(".//w:hyperlink"):   # liens : le texte est dans le lien, pas dans par.runs
            href = None
            try:
                href = doc.part.rels[h.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")].target_ref
            except Exception:
                pass
            txt = "".join(t.text or "" for t in h.xpath(".//w:t"))
            if txt:
                inner += f'<a href="{_esc(href)}">{_esc(txt)}</a>' if href and re.match(r"https?://", href) else _esc(txt)
        return name, inner

    def para_style(par):
        css = []
        al = par.alignment
        if al is not None and int(al) in ALIGN and int(al) != 0:
            css.append(f"text-align:{ALIGN[int(al)]}")
        ind = par.paragraph_format.left_indent
        if ind and ind.pt > 0:
            css.append(f"margin-left:{min(round(ind.pt), 200)}px")
        return f' style="{";".join(css)}"' if css else ""

    def table_html(tb):
        rows = []
        for r in tb.rows:
            cells, seen = [], set()
            for c in r.cells:
                if id(c._tc) in seen:   # cellule fusionnée : déjà vue
                    continue
                seen.add(id(c._tc))
                span = getattr(c._tc, "grid_span", 1) or 1
                cells.append(f'<td{f" colspan={chr(34)}{span}{chr(34)}" if span > 1 else ""}>' + block_html(c) + "</td>")
            rows.append("<tr>" + "".join(cells) + "</tr>")
        return "<table><tbody>" + "".join(rows) + "</tbody></table>"

    def block_html(container):
        out, cur_list = [], None   # cur_list = "ul" | "ol" en cours
        body = container.element.body if hasattr(container, "element") else container._tc
        for child in body.iterchildren():
            tag = child.tag.split("}")[-1]
            if tag == "tbl":
                if cur_list: out.append(f"</{cur_list}>"); cur_list = None
                out.append(table_html(Table(child, container)))
            elif tag == "p":
                par = Paragraph(child, container)
                name, inner = para_html(par)
                is_list = name.lower().startswith("list") or bool(child.xpath("./w:pPr/w:numPr"))
                if is_list:
                    kind = "ol" if ("number" in name.lower() or "num" in name.lower()) else "ul"
                    if cur_list != kind:
                        if cur_list: out.append(f"</{cur_list}>")
                        out.append(f"<{kind}>"); cur_list = kind
                    out.append(f"<li>{inner}</li>")
                    continue
                if cur_list: out.append(f"</{cur_list}>"); cur_list = None
                if not inner.strip():
                    out.append("<p><br></p>" if not child.xpath(".//w:br[@w:type='page']") else "<hr>")
                    continue
                m = re.match(r"(?:heading|titre)\s*(\d)", name.lower())
                if name.lower() == "title": h = "h1"
                elif m: h = f"h{min(int(m.group(1)), 3)}"
                else: h = "p"
                out.append(f"<{h}{para_style(par)}>{inner}</{h}>")
        if cur_list: out.append(f"</{cur_list}>")
        return "".join(out)

    return block_html(doc)
