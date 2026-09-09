import unittest

import app_desktop


class TestAppDesktop(unittest.TestCase):
    def test_fecha_servidor_gradio_quando_janela_nativa_fecha(self):
        class App:
            fechado = False

            def close(self):
                self.fechado = True

        app = App()

        app_desktop._fechar_servidor_gradio(app)

        self.assertTrue(app.fechado)


if __name__ == "__main__":
    unittest.main()
