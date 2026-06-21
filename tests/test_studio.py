import unittest

from studio.project import validar_projeto
from studio.viral_effects import (
    expressao_zoom,
    filtro_barra_progresso,
    filtro_lut,
    filtros_sfx,
)


class TestStudio(unittest.TestCase):
    def test_projeto_descarta_legenda_invalida(self):
        projeto = validar_projeto({
            "name": "Teste",
            "captions": [
                {"start": 0, "end": 1.5, "text": "Legenda valida"},
                {"start": 2, "end": 1, "text": "Fim invalido"},
                {"start": 2, "end": 3, "text": ""},
            ],
        })
        self.assertEqual(len(projeto["captions"]), 1)

    def test_zoom_dinamico_limita_intensidade(self):
        expressao = expressao_zoom([1.0, 3.5], intensidade=1.8)
        self.assertIn("1.300", expressao)
        self.assertIn("between(t,1.000,1.450)", expressao)

    def test_barra_progresso_usa_duracao(self):
        filtro = filtro_barra_progresso(10, altura=8)
        self.assertIn("t/10.000", filtro)
        self.assertIn("h=8", filtro)

    def test_lut_exige_cube(self):
        with self.assertRaises(ValueError):
            filtro_lut("visual.png")
        self.assertIn("lut3d", filtro_lut(r"D:\luts\cinema.cube"))

    def test_sfx_sao_atrasados_e_mixados(self):
        filtros, saida = filtros_sfx([{"tempo": 1.25, "volume": 0.8}])
        self.assertIn("adelay=1250|1250", filtros[0])
        self.assertIn("amix=inputs=2", filtros[-1])
        self.assertEqual(saida, "[aout]")


if __name__ == "__main__":
    unittest.main()
