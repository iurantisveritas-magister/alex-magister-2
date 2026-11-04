import os, io, json, time, tempfile, unittest, urllib.parse, docx
from reportlab.pdfgen import canvas
os.environ.update(ALEX_AUTOINIT="0", COOKIE_SECURE="1", SECRET_KEY="k" * 32, ADMIN_EMAIL="a@x.mx", ADMIN_PASSWORD="contraseña-larga-1")
for k in ("ALEX_PROVEEDOR", "ALEX_MODELO", "ALEX_ANTHROPIC_KEY"): os.environ.pop(k, None)
import app_web as W
from agente import ProveedorSimulado, ErrorProveedor

class Cli:
    def __init__(self): self.ck = ""
    def r(self, m, ruta, body=None, raw=None, hdr=None, csrf=True, ip="1.1.1.1"):
        b = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
        env = {"REQUEST_METHOD": m, "PATH_INFO": ruta, "CONTENT_LENGTH": str(len(b)), "wsgi.input": io.BytesIO(b), "REMOTE_ADDR": ip, "HTTP_COOKIE": self.ck}
        if csrf: env["HTTP_X_REQUESTED_WITH"] = "alex"
        for k, v in (hdr or {}).items(): env["HTTP_" + k.upper().replace("-", "_")] = v
        st = {}; out = W.application(env, lambda s, h: st.update(s=int(s.split()[0]), h=dict((a, b) for a, b in h) if not any(a == "Set-Cookie" for a, _ in h) else dict(h)))
        body = b"".join(out); cod = st["s"]
        if "Set-Cookie" in st["h"]: self.ck = st["h"]["Set-Cookie"].split(";")[0]
        try: return cod, json.loads(body), st["h"]
        except Exception: return cod, body, st["h"]
    def login(self, e="a@x.mx", p="contraseña-larga-1"): return self.r("POST", "/api/login", {"email": e, "password": p})
    def subir(self, i, nombre, datos): return self.r("POST", f"/api/expedientes/{i}/documentos", raw=datos, hdr={"X-Filename": urllib.parse.quote(nombre)})
    def esperar(self, i):
        for _ in range(100):
            c, d, _ = self.r("GET", f"/api/expedientes/{i}")
            if d["estado"] != "procesando": return d
            time.sleep(0.05)
        raise AssertionError("no terminó")

def nuevo_entorno():
    d = tempfile.mkdtemp(); os.environ["DATA_DIR"] = d; W._fallos.clear(); W._listo = False; W.iniciar()
    for k in ("ALEX_PROVEEDOR", "ALEX_MODELO", "ALEX_ANTHROPIC_KEY"): os.environ.pop(k, None)

def crear_usuario(email, pw):
    with W.db() as c: c.execute("INSERT INTO usuarios(email,pw,creado) VALUES(?,?,?)", (email, W.hash_pw(pw), "x"))

