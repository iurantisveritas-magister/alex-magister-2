"""Uso:  python analizar.py CARPETA proveedor modelo      (proveedor: anthropic | openai)
Lee TODOS los .txt/.docx/.pdf de la carpeta (un solo expediente), muestra a qué proveedor y modelo se enviará la
información, pide consentimiento escrito, y imprime el informe. Nada se envía antes de tu 'SI'."""
import sys, os, json
from nucleo import Expediente, contradicciones, verificar
from ingesta import cargar_en_expediente
from etapa2 import cobertura, reporte, validar_tipos
from agente import *

def main():
    if len(sys.argv) != 4: print(__doc__); return
    carpeta, prov, modelo = sys.argv[1:4]
    proveedores = {"anthropic": ProveedorAnthropic(), "openai": ProveedorOpenAI()}
    if prov not in proveedores: print("Proveedor no válido. Usa: anthropic u openai"); return
    exp = Expediente(os.path.basename(os.path.abspath(carpeta)))
    for n in sorted(os.listdir(carpeta)):
        if n.lower().endswith((".txt", ".docx", ".pdf")): cargar_en_expediente(exp, os.path.join(carpeta, n))
    print("Documentos leídos:", ", ".join(exp.documentos) or "ninguno")
    for a in exp.avisos: print("AVISO:", a)
    cfg = Config(prov, modelo)
    print(f"\nTU INFORMACIÓN SE ENVIARÁ A: {prov.upper()}  |  modelo: {modelo}")
    if input("Escribe SI para autorizar este envío (otra cosa cancela): ").strip().upper() != "SI": print("Cancelado. No se envió nada."); return
    cons = Consentimiento(); cons.otorgar(exp.id, cfg)
    try: r = proponer(exp, cfg, cons, proveedores[prov])
    except (ErrorProveedor, RespuestaInvalida, RuntimeError) as e: print("No se pudo completar:", e); return
    print("\n" + reporte(exp))
    for c in contradicciones(exp): print("\nCONTRADICCIÓN PENDIENTE:", json.dumps(c, ensure_ascii=False, indent=1))
    print("\nPROPUESTAS RECHAZADAS POR EL VERIFICADOR:", r["rechazados"] or "ninguna")
    print("ERRORES DE VERIFICACIÓN:", verificar(exp) or "ninguno")
if __name__ == "__main__": main()
