"""Prototype local d'annotation de PDF.

Le serveur Python fait quatre choses :
  1. servir la page web (dossier static/)
  2. tenir une bibliothèque de PDF dans le dossier « Mes documents » (ouvrir, enregistrer, renommer)
  3. relire les annotations déjà présentes dans un PDF
  4. écrire vos annotations (surlignages, notes, zones de texte, formes) dans le PDF
"""
import base64
import hashlib
import hmac
import gzip
import io
import json
import os
import re
import secrets
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote, urlparse

import pymupdf  # PyMuPDF : la bibliothèque qui lit et modifie les PDF
from flask import Flask, Response, abort, g, has_request_context, jsonify, redirect, request, send_file, send_from_directory, session

import pdfedit as pe
import textdocs
from releases import RELEASES, VERSION  # moteur de texte riche et d'édition du contenu natif

BASE = Path(__file__).parent
# Réglages par variables d'environnement (utile sur le serveur ; en local, les valeurs par défaut suffisent) :
#   DOCS_DIR      dossier des documents (défaut : « Mes documents » à côté du programme)
#   ENVIRONMENT   "production" sur le serveur (désactive le mode debug)
#   BEHIND_PROXY  "1" derrière Traefik : l'adresse et le https réels viennent des en-têtes du proxy
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development")
ROOT_DOCS = Path(os.environ.get("DOCS_DIR") or BASE / "Mes documents")  # dossier racine des documents (espace du premier administrateur + fichiers communs)
ROOT_DOCS.mkdir(parents=True, exist_ok=True)


class _UserDir:
    """Chemin qui pointe vers l'espace de la personne connectée (chaque compte DeepWell a le sien) ; hors requête : le dossier racine.
    Se comporte comme un Path (on peut faire DOCS / "x.pdf", DOCS.glob(...), etc.)."""
    def __init__(self, sub=""):
        self.sub = sub

    def _p(self):
        base = g.get("docs_dir") if has_request_context() else None
        base = base or ROOT_DOCS
        return base / self.sub if self.sub else base

    def __getattr__(self, name):
        return getattr(self._p(), name)

    def __truediv__(self, other):
        return self._p() / other

    def __fspath__(self):
        return os.fspath(self._p())

    def __str__(self):
        return str(self._p())


DOCS = _UserDir()
# Le PDF d'origine n'est JAMAIS modifié. Votre travail en cours est un « brouillon » enregistré à part,
# automatiquement ; le PDF final n'est fabriqué que quand vous le téléchargez.
PROJECTS = _UserDir(".brouillons")  # un fichier .json par document (vos modifications en cours)
CACHE = _UserDir(".cache")          # miniatures de la page d'accueil (recalculables à tout moment)

DOSSIERS = _UserDir(".dossiers.json")          # nom du document -> {"dossier": "année/matière/chapitre", "source": "deepwell:…"}
CLE_FILE = ROOT_DOCS / ".cle_integration"        # clé secrète qui autorise DeepWell à déposer des documents (voir plus bas)

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


SSO_DAYS = 3  # une connexion venue de DeepWell est revérifiée (un aller-retour invisible si DeepWell est toujours connecté) au bout de ce délai


def _dw_session():
    """Les infos du compte DeepWell connecté (id, nom, rôle), si la session vient de DeepWell et n'est pas trop ancienne."""
    d = session.get("dw")
    if isinstance(d, dict) and d.get("id") and time.time() - float(session.get("dwt", 0)) < SSO_DAYS * 86400:
        return d
    return None


def _logged_in():
    return (session.get("u") == AUTH_USER and session.get("v") == PW_VERSION) or bool(_dw_session())


# ---- Espaces : chaque compte DeepWell a ses propres documents. Le premier administrateur qui se connecte reprend les documents
# déjà présents (dossier racine) ; ensuite chaque compte a son dossier .espaces/<identifiant>. La connexion locale de secours = espace racine.
OWNER_FILE = ROOT_DOCS / ".proprio"
LINK_FILE = ROOT_DOCS / ".deepwell_url"


