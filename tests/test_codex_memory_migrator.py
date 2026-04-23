import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "skill"
    / "codex-memory-migrator"
    / "scripts"
    / "codex_memory_migrator.py"
)
SPEC = importlib.util.spec_from_file_location("codex_memory_migrator", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class CodexMemoryMigratorTests(unittest.TestCase):
    def test_infer_mappings_from_manifest_uses_source_home(self) -> None:
        manifest = {
            "source_codex_home": "/Users/olduser/.codex",
            "scan": {
                "top_path_prefixes": [
                    ["/Users/olduser/workspace-a", 3],
                    ["/Users/olduser/workspace-b", 1],
                ]
            },
        }

        result = MODULE.infer_mappings_from_manifest(manifest, Path("/Users/newuser"))

        self.assertEqual(result, [("/Users/olduser", "/Users/newuser")])

    def test_resolve_mappings_prefers_explicit_map_over_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = Path(temp_dir) / "manifest.json"
            manifest_path.write_text('{"source_codex_home": "/Users/ignored/.codex"}', encoding="utf-8")

            result = MODULE.resolve_mappings(
                ["/Users/real=/Users/target"],
                str(manifest_path),
                "/Users/newuser",
            )

        self.assertEqual(result, [("/Users/real", "/Users/target")])

    def test_install_skill_creates_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            skills_dir = Path(temp_dir) / "skills"

            target = MODULE.install_skill(skills_dir, force=False, copy_mode=False)

            self.assertTrue(target.is_symlink())
            self.assertEqual(target.resolve(), MODULE.SKILL_DIR.resolve())


if __name__ == "__main__":
    unittest.main()
