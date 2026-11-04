"""A-LEX núcleo determinista (v0). Sin IA, sin heurística de texto libre.
Solo compara datos estructurados que alguien (usuario o agente) declaró con fuente.
Nunca resuelve una contradicción: la muestra con sus fuentes."""
from dataclasses import dataclass, field
from collections import defaultdict

@dataclass(frozen=True)
class Fuente:
    documento: str          # nombre del archivo
    ubicacion: str          # p. ej. "p. 1" o "min 03:20"
    fragmento: str          # texto literal tomado del documento

@dataclass
class Hecho:
    id: str
    evento: str             # etiqueta del evento (ej. "diligencia-2025-04-14")
    atributo: str           # qué se afirma (ej. "hora_inicio")
    valor: str              # valor declarado (ej. "09:00")
    afirma: str             # quién lo afirma
    fuente: Fuente
    estado: str = "declarado"   # declarado | propuesto | confirmado_por_usuario

@dataclass
class Prueba:
    id: str
    tipo: str               # documental, testimonial, pericial...
    descripcion: str
    fuente: Fuente
    estado: str = "propuesto"   # propuesto | confirmado_por_usuario | rechazado

@dataclass
class Vinculo:
    hecho_id: str
    prueba_id: str
    explicacion: str
    estado: str = "declarado"   # declarado | propuesto | confirmado

@dataclass
class Expediente:
    id: str
    documentos: dict = field(default_factory=dict)   # nombre -> texto completo
    hechos: list = field(default_factory=list)
    pruebas: list = field(default_factory=list)
    vinculos: list = field(default_factory=list)

def contradicciones(exp):
    """Mismo evento + mismo atributo + valores distintos. No decide cuál es cierto."""
    grupos = defaultdict(list)
    for h in exp.hechos:
        grupos[(h.evento, h.atributo)].append(h)
    out = []
    for (evento, atributo), hs in grupos.items():
        if len({h.valor for h in hs}) > 1:
            out.append({"tipo": "contradiccion_documental", "evento": evento, "atributo": atributo,
                        "versiones": [{"hecho": h.id, "valor": h.valor, "afirma": h.afirma,
                                       "estado": h.estado, "documento": h.fuente.documento, "ubicacion": h.fuente.ubicacion,
                                       "fragmento": h.fuente.fragmento} for h in hs],
                        "resolucion": "PENDIENTE: corresponde al usuario"})
    return out

def lagunas(exp):
    con_prueba = {v.hecho_id for v in exp.vinculos}
    con_hecho = {v.prueba_id for v in exp.vinculos}
    return {
        "hechos_sin_prueba": [h.id for h in exp.hechos if h.id not in con_prueba],
        "pruebas_sin_hecho": [p.id for p in exp.pruebas if p.id not in con_hecho],
    }

def _n(t):
    import re
    return re.sub(r"\s+", " ", t).strip()

def verificar(exp):
    """Bloquea lo no sustentado: el fragmento literal debe existir en el documento citado."""
    errores = []
    ids_h = {h.id for h in exp.hechos}; ids_p = {p.id for p in exp.pruebas}
    for item in list(exp.hechos) + list(exp.pruebas):
        f = item.fuente
        doc = exp.documentos.get(f.documento)
        if doc is None:
            errores.append((item.id, f"documento no existe en el expediente: {f.documento}"))
            continue
        if isinstance(doc, dict):   # {ubicacion: texto} -> se exige la ubicación citada
            if f.ubicacion not in doc:
                errores.append((item.id, f"la ubicación citada no existe en el documento: {f.ubicacion}"))
            elif _n(f.fragmento) not in _n(doc[f.ubicacion]):
                errores.append((item.id, "el fragmento citado NO aparece literalmente en esa ubicación"))
        elif _n(f.fragmento) not in _n(doc):
            errores.append((item.id, "el fragmento citado NO aparece literalmente en el documento"))
    for v in exp.vinculos:
        if v.hecho_id not in ids_h or v.prueba_id not in ids_p:
            errores.append((f"{v.hecho_id}->{v.prueba_id}", "vínculo apunta a un elemento inexistente"))
        if not v.explicacion.strip():
            errores.append((f"{v.hecho_id}->{v.prueba_id}", "vínculo sin explicación"))
    return errores

def aceptar_inferencia_como_hipotesis(h):
    """Aceptar nunca convierte en hecho probado."""
    h.estado = "hipotesis_de_trabajo"
    return h