def space_for(uid, role):
    uid = re.sub(r"[^A-Za-z0-9_-]", "", str(uid or ""))[:80]
    if not uid:
        return ROOT_DOCS
    try:
        owner = OWNER_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        owner = ""
    if not owner and role == "admin":
        OWNER_FILE.write_text(uid, encoding="utf-8")
        owner = uid
    if uid == owner:
        return ROOT_DOCS
    d = ROOT_DOCS / ".espaces" / uid
    d.mkdir(parents=True, exist_ok=True)
    return d


def deepwell_url():
    """Adresse de DeepWell (communiquée par DeepWell lui-même, avec la clé d'intégration) ; vide = connexion locale seulement."""
    try:
        u = LINK_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return u if re.match(r"^https?://[^\s/]+$", u) else ""


@app.before_request
def pick_space():
    d = _dw_session()
    if d:
        g.docs_dir = space_for(d["id"], d.get("role"))


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


# ---- Arborescence : dossiers imbriqués, façon écran d'accueil. Un dossier = un chemin « A/B/C » ; les dossiers vides sont notés dans .arbo.json.
ARBO = _UserDir(".arbo.json")
ROOT_SCOLAIRE = "Scolaire"  # dossier où DeepWell range les cours (année / matière / chapitre)


def norm_path(s):
    parts = [re.sub(r"\s+", " ", x).strip()[:80] for x in re.split(r"[/\\]", str(s or ""))]
    return "/".join(x for x in parts if x and x not in (".", ".."))[:300]


def read_arbo():
    try:
        d = json.loads(ARBO.read_text(encoding="utf-8"))
        return sorted({norm_path(x) for x in d.get("folders", []) if norm_path(x)}) if isinstance(d, dict) else []
    except (OSError, ValueError):
        return []


def write_arbo(folders):
    tmp = ARBO.with_suffix(".tmp")
    tmp.write_text(json.dumps({"folders": sorted(set(folders))}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ARBO)


def remember(path):
    """Un dossier qui contient (ou contenait) des documents reste affiché même vide : on le note."""
    path = norm_path(path)
    if path and path not in read_arbo():
        write_arbo(read_arbo() + [path])


def ancestors(path):
    parts = path.split("/") if path else []
    return ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]


def all_folders():
    """Tous les dossiers : ceux créés à la main, leurs parents, et ceux où se trouve au moins un document."""
    out = set()
    for f in read_arbo():
        out.update(ancestors(f))
    for info in read_dossiers().values():
        out.update(ancestors(norm_path(info.get("dossier", ""))))
    return out


def rewrite_paths(fn):
    """Applique fn(chemin) -> nouveau chemin (ou None pour retirer) aux dossiers notés et au dossier de chaque document."""
    write_arbo([n for n in (fn(f) for f in read_arbo()) if n])
    m = read_dossiers()
    for info in m.values():
        if "dossier" in info:
            info["dossier"] = fn(norm_path(info["dossier"])) or ""
    write_dossiers(m)


def migrate_dossiers():
    """Une fois au démarrage : séparateurs « / » uniformes, documents de DeepWell sous « Scolaire », le dossier « Scolaire » existe."""
    m = read_dossiers()
    for info in m.values():
        d = norm_path(info.get("dossier", ""))
        if str(info.get("source", "")).startswith("deepwell:") and d and d.split("/")[0] != ROOT_SCOLAIRE:
            d = f"{ROOT_SCOLAIRE}/{d}"
        info["dossier"] = d
        remember(d)
    write_dossiers(m)
    if ROOT_SCOLAIRE not in read_arbo():
        write_arbo(read_arbo() + [ROOT_SCOLAIRE])


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
    if p in ("/api/integration/ping", "/api/integration/docs", "/api/integration/logo", "/api/integration/link", "/api/integration/credits"):  # DeepWell (de serveur à serveur) : clé secrète au lieu du cookie
        return None if _key_ok(request.remote_addr or "?") else (jsonify(error="Clé d'intégration refusée"), 401)
    if p in ("/login", "/api/login", "/api/me", "/healthz", "/sso/callback") or p.startswith("/static/"):
        return None
    if _logged_in():
        return None
    if p.startswith("/api/"):
        return jsonify(error="Connexion requise"), 401
    return redirect("/login")

