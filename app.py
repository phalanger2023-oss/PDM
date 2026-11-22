"""Prototype local d'annotation de PDF.

Le serveur Python fait quatre choses :
  1. servir la page web (dossier static/)
  2. tenir une bibliothèque de PDF dans le dossier « Mes documents » (ouvrir, enregistrer, renommer)
  3. relire les annotations déjà présentes dans un PDF
  4. écrire vos annotations (surlignages, notes, zones de texte, formes) dans le PDF
"""
import hashlib
import hmac
import io
import json
import os
import re
import secrets
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

import pymupdf  # PyMuPDF : la bibliothèque qui lit et modifie les PDF
from flask import Flask, Response, abort, jsonify, redirect, request, send_file, send_from_directory, session

import pdfedit as pe
from releases import RELEASES, VERSION  # moteur de texte riche et d'édition du contenu natif

BASE = Path(__file__).parent
# Réglages par variables d'environnement (utile sur le serveur ; en local, les valeurs par défaut suffisent) :
#   DOCS_DIR      dossier des documents (défaut : « Mes documents » à côté du programme)
#   ENVIRONMENT   "production" sur le serveur (désactive le mode debug)
#   BEHIND_PROXY  "1" derrière Traefik : l'adresse et le https réels viennent des en-têtes du proxy
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
DOCS = Path(os.environ.get("DOCS_DIR") or BASE / "Mes documents")  # vos PDF de travail
DOCS.mkdir(parents=True, exist_ok=True)
# Le PDF d'origine n'est JAMAIS modifié. Votre travail en cours est un « brouillon » enregistré à part,
# automatiquement ; le PDF final n'est fabriqué que quand vous le téléchargez.
PROJECTS = DOCS / ".brouillons"  # un fichier .json par document (vos modifications en cours)
CACHE = DOCS / ".cache"          # miniatures de la page d'accueil (recalculables à tout moment)

DOSSIERS = DOCS / ".dossiers.json"          # nom du document -> {"dossier": "année/matière/chapitre", "source": "deepwell:…"}
CLE_FILE = DOCS / ".cle_integration"        # clé secrète qui autorise DeepWell à déposer des documents (voir plus bas)

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 Mo maximum

if os.environ.get("BEHIND_PROXY") == "1":
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

# ---------------------------------------------------------------- Connexion (un seul compte)
# Réglages (dans le fichier .env du serveur ; voir outils/mot_de_passe.py) :
#   AUTH_USER     identifiant
#   AUTH_HASH     mot de passe haché (bcrypt) — jamais le mot de passe lui-même
#   SECRET_KEY    clé qui signe le cookie de connexion (longue, aléatoire, secrète)
#   SESSION_DAYS  durée de la connexion mémorisée (défaut : 90 jours)
# Sans AUTH_HASH, la connexion est désactivée : pratique en local, INTERDIT en production (voir plus bas).
AUTH_USER = os.environ.get("AUTH_USER", "")
AUTH_HASH = os.environ.get("AUTH_HASH", "").strip().strip("'\"")
AUTH_ENABLED = bool(AUTH_HASH)
SESSION_DAYS = int(os.environ.get("SESSION_DAYS", "90"))

if ENVIRONMENT == "production" and not (AUTH_HASH and AUTH_USER and os.environ.get("SECRET_KEY")):
    raise RuntimeError(
        "En production, AUTH_USER, AUTH_HASH et SECRET_KEY sont obligatoires : le site refuse de démarrer "
        "sans mot de passe. Générez-les avec « python outils/mot_de_passe.py » (voir DEPLOIEMENT.md)."
    )

