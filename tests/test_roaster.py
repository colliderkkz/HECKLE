from heckle.activity import ActivityEvent
from heckle.config import AppConfig
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer
from shiboken6 import delete

from heckle.roaster import (
    CREATIVE_DIRECTIONS,
    RoastService,
    SYSTEM_PROMPT,
    _RoastWorker,
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
    assert payload["tone_profile"]["aggression"] == "6/10"
    assert payload["tone_profile"]["brattiness"] == "10/10"
    assert payload["tone_profile"]["smugness"] == "10/10"
    assert payload["tone_profile"]["drama"] == "7/10"
    assert "至少组合两个雌小鬼风格标记" in payload["tone_profile"]["must_have"]


def test_clean_removes_model_prefix():
    assert _clean('  Backseat： “忙得很具体。”  ') == "忙得很具体。"
    assert _clean("HΞCKLE：窗口切得比脑子快。") == "窗口切得比脑子快。"


def test_prompt_uses_strong_bratty_anime_tone():
    assert "攻击性 6/10、屑度 10/10、得意感 10/10" in SYSTEM_PROMPT
    assert "成年虚构二次元小恶魔" in SYSTEM_PROMPT
    assert "装惊讶或假同情 → 戳穿这次杂鱼操作 → 得意坏笑收尾" in SYSTEM_PROMPT
    assert "每句必须至少组合两个风格标记" in SYSTEM_PROMPT
    forbidden_catchphrase = "\u9535\u9535"
    assert forbidden_catchphrase not in SYSTEM_PROMPT
    assert len(CREATIVE_DIRECTIONS) >= 12


def test_flirty_direction_is_rare_and_has_safety_boundaries():
    flirty = [item for item in CREATIVE_DIRECTIONS if item.startswith("低频暧昧")]
    assert len(flirty) == 1
    assert len(CREATIVE_DIRECTIONS) >= 15
    assert "不涉及身体部位、性行为、未成年或萝莉设定" in SYSTEM_PROMPT
    assert "不能凭空评价代码行数" in SYSTEM_PROMPT
    assert "绝不能直接称呼用户为“杂鱼”" in SYSTEM_PROMPT
    assert "毒舌强度 8/10" not in SYSTEM_PROMPT


def test_common_deepseek_console_url_is_corrected():
    config = AppConfig(
        api_base="https://platform.deepseek.com/api_keys", model="deepseek"
    )
    config.normalize_api_settings()
    assert config.api_base == "https://api.deepseek.com"
    assert config.model == "deepseek-chat"


def test_full_chat_completions_url_is_normalized():
    config = AppConfig(api_base="https://api.openai.com/v1/chat/completions")
    config.normalize_api_settings()
    assert config.api_base == "https://api.openai.com/v1"
    assert config.model == "gpt-4o-mini"


def test_async_worker_is_kept_alive_until_result(monkeypatch):
    captured = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            message = type("Message", (), {"content": "这点代码切窗口的次数倒不少。"})()
            choice = type("Choice", (), {"message": message})()
            return type("Completion", (), {"choices": [choice]})()

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client"] = kwargs
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr("heckle.roaster.OpenAI", FakeClient)
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
    assert captured["client"]["base_url"] == "https://api.openai.com/v1"
    assert captured["model"] == "gpt-4o-mini"


def test_worker_ignores_result_after_signal_source_is_deleted():
    worker = _RoastWorker(AppConfig(), {})
    assert not worker.autoDelete()
    delete(worker.signals)
    worker._emit_finished("来晚啦～", "")


def test_worker_reports_an_empty_model_response(monkeypatch):
    class FakeCompletions:
        def create(self, **kwargs):
            message = type("Message", (), {"content": "   "})()
            choice = type("Choice", (), {"message": message})()
            return type("Completion", (), {"choices": [choice]})()

    class FakeClient:
        def __init__(self, **kwargs):
            self.chat = type("Chat", (), {"completions": FakeCompletions()})()

    monkeypatch.setattr("heckle.roaster.OpenAI", FakeClient)
    app = QCoreApplication.instance() or QCoreApplication([])
    worker = _RoastWorker(AppConfig(api_key="test-key"), {})
    received = []
    worker.signals.finished.connect(lambda text, error: received.append((text, error)))

    worker.run()

    assert received == [("", "响应异常：模型返回的内容清理后为空")]