# ---------- Compression et cache des fichiers du site ----------
_GZ = {}  # (chemin, date, taille) -> version compressée des fichiers statiques (JS/CSS/HTML), calculée une seule fois
_GZ_TYPES = ("text/", "application/javascript", "application/json", "image/svg+xml")


@app.after_request
def compress_and_cache(resp):
    p = request.path
    if p.startswith("/static/vendor/") and resp.status_code == 200:
        resp.headers["Cache-Control"] = "public, max-age=86400"  # PDF.js (version figée dans l'image) : 1 jour sans revalider
    if (resp.status_code != 200 or request.method != "GET" or resp.headers.get("Content-Encoding")
            or "gzip" not in request.headers.get("Accept-Encoding", "") or not (resp.mimetype or "").startswith(_GZ_TYPES)
            or "attachment" in resp.headers.get("Content-Disposition", "")):
        return resp
    static = p.startswith("/static/") or p in ("/", "/login")
    try:
        resp.direct_passthrough = False
        body = resp.get_data()
    except Exception:
        return resp
    if len(body) < 1024:
        return resp
    key = (p, len(body), hash(body)) if static else None
    z = _GZ.get(key) if key else None
    if z is None:
        z = gzip.compress(body, compresslevel=9 if static else 5, mtime=0)
        if key:
            if len(_GZ) >= 60:
                _GZ.pop(next(iter(_GZ)))
            _GZ[key] = z
    resp.set_data(z)
    resp.headers["Content-Encoding"] = "gzip"
    resp.headers["Content-Length"] = str(len(z))
    resp.vary.add("Accept-Encoding")
    return resp


# Types d'annotations gérés par ce site (les autres, par exemple les liens, ne sont jamais touchés)
MANAGED = [
    pymupdf.PDF_ANNOT_HIGHLIGHT, pymupdf.PDF_ANNOT_TEXT, pymupdf.PDF_ANNOT_FREE_TEXT,
    pymupdf.PDF_ANNOT_SQUARE, pymupdf.PDF_ANNOT_CIRCLE, pymupdf.PDF_ANNOT_LINE,
    pymupdf.PDF_ANNOT_POLYGON,  # seulement ceux créés ici (les triangles)
    pymupdf.PDF_ANNOT_INK,      # seulement ceux créés ici (le crayon)
]
# La mise en page est rangée dans chaque annotation sous cette étiquette, pour la retrouver
# exactement quand on rouvre le PDF.
TAG = "annotpdf:"
FONTS = {"helv", "tiro", "cour"} | set(pe.CUSTOM)  # sans empattement, serif, machine à écrire + polices livrées avec le site
BOX_SHAPES = {"rect", "ellipse", "triangle"}
SHAPES = BOX_SHAPES | {"line", "arrow", "pen"}
MAX_PEN_POINTS = 4000
DEFAULT_TEXT = {"font": "helv", "size": 14, "color": "#000000", "align": 0, "fill": None, "border": False, "lh": 1.2}
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
    zc = 0  # rang d'empilement : l'ordre des annotations dans le PDF (la dernière est au-dessus)
    for page in doc:
        n = page.number + 1
        for a in page.annots(types=MANAGED):
            zc += 1
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
                                  "paras": paras, "z": zc, **style})
            else:  # Square, Circle, Line, Polygon
                if kind in ("Polygon", "Ink") and not (meta and meta.get("kind") in ("triangle", "pen")):
                    continue  # un polygone ou un tracé venu d'ailleurs : on n'y touche pas
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
                item = {"page": n, "kind": s["kind"], "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                        "stroke": s.get("stroke", "#e03131"), "width": s.get("width", 2),
                        "fill": s.get("fill"), "z": zc}
                if s["kind"] == "pen":
                    item["pts"] = s.get("pts") or []
                shapes.append(item)
    return highlights, notes, textboxes, shapes