app.secret_key = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config.update(
    PERMANENT_SESSION_LIFETIME=timedelta(days=SESSION_DAYS),  # la durée se prolonge à chaque visite
    SESSION_COOKIE_HTTPONLY=True,       # le cookie est invisible pour le JavaScript de la page
    SESSION_COOKIE_SAMESITE="Lax",      # il n'est pas envoyé par un autre site (protège des requêtes forgées)
    SESSION_COOKIE_SECURE=(ENVIRONMENT == "production"),  # uniquement en https sur le serveur
    SESSION_COOKIE_NAME="annotateur_session",
)
# Changer le mot de passe déconnecte tout le monde : la session retient une empreinte de l'ancien hachage
PW_VERSION = hashlib.sha256(AUTH_HASH.encode()).hexdigest()[:16]

_FAILS = {}  # adresse IP -> instants des échecs récents (limite les essais répétés)
MAX_FAILS, FAIL_WINDOW = 5, 15 * 60


def _too_many_fails(ip):
    now = time.time()
    recent = [t for t in _FAILS.get(ip, []) if now - t < FAIL_WINDOW]
    if recent:
        _FAILS[ip] = recent
    else:
        _FAILS.pop(ip, None)
    return len(recent) >= MAX_FAILS


def _password_ok(password):
    try:
        import bcrypt
        raw = password.encode()
        if len(raw) > 72:
            return False
        return bcrypt.checkpw(raw, AUTH_HASH.replace("$2y$", "$2b$", 1).encode())
    except Exception:
        return False


def _logged_in():
    return session.get("u") == AUTH_USER and session.get("v") == PW_VERSION


