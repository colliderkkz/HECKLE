from __future__ import annotations

import os
import re
import time
from collections import deque
from dataclasses import asdict, dataclass

from PySide6.QtCore import QObject, QTimer, Signal


@dataclass(frozen=True)
class WindowInfo:
    app: str
    process: str
    title: str
    hwnd: int = 0
    pid: int = 0

    @property
    def identity(self) -> tuple[str, str]:
        title = re.sub(r"^[*\u25cf\s]+|\s+", " ", self.title).strip().lower()
        return self.process.lower(), title


@dataclass
class ActivitySlice:
    app: str
    title: str
    duration: int


@dataclass
class ActivityEvent:
    event: str
    from_app: str | None
    to_app: str
    title: str
    previous_duration: int
    dwell_duration: int
    recent_activity: list[dict]

    def as_context(self) -> dict:
        return asdict(self)


class ActivityTracker:
    """Pure state machine for debounced switches and dwell milestones."""

    def __init__(
        self,
        debounce_seconds: float = 1.5,
        dwell_seconds: tuple[int, ...] = (300, 900, 1800, 3600),
        history_seconds: int = 1800,
    ) -> None:
        self.debounce_seconds = debounce_seconds
        self.dwell_seconds = tuple(sorted(dwell_seconds))
        self.history_seconds = history_seconds
        self.current: WindowInfo | None = None
        self.current_since = 0.0
        self.pending: WindowInfo | None = None
        self.pending_since = 0.0
        self.fired_dwell: set[int] = set()
        self.history: deque[tuple[float, ActivitySlice]] = deque()

    def update(self, window: WindowInfo | None, now: float | None = None) -> list[ActivityEvent]:
        now = time.monotonic() if now is None else now
        if window is None:
            return []
        if self.current is None:
            self.current = window
            self.current_since = now
            return []

        if window.identity != self.current.identity:
            if self.pending is None or window.identity != self.pending.identity:
                self.pending = window
                self.pending_since = now
                return []
            if now - self.pending_since >= self.debounce_seconds:
                return [self._confirm_switch(self.pending, now)]
            return []

        self.pending = None
        elapsed = int(now - self.current_since)
        reached = [
            threshold
            for threshold in self.dwell_seconds
            if elapsed >= threshold and threshold not in self.fired_dwell
        ]
        if reached:
            # If the machine wakes after a long sleep, emit only the latest milestone
            # instead of firing several stale roasts on consecutive polling ticks.
            self.fired_dwell.update(reached)
            return [
                ActivityEvent(
                    event="LONG_DWELL",
                    from_app=None,
                    to_app=self.current.app,
                    title=self.current.title,
                    previous_duration=0,
                    dwell_duration=elapsed,
                    recent_activity=self._recent(now),
                )
            ]
        return []

    def current_event(
        self, event_name: str = "MANUAL_ROAST", now: float | None = None
    ) -> ActivityEvent | None:
        if self.current is None:
            return None
        now = time.monotonic() if now is None else now
        return ActivityEvent(
            event=event_name,
            from_app=None,
            to_app=self.current.app,
            title=self.current.title,
            previous_duration=0,
            dwell_duration=max(0, int(now - self.current_since)),
            recent_activity=self._recent(now),
        )

    def _confirm_switch(self, new_window: WindowInfo, now: float) -> ActivityEvent:
        assert self.current is not None
        previous = self.current
        duration = max(0, int(now - self.current_since))
        self.history.append(
            (now, ActivitySlice(app=previous.app, title=previous.title, duration=duration))
        )
        self.current = new_window
        self.current_since = self.pending_since
        self.pending = None
        self.fired_dwell.clear()
        return ActivityEvent(
            event="WINDOW_SWITCH",
            from_app=previous.app,
            to_app=new_window.app,
            title=new_window.title,
            previous_duration=duration,
            dwell_duration=0,
            recent_activity=self._recent(now),
        )

    def _recent(self, now: float) -> list[dict]:
        while self.history and now - self.history[0][0] > self.history_seconds:
            self.history.popleft()
        return [asdict(item) for _, item in list(self.history)[-12:]]


_FRIENDLY_NAMES = {
    "code.exe": "VS Code",
    "chrome.exe": "Chrome",
    "msedge.exe": "Edge",
    "firefox.exe": "Firefox",
    "steam.exe": "Steam",
    "discord.exe": "Discord",
    "wechat.exe": "微信",
    "qq.exe": "QQ",
    "explorer.exe": "文件资源管理器",
    "windowsterminal.exe": "终端",
    "powershell.exe": "PowerShell",
    "pycharm64.exe": "PyCharm",
    "devenv.exe": "Visual Studio",
    "notepad.exe": "记事本",
}


def get_foreground_window() -> WindowInfo | None:
    """Read foreground metadata without screenshots, input hooks, or OCR."""
    if os.name != "nt":
        return None
    try:
        import psutil
        import win32gui
        import win32process

        hwnd = win32gui.GetForegroundWindow()
        if not hwnd or not win32gui.IsWindowVisible(hwnd):
            return None
        title = win32gui.GetWindowText(hwnd).strip()
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        if pid == os.getpid():
            return None
        process = psutil.Process(pid).name()
        app = _FRIENDLY_NAMES.get(process.lower(), process.removesuffix(".exe"))
        return WindowInfo(app=app, process=process, title=title, hwnd=hwnd, pid=pid)
    except Exception:
        # Foreground windows can disappear between Win32 calls; skip that sample.
        return None


class WindowMonitor(QObject):
    event_detected = Signal(object)

    def __init__(self, tracker: ActivityTracker, interval_ms: int = 500) -> None:
        super().__init__()
        self.tracker = tracker
        self.timer = QTimer(self)
        self.timer.setInterval(interval_ms)
        self.timer.timeout.connect(self.poll)

    def start(self) -> None:
        self.poll()
        self.timer.start()

    def poll(self) -> None:
        for event in self.tracker.update(get_foreground_window()):
            self.event_detected.emit(event)
