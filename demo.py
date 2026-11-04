from nucleo import *
ACTA = ("Acta simulada de inspección, de fecha 14 de abril de 2025: se asentó que la diligencia comenzó "
        "a las 09:00 horas y que se anexaron dos fotografías digitales, identificadas como F-01 y F-02.")
DECL = "En una declaración simulada de la inspectora se afirmó que la diligencia comenzó a las 09:30 horas."
exp = Expediente("EXP-SINTETICO-001", documentos={"acta.txt": ACTA, "declaracion.txt": DECL})
exp.hechos = [
  Hecho("H1","diligencia-2025-04-14","hora_inicio","09:00","Acta",
        Fuente("acta.txt","p.1","la diligencia comenzó a las 09:00 horas")),
  Hecho("H2","diligencia-2025-04-14","hora_inicio","09:30","Inspectora",
        Fuente("declaracion.txt","p.1","la diligencia comenzó a las 09:30 horas")),
  Hecho("H3","diligencia-2025-04-14","fotos_anexas","2","Acta",
        Fuente("acta.txt","p.1","dos fotografías digitales, identificadas como F-01 y F-02")),
]
exp.pruebas = [Prueba("P1","documental","Acta de inspección",Fuente("acta.txt","p.1","Acta simulada de inspección"))]
exp.vinculos = [Vinculo("H1","P1","El acta es el documento donde consta esta hora"),
                Vinculo("H3","P1","El acta describe las fotografías anexas")]
import json
print("VERIFICACIÓN:", verificar(exp) or "sin errores")
print("CONTRADICCIONES:", json.dumps(contradicciones(exp), ensure_ascii=False, indent=2))
print("LAGUNAS:", lagunas(exp))
