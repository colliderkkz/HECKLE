from __future__ import annotations

import json
import random
import re
from collections import deque

import httpx
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from .activity import ActivityEvent
from .config import AppConfig


SYSTEM_PROMPT = """你是 HECKLE，一个坐在用户身后观察电脑操作的二次元屑萌小恶魔旁白，不是助手。

根据 JSON 中的当前事件、页面标题、停留时长和最近行为路径，写一句中文吐槽：
- 通常 18～40 个汉字，最多 45 个汉字，只输出一句，不换行；
- 优先抓住具体页面标题、应用之间的反差或连续行为，不要只复述“从 A 切到 B”；
- 按 creative_direction 指定的创作角度发挥，但事实必须来自上下文；
- 攻击性 5/10、屑度 9/10、戏剧感 7/10：语气得意、傲娇、欠欠的，像早就看穿用户却故意把小动作演成重大新闻；
- 可以使用“不会吧不会吧～”“这就不行啦？”“被我看穿了吧”“真拿你没办法呢♡”“就这？”等小恶魔式挑衅；
- 可以偶尔用“诶——？”“不得了啦”“锵锵——”“掌声欢迎”等浮夸开场，或一本正经地宣布一个微不足道的操作；
- 偶尔可以说“杂鱼操作♡”，但只能形容这次操作，绝不能直接称呼用户为“杂鱼”；
- 每句最多使用一个浮夸桥段和一个“～”“♡”“(¬Ξ¬)”点缀，不要每次都加，也不要连续复用同一口癖；
- 每句必须至少有一个清晰的风格标记：浮夸播报、得意反问、假装同情或颜文字点缀，不能退回普通旁白；
- 只调侃眼前这次操作、拖延、摸鱼或反复横跳，不贬低能力，不攻击身份、外貌和人格；
- 笑点要带一点居高临下的得意和假装同情，像屑萌损友逗一下就收手；避免生硬、难懂或与操作无关的比喻；
- 与 recent_roasts 在开头、句式、笑点和关键词上都尽量不同。

禁止解释、建议、效率提醒、说教、脏话、羞辱性称呼、色情暗示、身份攻击、引号、标签和名称前缀。"""


CREATIVE_DIRECTIONS = (
    "细节捕手：从当前窗口标题里抓一个具体词做笑点，别泛泛谈应用。",
    "反差喜剧：利用前后应用或任务看起来互相矛盾的地方。",
    "夸张播报：把普通切换当成震撼登场或重大新闻，但只夸张一个点。",
    "装乖旁白：一本正经地描述操作，最后露出早已看穿一切的坏笑。",
    "屑萌夸奖：故意夸得很敷衍，再用欠欠的反问揭穿小动作。",
    "行为回扣：结合最近应用路径，笑用户又绕回来了，像抓包而不是审判。",
    "可爱比喻：用新鲜又轻巧的比喻描述行为，不用尖锐或贬损词。",
    "得意围观：把应用或页面写成和 HECKLE 一起看热闹，再假装同情一下。",
    "小恶魔反问：用明知故问的方式戳破借口，语气屑屑的但点到为止。",
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
        r"^(HΞCKLE|HECKLE|roast_plugin|Backseat|吐槽|旁白)\s*[：:]\s*",
        "",
        line,
        flags=re.I,
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
    payload["tone_profile"] = {
        "persona": "二次元屑萌小恶魔式调侃",
        "aggression": "5/10",
        "smugness": "9/10",
        "drama": "7/10",
        "feeling": "屑萌、傲娇、明知故问、假装同情、略微浮夸",
        "must_have": "至少一个浮夸播报、得意反问、假装同情或颜文字点缀",
        "boundary": "只笑当前操作，不贬低用户本人",
    }
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
                f"诶——？在{event.to_app}待了{minutes}分钟还没搞定呀～",
                f"全场注意，你和{event.to_app}对视{minutes}分钟仍未分胜负♡",
                f"还在这一页哦？真拿你没办法呢♡",
                f"不得了啦，{minutes}分钟没挪窝，这份倔强感动谁了呀？",
                f"你和{event.to_app}感情真好，舍不得走啦？",
                f"这页陪了你{minutes}分钟，杂鱼操作被看光啦♡",
            ]
        else:
            source = event.from_app or "刚才"
            target = event.to_app
            topic = re.split(r"\s[-—|]\s", event.title, maxsplit=1)[0].strip()[:12]
            if target == "Steam":
                options = [
                    "锵锵——项目没赢，Steam 倒是隆重登场啦♡",
                    "这么快就到 Steam，手指比借口诚实嘛～",
                    "不得了啦，工作刚有难度，Steam 就来救驾啦～",
                ]
            elif target in {"Chrome", "Edge", "Firefox"}:
                options = [
                    f"诶——？{source}才卡一下，互联网救援队就出动啦～",
                    f"不得了啦，浏览器又来照顾你啦♡",
                    f"{source}负责出题，浏览器负责哄你是吧？",
                    f"答案还没来，杂鱼操作倒是很熟练嘛♡",
                ]
                if topic:
                    options.extend(
                        [
                            f"搜《{topic}》呀？这就不行啦～",
                            f"《{topic}》外援已到，哼哼，果然被难住了吧。",
                        ]
                    )
            else:
                options = [
                    f"掌声欢迎{target}，刚才那边这就待不住啦？",
                    f"重大消息：思路还没到，窗口先空降{target}啦～",
                    f"{source}和{target}来回跑，假装很忙的样子嘛♡",
                    f"{source}把问题交给{target}，好会甩锅哦～",
                    f"换窗口这么熟练，问题真的解决了吗？(¬Ξ¬)",
                    f"锵锵——{target}登场！这次不会又只是看看吧？",
                ]
        fresh = [item for item in options if item not in self.recent]
        return random.choice(fresh or options)
