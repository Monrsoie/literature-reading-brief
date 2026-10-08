import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1]


@unittest.skipUnless(os.name == 'nt' and shutil.which('powershell'), 'Windows installer tests')
class InstallationTests(unittest.TestCase):
    def run_install(self, vault, codex_config, *options):
        env = dict(os.environ, CODEX_HOME=str(codex_config))
        return subprocess.run(
            ['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
             str(SOURCE / 'install.ps1'), '-VaultPath', str(vault),
             '-SkipDependencies', *options],
            env=env, capture_output=True)

    def test_installs_clean_workspace_and_registers_local_wrapper(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / '用户文库'
            config = root / 'codex-config'
            result = self.run_install(vault, config)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((vault / '.gitignore').is_file())
            self.assertTrue((vault / '_skills/literature-workflow/references/guided-reading.md').is_file())
            self.assertEqual(list((vault / '_data/brain').iterdir()), [])
            wrapper = (config / 'skills/literature-reading-brief/SKILL.md').read_text(encoding='utf-8')
            self.assertIn(vault.as_posix(), wrapper)
            self.assertFalse((vault / 'references.bib').exists())
            self.assertFalse((vault / '_scripts/__pycache__').exists())

    def test_conflict_preserves_existing_files_and_does_not_register(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / 'vault'
            vault.mkdir()
            existing = vault / 'SKILL.md'
            existing.write_text('existing user instructions', encoding='utf-8')
            result = self.run_install(vault, root / 'config')
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(existing.read_text(encoding='utf-8'), 'existing user instructions')
            self.assertEqual(list(vault.iterdir()), [existing])
            self.assertFalse((root / 'config').exists())

    def test_same_source_reinstall_preserves_runtime_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / 'vault'
            config = root / 'config'
            first = self.run_install(vault, config, '-SkipSkillRegistration')
            self.assertEqual(first.returncode, 0, first.stderr)
            receipt = vault / '_data/daily-delivery/test.json'
            receipt.parent.mkdir(parents=True)
            receipt.write_text(json.dumps({'status': 'delivered'}), encoding='utf-8')
            second = self.run_install(vault, config, '-SkipSkillRegistration')
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(json.loads(receipt.read_text(encoding='utf-8')), {'status': 'delivered'})


if __name__ == '__main__':
    unittest.main()
