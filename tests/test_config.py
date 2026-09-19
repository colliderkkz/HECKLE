import json
import shutil
from pathlib import Path

from heckle.config import ConfigStore


def test_roast_plugin_settings_migrate_to_heckle(monkeypatch):
    test_root = Path.cwd() / ".test-config-migration"
    shutil.rmtree(test_root, ignore_errors=True)
    try:
        legacy = test_root / "roast_plugin" / "settings.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_text(
            json.dumps(
                {
                    "api_key": "migration-test-key",
                    "api_base": "https://api.deepseek.com",
                    "model": "deepseek-chat",
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setenv("APPDATA", str(test_root))

        config = ConfigStore().load()

        assert config.api_key == "migration-test-key"
        migrated = test_root / "HECKLE" / "settings.json"
        assert migrated.exists()
        assert json.loads(migrated.read_text(encoding="utf-8"))["api_key"] == "migration-test-key"
    finally:
        shutil.rmtree(test_root, ignore_errors=True)
