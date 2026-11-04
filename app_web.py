"""A-LEX MAGISTER 2 — aplicación web (WSGI, sin frameworks). Usuario y contraseña, aislamiento por usuario,
carga de documentos, análisis con consentimiento, revisión humana. Configuración solo por variables de entorno."""
import os, re, json, hmac, hashlib, base64, time, sqlite3, secrets, threading, tempfile, traceback, sys, urllib.parse
from contextlib import contextmanager
from dataclasses import asdict
from nucleo import Expediente, Hecho, Prueba, Vinculo, Fuente, contradicciones, verificar
from ingesta import ingerir
from etapa2 import cobertura, proponer_vinculos_por_procedencia
from agente import (Config, Consentimiento, ProveedorSimulado, ProveedorAnthropic, ProveedorOpenAI,
                    proponer, SinConsentimiento, ErrorProveedor, RespuestaInvalida)

WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
MAX_ARCHIVO = 20 * 1024 * 1024
MAX_DOCS = 30
EXT_OK = ("txt", "docx", "pdf")
FABRICA = {"anthropic": ProveedorAnthropic, "openai": ProveedorOpenAI}
LLAVES = {"anthropic": "ALEX_ANTHROPIC_KEY", "openai": "ALEX_OPENAI_KEY"}
_listo = False; _lock = threading.Lock(); _fallos = {}; _SECRETO = None

class HTTPError(Exception):
    def __init__(self, codigo, msg): self.codigo, self.msg = codigo, msg

# ---------- base de datos ----------
def _ruta_db(): return os.path.join(os.environ.get("DATA_DIR", "./data"), "alex.db")

@contextmanager
def db():
    c = sqlite3.connect(_ruta_db(), timeout=30); c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    try:
        yield c; c.commit()
    finally: c.close()

def hash_pw(pw, salt=None):
    salt = salt or secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${h.hex()}"