def clear_managed(doc):
    """Retire les annotations des types gérés (elles seront réécrites depuis le navigateur)."""
    for page in doc:
        for a in list(page.annots(types=MANAGED)):
            if a.type[1] in ("Polygon", "Ink") and not meta_of(a):
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
    if kind == "pen":  # tracé à main levée : une suite de points
        pts = [(float(p[0]), float(p[1])) for p in (s.get("pts") or [])[:MAX_PEN_POINTS] if isinstance(p, (list, tuple)) and len(p) >= 2]
        if len(pts) < 2:
            return
        pts = [(round(x, 1), round(y, 1)) for x, y in pts]
        a = page.add_ink_annot([pts])
        a.set_colors(stroke=hex_to_rgb(stroke))
        a.set_border(width=width)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        a.set_info(subject=TAG + json.dumps({"kind": "pen", "stroke": stroke, "width": width, "fill": None,
                                             "rect": [min(xs), min(ys), max(xs), max(ys)], "pts": pts}))
        a.update()
        return
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

    # Textes et formes dans un seul ordre d'empilement (champ « z » : le plus grand est au-dessus ;
    # sans « z », l'ordre reçu est conservé, formes au-dessus des textes comme avant).
    stack = [("t", t) for t in payload.get("textboxes", [])] + [("s", s) for s in payload.get("shapes", [])]

    def zkey(entry):
        try:
            return float(entry[1].get("z"))
        except (TypeError, ValueError):
            return float("inf") if entry[0] == "s" else float("-inf")  # pas de z : ancien comportement
    stack.sort(key=zkey)  # tri stable

    for kind, t in stack:
        if kind == "s":
            page = page_of(t)
            if page is not None:
                add_shape(page, t)
            continue
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
            "lh": min(max(float(t.get("lh", 1.2)), 0.8), 3.0),
        }
        rect = pymupdf.Rect(t["x0"], t["y0"], t["x1"], t["y1"])
        a = pe.write_text_annot(doc, page, rect, paras, style, ctx)
        a.set_info(subject=TAG + json.dumps({**style, "rect": list(a.rect), "paras": paras}))

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
    dw = deepwell_url()
    if dw and request.args.get("local") != "1":  # compte unique : on se connecte sur DeepWell, qui renvoie ici (/login?local=1 = connexion de secours)
        return redirect(f"{dw}/?pdm_return={quote(request.url_root, safe='')}")
    return send_from_directory("static", "login.html")


def _b64u(b):
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


@app.get("/sso/callback")
def sso_callback():
    """Retour de DeepWell : jeton signé (clé d'intégration), valable une minute, utilisable une seule fois."""
    ip = request.remote_addr or "?"
    bad = (jsonify(error="Connexion refusée"), 401)
    if _too_many_fails(ip):
        return bad
    try:
        body, sig = request.args.get("token", "").split(".")
        good = _b64u(hmac.new(integration_key().encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig.encode(), good.encode()):
            raise ValueError
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        now = time.time()
        if float(data["exp"]) < now or str(data["jti"]) in _SSO_SEEN:
            raise ValueError
        _SSO_SEEN[str(data["jti"])] = now
        for k in [k for k, t in _SSO_SEEN.items() if now - t > 300]:
            _SSO_SEEN.pop(k, None)
        uid = re.sub(r"[^A-Za-z0-9_-]", "", str(data["uid"]))
        if not uid:
            raise ValueError
    except Exception:
        _FAILS.setdefault(ip, []).append(time.time())
        return bad
    session.clear()
    session["dw"] = {"id": uid, "name": str(data.get("name") or "")[:80], "role": "admin" if data.get("role") == "admin" else "user"}
    session["dwt"] = time.time()
    session.permanent = True
    nxt = request.args.get("next", "/")
    return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else "/")


_SSO_SEEN = {}  # identifiants de jetons déjà utilisés


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
    d = _dw_session()
    return jsonify(auth=AUTH_ENABLED, logged=(not AUTH_ENABLED) or _logged_in(), days=SESSION_DAYS, sso=bool(d), name=(d or {}).get("name", ""))


@app.get("/api/releases")
def api_releases():
    return jsonify(version=VERSION, releases=RELEASES)


@app.get("/healthz")
def healthz():
    """Contrôle de santé pour Docker : le service répond et le dossier des documents est accessible."""
    ok = DOCS.is_dir() and os.access(DOCS, os.W_OK)
    return jsonify(status="ok" if ok else "erreur"), (200 if ok else 503)


_PAGES = {}  # (nom) -> (taille, date de modif, nombre de pages) : évite de rouvrir chaque PDF à chaque affichage de l'accueil


