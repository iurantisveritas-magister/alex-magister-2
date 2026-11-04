import os, tempfile, unittest, docx
from reportlab.pdfgen import canvas
from nucleo import *
from ingesta import *
T = tempfile.mkdtemp()
def p(n): return os.path.join(T, n)
ACTA = "Acta simulada de inspección, de fecha 14 de abril de 2025: se asentó que la diligencia comenzó a las 09:00 horas."
DECL = "En una declaración simulada de la inspectora se afirmó que la diligencia comenzó a las 09:30 horas."
open(p("acta.txt"), "w", encoding="utf-8").write(ACTA)
d = docx.Document(); d.add_paragraph(DECL); d.save(p("declaracion.docx"))
c = canvas.Canvas(p("nativo.pdf")); c.drawString(72, 750, "Pagina uno con texto suficiente para extraer"); c.showPage()
c.drawString(72, 750, "Pagina dos tambien con texto suficiente aqui"); c.save()
c = canvas.Canvas(p("escaneo.pdf")); c.rect(50, 50, 200, 200); c.save()   # sin texto = simula escaneo

class T_(unittest.TestCase):
    def test_flujo_completo_txt_docx(self):
        e = Expediente("E"); cargar_en_expediente(e, p("acta.txt")); cargar_en_expediente(e, p("declaracion.docx"))
        e.hechos = [Hecho("H1","ev","hora","09:00","Acta",Fuente("acta.txt","párr. 1","comenzó a las 09:00 horas")),
                    Hecho("H2","ev","hora","09:30","Inspectora",Fuente("declaracion.docx","párr. 1","comenzó a las 09:30 horas"))]
        self.assertEqual(verificar(e), []); self.assertEqual(len(contradicciones(e)), 1)
    def test_pdf_paginas(self):
        r = ingerir(p("nativo.pdf")); self.assertEqual([f.ubicacion for f in r.fragmentos], ["p. 1","p. 2"])
    def test_pdf_escaneado_se_marca_no_se_inventa(self):
        r = ingerir(p("escaneo.pdf")); self.assertEqual(r.fragmentos, []); self.assertIn("OCR", r.avisos[0])
    def test_ubicacion_incorrecta_se_bloquea(self):
        e = Expediente("E"); cargar_en_expediente(e, p("nativo.pdf"))
        e.hechos = [Hecho("H","ev","x","1","A",Fuente("nativo.pdf","p. 2","Pagina uno con texto"))]
        self.assertTrue(any("NO aparece" in m for _, m in verificar(e)))   # el texto está en p.1, no en p.2
    def test_hash_estable_y_formato_no_soportado(self):
        self.assertEqual(ingerir(p("acta.txt")).sha256, ingerir(p("acta.txt")).sha256)
        open(p("x.mp3"), "wb").write(b"0"); self.assertIn("no soportado", ingerir(p("x.mp3")).avisos[0])
unittest.main()
