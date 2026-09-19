from __future__ import annotations

import json
import random
import re
from collections import deque

import httpx
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from .activity import ActivityEvent
from .config import AppConfig


SYSTEM_PROMPT = """你是 roast_plugin，一个坐在用户身后观察电脑操作的毒舌旁白，不是助手。

根据 JSON 中的当前事件、页面标题、停留时长和最近行为路径，写一句中文吐槽：
- 通常 18～40 个汉字，最多 45 个汉字，只输出一句，不换行；
- 优先抓住具体页面标题、应用之间的反差或连续行为，不要只复述“从 A 切到 B”；
- 按 creative_direction 指定的创作角度发挥，但事实必须来自上下文；
- 毒舌强度 8/10：像损友精准拆台，刻薄、挖苦、阴阳怪气，不温柔安慰；
- 只嘲讽用户眼前这次操作、拖延、摸鱼或反复横跳，不攻击身份、外貌和人格；
- 可以有尖锐比喻、反问和回扣，但必须自然，不能像机器硬编段子；
- 与 recent_roasts 在开头、句式、笑点和关键词上都尽量不同。

禁止解释、建议、效率提醒、说教、脏话、身份攻击、引号、标签和名称前缀。"""


CREATIVE_DIRECTIONS = (
    "细节捕手：从当前窗口标题里抓一个具体词做笑点，别泛泛谈应用。",
    "反差喜剧：利用前后应用或任务看起来互相矛盾的地方。",
    "冷面旁白：像纪录片解说一样认真描述这件很普通的操作。",
    "假装夸奖：先一本正经地肯定，再在后半句毫不留情地拆台。",
    "行为回扣：结合最近应用路径，吐槽反复横跳、回访或循环。",
    "荒诞比喻：用一个新鲜但容易听懂的比喻描述当前行为。",
    "拟人观察：把应用或页面写成正在等候、拉扯或围观用户。",
    "一句判词：给这段操作下一个精炼、出其不意的结论。",
)


class _WorkerSignals(QObject):
    finished = Signal(str, str)


class _RoastWorker(QRunnable):
    def __init__(self, config: AppConfig, payload: dict) -> None:
        super().__init__()
        self.config = config
        self.payload = payload
        self.signals = _WorkerSignals()

    def run(self) -> None:
        try:
            base = self.config.api_base.rstrip("/")
            endpoint = base if base.endswith("/chat/completions") else base + "/chat/completions"
            response = httpx.post(
                endpoint,
                headers={"Authorization": f"Bearer {self.config.api_key}"},
                json={
                    "model": self.config.model,
                    "temperature": 1.1,
                    "top_p": 0.95,
                    "max_tokens": 120,
                    "messages": [
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": json.dumps(self.payload, ensure_ascii=False),
                        },
                    ],
                },
                timeout=15,
            )
            response.raise_for_status()
            text = response.json()["choices"][0]["message"]["content"]
            self.signals.finished.emit(_clean(text), "")
        except httpx.HTTPStatusError as exc:
            message = _response_error(exc.response)
            self.signals.finished.emit("", f"HTTP {exc.response.status_code}：{message}")
        except httpx.RequestError as exc:
            self.signals.finished.emit("", f"网络错误：{str(exc)[:100]}")
        except Exception as exc:
            self.signals.finished.emit("", f"响应异常：{type(exc).__name__}")


def _response_error(response: httpx.Response) -> str:
    try:
        detail = response.json().get("error", {}).get("message", "")
    except (ValueError, AttributeError):
        detail = ""
    return str(detail or response.reason_phrase or "请求失败")[:140]


def _clean(text: str) -> str:
    line = re.sub(r"\s+", " ", text).strip()
    line = re.sub(
        r"^(roast_plugin|Backseat|吐槽|旁白)\s*[：:]\s*", "", line, flags=re.I
    )
    return line.strip().strip('"“”')[:90]


def _duration_label(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}秒"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}分钟"
    hours, remaining = divmod(minutes, 60)
    return f"{hours}小时{remaining}分钟" if remaining else f"{hours}小时"