def _page_count(p, st):
    key = (st.st_size, st.st_mtime_ns)
    hit = _PAGES.get(str(p))
    if hit and hit[0] == key:
        return hit[1]
    n = 0
    try:
        d = pymupdf.open(p)
        n = d.page_count
        d.close()
    except Exception:
        return 0  # illisible : on ne mémorise pas (il pourra être réparé)
    _PAGES[str(p)] = (key, n)
    if len(_PAGES) > 5000:
        _PAGES.pop(next(iter(_PAGES)))
    return n


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
        pages = _page_count(p, st)
        items.append({"name": p.name, "size": st.st_size, "modified": modified, "draft": draft, "pages": pages,
                      "folder": norm_path((meta.get(p.name) or {}).get("dossier", ""))})
    for p in DOCS.glob("*.pdmdoc"):  # documents texte (façon Word)
        st = p.stat()
        items.append({"name": p.name, "size": st.st_size, "modified": st.st_mtime, "draft": False, "pages": 0, "kind": "text",
                      "folder": norm_path((meta.get(p.name) or {}).get("dossier", ""))})
    items.sort(key=lambda i: i["modified"], reverse=True)
    if CACHE.exists():  # ménage : miniatures de documents qui n'existent plus (recalculables, donc sans risque)
        known = {i["name"].rsplit(".", 1)[0] for i in items}
        for t in CACHE.glob("*.png"):
            if t.stem not in known and not t.name.endswith(".tmp.png"):
                try:
                    t.unlink()
                except OSError:
                    pass
    return jsonify(items[:1000])


def _folder_item(path, docs_by_folder, folders):
    sub = [f for f in folders if "/" in f and f.rsplit("/", 1)[0] == path]
    return {"path": path, "name": path.rsplit("/", 1)[-1], "parent": path.rsplit("/", 1)[0] if "/" in path else "",
            "items": len(sub) + docs_by_folder.get(path, 0)}


@app.get("/api/folders")
def list_folders():
    """Tous les dossiers (avec le nombre d'éléments directs) : l'accueil affiche ceux du dossier courant."""
    folders = sorted(all_folders(), key=lambda x: x.lower())
    count = {}
    for info in read_dossiers().values():
        d = norm_path(info.get("dossier", ""))
        count[d] = count.get(d, 0) + 1
    return jsonify([_folder_item(f, count, folders) for f in folders])


def _folder_args():
    b = request.get_json(silent=True) or {}
    return b, norm_path(b.get("path"))


@app.post("/api/folders")
def folder_create():
    """Crée un dossier : « parent » (facultatif) + « name »."""
    b = request.get_json(silent=True) or {}
    name = norm_path(b.get("name"))
    if not name or "/" in name:
        return jsonify(error="Donnez un nom au dossier (sans « / »)."), 400
    path = norm_path(f"{norm_path(b.get('parent'))}/{name}")
    if path in all_folders():
        return jsonify(error=f"Le dossier « {name} » existe déjà ici."), 409
    write_arbo(read_arbo() + [path])
    return jsonify(ok=True, path=path)


@app.post("/api/folders/rename")
def folder_rename():
    b, path = _folder_args()
    name = norm_path(b.get("newName"))
    if path not in all_folders() or not name or "/" in name:
        return jsonify(error="Dossier introuvable ou nom invalide."), 400
    new = norm_path(f"{path.rsplit('/', 1)[0] if '/' in path else ''}/{name}")
    if new == path:
        return jsonify(ok=True, path=path)
    if new in all_folders():
        return jsonify(error=f"Le dossier « {name} » existe déjà ici."), 409
    rewrite_paths(lambda f: new + f[len(path):] if f == path or f.startswith(path + "/") else f)
    return jsonify(ok=True, path=new)


@app.post("/api/folders/move")
def folder_move():
    """Déplace un dossier (avec tout son contenu) dans « to » ('' = l'accueil)."""
    b, path = _folder_args()
    to = norm_path(b.get("to"))
    if path not in all_folders() or (to and to not in all_folders()):
        return jsonify(error="Dossier introuvable."), 404
    if to == path or to.startswith(path + "/"):
        return jsonify(error="Un dossier ne peut pas être déplacé dans lui-même."), 400
    new = norm_path(f"{to}/{path.rsplit('/', 1)[-1]}")
    if new == path:
        return jsonify(ok=True, path=path)
    if new in all_folders():
        return jsonify(error="Un dossier du même nom existe déjà à cet endroit."), 409
    rewrite_paths(lambda f: new + f[len(path):] if f == path or f.startswith(path + "/") else f)
    return jsonify(ok=True, path=new)


