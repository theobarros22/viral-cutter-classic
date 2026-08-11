import pathlib
import unittest


INTERFACE = pathlib.Path(__file__).resolve().parents[1] / "interface.py"


class ClassicDesktopLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = INTERFACE.read_text(encoding="utf-8")

    def test_classic_header_is_compact_and_versioned(self):
        self.assertIn('class="classic-topbar"', self.source)
        self.assertIn("Viral Cutter Classic", self.source)
        self.assertIn("2.3.2", self.source)
        self.assertNotIn('<div class="app-header">', self.source)

    def test_cut_tab_uses_three_horizontal_work_areas(self):
        self.assertIn('elem_classes="classic-shell"', self.source)
        self.assertIn('elem_classes="workflow-panel"', self.source)
        self.assertIn('elem_classes="workspace-panel"', self.source)
        self.assertIn('elem_classes="inspector-panel"', self.source)

    def test_viewport_has_no_global_scroll(self):
        self.assertIn("height: 100dvh", self.source)
        self.assertIn("overflow: hidden", self.source)
        self.assertIn("@media (max-width: 1200px)", self.source)

    def test_existing_tabs_and_processing_callbacks_remain(self):
        self.assertIn('gr.Tab("Corte Viral", id="tab_corte")', self.source)
        self.assertIn('gr.Tab("Legendas Animadas", id="tab_legendas")', self.source)
        self.assertIn("btn_processar.click(", self.source)
        self.assertIn("fn=ao_processar,", self.source)
        self.assertIn("btn_enviar_legenda.click(", self.source)


if __name__ == "__main__":
    unittest.main()
