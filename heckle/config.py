from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class AppConfig:
    paused: bool = False
    frequency: str = "normal"
    api_key: str = ""
    api_base: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    bubble_x: int | None = None
    bubble_y: int | None = None
    display_seconds: int = 8
    debounce_seconds: float = 1.5
    dwell_minutes: tuple[int, ...] = (5, 15, 30, 60)

    @property
    def minimum_interval(self) -> int:
        return {"low": 120, "normal": 45, "high": 15}.get(self.frequency, 45)

    def normalize_api_settings(self) -> None:
        base = self.api_base.strip().rstrip("/")
        if "platform.deepseek.com" in base:
            base = "https://api.deepseek.com"
        self.api_base = base or "https://api.openai.com/v1"
        model = self.model.strip()
        if "api.deepseek.com" in self.api_base and model.lower() in {"", "deepseek"}:
            model = "deepseek-chat"
        self.model = model or "gpt-4o-mini"

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "AppConfig":
        allowed = cls.__dataclass_fields__.keys()
        values = {key: value for key, value in raw.items() if key in allowed}
        if "dwell_minutes" in values:
            values["dwell_minutes"] = tuple(int(x) for x in values["dwell_minutes"])
        config = cls(**values)
        config.normalize_api_settings()
        return config


class ConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        appdata = Path(os.environ.get("APPDATA", Path.home()))
        self.path = path or appdata / "HECKLE" / "settings.json"
        self.legacy_paths = (
            []
            if path
            else [
                appdata / "roast_plugin" / "settings.json",
                appdata / "Backseat" / "settings.json",
            ]
        )

    def load(self) -> AppConfig:
        try:
            source = self.path
            if not source.exists():
                source = next(
                    (candidate for candidate in self.legacy_paths if candidate.exists()),
                    source,
                )
            config = AppConfig.from_dict(json.loads(source.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError):
            return AppConfig()
        if source != self.path:
            try:
                self.save(config)
            except OSError:
                # The loaded legacy settings still work even if migration is blocked.
                pass
        return config

    def save(self, config: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(
            json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temp.replace(self.path)
