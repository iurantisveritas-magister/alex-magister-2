"""Etapa 2: relación hecho <-> prueba. Determinista. Todo lo que el sistema propone queda 'propuesto'
hasta que el usuario lo confirme. Nada se vincula por parecido de texto."""
from nucleo import Vinculo

TIPOS = ["confesional", "declaración de parte", "testimonial", "documental pública", "documental privada",
         "pericial", "documental electrónica", "avance de la ciencia", "inspección", "otra (especificar)"]
ROT_HECHO = "Hecho sin correlación de prueba: analizar su pertinencia"
ROT_PRUEBA = "Prueba sin hecho vinculado: analizar su pertinencia"

def validar_tipos(exp):
    return [(p.id, f"tipo de prueba fuera del catálogo: {p.tipo!r}") for p in exp.pruebas if p.tipo not in TIPOS]

def proponer_vinculos_por_procedencia(exp):
    """Regla estructural (no de texto): si el hecho fue extraído del MISMO documento que constituye
    la prueba, se propone el vínculo. Se marca 'propuesto' y no se duplica uno ya existente."""
    existentes = {(v.hecho_id, v.prueba_id) for v in exp.vinculos}
    nuevos = []
    for h in exp.hechos:
        for p in exp.pruebas:
            if h.fuente.documento == p.fuente.documento and (h.id, p.id) not in existentes:
                nuevos.append(Vinculo(h.id, p.id,
                    f"Procedencia: el hecho se extrajo de {h.fuente.documento}, que es el documento de la prueba.",
                    "propuesto"))
    exp.vinculos.extend(nuevos)
    return nuevos

def confirmar(exp, hecho_id, prueba_id):
    for v in exp.vinculos:
        if (v.hecho_id, v.prueba_id) == (hecho_id, prueba_id):
            v.estado = "confirmado"; return v
    raise KeyError("vínculo inexistente")

def cobertura(exp):
    por_h = {h.id: [] for h in exp.hechos}; por_p = {p.id: [] for p in exp.pruebas}
    for v in exp.vinculos:
        if v.hecho_id in por_h and v.prueba_id in por_p:
            por_h[v.hecho_id].append((v.prueba_id, v.estado)); por_p[v.prueba_id].append((v.hecho_id, v.estado))
    hechos = {}
    for hid, lst in por_h.items():
        if not lst: hechos[hid] = ("SIN_PRUEBA", ROT_HECHO)
        elif all(e == "propuesto" for _, e in lst): hechos[hid] = ("POR_CONFIRMAR", "Solo hay vínculos propuestos")
        else: hechos[hid] = ("VINCULADO", ", ".join(p for p, _ in lst))
    pruebas = {}
    for pid, lst in por_p.items():
        if not lst: pruebas[pid] = ("SIN_HECHO", ROT_PRUEBA)
        elif all(e == "propuesto" for _, e in lst): pruebas[pid] = ("POR_CONFIRMAR", "Solo hay vínculos propuestos")
        else: pruebas[pid] = ("VINCULADA", ", ".join(h for h, _ in lst))
    return {"hechos": hechos, "pruebas": pruebas}

def reporte(exp):
    c = cobertura(exp); L = ["== HECHOS =="]
    for h in exp.hechos: L.append(f"{h.id} [{h.atributo}={h.valor}] -> {c['hechos'][h.id][0]}: {c['hechos'][h.id][1]}")
    L.append("== PRUEBAS ==")
    for p in exp.pruebas: L.append(f"{p.id} ({p.tipo}: {p.descripcion}) -> {c['pruebas'][p.id][0]}: {c['pruebas'][p.id][1]}")
    return "\n".join(L)
