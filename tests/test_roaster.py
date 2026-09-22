from heckle.activity import ActivityEvent
from heckle.config import AppConfig
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

from heckle.roaster import (
    CREATIVE_DIRECTIONS,
    RoastService,
    SYSTEM_PROMPT,
    _clean,
    build_roast_payload,
)


def test_payload_adds_behavior_summary_and_creative_direction():
    event = ActivityEvent(
        event="WINDOW_SWITCH",
        from_app="Chrome",
        to_app="VS Code",
        title="main.py - roast",
        previous_duration=2400,
        dwell_duration=0,
        recent_activity=[
            {"app": "VS Code", "title": "main.py", "duration": 300},
            {"app": "Chrome", "title": "Python docs", "duration": 2400},
        ],
    )
    payload = build_roast_payload(event, ["上一条吐槽"], CREATIVE_DIRECTIONS[0])
    summary = payload["behavior_summary"]
    assert summary["recent_route"] == "VS Code → Chrome → VS Code"
    assert summary["current_app_appearances"] == 2
    assert summary["previous_stay"] == "40分钟"
    assert summary["recent_sessions"][-1]["stay"] == "40分钟"
    assert payload["recent_roasts"] == ["上一条吐槽"]
    assert payload["avoid_openings"] == ["上一条吐槽"]
    assert payload["tone_profile"]["aggression"] == "5/10"
    assert payload["tone_profile"]["smugness"] == "9/10"
    assert payload["tone_profile"]["drama"] == "7/10"
    assert "至少一个浮夸叙事" in payload["tone_profile"]["must_have"]


def test_clean_removes_model_prefix():
    assert _clean('  Backseat： “忙得很具体。”  ') == "忙得很具体。"
    assert _clean("HΞCKLE：窗口切得比脑子快。") == "窗口切得比脑子快。"


def test_prompt_uses_playful_low_aggression_tone():
    assert "攻击性 5/10、屑度 9/10、戏剧感 7/10" in SYSTEM_PROMPT
    assert "二次元屑萌小恶魔" in SYSTEM_PROMPT
    assert "把小动作演成重大新闻" in SYSTEM_PROMPT
    assert "每句必须至少有一个清晰的风格标记" in SYSTEM_PROMPT
    forbidden_catchphrase = "\u9535\u9535"
    assert forbidden_catchphrase not in SYSTEM_PROMPT
    assert len(CREATIVE_DIRECTIONS) >= 12
    assert "绝不能直接称呼用户为“杂鱼”" in SYSTEM_PROMPT
    assert "毒舌强度 8/10" not in SYSTEM_PROMPT


def test_common_deepseek_console_url_is_corrected():
    config = AppConfig(
        api_base="https://platform.deepseek.com/api_keys", model="deepseek"
    )
    config.normalize_api_settings()
    assert config.api_base == "https://api.deepseek.com"
    assert config.model == "deepseek-chat"


def test_async_worker_is_kept_alive_until_result(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "这点代码切窗口的次数倒不少。"}}]}

    monkeypatch.setattr("heckle.roaster.httpx.post", lambda *args, **kwargs: FakeResponse())
    app = QCoreApplication.instance() or QCoreApplication([])
    service = RoastService(AppConfig(api_key="test-key"))
    event = ActivityEvent("SESSION_START", None, "VS Code", "main.py", 0, 5, [])
    received = []
    loop = QEventLoop()
    service.roast_ready.connect(lambda text: (received.append(text), loop.quit()))
    service.generate(event)
    QTimer.singleShot(2000, loop.quit)
    loop.exec()
    assert received == ["这点代码切窗口的次数倒不少。"]
    assert not service._workers
