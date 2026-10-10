"""Installer safeguards and launcher delegation; no biological validation."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def load_script(name):
    path = Path(__file__).resolve().parents[1] / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sync = load_script("skill_sync")
launcher = load_script("run_toolkit")


class SkillSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "repository"
        self.target = self.base / "installed"
        files = {"VERSION": "v0.1.0-exploratory\n", "SKILL.md": "original instructions\n",
                 "scripts/run_toolkit.py": "launcher\n", "Run.ps1": "entry\n",
                 "vpt_cli.py": "core entry\n", "scripts/run_guard.py": "guard\n",
                 "scripts/plot_results.R": "plot\n",
                 "agents/openai.yaml": "interface: {}\n"}
        for name, text in files.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_install_is_thin_and_points_to_repository(self):
        result = sync.sync(self.root, self.target)
        self.assertFalse(result["core_code_copied"])
        self.assertEqual(sync.inspect_install(self.root, self.target)["state"], "CLEAN")
        self.assertFalse((self.target / "vpt_cli.py").exists())
        self.assertEqual(sync.read_json(self.target / "scripts/toolkit_path.json")["toolkit_path"], str(self.root.resolve()))

    def test_update_detects_content_changes_without_version_bump(self):
        sync.sync(self.root, self.target)
        (self.root / "SKILL.md").write_text("new instructions", encoding="utf-8")
        result = sync.inspect_install(self.root, self.target)
        self.assertEqual(result["state"], "CLEAN")
        self.assertTrue(result["update_available"])
        sync.sync(self.root, self.target)
        self.assertFalse(sync.inspect_install(self.root, self.target)["update_available"])

    def test_user_edit_blocks_overwrite_without_backup(self):
        sync.sync(self.root, self.target)
        edited = self.target / "SKILL.md"
        edited.write_text("user changes", encoding="utf-8")
        self.assertEqual(sync.inspect_install(self.root, self.target)["modified_files"], ["SKILL.md"])
        with self.assertRaisesRegex(ValueError, "拒绝覆盖"):
            sync.sync(self.root, self.target)
        self.assertEqual(edited.read_text(encoding="utf-8"), "user changes")

    def test_backup_preserves_user_edits_and_extra_files(self):
        sync.sync(self.root, self.target)
        (self.target / "SKILL.md").write_text("user changes", encoding="utf-8")
        (self.target / "personal.txt").write_text("personal", encoding="utf-8")
        result = sync.sync(self.root, self.target, self.base / "backups")
        backup = Path(result["backup_path"])
        self.assertEqual((backup / "SKILL.md").read_text(encoding="utf-8"), "user changes")
        self.assertEqual((backup / "personal.txt").read_text(encoding="utf-8"), "personal")
        self.assertTrue((self.target / "personal.txt").exists())
        self.assertEqual(sync.inspect_install(self.root, self.target)["state"], "CLEAN")

    def test_legacy_untracked_install_requires_backup(self):
        self.target.mkdir()
        (self.target / "SKILL.md").write_text("legacy", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "拒绝覆盖"):
            sync.sync(self.root, self.target)
        self.assertEqual((self.target / "SKILL.md").read_text(encoding="utf-8"), "legacy")

    def test_backup_inside_skill_is_rejected_before_update(self):
        sync.sync(self.root, self.target)
        (self.target / "SKILL.md").write_text("user", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "不能位于"):
            sync.sync(self.root, self.target, self.target / "backups")
        self.assertFalse((self.target / "backups").exists())

    def test_new_managed_collision_requires_backup(self):
        sync.sync(self.root, self.target)
        manifest = sync.read_json(self.target / sync.MANIFEST)
        manifest["files"].pop("agents/openai.yaml")
        (self.target / sync.MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "拒绝覆盖"):
            sync.sync(self.root, self.target)

    def test_doctor_without_config_does_not_claim_model_ready(self):
        sync.sync(self.root, self.target)
        result = sync.doctor(self.root, self.target)
        self.assertEqual(result["state"], "INSTALLATION_ONLY")
        self.assertFalse(result["runtime_checked"])
        self.assertEqual(result["scientific_validation"], "NOT_ESTABLISHED")

    def _doctor_config(self, engine="dosedirko"):
        executable = self.root / "runtime"
        executable.write_text("fixture", encoding="utf-8")
        source = self.root / "external/dosedirko/api.py"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("fixture", encoding="utf-8")
        config = {"input": {"format": "10x"}, "runtime": {"python_monitor": str(executable),
            "python_data": str(executable), "Rscript": str(executable), "R_library": str(self.root)},
            "engine": {"id": engine, "source_dir": str(source.parents[1]),
                "source_sha256": {"api.py": sync.digest(source.read_bytes())}}}
        path = self.root / "job.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        return path

    def test_doctor_missing_dependency_blocks_without_running_algorithm(self):
        config = self._doctor_config()
        with patch.object(sync, "probe_python", return_value={"packages": {"tensorly": None}}), \
             patch.object(sync, "probe_r", return_value={"packages": {"svglite": "2.2.2"}}):
            result = sync.doctor(self.root, self.target, config)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertTrue(any("tensorly" in error for error in result["errors"]))

    def test_doctor_unintegrated_engine_never_claims_ready(self):
        config = self._doctor_config("celloracle")
        with patch.object(sync, "probe_python", return_value={"packages": {}}), \
             patch.object(sync, "probe_r", return_value={"packages": {}}):
            result = sync.doctor(self.root, self.target, config)
        self.assertEqual(result["state"], "BLOCKED")
        self.assertTrue(any("celloracle" in error for error in result["errors"]))

    def _missing_package_report(self, package, input_format):
        path = self._doctor_config()
        config = sync.read_json(path)
        config['input']['format'] = input_format
        path.write_text(json.dumps(config), encoding='utf-8')
        def probe(executable, names, dependency_paths):
            return {'packages': {name: None if name == package else 'software_fixture' for name in names}}
        with patch.object(sync, 'probe_python', side_effect=probe), \
             patch.object(sync, 'probe_r', return_value={'packages': {'svglite': '2.2.2'}}):
            return sync.doctor(self.root, self.target, path)

    def test_missing_sklearn_blocks_dosedirko_before_execution(self):
        report = self._missing_package_report('scikit-learn', '10x')
        self.assertEqual(report['state'], 'BLOCKED')
        self.assertTrue(any('scikit-learn' in error for error in report['errors']))

    def test_missing_h5py_blocks_h5ad_before_execution(self):
        report = self._missing_package_report('h5py', 'h5ad')
        self.assertEqual(report['state'], 'BLOCKED')
        self.assertTrue(any('h5py' in error for error in report['errors']))

    def test_launcher_passes_literal_paths_and_never_shell_interpolates(self):
        config = self.base / "job $(not-a-command).json"
        config.write_text("{}", encoding="utf-8")
        command = launcher.build_command(self.root, config, self.base / "output with spaces")
        self.assertEqual(command[command.index("-Config") + 1], str(config.resolve()))
        self.assertEqual(command[command.index("-File") + 1], str(self.root / "Run.ps1"))
        self.assertEqual(command[-1], str((self.base / "output with spaces").resolve()))

    def test_launcher_missing_config_fails_before_powershell(self):
        with self.assertRaisesRegex(ValueError, "配置文件不存在"):
            launcher.build_command(self.root, self.base / "missing.json")


if __name__ == "__main__":
    unittest.main()