def read_dossiers():
    try:
        d = json.loads(DOSSIERS.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def write_dossiers(d):
    tmp = DOSSIERS.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(DOSSIERS)


def integration_key(new=False):
    """La clé d'intégration (créée au premier besoin). Elle ne sert qu'à DeepWell, jamais à se connecter au site."""
    if new or not CLE_FILE.exists():
        CLE_FILE.write_text(secrets.token_urlsafe(32), encoding="utf-8")
        try:
            os.chmod(CLE_FILE, 0o600)
        except OSError:
            pass
    return CLE_FILE.read_text(encoding="utf-8").strip()


def _key_ok(ip):
    """Vérifie l'en-tête X-PDM-Key (comparaison à temps constant) ; trop d'échecs d'une même adresse = blocage temporaire."""
    if _too_many_fails(ip):
        return False
    given = request.headers.get("X-PDM-Key", "")
    if given and hmac.compare_digest(given.encode(), integration_key().encode()):
        return True
    _FAILS.setdefault(ip, []).append(time.time())
    return False


@app.before_request
def require_login():
    if not AUTH_ENABLED:
        return None
    # Une requête qui modifie quelque chose doit venir de ce site même (et pas d'une autre page web)
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("Origin")
        if origin and urlparse(origin).netloc != request.host:
            abort(403)
    p = request.path
    if p in ("/api/integration/ping", "/api/integration/docs"):  # DeepWell (de serveur à serveur) : clé secrète au lieu du cookie
        return None if _key_ok(request.remote_addr or "?") else (jsonify(error="Clé d'intégration refusée"), 401)
    if p in ("/login", "/api/login", "/api/me", "/healthz") or p.startswith("/static/"):
        return None
    if _logged_in():
        return None
    if p.startswith("/api/"):
        return jsonify(error="Connexion requise"), 401
    return redirect("/login")

# Types d'annotations gérés par ce site (les autres, par exemple les liens, ne sont jamais touchés)
MANAGED = [
    pymupdf.PDF_ANNOT_HIGHLIGHT, pymupdf.PDF_ANNOT_TEXT, pymupdf.PDF_ANNOT_FREE_TEXT,
    pymupdf.PDF_ANNOT_SQUARE, pymupdf.PDF_ANNOT_CIRCLE, pymupdf.PDF_ANNOT_LINE,
    pymupdf.PDF_ANNOT_POLYGON,  # seulement ceux créés ici (les triangles)
]
# La mise en page est rangée dans chaque annotation sous cette étiquette, pour la retrouver
# exactement quand on rouvre le PDF.
TAG = "annotpdf:"
FONTS = {"helv", "tiro", "cour"}  # sans empattement, serif, machine à écrire
BOX_SHAPES = {"rect", "ellipse", "triangle"}
SHAPES = BOX_SHAPES | {"line", "arrow"}
DEFAULT_TEXT = {"font": "helv", "size": 14, "color": "#000000", "align": 0, "fill": None, "border": False}
DEFAULT_HL = "#ffe000"
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


# ---------- Petits outils ----------
def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def rgb_to_hex(c):
    return "#" + "".join(f"{round(v * 255):02x}" for v in c)


def safe_hex(h, default):
    return h if isinstance(h, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", h) else default


def clean_name(raw):
    """Nom de fichier propre pour Windows, toujours terminé par .pdf"""
    raw = (raw or "").strip()
    if raw.lower().endswith(".pdf"):
        raw = raw[:-4]
    raw = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", raw).strip(" .")[:120] or "document"
    if raw.upper() in RESERVED:
        raw = "_" + raw
    return raw + ".pdf"


def unique_name(name):
    """Si le nom existe déjà dans Mes documents, ajoute (2), (3)... pour ne rien écraser."""
    name = clean_name(name)
    stem = name[:-4]
    n = 1
    while (DOCS / name).exists():
        n += 1
        name = f"{stem} ({n}).pdf"
    return name


def doc_file(name):
    return DOCS / clean_name(name)


def project_file(name):
    return PROJECTS / (clean_name(name)[:-4] + ".json")


def thumb_file(name):
    return CACHE / (clean_name(name)[:-4] + ".png")


def read_project(name):
    """Le brouillon d'un document : {"rev": n, "saved": heure, "state": {...}}, ou None s'il n'y en a pas."""
    p = project_file(name)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_json_atomic(path, obj):
    """Écrit d'abord dans un fichier temporaire puis le met en place : jamais de brouillon à moitié écrit."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def meta_of(a):
    subject = a.info.get("subject", "")
    if subject.startswith(TAG):
        try:
            return json.loads(subject[len(TAG):])
        except ValueError:
            pass
    return None


# ---------- Lire les annotations d'un PDF ----------
def read_annotations(doc):
    highlights, notes, textboxes, shapes = [], [], [], []
    for page in doc:
        n = page.number + 1
        for a in page.annots(types=MANAGED):
            kind = a.type[1]
            meta = meta_of(a)
            if kind == "Highlight":
                v = a.vertices or []
                rects = [list(pymupdf.Quad(*v[i:i + 4]).rect) for i in range(0, len(v) - 3, 4)]
                stroke = a.colors.get("stroke")
                highlights.append({"page": n, "rects": rects or [list(a.rect)],
                                   "color": rgb_to_hex(stroke) if stroke else DEFAULT_HL})
            elif kind == "Text":
                notes.append({"page": n, "x": a.rect.x0, "y": a.rect.y0,
                              "text": a.info.get("content", "")})
            elif kind == "FreeText":
                style = {**DEFAULT_TEXT, **{k: v for k, v in (meta or {}).items() if k in DEFAULT_TEXT}}
                r = a.rect
                if meta and "rect" in meta:  # position exacte mémorisée à l'enregistrement
                    r = pymupdf.Rect(meta["rect"])
                elif style["border"]:  # annotation venue d'ailleurs : le trait déborde d'un demi-point
                    r = pymupdf.Rect(r.x0 + 0.5, r.y0 + 0.5, r.x1 - 0.5, r.y1 - 0.5)
                paras = (meta or {}).get("paras") or pe.normalize_paras({"text": a.info.get("content", "")})
                textboxes.append({"page": n, "x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1,
                                  "paras": paras, **style})
            else:  # Square, Circle, Line, Polygon
                if kind == "Polygon" and not (meta and meta.get("kind") == "triangle"):
                    continue  # un polygone venu d'ailleurs : on n'y touche pas
                if meta and "rect" in meta:
                    s = dict(meta)
                else:  # forme créée dans un autre logiciel : on en déduit l'essentiel
                    colors, r = a.colors, a.rect
                    s = {"kind": {"Square": "rect", "Circle": "ellipse"}.get(kind, "line"),
                         "stroke": rgb_to_hex(colors["stroke"]) if colors.get("stroke") else "#e03131",
                         "width": a.border.get("width") or 2,
                         "fill": rgb_to_hex(colors["fill"]) if colors.get("fill") else None,
                         "rect": [r.x0, r.y0, r.x1, r.y1]}
                    if kind == "Line":
                        v = a.vertices
                        if v and len(v) >= 2:
                            s["rect"] = [v[0][0], v[0][1], v[1][0], v[1][1]]
                        if a.line_ends and a.line_ends[1]:
                            s["kind"] = "arrow"
                x0, y0, x1, y1 = s["rect"]
                shapes.append({"page": n, "kind": s["kind"], "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                               "stroke": s.get("stroke", "#e03131"), "width": s.get("width", 2),
                               "fill": s.get("fill")})
    return highlights, notes, textboxes, shapes


def clear_managed(doc):
    """Retire les annotations des types gérés (elles seront réécrites depuis le navigateur)."""
    for page in doc:
        for a in list(page.annots(types=MANAGED)):
            if a.type[1] == "Polygon" and not meta_of(a):
                continue
            page.delete_annot(a)


# ---------- Écrire les annotations dans un PDF ----------
def add_shape(page, s):
    kind = s.get("kind")
    if kind not in SHAPES:
        return
    stroke = safe_hex(s.get("stroke"), "#e03131")
    width = min(max(float(s.get("width", 2)), 0.5), 24)
    fill = safe_hex(s.get("fill"), None) if kind in BOX_SHAPES else None
    x0, y0, x1, y1 = (float(s[k]) for k in ("x0", "y0", "x1", "y1"))
    if kind in BOX_SHAPES:  # on range les coins : x0 < x1 et y0 < y1
        x0, x1, y0, y1 = min(x0, x1), max(x0, x1), min(y0, y1), max(y0, y1)
    if kind == "rect":
        a = page.add_rect_annot(pymupdf.Rect(x0, y0, x1, y1))
    elif kind == "ellipse":
        a = page.add_circle_annot(pymupdf.Rect(x0, y0, x1, y1))
    elif kind == "triangle":
        a = page.add_polygon_annot([pymupdf.Point((x0 + x1) / 2, y0), pymupdf.Point(x1, y1), pymupdf.Point(x0, y1)])
    else:
        a = page.add_line_annot(pymupdf.Point(x0, y0), pymupdf.Point(x1, y1))
        a.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE,
                        pymupdf.PDF_ANNOT_LE_CLOSED_ARROW if kind == "arrow" else pymupdf.PDF_ANNOT_LE_NONE)
    colors = {"stroke": hex_to_rgb(stroke)}
    if fill:
        colors["fill"] = hex_to_rgb(fill)
    elif kind == "arrow":
        colors["fill"] = hex_to_rgb(stroke)  # pointe de flèche pleine
    a.set_colors(**colors)
    a.set_border(width=width)
    a.set_info(subject=TAG + json.dumps({"kind": kind, "stroke": stroke, "width": width, "fill": fill,
                                         "rect": [x0, y0, x1, y1]}))
    a.update()


def annotate(pdf_bytes, payload):
    """Renvoie (PDF, rapport) avec les modifications du contenu natif et exactement les annotations
    reçues (les anciennes annotations sont remplacées)."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    report = {}
    if payload.get("natives") or payload.get("nimages"):
        report = pe.apply_native(doc, payload.get("natives", []), payload.get("nimages", []))
    clear_managed(doc)  # on repart propre : pas de doublons avec ce qui existait déjà
    count = len(doc)
    ctx = {}

    def page_of(item):
        n = int(item.get("page", 0))
        return doc[n - 1] if 1 <= n <= count else None

    for h in payload.get("highlights", []):
        page = page_of(h)
        if page is None or not h.get("rects"):
            continue
        quads = [pymupdf.Rect(*r).quad for r in h["rects"]]
        a = page.add_highlight_annot(quads=quads)
        a.set_colors(stroke=hex_to_rgb(safe_hex(h.get("color"), DEFAULT_HL)))
        a.update()

    for n in payload.get("notes", []):
        page = page_of(n)
        if page is not None:
            page.add_text_annot(pymupdf.Point(n["x"], n["y"]), n.get("text", ""))

    for t in payload.get("textboxes", []):
        page = page_of(t)
        paras = pe.normalize_paras(t)
        if page is None or not pe.plain_text(paras).strip():
            continue  # on n'écrit pas les zones vides
        style = {
            "font": t.get("font") if t.get("font") in FONTS else "helv",
            "size": min(max(float(t.get("size", 14)), 4), 200),
            "color": safe_hex(t.get("color"), "#000000"),
            "align": t.get("align") if t.get("align") in (0, 1, 2) else 0,
            "fill": safe_hex(t.get("fill"), None),
            "border": bool(t.get("border")),
        }
        rect = pymupdf.Rect(t["x0"], t["y0"], t["x1"], t["y1"])
        a = pe.write_text_annot(doc, page, rect, paras, style, ctx)
        a.set_info(subject=TAG + json.dumps({**style, "rect": list(rect), "paras": paras}))

    for s in payload.get("shapes", []):
        page = page_of(s)
        if page is not None:
            add_shape(page, s)

    pe.finalize_aps(doc, ctx)  # en dernier : voir la remarque dans pdfedit.write_text_annot
    out = doc.tobytes(garbage=1, deflate=True)
    doc.close()
    return out, report


def annotations_json(pdf_bytes):
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    highlights, notes, textboxes, shapes = read_annotations(doc)
    doc.close()
    return {"highlights": highlights, "notes": notes, "textboxes": textboxes, "shapes": shapes}


# ---------- Routes ----------
@app.get("/")
def home():
    return send_from_directory("static", "index.html")


@app.get("/login")
def login_page():
    if AUTH_ENABLED and _logged_in():
        return redirect("/")
    return send_from_directory("static", "login.html")


@app.post("/api/login")
def api_login():
    if not AUTH_ENABLED:
        return jsonify(ok=True)
    ip = request.remote_addr or "?"
    if _too_many_fails(ip):
        return jsonify(error="Trop d'essais. Réessayez dans quelques minutes."), 429
    data = request.get_json(silent=True) or {}
    user_ok = hmac.compare_digest(str(data.get("username", "")).encode(), AUTH_USER.encode())
    pass_ok = _password_ok(str(data.get("password", "")))  # toujours calculé : même durée dans tous les cas
    if not (user_ok and pass_ok):
        _FAILS.setdefault(ip, []).append(time.time())
        time.sleep(0.6)
        return jsonify(error="Identifiant ou mot de passe incorrect."), 401
    _FAILS.pop(ip, None)
    session.clear()
    session["u"], session["v"] = AUTH_USER, PW_VERSION
    session.permanent = bool(data.get("remember"))  # « Rester connecté » : cookie durable ; sinon : jusqu'à la fermeture
    return jsonify(ok=True)


@app.post("/api/logout")
def api_logout():
    session.clear()
    return jsonify(ok=True)


@app.get("/api/me")
def api_me():
    return jsonify(auth=AUTH_ENABLED, logged=(not AUTH_ENABLED) or _logged_in(), days=SESSION_DAYS)


@app.get("/api/releases")
def api_releases():
    return jsonify(version=VERSION, releases=RELEASES)


@app.get("/healthz")
def healthz():
    """Contrôle de santé pour Docker : le service répond et le dossier des documents est accessible."""
    ok = DOCS.is_dir() and os.access(DOCS, os.W_OK)
    return jsonify(status="ok" if ok else "erreur"), (200 if ok else 503)


@app.get("/api/docs")
def list_docs():
    """Les PDF de Mes documents, du plus récemment travaillé au plus ancien (page d'accueil)."""
    items = []
    meta = read_dossiers()
    for p in DOCS.glob("*.pdf"):
        st = p.stat()
        modified, draft = st.st_mtime, False
        pf = project_file(p.name)
        if pf.exists():
            draft, modified = True, max(modified, pf.stat().st_mtime)
        pages = 0
        try:
            d = pymupdf.open(p)
            pages = d.page_count
            d.close()
        except Exception:
            pass
        items.append({"name": p.name, "size": st.st_size, "modified": modified, "draft": draft, "pages": pages,
                      "folder": (meta.get(p.name) or {}).get("dossier", "")})
    items.sort(key=lambda i: i["modified"], reverse=True)
    if CACHE.exists():  # ménage : miniatures de documents qui n'existent plus (recalculables, donc sans risque)
        known = {i["name"][:-4] for i in items}
        for t in CACHE.glob("*.png"):
            if t.stem not in known and not t.name.endswith(".tmp.png"):
                try:
                    t.unlink()
                except OSError:
                    pass
    return jsonify(items[:1000])


@app.post("/api/docs")
def add_doc():
    """Ajoute à Mes documents le PDF choisi, et renvoie ses annotations déjà présentes."""
    f = request.files.get("file")
    if f is None:
        return jsonify(error="Aucun fichier reçu"), 400
    data = f.read()
    try:
        info = annotations_json(data)
    except Exception:
        return jsonify(error="Ce fichier n'est pas un PDF valide"), 400
    name = unique_name(f.filename or "document.pdf")
    (DOCS / name).write_bytes(data)
    return jsonify(name=name, **info)


@app.get("/api/docs/<name>/annotations")
def doc_annotations(name):
    p = doc_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    return jsonify(name=p.name, **annotations_json(p.read_bytes()))


@app.get("/api/docs/<name>/pdf")
def doc_pdf(name):
    p = doc_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    if request.args.get("dl") == "1":  # « Télécharger l'original » : le PDF d'origine n'est jamais modifié par l'éditeur
        return send_file(p, mimetype="application/pdf", max_age=0, as_attachment=True, download_name=p.name)
    return send_file(p, mimetype="application/pdf", max_age=0)


@app.get("/api/docs/<name>/project")
def project_get(name):
    """Le brouillon enregistré automatiquement (ou null si le document n'a jamais été modifié)."""
    if not doc_file(name).exists():
        return jsonify(error="Document introuvable"), 404
    return jsonify(project=read_project(name))


@app.put("/api/docs/<name>/project")
def project_put(name):
    """Enregistre le brouillon. « baseRev » = la version que le navigateur croit être la dernière : si le
    brouillon a changé entre-temps (autre onglet), on refuse pour ne pas écraser un travail plus récent."""
    if not doc_file(name).exists():
        return jsonify(error="Document introuvable"), 404
    if (request.content_length or 0) > 20 * 1024 * 1024:
        return jsonify(error="Brouillon trop volumineux"), 413
    data = request.get_json(silent=True) or {}
    state = data.get("state")
    if not isinstance(state, dict):
        return jsonify(error="Brouillon invalide"), 400
    cur = read_project(name)
    cur_rev = int(cur.get("rev", 0)) if cur else 0
    try:
        base = int(data.get("baseRev", -1))
    except (TypeError, ValueError):
        base = -1
    if base != cur_rev and not data.get("force"):
        return jsonify(error="Ce document a été modifié ailleurs (un autre onglet ?).", rev=cur_rev), 409
    proj = {"rev": cur_rev + 1, "saved": time.time(), "state": state}
    write_json_atomic(project_file(name), proj)
    return jsonify(rev=proj["rev"], saved=proj["saved"])


@app.delete("/api/docs/<name>/project")
def project_delete(name):
    """Revient au PDF d'origine : le brouillon est supprimé."""
    for f in (project_file(name), thumb_file(name)):
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass
    return jsonify(ok=True)


@app.post("/api/docs/<name>/rename")
def doc_rename(name):
    p = doc_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    want = str((request.get_json(silent=True) or {}).get("newName") or "").strip()
    if not want:
        return jsonify(error="Donnez un nom au document."), 400
    new = doc_file(want)
    if new == p:
        return jsonify(ok=True, name=p.name)
    if new.exists():
        return jsonify(error=f"Un document « {new.name} » existe déjà"), 409
    p.rename(new)
    m = read_dossiers()
    if p.name in m:
        m[new.name] = m.pop(p.name)
        write_dossiers(m)
    src, dst = project_file(p.name), project_file(new.name)
    if src.exists():  # le brouillon suit le document
        dst.parent.mkdir(parents=True, exist_ok=True)
        src.replace(dst)
    try:  # la miniature se recalcule toute seule : inutile de la déplacer (et Windows refuse si elle est en cours de lecture)
        thumb_file(p.name).unlink(missing_ok=True)
    except OSError:
        pass
    return jsonify(ok=True, name=new.name)


@app.get("/api/docs/<name>/thumb")
def doc_thumb(name):
    """Miniature de la 1re page, AVEC vos modifications (recalculée seulement si le document a changé)."""
    p = doc_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    t, pf = thumb_file(name), project_file(name)
    newest = max(p.stat().st_mtime, pf.stat().st_mtime if pf.exists() else 0)
    if not t.exists() or t.stat().st_mtime < newest:
        try:
            data = p.read_bytes()
            proj = read_project(name)
            if proj and isinstance(proj.get("state"), dict):
                data, _ = annotate(data, proj["state"])
            doc = pymupdf.open(stream=data, filetype="pdf")
            page = doc[0]
            zoom = 360 / max(page.rect.width, 1)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            CACHE.mkdir(parents=True, exist_ok=True)
            tmp = t.with_name(t.name + ".tmp.png")
            pix.save(tmp)
            tmp.replace(t)
            doc.close()
        except Exception:
            return jsonify(error="Miniature indisponible"), 404
    return send_file(t, mimetype="image/png", max_age=0)


@app.get("/api/docs/<name>/export")
def doc_export(name):
    """Télécharge le PDF final depuis la page d'accueil, sans l'ouvrir : l'original + votre brouillon."""
    p = doc_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    proj = read_project(name)
    if proj and isinstance(proj.get("state"), dict):
        out, _ = annotate(p.read_bytes(), proj["state"])
        return send_file(io.BytesIO(out), mimetype="application/pdf", as_attachment=True, download_name=p.name)
    return send_file(p, mimetype="application/pdf", as_attachment=True, download_name=p.name)


@app.post("/api/docs/<name>/download")
def doc_download(name):
    """Renvoie une copie annotée à télécharger (Mes documents n'est pas modifié)."""
    payload = request.get_json(force=True)
    p = doc_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    out, _ = annotate(p.read_bytes(), payload)
    return send_file(io.BytesIO(out), mimetype="application/pdf", as_attachment=True,
                     download_name=clean_name(payload.get("newName") or p.name))


@app.get("/api/docs/<name>/content")
def doc_content(name):
    """Le contenu natif du PDF : paragraphes de texte et images, page par page."""
    p = doc_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    doc = pymupdf.open(stream=p.read_bytes(), filetype="pdf")
    usage = pe.image_usage(doc)
    pages = []
    for page in doc:
        blocks = pe.read_blocks(page)
        pages.append({"blocks": blocks, "images": pe.read_images(page, usage), "graphics": pe.read_graphics(page, blocks)})
    doc.close()
    return jsonify(pages=pages)


@app.get("/api/docs/<name>/clip/<kind>/<int:pno>/<x0>/<y0>/<x1>/<y1>.png")
def doc_clip(name, kind, pno, x0, y0, x1, y1):
    """Aperçu d'un morceau de page (formule, trait, image partagée...) pendant qu'on le déplace."""
    p = doc_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    try:
        bbox = [float(v) for v in (x0, y0, x1, y1)]
        png = pe.clip_png(p.read_bytes(), pno, kind if kind in ("text", "graphic", "graphic_rest", "shared", "inline") else "text", bbox)
    except Exception:
        return jsonify(error="Aperçu impossible"), 404
    return Response(png, mimetype="image/png", headers={"Cache-Control": "max-age=600"})


@app.get("/api/docs/<name>/image/<int:xref>")
def doc_image(name, xref):
    """Une image du PDF au format PNG (pour l'aperçu quand on la déplace)."""
    p = doc_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    doc = pymupdf.open(stream=p.read_bytes(), filetype="pdf")
    try:
        png = pe.image_png(doc, xref)
    except Exception:
        return jsonify(error="Image introuvable"), 404
    finally:
        doc.close()
    return Response(png, mimetype="image/png", headers={"Cache-Control": "max-age=3600"})


@app.delete("/api/docs/<name>")
def doc_delete(name):
    p = doc_file(name)
    for f in (p, project_file(name), thumb_file(name)):
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass
    m = read_dossiers()
    if m.pop(p.name, None) is not None:
        write_dossiers(m)
    return jsonify(ok=True)


# ---------------------------------------------------------------- Intégration DeepWell
@app.get("/api/integration/key")
def integration_key_get():
    """La clé à recopier dans DeepWell (Réglages → Google Drive → PDM). Réservé à l'utilisateur connecté."""
    return jsonify(key=integration_key())


@app.post("/api/integration/key/renew")
def integration_key_renew():
    """Nouvelle clé : l'ancienne cesse de fonctionner (à recopier dans DeepWell)."""
    return jsonify(key=integration_key(new=True))


@app.get("/api/integration/ping")
def integration_ping():
    return jsonify(ok=True, app="PDM", version=VERSION)


@app.post("/api/integration/docs")
def integration_add_doc():
    """DeepWell dépose un PDF de cours : champs « file », « folder » (année/matière/chapitre) et « source » (identifiant côté DeepWell,
    pour ne jamais créer de doublon si la demande est rejouée). Renvoie le nom du document dans PDM."""
    f = request.files.get("file")
    source = str(request.form.get("source") or "")[:200]
    folder = " / ".join(x.strip() for x in re.split(r"[/\\]", request.form.get("folder") or "") if x.strip())[:300]
    if f is None:
        return jsonify(error="Aucun fichier reçu"), 400
    m = read_dossiers()
    if source:
        for name, info in m.items():
            if info.get("source") == source and (DOCS / name).exists():
                return jsonify(name=name, folder=info.get("dossier", ""), existing=True)
    data = f.read()
    try:
        annotations_json(data)
    except Exception:
        return jsonify(error="Ce fichier n'est pas un PDF valide"), 400
    name = unique_name(f.filename or "document.pdf")
    (DOCS / name).write_bytes(data)
    m[name] = {"dossier": folder, "source": source}
    write_dossiers(m)
    return jsonify(name=name, folder=folder, existing=False)


if __name__ == "__main__":
    # Lancement local (lancer.bat). Sur le serveur, c'est gunicorn qui démarre le site (voir le Dockerfile).
    app.run(debug=(ENVIRONMENT != "production"), port=5000)
