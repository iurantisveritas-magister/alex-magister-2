import unittest
from nucleo import *; from etapa2 import *
def base():
    e=Expediente("E")
    e.hechos=[Hecho("H1","ev","a","1","X",Fuente("a.txt","p1","x")),Hecho("H2","ev","b","2","X",Fuente("b.txt","p1","x")),
              Hecho("H3","ev","c","3","X",Fuente("zzz.txt","p1","x"))]
    e.pruebas=[Prueba("P1","documental pública","a",Fuente("a.txt","p1","x")),Prueba("P2","testimonial","b",Fuente("b.txt","p1","x")),
               Prueba("P3","pericial","c",Fuente("c.pdf","p1","x"))]
    return e
class T(unittest.TestCase):
    def test_detecta_hecho_sin_prueba_y_prueba_sin_hecho(self):
        c=cobertura(base()); self.assertEqual(c["hechos"]["H1"][0],"SIN_PRUEBA"); self.assertEqual(c["pruebas"]["P3"][0],"SIN_HECHO")
    def test_procedencia_propone_solo_mismo_documento(self):
        e=base(); n=proponer_vinculos_por_procedencia(e)
        self.assertEqual({(v.hecho_id,v.prueba_id) for v in n},{("H1","P1"),("H2","P2")})
        self.assertTrue(all(v.estado=="propuesto" for v in n))
    def test_propuesto_no_cuenta_como_vinculado(self):
        e=base(); proponer_vinculos_por_procedencia(e); self.assertEqual(cobertura(e)["hechos"]["H1"][0],"POR_CONFIRMAR")
    def test_confirmar_vincula(self):
        e=base(); proponer_vinculos_por_procedencia(e); confirmar(e,"H1","P1"); self.assertEqual(cobertura(e)["hechos"]["H1"][0],"VINCULADO")
    def test_no_duplica(self):
        e=base(); proponer_vinculos_por_procedencia(e); self.assertEqual(proponer_vinculos_por_procedencia(e),[])
    def test_h3_y_p3_siguen_huerfanos(self):
        e=base(); proponer_vinculos_por_procedencia(e); c=cobertura(e)
        self.assertEqual(c["hechos"]["H3"][0],"SIN_PRUEBA"); self.assertEqual(c["pruebas"]["P3"][0],"SIN_HECHO")
    def test_tipo_fuera_de_catalogo(self):
        e=base(); e.pruebas[0].tipo="rumor"; self.assertEqual(validar_tipos(e)[0][0],"P1")
    def test_vinculo_a_inexistente_lo_bloquea_el_verificador(self):
        e=base(); e.documentos={"a.txt":"x","b.txt":"x","zzz.txt":"x","c.pdf":"x"}; e.vinculos=[Vinculo("H9","P1","e")]
        self.assertTrue(any("inexistente" in m for _,m in verificar(e)))
unittest.main()