@app.post("/api/folders/delete")
def folder_delete():
    """Supprime le dossier SEUL : ses documents et sous-dossiers remontent dans le dossier parent (rien n'est perdu)."""
    b, path = _folder_args()
    if path not in all_folders():
        return jsonify(error="Dossier introuvable."), 404
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    def fn(f):
        if f == path:
            return parent or None
        return norm_path(f"{parent}/{f[len(path) + 1:]}") if f.startswith(path + "/") else f
    rewrite_paths(fn)
    return jsonify(ok=True)


@app.post("/api/docs/<name>/move")
def doc_move(name):
    p = text_file(name) if name.lower().endswith(".pdmdoc") else doc_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    to = norm_path((request.get_json(silent=True) or {}).get("folder"))
    m = read_dossiers()
    remember(m.get(p.name, {}).get("dossier", ""))
    m.setdefault(p.name, {})["dossier"] = to
    write_dossiers(m)
    remember(to)
    return jsonify(ok=True, folder=to)


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
    where = norm_path(request.form.get("folder"))  # le document arrive dans le dossier ouvert à l'écran
    if where:
        m = read_dossiers()
        m[name] = {**m.get(name, {}), "dossier": where}
        write_dossiers(m)
        remember(where)
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
    if name.lower().endswith(".pdmdoc"):
        return text_delete(name)
    p = doc_file(name)
    for f in (p, project_file(name), thumb_file(name)):
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass
    m = read_dossiers()
    old = m.pop(p.name, None)
    if old is not None:
        remember(old.get("dossier", ""))
        write_dossiers(m)
    return jsonify(ok=True)


# ---------------------------------------------------------------- Documents texte (façon Word / Google Docs)
def text_file(name):
    raw = re.sub(r"\.pdmdoc$", "", (name or "").strip(), flags=re.I)
    raw = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", raw).strip(" .")[:120] or "Document"
    if raw.upper() in RESERVED:
        raw = "_" + raw
    return DOCS / (raw + ".pdmdoc")


def unique_text_name(stem):
    p, n = text_file(stem), 1
    base = p.name[:-7]
    while p.exists():
        n += 1
        p = DOCS / f"{base} ({n}).pdmdoc"
    return p.name


def _text_thumb(p):
    t = CACHE / (p.stem + ".txt.png")
    if not t.exists() or t.stat().st_mtime < p.stat().st_mtime:
        CACHE.mkdir(parents=True, exist_ok=True)
        t.write_bytes(textdocs.pdf_first_page_png(textdocs.html_to_pdf(p.read_text(encoding="utf-8"))))
    return t


@app.post("/api/texts")
def text_create():
    b = request.get_json(silent=True) or {}
    name = unique_text_name(str(b.get("name") or "Document sans titre"))
    (DOCS / name).write_text("", encoding="utf-8")
    where = norm_path(b.get("folder"))
    if where:
        m = read_dossiers()
        m[name] = {"dossier": where}
        write_dossiers(m)
        remember(where)
    return jsonify(name=name)


@app.post("/api/texts/import")
def text_import():
    """Ouvre un fichier Word (.docx) : il devient un document texte modifiable."""
    f = request.files.get("file")
    if f is None or not (f.filename or "").lower().endswith(".docx"):
        return jsonify(error="Choisissez un fichier Word (.docx)."), 400
    try:
        html = textdocs.docx_to_html(f.read())
    except Exception:
        return jsonify(error="Ce fichier Word n'a pas pu être lu."), 400
    name = unique_text_name(re.sub(r"\.docx$", "", f.filename, flags=re.I))
    (DOCS / name).write_text(html, encoding="utf-8")
    where = norm_path(request.form.get("folder"))
    if where:
        m = read_dossiers()
        m[name] = {"dossier": where}
        write_dossiers(m)
        remember(where)
    return jsonify(name=name)


