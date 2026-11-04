from nucleo import *; from etapa2 import *
exp = Expediente("EXP-SINTETICO-001")
exp.hechos = [
 Hecho("H1","dilig","hora_inicio","09:00","Acta",Fuente("acta.txt","p.1","x")),
 Hecho("H2","dilig","hora_inicio","09:30","Inspectora",Fuente("declaracion.txt","p.1","x")),
 Hecho("H3","dilig","fotos_anexas","2","Acta",Fuente("acta.txt","p.1","x")),
 Hecho("H4","dilig","presencia_testigo","sí","Acta",Fuente("otro_escrito.txt","p.1","x"))]
exp.pruebas = [
 Prueba("P1","documental pública","Acta de inspección",Fuente("acta.txt","p.1","x")),
 Prueba("P2","testimonial","Declaración de la inspectora",Fuente("declaracion.txt","p.1","x")),
 Prueba("P3","documental electrónica","Fotografía F-01",Fuente("F-01.jpg","-","x"))]
print("ANTES de proponer:\n"+reporte(exp)+"\n")
for v in proponer_vinculos_por_procedencia(exp): print("propuesto:",v.hecho_id,"->",v.prueba_id)
print("\nDESPUÉS:\n"+reporte(exp))
confirmar(exp,"H1","P1"); confirmar(exp,"H2","P2")
print("\nTras confirmar H1-P1 y H2-P2:\n"+reporte(exp))
