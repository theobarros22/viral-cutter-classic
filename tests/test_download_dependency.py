import importlib.util
import unittest


class DownloadDependencyTests(unittest.TestCase):
    def test_yt_dlp_is_available_to_the_application(self):
        """The link-download flow must work without the user installing a venv."""
        self.assertIsNotNone(importlib.util.find_spec("yt_dlp"))


if __name__ == "__main__":
    unittest.main()