@app.get("/api/texts/<name>")
def text_get(name):
    p = text_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    return jsonify(name=p.name, html=p.read_text(encoding="utf-8"), modified=p.stat().st_mtime)


@app.put("/api/texts/<name>")
def text_put(name):
    p = text_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    html = textdocs.sanitize_html((request.get_json(silent=True) or {}).get("html", ""))
    tmp = p.with_suffix(".tmp")
    tmp.write_text(html, encoding="utf-8")
    tmp.replace(p)
    return jsonify(ok=True, saved=p.stat().st_mtime)


@app.post("/api/texts/<name>/rename")
def text_rename(name):
    p = text_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    want = str((request.get_json(silent=True) or {}).get("newName") or "").strip()
    if not want:
        return jsonify(error="Donnez un nom au document."), 400
    new = text_file(want)
    if new == p:
        return jsonify(ok=True, name=p.name)
    if new.exists():
        return jsonify(error=f"Un document « {new.name} » existe déjà"), 409
    p.rename(new)
    m = read_dossiers()
    if p.name in m:
        m[new.name] = m.pop(p.name)
        write_dossiers(m)
    return jsonify(ok=True, name=new.name)


def text_delete(name):
    p = text_file(name)
    p.unlink(missing_ok=True)
    (CACHE / (p.stem + ".txt.png")).unlink(missing_ok=True)
    m = read_dossiers()
    old = m.pop(p.name, None)
    if old is not None:
        remember(old.get("dossier", ""))
        write_dossiers(m)
    return jsonify(ok=True)


@app.get("/api/texts/<name>/thumb")
def text_thumb(name):
    p = text_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    try:
        png = _text_thumb(p).read_bytes()
    except Exception:
        return jsonify(error="Miniature impossible"), 404
    return Response(png, mimetype="image/png", headers={"Cache-Control": "max-age=60"})


@app.get("/api/texts/<name>/export")
def text_export(name):
    """?fmt=pdf (défaut) ou docx. Le document enregistré est exporté tel quel."""
    p = text_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    html, stem = p.read_text(encoding="utf-8"), p.name[:-7]
    from urllib.parse import quote
    if request.args.get("fmt") == "docx":
        data = textdocs.html_to_docx(html)
        mime, fn = "application/vnd.openxmlformats-officedocument.wordprocessingml.document", f"{stem}.docx"
    else:
        data, mime, fn = textdocs.html_to_pdf(html, stem), "application/pdf", f"{stem}.pdf"
    return Response(data, mimetype=mime, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(fn)}"})


@app.post("/api/texts/<name>/to-pdf")
def text_to_pdf(name):
    """Fabrique un vrai PDF dans Mes documents (à annoter ensuite), dans le même dossier. Le document texte reste modifiable."""
    p = text_file(name)
    if not p.exists():
        return jsonify(error="Document introuvable"), 404
    pdf = textdocs.html_to_pdf(p.read_text(encoding="utf-8"), p.name[:-7])
    out = unique_name(p.name[:-7] + ".pdf")
    (DOCS / out).write_bytes(pdf)
    where = norm_path((read_dossiers().get(p.name) or {}).get("dossier", ""))
    if where:
        m = read_dossiers()
        m[out] = {"dossier": where}
        write_dossiers(m)
    return jsonify(name=out)


# ---------------------------------------------------------------- Intégration DeepWell
@app.get("/api/integration/key")
def integration_key_get():
    """La clé à recopier dans DeepWell (Réglages → Google Drive → PDM). Réservé à l'utilisateur connecté."""
    return jsonify(key=integration_key())


@app.post("/api/integration/key/renew")
def integration_key_renew():
    """Nouvelle clé : l'ancienne cesse de fonctionner (à recopier dans DeepWell)."""
    return jsonify(key=integration_key(new=True))


CREDITS_FILE = ROOT_DOCS / ".credits.json"  # crédits des notes de version, écrits dans DeepWell et copiés ici