def verifica_pw(pw, almacenado):
    try:
        _, s, h = almacenado.split("$")
        n = hashlib.scrypt(pw.encode(), salt=bytes.fromhex(s), n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(n.hex(), h)
    except Exception: return False

_FALSO = hash_pw("no-existe-este-usuario")

def iniciar():
    global _listo, _SECRETO
    os.makedirs(os.environ.get("DATA_DIR", "./data"), exist_ok=True)
    _SECRETO = (os.environ.get("SECRET_KEY") or secrets.token_hex(32)).encode()
    if not os.environ.get("SECRET_KEY"): print("AVISO: SECRET_KEY no definida; las sesiones se pierden al reiniciar.", file=sys.stderr)
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS usuarios(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw TEXT NOT NULL, creado TEXT);
        CREATE TABLE IF NOT EXISTS expedientes(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES usuarios(id),
          nombre TEXT, creado TEXT, estado TEXT DEFAULT 'nuevo', error TEXT, datos_json TEXT, consent_huella TEXT, consent_fecha TEXT);
        CREATE TABLE IF NOT EXISTS documentos(id INTEGER PRIMARY KEY, exp_id INTEGER NOT NULL REFERENCES expedientes(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL, nombre TEXT, sha256 TEXT, bytes INTEGER, contenido_json TEXT, avisos_json TEXT, original BLOB, UNIQUE(exp_id,nombre));
        CREATE TABLE IF NOT EXISTS decisiones(id INTEGER PRIMARY KEY, exp_id INTEGER, user_id INTEGER, fecha TEXT, tipo TEXT, elemento TEXT, accion TEXT);
        """)
        c.execute("UPDATE expedientes SET estado='error', error='Interrumpido por un reinicio del servicio. Vuelva a analizar.' WHERE estado='procesando'")
        e, p = os.environ.get("ADMIN_EMAIL", "").strip().lower(), os.environ.get("ADMIN_PASSWORD", "")
        if e and p:
            if len(p) < 10: print("ERROR: ADMIN_PASSWORD debe tener al menos 10 caracteres; usuario no creado.", file=sys.stderr)
            elif not c.execute("SELECT 1 FROM usuarios WHERE email=?", (e,)).fetchone():
                c.execute("INSERT INTO usuarios(email,pw,creado) VALUES(?,?,?)", (e, hash_pw(p), _ahora()))
    _listo = True

def _ahora(): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

# ---------- sesión ----------
def _firmar(uid, dur=8 * 3600):
    p = f"{uid}.{int(time.time()) + dur}"
    return base64.urlsafe_b64encode(f"{p}.{hmac.new(_SECRETO, p.encode(), hashlib.sha256).hexdigest()}".encode()).decode()

def _leer(token):
    try:
        p, s = base64.urlsafe_b64decode(token.encode()).decode().rsplit(".", 1)
        if not hmac.compare_digest(hmac.new(_SECRETO, p.encode(), hashlib.sha256).hexdigest(), s): return None
        uid, exp = p.split(".")
        return int(uid) if int(exp) > time.time() else None
    except Exception: return None

# ---------- peticiones ----------
class Req:
    def __init__(self, env):
        self.env, self.metodo, self.ruta = env, env["REQUEST_METHOD"], env.get("PATH_INFO", "/")
        self.user_id = None; self.set_cookie = None
        ck = {}
        for parte in env.get("HTTP_COOKIE", "").split(";"):
            if "=" in parte: k, v = parte.strip().split("=", 1); ck[k] = v
        self.user_id = _leer(ck.get("alex_sess", ""))
    def header(self, n): return self.env.get("HTTP_" + n.upper().replace("-", "_"), "")
    @property
    def ip(self):
        if os.environ.get("TRUST_PROXY") == "1" and self.header("X-Forwarded-For"): return self.header("X-Forwarded-For").split(",")[0].strip()
        return self.env.get("REMOTE_ADDR", "?")
    def cuerpo(self, limite):
        n = int(self.env.get("CONTENT_LENGTH") or 0)
        if n > limite: raise HTTPError(413, "El archivo supera el tamaño máximo permitido.")
        return self.env["wsgi.input"].read(n) if n else b""
    def json(self):
        try:
            d = json.loads(self.cuerpo(1_000_000) or b"{}"); assert isinstance(d, dict); return d
        except HTTPError: raise
        except Exception: raise HTTPError(400, "Solicitud inválida.")

RUTAS = []
def ruta(metodo, patron, auth=True):
    def deco(f): RUTAS.append((metodo, re.compile("^" + patron + "$"), f, auth)); return f
    return deco

def _cookie(token, borrar=False):
    seg = "; Secure" if os.environ.get("COOKIE_SECURE", "1") == "1" else ""
    return f"alex_sess={'' if borrar else token}; HttpOnly; SameSite=Strict; Path=/; Max-Age={0 if borrar else 8*3600}{seg}"

# ---------- configuración de IA ----------
def _cfg_env(): return os.environ.get("ALEX_PROVEEDOR", "").lower(), os.environ.get("ALEX_MODELO", "")
def _real_ok():
    p, m = _cfg_env(); return p in FABRICA and bool(m) and bool(os.environ.get(LLAVES[p]))

def _envio(demo):
    """Devuelve (Config, proveedor, externo, motivo_no_disponible)."""
    if demo: return Config("simulado", "demostracion"), None, False, None
    if not _real_ok(): return None, None, True, "El servicio aún no tiene un proveedor de IA configurado. Use el expediente de ejemplo."
    p, m = _cfg_env(); return Config(p, m), FABRICA[p](), True, None

DEMO_DOCS = {
 "acta.txt": "Acta simulada de inspección, de fecha 14 de abril de 2025: se asentó que la diligencia comenzó a las 09:00 horas y que se anexaron dos fotografías digitales, identificadas como F-01 y F-02.",
 "declaracion.txt": "En una declaración simulada de la inspectora se afirmó que la diligencia comenzó a las 09:30 horas.",
 "escrito_partes.txt": "La parte quejosa manifiesta que el testigo T-01 estuvo presente durante toda la diligencia.",
 "ofrecimiento_pruebas.txt": "Se ofrece la pericial en materia de grafoscopía respecto de la firma del acta."}
def _a(ev, at, v, af, doc, fr, ref): return {"ref": ref, "evento": ev, "atributo": at, "valor": v, "afirma": af, "documento": doc, "ubicacion": "párr. 1", "fragmento": fr}
def _p(ref, tipo, d, doc, fr): return {"ref": ref, "tipo": tipo, "descripcion": d, "documento": doc, "ubicacion": "párr. 1", "fragmento": fr}
DEMO_RESPUESTA = json.dumps({"hechos": [
  _a("diligencia-2025-04-14", "hora_inicio", "09:00", "Acta", "acta.txt", "la diligencia comenzó a las 09:00 horas", "h1"),
  _a("diligencia-2025-04-14", "hora_inicio", "09:30", "Inspectora", "declaracion.txt", "la diligencia comenzó a las 09:30 horas", "h2"),
  _a("diligencia-2025-04-14", "fotografías_anexas", "2 (F-01 y F-02)", "Acta", "acta.txt", "dos fotografías digitales, identificadas como F-01 y F-02", "h3"),
  _a("diligencia-2025-04-14", "presencia_del_testigo_T-01", "toda la diligencia", "Parte quejosa", "escrito_partes.txt", "el testigo T-01 estuvo presente durante toda la diligencia", "h4")],
 "pruebas": [
  _p("p1", "documental pública", "Acta de inspección", "acta.txt", "Acta simulada de inspección"),
  _p("p2", "testimonial", "Declaración de la inspectora", "declaracion.txt", "declaración simulada de la inspectora"),
  _p("p3", "documental electrónica", "Fotografías F-01 y F-02", "acta.txt", "dos fotografías digitales, identificadas como F-01 y F-02"),
  _p("p4", "pericial", "Pericial en grafoscopía sobre la firma del acta", "ofrecimiento_pruebas.txt", "la pericial en materia de grafoscopía")],
 "vinculos": [{"hecho": "h1", "prueba": "p1", "explicacion": "El acta consigna la hora de inicio."},
              {"hecho": "h2", "prueba": "p2", "explicacion": "La declaración consigna la hora de inicio que afirma la inspectora."},
              {"hecho": "h3", "prueba": "p3", "explicacion": "El acta describe las fotografías que se anexaron."}]}, ensure_ascii=False)

# ---------- carga y guardado ----------
def _fila(c, user_id, exp_id):
    r = c.execute("SELECT * FROM expedientes WHERE id=? AND user_id=?", (exp_id, user_id)).fetchone()
    if not r: raise HTTPError(404, "Expediente no encontrado.")   # mismo error exista o no: no revela expedientes ajenos
    return r

def _exp(c, r):
    e = Expediente(f"{r['user_id']}:{r['id']}")
    for d in c.execute("SELECT nombre, contenido_json FROM documentos WHERE exp_id=? AND user_id=?", (r["id"], r["user_id"])):
        e.documentos[d["nombre"]] = json.loads(d["contenido_json"])
    d = json.loads(r["datos_json"] or "{}")
    e.hechos = [Hecho(**{**x, "fuente": Fuente(**x["fuente"])}) for x in d.get("hechos", [])]
    e.pruebas = [Prueba(**{**x, "fuente": Fuente(**x["fuente"])}) for x in d.get("pruebas", [])]
    e.vinculos = [Vinculo(**x) for x in d.get("vinculos", [])]
    e.auditoria = d.get("auditoria", []); return e, d

def _guardar(c, r_id, e, d, **extra):
    d = {**d, "hechos": [asdict(h) for h in e.hechos], "pruebas": [asdict(p) for p in e.pruebas],
         "vinculos": [asdict(v) for v in e.vinculos], "auditoria": e.__dict__.get("auditoria", []), **extra}
    c.execute("UPDATE expedientes SET datos_json=? WHERE id=?", (json.dumps(d, ensure_ascii=False), r_id))

def _activos(e):
    a = Expediente(e.id, documentos=e.documentos)
    a.hechos = [h for h in e.hechos if h.estado != "rechazado"]; a.pruebas = [p for p in e.pruebas if p.estado != "rechazado"]
    hs, ps = {h.id for h in a.hechos}, {p.id for p in a.pruebas}
    a.vinculos = [v for v in e.vinculos if v.estado != "rechazado" and v.hecho_id in hs and v.prueba_id in ps]
    return a

def _detalle(c, r):
    e, d = _exp(c, r); a = _activos(e); demo = bool(d.get("demo"))
    cfg, _, externo, motivo = _envio(demo)
    vigente = bool(cfg) and r["consent_huella"] == cfg.huella(e.id)
    docs = [{"id": x["id"], "nombre": x["nombre"], "sha256": x["sha256"], "avisos": json.loads(x["avisos_json"] or "[]")}
            for x in c.execute("SELECT id,nombre,sha256,avisos_json FROM documentos WHERE exp_id=? ORDER BY id", (r["id"],))]
    pend = sum(1 for x in a.hechos + a.pruebas if x.estado == "propuesto") + sum(1 for v in a.vinculos if v.estado == "propuesto")
    return {"id": r["id"], "nombre": r["nombre"], "estado": r["estado"], "error": r["error"], "demo": demo, "documentos": docs,
            "envio": {"proveedor": cfg.proveedor if cfg else None, "modelo": cfg.modelo if cfg else None, "externo": externo,
                      "disponible": bool(cfg), "motivo": motivo, "consentimiento_vigente": vigente},
            "hechos": [asdict(h) for h in e.hechos], "pruebas": [asdict(p) for p in e.pruebas], "vinculos": [asdict(v) for v in e.vinculos],
            "contradicciones": contradicciones(a), "cobertura": cobertura(a), "errores_verificacion": verificar(a),
            "rechazados_verificador": d.get("rechazados", []), "pendientes": pend}

# ---------- análisis en segundo plano ----------
def _analizar(user_id, exp_id):
    try:
        with db() as c:
            r = _fila(c, user_id, exp_id); e, d = _exp(c, r)
        cfg, prov, _, motivo = _envio(bool(d.get("demo")))
        if not cfg: raise RuntimeError(motivo)
        if d.get("demo"): prov = ProveedorSimulado([DEMO_RESPUESTA])
        cons = Consentimiento()
        if r["consent_huella"]: cons._ok.add(r["consent_huella"])
        res = proponer(e, cfg, cons, prov)
        a = _activos(e); a.vinculos = e.vinculos; proponer_vinculos_por_procedencia(a)
        with db() as c:
            _guardar(c, exp_id, e, d, rechazados=res["rechazados"])
            c.execute("UPDATE expedientes SET estado='listo', error=NULL WHERE id=?", (exp_id,))
    except (SinConsentimiento, ErrorProveedor, RespuestaInvalida, RuntimeError) as ex:
        msg = "El proveedor de IA respondió con el error %s. Intente de nuevo más tarde." % ex.codigo if isinstance(ex, ErrorProveedor) else str(ex)
        with db() as c: c.execute("UPDATE expedientes SET estado='error', error=? WHERE id=?", (msg, exp_id))
    except Exception:
        traceback.print_exc(file=sys.stderr)
        with db() as c: c.execute("UPDATE expedientes SET estado='error', error='Error interno al analizar.' WHERE id=?", (exp_id,))

# ---------- rutas ----------
@ruta("GET", "/healthz", auth=False)
def _salud(rq): return 200, {"ok": True}

@ruta("POST", "/api/login", auth=False)
def _login(rq):
    d = rq.json(); email = str(d.get("email", "")).strip().lower(); pw = str(d.get("password", ""))
    clave = (rq.ip, email); n, desde = _fallos.get(clave, (0, time.time()))
    if time.time() - desde > 600: n, desde = 0, time.time()
    if n >= 5: raise HTTPError(429, "Demasiados intentos. Espere 10 minutos.")
    with db() as c: u = c.execute("SELECT * FROM usuarios WHERE email=?", (email,)).fetchone()
    if not verifica_pw(pw, u["pw"] if u else _FALSO) or not u:
        _fallos[clave] = (n + 1, desde); raise HTTPError(401, "Usuario o contraseña incorrectos.")
    _fallos.pop(clave, None); rq.set_cookie = _cookie(_firmar(u["id"])); return 200, {"email": u["email"]}

@ruta("POST", "/api/logout", auth=False)
def _logout(rq): rq.set_cookie = _cookie("", borrar=True); return 200, {"ok": True}

@ruta("GET", "/api/yo")
def _yo(rq):
    with db() as c: u = c.execute("SELECT email FROM usuarios WHERE id=?", (rq.user_id,)).fetchone()
    if not u: raise HTTPError(401, "Sesión inválida.")
    return 200, {"email": u["email"]}

@ruta("GET", "/api/expedientes")
def _lista(rq):
    with db() as c:
        return 200, [{"id": r["id"], "nombre": r["nombre"], "estado": r["estado"], "creado": r["creado"]}
                     for r in c.execute("SELECT id,nombre,estado,creado FROM expedientes WHERE user_id=? ORDER BY id DESC", (rq.user_id,))]

def _crear(c, user_id, nombre, demo=False):
    cur = c.execute("INSERT INTO expedientes(user_id,nombre,creado,datos_json) VALUES(?,?,?,?)",
                    (user_id, nombre, _ahora(), json.dumps({"demo": demo}))); return cur.lastrowid

@ruta("POST", "/api/expedientes")
def _nuevo(rq):
    with db() as c: return 201, {"id": _crear(c, rq.user_id, "Expediente " + time.strftime("%d/%m/%Y %H:%M"))}

def _guardar_doc(c, user_id, exp_id, nombre, datos):
    ext = nombre.lower().rsplit(".", 1)[-1] if "." in nombre else ""
    if ext not in EXT_OK: raise HTTPError(400, f"Formato .{ext or '?'} no soportado. Use: Word, PDF o TXT.")
    if c.execute("SELECT COUNT(*) FROM documentos WHERE exp_id=?", (exp_id,)).fetchone()[0] >= MAX_DOCS and \
       not c.execute("SELECT 1 FROM documentos WHERE exp_id=? AND nombre=?", (exp_id, nombre)).fetchone():
        raise HTTPError(400, f"Máximo {MAX_DOCS} documentos por expediente.")
    with tempfile.NamedTemporaryFile(suffix="." + ext, delete=False) as t: t.write(datos); ruta_t = t.name
    try: res = ingerir(ruta_t)
    except Exception: raise HTTPError(400, "No se pudo leer el archivo. Verifique que no esté dañado ni protegido con contraseña.")
    finally: os.unlink(ruta_t)
    c.execute("INSERT OR REPLACE INTO documentos(exp_id,user_id,nombre,sha256,bytes,contenido_json,avisos_json,original) VALUES(?,?,?,?,?,?,?,?)",
              (exp_id, user_id, nombre, res.sha256, len(datos), json.dumps({f.ubicacion: f.texto for f in res.fragmentos}, ensure_ascii=False),
               json.dumps(res.avisos, ensure_ascii=False), datos))
    return res

@ruta("POST", "/api/expedientes/demo")
def _demo(rq):
    with db() as c:
        i = _crear(c, rq.user_id, "Ejemplo sintético: inspección de 14 de abril de 2025", demo=True)
        for n, t in DEMO_DOCS.items(): _guardar_doc(c, rq.user_id, i, n, t.encode("utf-8"))
    return 201, {"id": i}

@ruta("GET", r"/api/expedientes/(\d+)")
def _ver(rq, i):
    with db() as c: return 200, _detalle(c, _fila(c, rq.user_id, int(i)))

@ruta("POST", r"/api/expedientes/(\d+)/documentos")
def _subir(rq, i):
    nombre = urllib.parse.unquote(rq.header("X-Filename")); nombre = re.sub(r"[\x00-\x1f\\/]", "", nombre).strip()[-150:]
    if not nombre: raise HTTPError(400, "Falta el nombre del archivo.")
    datos = rq.cuerpo(MAX_ARCHIVO)
    if not datos: raise HTTPError(400, "Archivo vacío.")
    with db() as c:
        r = _fila(c, rq.user_id, int(i))
        if r["estado"] == "procesando": raise HTTPError(409, "El expediente se está analizando; espere a que termine.")
        res = _guardar_doc(c, rq.user_id, r["id"], nombre, datos)
    return 201, {"nombre": nombre, "sha256": res.sha256, "avisos": res.avisos}

@ruta("POST", r"/api/expedientes/(\d+)/analizar")
def _analiza(rq, i):
    d = rq.json()
    with db() as c:
        r = _fila(c, rq.user_id, int(i)); e, dd = _exp(c, r)
        if not e.documentos: raise HTTPError(400, "Agregue al menos un documento.")
        cfg, _, _, motivo = _envio(bool(dd.get("demo")))
        if not cfg: raise HTTPError(400, motivo)
        h = cfg.huella(e.id)
        if r["consent_huella"] != h:
            if d.get("consentimiento") is not True: raise HTTPError(400, "Se requiere su autorización expresa para enviar el contenido al proveedor indicado.")
            c.execute("UPDATE expedientes SET consent_huella=?, consent_fecha=? WHERE id=?", (h, _ahora(), r["id"]))
            c.execute("INSERT INTO decisiones(exp_id,user_id,fecha,tipo,elemento,accion) VALUES(?,?,?,?,?,?)",
                      (r["id"], rq.user_id, _ahora(), "consentimiento", f"{cfg.proveedor}/{cfg.modelo}", "otorgado"))
        if c.execute("UPDATE expedientes SET estado='procesando', error=NULL WHERE id=? AND estado!='procesando'", (r["id"],)).rowcount == 0:
            raise HTTPError(409, "Ya se está analizando.")
    threading.Thread(target=_analizar, args=(rq.user_id, r["id"]), daemon=True).start()
    return 202, {"estado": "procesando"}

@ruta("POST", r"/api/expedientes/(\d+)/decision")
def _decide(rq, i):
    d = rq.json(); tipo, ident, acc = d.get("tipo"), str(d.get("id", "")), d.get("accion")
    if tipo not in ("hecho", "prueba", "vinculo") or acc not in ("confirmar", "rechazar"): raise HTTPError(400, "Solicitud inválida.")
    with db() as c:
        r = _fila(c, rq.user_id, int(i))
        if r["estado"] == "procesando": raise HTTPError(409, "El expediente se está analizando.")
        e, dd = _exp(c, r); hallado = None
        if tipo == "hecho": hallado = next((x for x in e.hechos if x.id == ident), None)
        elif tipo == "prueba": hallado = next((x for x in e.pruebas if x.id == ident), None)
        else: hallado = next((v for v in e.vinculos if f"{v.hecho_id}|{v.prueba_id}" == ident), None)
        if not hallado: raise HTTPError(404, "Elemento no encontrado.")
        hallado.estado = ("confirmado" if tipo == "vinculo" else "confirmado_por_usuario") if acc == "confirmar" else "rechazado"
        _guardar(c, r["id"], e, dd)
        c.execute("INSERT INTO decisiones(exp_id,user_id,fecha,tipo,elemento,accion) VALUES(?,?,?,?,?,?)", (r["id"], rq.user_id, _ahora(), tipo, ident, acc))
        return 200, _detalle(c, _fila(c, rq.user_id, int(i)))

# ---------- WSGI ----------
CSP = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
SEG = [("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"), ("Referrer-Policy", "no-referrer"),
       ("Content-Security-Policy", CSP), ("Strict-Transport-Security", "max-age=31536000; includeSubDomains")]
ESTATICOS = {"/": ("index.html", "text/html; charset=utf-8"), "/static/app.js": ("app.js", "application/javascript; charset=utf-8"),
             "/static/app.css": ("app.css", "text/css; charset=utf-8")}
MOTIVOS = {200: "OK", 201: "Created", 202: "Accepted", 400: "Bad Request", 401: "Unauthorized", 403: "Forbidden", 404: "Not Found",
           405: "Method Not Allowed", 409: "Conflict", 413: "Payload Too Large", 429: "Too Many Requests", 500: "Internal Server Error"}

def application(env, start):
    global _listo
    if not _listo:
        with _lock:
            if not _listo: iniciar()
    rq = Req(env); extra = []
    try:
        if rq.metodo == "GET" and rq.ruta in ESTATICOS:
            f, tipo = ESTATICOS[rq.ruta]; cuerpo = open(os.path.join(WEB, f), "rb").read()
            hdr = [("Content-Type", tipo), ("Cache-Control", "no-cache")]; cod = 200
        else:
            handler = None
            for m, rx, fn, auth in RUTAS:
                mt = rx.match(rq.ruta)
                if mt and m == rq.metodo: handler = (fn, mt.groups(), auth); break
            if not handler: raise HTTPError(404, "No encontrado.")
            fn, grupos, auth = handler
            if rq.metodo not in ("GET", "HEAD") and rq.header("X-Requested-With") != "alex": raise HTTPError(403, "Solicitud no permitida.")
            if auth and not rq.user_id: raise HTTPError(401, "Inicie sesión.")
            cod, obj = fn(rq, *grupos); cuerpo = json.dumps(obj, ensure_ascii=False).encode()
            hdr = [("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store")]
    except HTTPError as ex:
        cod = ex.codigo; cuerpo = json.dumps({"error": ex.msg}, ensure_ascii=False).encode()
        hdr = [("Content-Type", "application/json; charset=utf-8"), ("Cache-Control", "no-store")]
    except Exception:
        traceback.print_exc(file=sys.stderr); cod = 500
        cuerpo = json.dumps({"error": "Error interno."}).encode(); hdr = [("Content-Type", "application/json")]
    if rq.set_cookie: hdr.append(("Set-Cookie", rq.set_cookie))
    start(f"{cod} {MOTIVOS.get(cod, 'OK')}", hdr + SEG + [("Content-Length", str(len(cuerpo)))])
    return [cuerpo]

if os.environ.get("ALEX_AUTOINIT", "1") == "1": iniciar()