class T(unittest.TestCase):
    def setUp(self): nuevo_entorno()
    def test_login_y_seguridad_basica(self):
        c = Cli(); self.assertEqual(c.r("GET", "/api/expedientes")[0], 401)
        self.assertEqual(c.login(p="mala")[0], 401); cod, _, h = c.login(); self.assertEqual(cod, 200)
        self.assertIn("HttpOnly", h["Set-Cookie"]); self.assertIn("SameSite=Strict", h["Set-Cookie"]); self.assertIn("Secure", h["Set-Cookie"])
        self.assertIn("Content-Security-Policy", h); self.assertEqual(h["X-Frame-Options"], "DENY")
        self.assertEqual(c.r("POST", "/api/expedientes", csrf=False)[0], 403)      # sin cabecera anti-CSRF
        self.assertEqual(c.r("GET", "/api/expedientes")[0], 200)
    def test_bloqueo_por_intentos(self):
        c = Cli()
        for _ in range(5): c.login(p="mala")
        self.assertEqual(c.login()[0], 429)                       # ni la contraseña correcta pasa durante el bloqueo
        self.assertEqual(Cli().login(e="otro@x.mx", p="mala")[0], 401)   # otra cuenta no queda bloqueada
    def test_cookie_manipulada(self):
        c = Cli(); c.login(); c.ck = c.ck[:-3] + "AAA"; self.assertEqual(c.r("GET", "/api/yo")[0], 401)
    def test_aislamiento_entre_usuarios(self):
        crear_usuario("b@x.mx", "otra-contraseña-2"); a, b = Cli(), Cli(); a.login(); b.login("b@x.mx", "otra-contraseña-2")
        i = a.r("POST", "/api/expedientes/demo")[1]["id"]
        self.assertEqual(b.r("GET", f"/api/expedientes/{i}")[0], 404); self.assertEqual(b.r("GET", "/api/expedientes")[1], [])
        self.assertEqual(b.subir(i, "x.txt", b"hola")[0], 404); self.assertEqual(b.r("POST", f"/api/expedientes/{i}/analizar", {"consentimiento": True})[0], 404)
        self.assertEqual(b.r("POST", f"/api/expedientes/{i}/decision", {"tipo": "hecho", "id": "A-H1", "accion": "rechazar"})[0], 404)
        self.assertEqual(a.r("GET", f"/api/expedientes/{i}")[0], 200)
    def test_subida_formatos_y_limites(self):
        c = Cli(); c.login(); i = c.r("POST", "/api/expedientes")[1]["id"]
        self.assertEqual(c.subir(i, "a.txt", "Texto con acentos: inspección.".encode())[0], 201)
        t = tempfile.mkdtemp(); p = os.path.join(t, "d.docx"); d = docx.Document(); d.add_paragraph("Párrafo de prueba"); d.save(p)
        self.assertEqual(c.subir(i, "d.docx", open(p, "rb").read())[0], 201)
        p2 = os.path.join(t, "e.pdf"); k = canvas.Canvas(p2); k.rect(5, 5, 50, 50); k.save()
        cod, r, _ = c.subir(i, "escaneo.pdf", open(p2, "rb").read()); self.assertEqual(cod, 201); self.assertIn("OCR", r["avisos"][0])
        self.assertEqual(c.subir(i, "virus.exe", b"MZ")[0], 400); self.assertEqual(c.subir(i, "roto.docx", b"no es docx")[0], 400)
        self.assertEqual(c.subir(i, "../../etc/passwd.txt", b"x")[1]["nombre"], "....etcpasswd.txt")
        self.assertEqual(c.r("POST", f"/api/expedientes/{i}/documentos", raw=b"x" * 10, hdr={"X-Filename": "g.txt", "Content-Length": str(W.MAX_ARCHIVO + 1)})[0] in (201, 413), True)
        self.assertEqual(len(c.r("GET", f"/api/expedientes/{i}")[1]["documentos"]), 5)
    def test_demo_completo_con_consentimiento(self):
        c = Cli(); c.login(); i = c.r("POST", "/api/expedientes/demo")[1]["id"]
        self.assertEqual(c.r("POST", f"/api/expedientes/{i}/analizar", {})[0], 400)            # sin autorización expresa no corre
        self.assertEqual(c.r("GET", f"/api/expedientes/{i}")[1]["hechos"], [])
        self.assertEqual(c.r("POST", f"/api/expedientes/{i}/analizar", {"consentimiento": True})[0], 202)
        d = c.esperar(i); self.assertEqual(d["estado"], "listo", d["error"])
        self.assertEqual(len(d["hechos"]), 4); self.assertEqual(len(d["pruebas"]), 4)
        self.assertEqual(len(d["contradicciones"]), 1); self.assertEqual({v["valor"] for v in d["contradicciones"][0]["versiones"]}, {"09:00", "09:30"})
        cob = d["cobertura"]; self.assertEqual(cob["hechos"]["A-H4"][0], "SIN_PRUEBA"); self.assertEqual(cob["pruebas"]["A-P4"][0], "SIN_HECHO")
        self.assertEqual(d["errores_verificacion"], []); self.assertTrue(all(h["estado"] == "propuesto" for h in d["hechos"]))
        self.assertGreater(d["pendientes"], 0); self.assertTrue(d["envio"]["consentimiento_vigente"]); self.assertFalse(d["envio"]["externo"])
    def test_decisiones_humanas_y_auditoria(self):
        c = Cli(); c.login(); i = c.r("POST", "/api/expedientes/demo")[1]["id"]
        c.r("POST", f"/api/expedientes/{i}/analizar", {"consentimiento": True}); c.esperar(i)
        d = c.r("POST", f"/api/expedientes/{i}/decision", {"tipo": "hecho", "id": "A-H1", "accion": "confirmar"})[1]
        self.assertEqual(next(h for h in d["hechos"] if h["id"] == "A-H1")["estado"], "confirmado_por_usuario")
        d = c.r("POST", f"/api/expedientes/{i}/decision", {"tipo": "hecho", "id": "A-H2", "accion": "rechazar"})[1]
        self.assertEqual(d["contradicciones"], [])                      # al rechazar una versión ya no hay contradicción activa
        d = c.r("POST", f"/api/expedientes/{i}/decision", {"tipo": "vinculo", "id": "A-H1|A-P1", "accion": "confirmar"})[1]
        self.assertEqual(c.r("POST", f"/api/expedientes/{i}/decision", {"tipo": "hecho", "id": "NOEXISTE", "accion": "confirmar"})[0], 404)
        self.assertEqual(c.r("POST", f"/api/expedientes/{i}/decision", {"tipo": "otro", "id": "x", "accion": "confirmar"})[0], 400)
        with W.db() as db: n = db.execute("SELECT COUNT(*) FROM decisiones").fetchone()[0]
        self.assertEqual(n, 4)                                          # consentimiento + 3 decisiones
        c.r("POST", f"/api/expedientes/{i}/analizar", {}); d = c.esperar(i)       # reanalizar no revive lo rechazado ni duplica
        self.assertEqual(len(d["hechos"]), 4); self.assertEqual(next(h for h in d["hechos"] if h["id"] == "A-H2")["estado"], "rechazado")
    def test_sin_proveedor_real_no_analiza_documentos_propios(self):
        c = Cli(); c.login(); i = c.r("POST", "/api/expedientes")[1]["id"]; c.subir(i, "a.txt", b"texto")
        cod, r, _ = c.r("POST", f"/api/expedientes/{i}/analizar", {"consentimiento": True}); self.assertEqual(cod, 400); self.assertIn("proveedor", r["error"])
    def test_proveedor_real_flujo_y_cambio_de_modelo_invalida_consentimiento(self):
        os.environ.update(ALEX_PROVEEDOR="anthropic", ALEX_MODELO="m1", ALEX_ANTHROPIC_KEY="sk-x")
        resp = json.dumps({"hechos": [{"ref": "h", "evento": "e", "atributo": "a", "valor": "v", "afirma": "X", "documento": "a.txt", "ubicacion": "párr. 1", "fragmento": "texto de prueba"}], "pruebas": [], "vinculos": []})
        usado = {"n": 0}
        class Falso(ProveedorSimulado):
            def __init__(s): super().__init__([resp] * 3)
            def completar(s, a, b, m): usado["n"] += 1; return super().completar(a, b, m)
        W.FABRICA["anthropic"] = Falso
        try:
            c = Cli(); c.login(); i = c.r("POST", "/api/expedientes")[1]["id"]; c.subir(i, "a.txt", b"Un texto de prueba aqui")
            self.assertEqual(c.r("POST", f"/api/expedientes/{i}/analizar", {})[0], 400); self.assertEqual(usado["n"], 0)
            self.assertEqual(c.r("POST", f"/api/expedientes/{i}/analizar", {"consentimiento": True})[0], 202); d = c.esperar(i)
            self.assertEqual(d["estado"], "listo"); self.assertEqual(len(d["hechos"]), 1); self.assertEqual(usado["n"], 1)
            self.assertEqual((d["envio"]["proveedor"], d["envio"]["modelo"], d["envio"]["externo"]), ("anthropic", "m1", True))
            os.environ["ALEX_MODELO"] = "m2"                              # cambia el modelo: el consentimiento ya no vale
            self.assertFalse(c.r("GET", f"/api/expedientes/{i}")[1]["envio"]["consentimiento_vigente"])
            self.assertEqual(c.r("POST", f"/api/expedientes/{i}/analizar", {})[0], 400); self.assertEqual(usado["n"], 1)
        finally:
            from agente import ProveedorAnthropic; W.FABRICA["anthropic"] = ProveedorAnthropic
    def test_error_del_proveedor_se_muestra_sin_filtrar_datos(self):
        os.environ.update(ALEX_PROVEEDOR="openai", ALEX_MODELO="m", ALEX_OPENAI_KEY="sk-SECRETA")
        class Roto:
            def completar(s, a, b, m): raise ErrorProveedor(503)
        W.FABRICA["openai"] = Roto
        try:
            c = Cli(); c.login(); i = c.r("POST", "/api/expedientes")[1]["id"]; c.subir(i, "a.txt", b"texto")
            c.r("POST", f"/api/expedientes/{i}/analizar", {"consentimiento": True}); d = c.esperar(i)
            self.assertEqual(d["estado"], "error"); self.assertIn("503", d["error"]); self.assertNotIn("SECRETA", json.dumps(d))
        finally:
            from agente import ProveedorOpenAI; W.FABRICA["openai"] = ProveedorOpenAI
    def test_estaticos_y_salud(self):
        c = Cli(); cod, b, h = c.r("GET", "/"); self.assertEqual(cod, 200); self.assertIn(b"A-LEX MAGISTER", b)
        self.assertEqual(c.r("GET", "/static/app.js")[0], 200); self.assertEqual(c.r("GET", "/healthz")[1], {"ok": True})
        self.assertEqual(c.r("GET", "/static/../app_web.py")[0], 404)
    def test_contrasenas_en_scrypt(self):
        with W.db() as db: pw = db.execute("SELECT pw FROM usuarios").fetchone()[0]
        self.assertTrue(pw.startswith("scrypt$")); self.assertNotIn("contraseña", pw)
unittest.main()