@app.post("/api/integration/credits")
def integration_credits():
    c = (request.get_json(silent=True) or {}).get("credits")
    if not isinstance(c, dict):
        return jsonify(error="Crédits invalides"), 400
    t = lambda v, n: v.strip()[:n] if isinstance(v, str) else ""
    out = {"lines": [{"label": t(l.get("label"), 60), "value": t(l.get("value"), 300)} for l in (c.get("lines") or [])[:20] if isinstance(l, dict)],
           "quote": t(c.get("quote"), 500), "quote_author": t(c.get("quote_author"), 100)}
    CREDITS_FILE.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    return jsonify(ok=True)


@app.get("/api/credits")
def api_credits():
    try:
        return jsonify(json.loads(CREDITS_FILE.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return jsonify(lines=[], quote="", quote_author="")


@app.post("/api/integration/link")
def integration_link():
    """DeepWell dit où il se trouve : c'est la seule adresse vers laquelle PDM renvoie pour se connecter."""
    u = str((request.get_json(silent=True) or {}).get("deepwell_url") or "").strip().rstrip("/")
    if not re.match(r"^https?://[^\s/]+$", u):
        return jsonify(error="Adresse invalide"), 400
    LINK_FILE.write_text(u, encoding="utf-8")
    return jsonify(ok=True)


@app.get("/api/integration/ping")
def integration_ping():
    return jsonify(ok=True, app="PDM", version=VERSION)


@app.post("/api/integration/docs")
def integration_add_doc():
    """DeepWell dépose un PDF de cours : champs « file », « folder » (année/matière/chapitre) et « source » (identifiant côté DeepWell,
    pour ne jamais créer de doublon si la demande est rejouée). Renvoie le nom du document dans PDM."""
    if request.form.get("user_id"):  # le document va dans l'espace de la personne qui l'a demandé dans DeepWell
        g.docs_dir = space_for(request.form.get("user_id"), request.form.get("user_role"))
    f = request.files.get("file")
    source = str(request.form.get("source") or "")[:200]
    folder = norm_path(request.form.get("folder"))
    if folder.split("/")[0] != ROOT_SCOLAIRE:
        folder = norm_path(f"{ROOT_SCOLAIRE}/{folder}")
    if f is None:
        return jsonify(error="Aucun fichier reçu"), 400
    m = read_dossiers()
    if source:
        for name, info in m.items():
            if info.get("source") == source and (DOCS / name).exists():
                return jsonify(name=name, folder=norm_path(info.get("dossier", "")), existing=True)
    data = f.read()
    try:
        annotations_json(data)
    except Exception:
        return jsonify(error="Ce fichier n'est pas un PDF valide"), 400
    name = unique_name(f.filename or "document.pdf")
    (DOCS / name).write_bytes(data)
    m[name] = {"dossier": folder, "source": source}
    write_dossiers(m)
    remember(folder)
    return jsonify(name=name, folder=folder, existing=False)


LOGO_FILE = ROOT_DOCS / ".logo_deepwell.svg"       # logo choisi dans DeepWell (fond de l'accueil) ; absent = logo de base


@app.post("/api/integration/logo")
def integration_logo():
    """DeepWell envoie l'icône choisie dans ses réglages (SVG). Vide = on revient au logo de base."""
    svg = str((request.get_json(silent=True) or {}).get("svg") or "")
    if not svg.strip():
        LOGO_FILE.unlink(missing_ok=True)
        return jsonify(ok=True, custom=False)
    low = svg.lower()
    if len(svg) > 4_000_000 or not low.lstrip().startswith("<svg") or "<script" in low or "<foreignobject" in low or re.search(r"\son\w+\s*=", low):
        return jsonify(error="Logo refusé"), 400
    LOGO_FILE.write_text(svg, encoding="utf-8")
    return jsonify(ok=True, custom=True)


@app.get("/home-logo.svg")
def home_logo():
    """Fond de l'accueil : le logo envoyé par DeepWell, sinon celui de base (static/home-bg.svg)."""
    path = LOGO_FILE if LOGO_FILE.exists() else Path(app.static_folder) / "home-bg.svg"
    resp = send_file(path, mimetype="image/svg+xml", conditional=True)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


migrate_dossiers()


if __name__ == "__main__":
    # Lancement local (lancer.bat). Sur le serveur, c'est gunicorn qui démarre le site (voir le Dockerfile).
    app.run(debug=(ENVIRONMENT != "production"), port=5000)
