from __future__ import annotations

import os
import signal
import sys
import time

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from .activity import ActivityEvent, ActivityTracker, WindowMonitor
from .config import ConfigStore
from .roaster import RoastService
from .ui import RoastBubble


class HeckleController(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.store = ConfigStore()
        self.config = self.store.load()
        self.tracker = ActivityTracker(
            debounce_seconds=self.config.debounce_seconds,
            dwell_seconds=tuple(minutes * 60 for minutes in self.config.dwell_minutes),
        )
        self.monitor = WindowMonitor(self.tracker)
        self.roaster = RoastService(self.config)
        self.bubble = RoastBubble(self.config, self.store)
        self.last_roast_at = float("-inf")
        self.monitor.event_detected.connect(self._on_event)
        self.roaster.roast_ready.connect(self.bubble.show_roast)
        self.roaster.api_error.connect(
            lambda error: self.bubble.show_roast(f"API 调用失败：{error}")
        )
        self.bubble.roast_now_requested.connect(self._roast_now)

    def start(self) -> None:
        self.bubble.show_roast("HΞCKLE — Judging every click.")
        self.monitor.start()
        QTimer.singleShot(2000, self._initial_roast)

    def _initial_roast(self) -> None:
        self._roast_now("SESSION_START")

    def _roast_now(self, event_name: str = "MANUAL_ROAST") -> None:
        if self.config.paused:
            self.bubble.show_roast("还暂停着呢，想挨骂先点“继续吐槽”。")
            return
        event = self.tracker.current_event(event_name)
        if event is None:
            self.bubble.show_roast("暂时读不到前台窗口，连骂你的素材都藏好了。")
            return
        self._on_event(event, force=True)

    def _on_event(self, event: ActivityEvent, force: bool = False) -> None:
        if self.config.paused:
            return
        now = time.monotonic()
        if not force and now - self.last_roast_at < self.config.minimum_interval:
            return
        self.last_roast_at = now
        self.roaster.generate(event)


def main() -> int:
    if os.name != "nt":
        print("HECKLE currently supports Windows only.", file=sys.stderr)
        return 1
    app = QApplication(sys.argv)
    app.setApplicationName("HECKLE")
    app.setOrganizationName("HECKLE")
    app.setQuitOnLastWindowClosed(False)

    def quit_from_console(_signum, _frame) -> None:
        app.quit()

    signal.signal(signal.SIGINT, quit_from_console)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, quit_from_console)
    controller = HeckleController()
    controller.start()
    try:
        return app.exec()
    except KeyboardInterrupt:
        # A second Ctrl+C can arrive while Qt is leaving the event loop.
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
