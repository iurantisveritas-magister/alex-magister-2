import unittest
from nucleo import *
def base():
    d={"a.txt":"el acto ocurrió a las 09:00","b.txt":"el acto ocurrió a las 09:30"}
    e=Expediente("E",documentos=d)
    e.hechos=[Hecho("H1","ev","hora","09:00","A",Fuente("a.txt","p1","a las 09:00")),
              Hecho("H2","ev","hora","09:30","B",Fuente("b.txt","p1","a las 09:30"))]
    e.pruebas=[Prueba("P1","documental","x",Fuente("a.txt","p1","el acto"))]
    return e
class T(unittest.TestCase):
    def test_contradiccion_detectada_y_no_resuelta(self):
        c=contradicciones(base()); self.assertEqual(len(c),1)
        self.assertIn("PENDIENTE",c[0]["resolucion"]); self.assertEqual(len(c[0]["versiones"]),2)
    def test_mismo_valor_no_es_contradiccion(self):
        e=base(); e.hechos[1].valor="09:00"; self.assertEqual(contradicciones(e),[])
    def test_eventos_distintos_no_se_comparan(self):
        e=base(); e.hechos[1].evento="otro"; self.assertEqual(contradicciones(e),[])
    def test_cita_inventada_se_bloquea(self):
        e=base(); e.hechos[0].fuente=Fuente("a.txt","p1","texto que no existe")
        self.assertTrue(any("NO aparece" in m for _,m in verificar(e)))
    def test_documento_inexistente(self):
        e=base(); e.hechos[0].fuente=Fuente("zzz.txt","p1","x")
        self.assertTrue(verificar(e))
    def test_lagunas(self):
        e=base(); l=lagunas(e)
        self.assertEqual(l["hechos_sin_prueba"],["H1","H2"]); self.assertEqual(l["pruebas_sin_hecho"],["P1"])
    def test_vinculo_sin_explicacion(self):
        e=base(); e.vinculos=[Vinculo("H1","P1"," ")]; self.assertTrue(verificar(e))
    def test_aceptar_inferencia_no_prueba(self):
        h=aceptar_inferencia_como_hipotesis(base().hechos[0]); self.assertNotEqual(h.estado,"confirmado_por_usuario")
unittest.main()
