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

    def test_page_scrolls_when_workspace_exceeds_viewport(self):
        self.assertIn("height: 100dvh", self.source)
        self.assertIn("body { margin: 0 !important; overflow-y: auto; }", self.source)
        self.assertNotIn("html, body { width: 100%; height: 100%; overflow: hidden; }", self.source)
        self.assertIn("min-height: calc(100dvh - 104px)", self.source)
        self.assertNotIn("height: calc(100dvh - 196px)", self.source)
        self.assertIn("@media (max-width: 1200px)", self.source)

    def test_shell_fits_remaining_viewport_and_panels_scroll_visibly(self):
        self.assertNotIn("height: calc(100dvh - 116px)", self.source)
        self.assertGreaterEqual(self.source.count("scrollbar-gutter: stable"), 2)
        self.assertGreaterEqual(self.source.count("overscroll-behavior: contain"), 2)
        self.assertIn(".workspace-panel::-webkit-scrollbar", self.source)
        self.assertIn(".inspector-scroll::-webkit-scrollbar", self.source)

    def test_existing_tabs_and_processing_callbacks_remain(self):
        self.assertIn('gr.Tab("Corte Viral", id="tab_corte")', self.source)
        self.assertIn('gr.Tab("Legendas Animadas", id="tab_legendas")', self.source)
        self.assertIn("btn_processar.click(", self.source)
        self.assertIn("fn=ao_processar,", self.source)
        self.assertIn("btn_enviar_legenda.click(", self.source)

    def test_processing_ui_exposes_resume_choice_and_live_progress(self):
        self.assertIn('label="Se houver trabalho anterior"', self.source)
        self.assertIn('"Retomar trabalho"', self.source)
        self.assertIn('"Reprocessar tudo"', self.source)
        self.assertIn('"Cancelar"', self.source)
        self.assertIn("progresso_evento_callback=cb_evento", self.source)
        self.assertIn("progress(percentual", self.source)


if __name__ == "__main__":
    unittest.main()
