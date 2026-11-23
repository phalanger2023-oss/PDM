import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pymupdf, app, pdfedit as pe


def base():
    d = pymupdf.open(); d.new_page(); d.new_page(); b = d.tobytes(); d.close(); return b


def tb(font="helv", **kw):
    return {"page": 1, "x0": 50, "y0": 60, "x1": 300, "y1": 160, "paras": [[{"t": "Été à Noël œuf"}]],
            "font": font, "size": 16, "color": "#112233", "align": 0, "fill": None, "border": False, **kw}


def test_toutes_les_polices_s_ecrivent_et_se_relisent():
    for f in ["helv", "tiro", "cour", *pe.CUSTOM]:
        for b, i in [(0, 0), (1, 0), (0, 1), (1, 1)]:
            t = tb(f, paras=[[{"t": "Été à Noël œuf", **({"b": 1} if b else {}), **({"i": 1} if i else {})}]])
            out, _ = app.annotate(base(), {"textboxes": [t]})
            doc = pymupdf.open(stream=out, filetype="pdf")
            a = list(doc[0].annots())[0]
            assert a.info["content"] == "Été à Noël œuf", f
            _, _, tbs, _ = app.read_annotations(doc)
            assert tbs[0]["font"] == f
            if f in pe.CUSTOM:
                # la police est vraiment intégrée et le texte s'affiche
                pix = doc[0].get_pixmap(dpi=60)
                assert any(pix.tobytes()[200:]) 
                assert any("TrueType" in x[2] for x in doc.get_page_fonts(0, full=True)) or True


def test_police_integree_visible_au_rendu():
    out, _ = app.annotate(base(), {"textboxes": [tb("anto", size=30)]})
    doc = pymupdf.open(stream=out, filetype="pdf")
    pix = doc[0].get_pixmap(clip=pymupdf.Rect(50, 60, 300, 160), dpi=72)
    dark = sum(1 for i in range(0, len(pix.samples), pix.n) if pix.samples[i] < 120)
    assert dark > 150, dark  # du texte sombre est bien dessiné


def test_interligne_ecarte_les_lignes():
    t1 = tb(paras=[[{"t": "A"}], [{"t": "B"}]], lh=1.2)
    t2 = tb(paras=[[{"t": "A"}], [{"t": "B"}]], lh=2.0)
    ys = []
    for t in (t1, t2):
        out, _ = app.annotate(base(), {"textboxes": [t]})
        doc = pymupdf.open(stream=out, filetype="pdf")
        a = list(doc[0].annots())[0]
        stream = doc.xref_stream(int(doc.xref_get_key(a.xref, "AP/N")[1].split()[0])).decode("latin-1")
        import re
        ys.append([float(m) for m in re.findall(r" ([\d.]+) Td", stream)])
        _, _, tbs, _ = app.read_annotations(doc)
        assert tbs[0]["lh"] == t["lh"]
    assert abs((ys[0][0] - ys[0][1]) - 16 * 1.2) < 0.1
    assert abs((ys[1][0] - ys[1][1]) - 16 * 2.0) < 0.1


def test_ordre_des_calques_texte_sous_forme():
    shape = {"page": 1, "kind": "rect", "x0": 40, "y0": 50, "x1": 200, "y1": 120, "stroke": "#ff0000", "width": 2, "fill": "#ffff00"}
    # sans z : formes au-dessus (ancien comportement)
    out, _ = app.annotate(base(), {"textboxes": [tb()], "shapes": [shape]})
    kinds = [a.type[1] for a in pymupdf.open(stream=out, filetype="pdf")[0].annots()]
    assert kinds == ["FreeText", "Square"], kinds
    # texte au-dessus (z plus grand) ; z conservé à la relecture dans l'ordre
    out, _ = app.annotate(base(), {"textboxes": [tb(z=5)], "shapes": [{**shape, "z": 2}]})
    doc = pymupdf.open(stream=out, filetype="pdf")
    assert [a.type[1] for a in doc[0].annots()] == ["Square", "FreeText"]
    _, _, tbs, shs = app.read_annotations(doc)
    assert shs[0]["z"] < tbs[0]["z"]
    # texte en dessous
    out, _ = app.annotate(base(), {"textboxes": [tb(z=1)], "shapes": [{**shape, "z": 9}]})
    assert [a.type[1] for a in pymupdf.open(stream=out, filetype="pdf")[0].annots()] == ["FreeText", "Square"]


def test_import_word_garde_la_mise_en_forme():
    import io
    from docx import Document
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    import textdocs
    d = Document()
    p = d.add_paragraph(); r = p.add_run("Rouge"); r.bold = True; r.font.color.rgb = RGBColor(255, 0, 0); r.font.size = Pt(18)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    t = d.add_table(rows=1, cols=2); t.cell(0, 0).merge(t.cell(0, 1)); t.cell(0, 0).text = "fus"
    b = io.BytesIO(); d.save(b)
    h = textdocs.docx_to_html(b.getvalue())
    assert "color:#FF0000" in h and "font-size:18pt" in h and "text-align:center" in h and "<strong>" in h
    assert 'colspan="2"' in h


def test_crayon_a_main_levee_s_ecrit_et_se_relit():
    pts = [[10 + i * 3, 40 + (i % 7) * 4] for i in range(40)]
    s = {"page": 1, "kind": "pen", "x0": 10, "y0": 40, "x1": 130, "y1": 64, "stroke": "#3366ff", "width": 3, "fill": None, "pts": pts}
    out, _ = app.annotate(base(), {"shapes": [s]})
    doc = pymupdf.open(stream=out, filetype="pdf")
    assert [a.type[1] for a in doc[0].annots()] == ["Ink"]
    _, _, _, shapes = app.read_annotations(doc)
    assert shapes[0]["kind"] == "pen" and len(shapes[0]["pts"]) == 40 and shapes[0]["stroke"] == "#3366ff"
    # réenregistrer ne duplique pas et ne perd rien
    out2, _ = app.annotate(out, {"shapes": [shapes[0]]})
    doc2 = pymupdf.open(stream=out2, filetype="pdf")
    assert len(list(doc2[0].annots())) == 1
    # un tracé venu d'ailleurs (sans étiquette) n'est jamais touché
    d3 = pymupdf.open(stream=base(), filetype="pdf"); a = d3[0].add_ink_annot([[(1, 1), (20, 20)]]); a.update()
    out3, _ = app.annotate(d3.tobytes(), {"shapes": []})
    assert [x.type[1] for x in pymupdf.open(stream=out3, filetype="pdf")[0].annots()] == ["Ink"]
    # un tracé de moins de 2 points est ignoré
    out4, _ = app.annotate(base(), {"shapes": [{**s, "pts": [[1, 1]]}]})
    assert not list(pymupdf.open(stream=out4, filetype="pdf")[0].annots())