def build_roast_payload(
    event: ActivityEvent, recent_roasts: list[str], creative_direction: str
) -> dict:
    payload = event.as_context()
    activity = event.recent_activity[-12:]
    route = [str(item.get("app", "")) for item in activity if item.get("app")]
    route.append(event.to_app)
    payload["behavior_summary"] = {
        "recent_route": " → ".join(route[-8:]),
        "recorded_switches": len(activity),
        "current_app_appearances": route.count(event.to_app),
        "previous_stay": _duration_label(event.previous_duration)
        if event.previous_duration
        else None,
        "current_stay": _duration_label(event.dwell_duration)
        if event.dwell_duration
        else None,
    }
    payload["creative_direction"] = creative_direction
    payload["recent_roasts"] = recent_roasts[-8:]
    return payload


class RoastService(QObject):
    roast_ready = Signal(str)
    api_error = Signal(str)

    def __init__(self, config: AppConfig) -> None:
        super().__init__()
        self.config = config
        self.pool = QThreadPool.globalInstance()
        self.recent: deque[str] = deque(maxlen=8)
        self.recent_directions: deque[str] = deque(maxlen=3)
        self._workers: set[_RoastWorker] = set()
        self.busy = False

    def generate(self, event: ActivityEvent) -> None:
        if self.busy:
            return
        if not self.config.api_key.strip():
            self._deliver(self._fallback(event))
            return
        direction = self._pick_direction()
        payload = build_roast_payload(event, list(self.recent), direction)
        worker = _RoastWorker(self.config, payload)
        worker.signals.finished.connect(
            lambda text, error, active_worker=worker: self._finish(
                text, error, active_worker
            )
        )
        self.busy = True
        self._workers.add(worker)
        self.pool.start(worker)

    def _finish(self, text: str, error: str, worker: _RoastWorker) -> None:
        self._workers.discard(worker)
        self.busy = False
        if text:
            self._deliver(text)
        else:
            self.api_error.emit(error or "未知错误")

    def _deliver(self, text: str) -> None:
        if text:
            self.recent.append(text)
            self.roast_ready.emit(text)

    def _pick_direction(self) -> str:
        candidates = [
            direction
            for direction in CREATIVE_DIRECTIONS
            if direction not in self.recent_directions
        ]
        direction = random.choice(candidates or list(CREATIVE_DIRECTIONS))
        self.recent_directions.append(direction)
        return direction

    def _fallback(self, event: ActivityEvent) -> str:
        if event.event == "LONG_DWELL":
            minutes = max(1, event.dwell_duration // 60)
            options = [
                f"{event.to_app}看了{minutes}分钟，还没看透？",
                f"在{event.to_app}扎根{minutes}分钟了。",
                f"{event.to_app}这是把你焊住了？",
                f"{minutes}分钟没挪窝，{event.to_app}快收房租了。",
                f"你和{event.to_app}的沉默对视已持续{minutes}分钟。",
                f"这一页陪了你{minutes}分钟，比谁都有耐心。",
            ]
        else:
            source = event.from_app or "刚才"
            target = event.to_app
            topic = re.split(r"\s[-—|]\s", event.title, maxsplit=1)[0].strip()[:12]
            if target == "Steam":
                options = [
                    "项目推进得不错，都推进到 Steam 了。",
                    "工作告一段落，游戏宣布接管现场。",
                    "生产力刚下班，Steam 就准点打卡了。",
                ]
            elif target in {"Chrome", "Edge", "Firefox"}:
                options = [
                    f"从{source}逃到互联网找答案了？",
                    f"{source}不会，浏览器总会吧。",
                    f"浏览器一开，困难就算转交出去了。",
                    f"看来{source}负责提问，互联网负责做人。",
                ]
                if topic:
                    options.extend(
                        [
                            f"盯上《{topic}》了，答案最好自己出现。",
                            f"搜索{topic}，主打一个场外求援。",
                        ]
                    )
            else:
                options = [
                    f"{source}待不住，{target}也未必行。",
                    f"又切到{target}，思路挺会搬家。",
                    f"从{source}到{target}，忙得很具体。",
                    f"{source}把问题交接给{target}了。",
                    f"窗口换得很果断，思路正在路上。",
                    f"{target}隆重登场，希望它知道该干什么。",
                ]
        fresh = [item for item in options if item not in self.recent]
        return random.choice(fresh or options)
