"""
test_local_model_config.py
============================

Validates core/local_model_config.py's ``load_local_env_file`` in isolation.
Critically: this loader must NEVER run as an import-time side effect of
``content_provider.py`` or anything else the test suite touches — every test
here uses an explicit temp file and explicit ``path=`` argument so the
repo's real ``.pbe_model.env`` (present for Emma's own local use) never
leaks into this process's environment or affects any other test's baseline
"no model configured" assumption.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from core.local_model_config import load_local_env_file


class TestLoadLocalEnvFile(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_env = dict(os.environ)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._saved_env)

    def _write_temp(self, content: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".env")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        self.addCleanup(lambda: os.path.exists(path) and os.remove(path))
        return path

    def test_missing_file_is_a_noop(self) -> None:
        applied = load_local_env_file(path="/nonexistent/definitely/not/here.env")
        assert applied == {}

    def test_applies_simple_key_value_pairs(self) -> None:
        path = self._write_temp(
            "PBE_MODEL_BASE_URL=http://127.0.0.1:11434/v1\n"
            "PBE_MODEL_NAME=llama3.2\n"
        )
        os.environ.pop("PBE_MODEL_BASE_URL", None)
        os.environ.pop("PBE_MODEL_NAME", None)
        applied = load_local_env_file(path=path)
        assert applied == {
            "PBE_MODEL_BASE_URL": "http://127.0.0.1:11434/v1",
            "PBE_MODEL_NAME": "llama3.2",
        }
        assert os.environ["PBE_MODEL_BASE_URL"] == "http://127.0.0.1:11434/v1"
        assert os.environ["PBE_MODEL_NAME"] == "llama3.2"

    def test_never_overrides_an_existing_real_env_var(self) -> None:
        os.environ["PBE_MODEL_NAME"] = "already-set-by-shell"
        path = self._write_temp("PBE_MODEL_NAME=from-file\n")
        applied = load_local_env_file(path=path)
        assert applied == {}  # nothing applied — key already present
        assert os.environ["PBE_MODEL_NAME"] == "already-set-by-shell"

    def test_ignores_blank_lines_and_comments(self) -> None:
        path = self._write_temp(
            "# a comment\n\nPBE_MODEL_ENABLED=1\n   \n# another comment\n"
        )
        os.environ.pop("PBE_MODEL_ENABLED", None)
        applied = load_local_env_file(path=path)
        assert applied == {"PBE_MODEL_ENABLED": "1"}

    def test_strips_matching_quotes(self) -> None:
        path = self._write_temp('PBE_MODEL_NAME="llama3.2"\nPBE_MODEL_API_KEY=\'ollama\'\n')
        os.environ.pop("PBE_MODEL_NAME", None)
        os.environ.pop("PBE_MODEL_API_KEY", None)
        applied = load_local_env_file(path=path)
        assert applied == {"PBE_MODEL_NAME": "llama3.2", "PBE_MODEL_API_KEY": "ollama"}

    def test_malformed_lines_without_equals_are_skipped(self) -> None:
        path = self._write_temp("not a valid line\nPBE_MODEL_ENABLED=1\n")
        os.environ.pop("PBE_MODEL_ENABLED", None)
        applied = load_local_env_file(path=path)
        assert applied == {"PBE_MODEL_ENABLED": "1"}

    def test_repo_root_default_does_not_affect_other_tests_baseline(self) -> None:
        """The default (no explicit path) resolves to <repo_root>/.pbe_model.env.
        This test only proves the resolution doesn't raise and returns a
        dict — it deliberately does NOT assert on real repo file contents,
        since Emma's local .pbe_model.env is machine-specific and this test
        must pass identically whether or not that file exists.
        """
        applied = load_local_env_file()
        assert isinstance(applied, dict)


def main() -> int:
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(__import__(__name__))
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
