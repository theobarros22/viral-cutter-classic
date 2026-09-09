from pathlib import Path
import unittest


class TestLauncher(unittest.TestCase):
    def test_lancador_ativa_ou_abre_app_nativo_sem_diagnostico_extra(self):
        lancador = Path(__file__).parents[1] / "ViralCutter.vbs"

        conteudo = lancador.read_text(encoding="utf-8")

        self.assertIn('If sh.AppActivate("Viral Cutter Classic") Then', conteudo)
        self.assertIn('shellApp.ShellExecute pyw', conteudo)
        self.assertNotIn('diagnostico.py', conteudo)


if __name__ == "__main__":
    unittest.main()
