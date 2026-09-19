from heckle.activity import ActivityTracker, WindowInfo


def window(app: str, title: str) -> WindowInfo:
    return WindowInfo(app=app, process=f"{app}.exe", title=title)


def test_switch_is_debounced_and_contains_history():
    tracker = ActivityTracker(debounce_seconds=1.5, dwell_seconds=(300,))
    vscode = window("VS Code", "main.py")
    chrome = window("Chrome", "Python docs")
    assert tracker.update(vscode, 0) == []
    assert tracker.update(chrome, 10) == []
    assert tracker.update(chrome, 11) == []
    events = tracker.update(chrome, 11.6)
    assert len(events) == 1
    assert events[0].event == "WINDOW_SWITCH"
    assert events[0].from_app == "VS Code"
    assert events[0].to_app == "Chrome"
    assert events[0].previous_duration == 11
    assert events[0].recent_activity[-1]["app"] == "VS Code"


def test_fast_switch_back_is_merged_away():
    tracker = ActivityTracker(debounce_seconds=1.5, dwell_seconds=(300,))
    vscode = window("VS Code", "main.py")
    chrome = window("Chrome", "Search")
    tracker.update(vscode, 0)
    tracker.update(chrome, 5)
    assert tracker.update(vscode, 5.5) == []
    assert tracker.current == vscode


def test_each_dwell_threshold_only_fires_once():
    tracker = ActivityTracker(debounce_seconds=1.5, dwell_seconds=(5, 10))
    vscode = window("VS Code", "main.py")
    tracker.update(vscode, 0)
    first = tracker.update(vscode, 5)
    assert [event.dwell_duration for event in first] == [5]
    assert tracker.update(vscode, 7) == []
    second = tracker.update(vscode, 10)
    assert [event.dwell_duration for event in second] == [10]
    assert tracker.update(vscode, 12) == []


def test_sleep_does_not_burst_old_dwell_milestones():
    tracker = ActivityTracker(debounce_seconds=1.5, dwell_seconds=(5, 10, 20))
    vscode = window("VS Code", "main.py")
    tracker.update(vscode, 0)
    assert len(tracker.update(vscode, 21)) == 1
    assert tracker.update(vscode, 22) == []


def test_current_event_supports_forced_roast():
    tracker = ActivityTracker()
    vscode = window("VS Code", "main.py")
    tracker.update(vscode, 10)
    event = tracker.current_event("MANUAL_ROAST", 25)
    assert event is not None
    assert event.event == "MANUAL_ROAST"
    assert event.to_app == "VS Code"
    assert event.dwell_duration == 15
