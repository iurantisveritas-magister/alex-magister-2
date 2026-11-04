"""Ingesta con procedencia: archivo, ubicación, método y hash de integridad.
Niveles: TXT, DOCX, PDF nativo. PDF escaneado se DETECTA y se marca (OCR = nivel 2)."""
import hashlib, os
from dataclasses import dataclass

@dataclass
class Fragmento:
    documento: str
    ubicacion: str
    texto: str
    metodo: str

@dataclass
class Resultado:
    documento: str
    sha256: str
    fragmentos: list
    avisos: list

def _hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()

def _txt(path, nombre):
    with open(path, "rb") as f: raw = f.read()
    for enc in ("utf-8", "cp1252"):
        try:
            t = raw.decode(enc); break
        except UnicodeDecodeError:
            continue
    frs = [Fragmento(nombre, f"párr. {i}", p.strip(), f"txt/{enc}")
           for i, p in enumerate([x for x in t.split("\n\n") if x.strip()], 1)]
    return frs, []

def _docx(path, nombre):
    import docx
    d = docx.Document(path); frs = []; i = 0
    for p in d.paragraphs:
        if p.text.strip():
            i += 1; frs.append(Fragmento(nombre, f"párr. {i}", p.text.strip(), "docx/python-docx"))
    for ti, t in enumerate(d.tables, 1):
        for ri, row in enumerate(t.rows, 1):
            txt = " | ".join(c.text.strip() for c in row.cells)
            if txt.strip(" |"):
                frs.append(Fragmento(nombre, f"tabla {ti} fila {ri}", txt, "docx/python-docx"))
    return frs, ["DOCX no conserva número de página; la ubicación es párrafo/tabla."]

def _pdf(path, nombre):
    import pypdf
    r = pypdf.PdfReader(path); frs = []; avisos = []
    for n, pg in enumerate(r.pages, 1):
        t = (pg.extract_text() or "").strip()
        if len(t) < 20:
            avisos.append(f"p. {n}: sin texto extraíble (posible escaneo). Requiere OCR; NO se inventó contenido.")
        else:
            frs.append(Fragmento(nombre, f"p. {n}", t, "pdf/pypdf"))
    return frs, avisos

def ingerir(path):
    nombre = os.path.basename(path); ext = nombre.lower().rsplit(".", 1)[-1]
    f = {"txt": _txt, "docx": _docx, "pdf": _pdf}.get(ext)
    if not f:
        return Resultado(nombre, _hash(path), [], [f"formato .{ext} aún no soportado (nivel posterior)"])
    frs, av = f(path, nombre)
    return Resultado(nombre, _hash(path), frs, av)

def cargar_en_expediente(exp, path):
    """Registra el documento con texto por ubicación, para que el verificador exija cita exacta."""
    r = ingerir(path)
    exp.documentos[r.documento] = {fr.ubicacion: fr.texto for fr in r.fragmentos}
    exp.__dict__.setdefault("integridad", {})[r.documento] = r.sha256
    exp.__dict__.setdefault("avisos", []).extend(f"{r.documento}: {a}" for a in r.avisos)
    return r
