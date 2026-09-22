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
- 涉及时长时只能引用 behavior_summary 中已经换算好的文字，不要自行计算原始秒数；
- 按 creative_direction 指定的创作角度发挥，但事实必须来自上下文；
- 攻击性 5/10、屑度 9/10、戏剧感 7/10：语气得意、傲娇、欠欠的，像早就看穿用户却故意把小动作演成重大新闻；
- 可以使用“不会吧不会吧～”“这就不行啦？”“被我看穿了吧”“真拿你没办法呢♡”“就这？”等小恶魔式挑衅，但不要把它们当固定模板；
- 浮夸感可以来自新闻播报、游戏系统提示、法庭判词、舞台报幕、史诗旁白或假装客服，不必依赖固定开场白；
- 偶尔可以说“杂鱼操作♡”，但只能形容这次操作，绝不能直接称呼用户为“杂鱼”；
- 每句最多使用一个浮夸桥段和一个“～”“♡”“(¬Ξ¬)”点缀，不要每次都加，也不要连续复用同一口癖；
- 只有 creative_direction 明确标记为“低频暧昧”时，才允许使用一句轻微成人向双关；必须含蓄、不露骨，不涉及身体部位、性行为、未成年或萝莉设定；
- HECKLE 不读取代码正文，不能凭空评价代码行数或内容长短；长短双关只能依据上下文提供的停留时长、切换速度或反复次数；
- 每句必须至少有一个清晰的风格标记：浮夸叙事、得意反问、假装同情或颜文字点缀，不能退回普通旁白；
- 只调侃眼前这次操作、拖延、摸鱼或反复横跳，不贬低能力，不攻击身份、外貌和人格；
- 笑点要带一点居高临下的得意和假装同情，像屑萌损友逗一下就收手；避免生硬、难懂或与操作无关的比喻；
- 必须避开 avoid_openings，并与 recent_roasts 在开头、句式、叙事身份、笑点和关键词上明显不同。

禁止解释、建议、效率提醒、说教、脏话、羞辱性称呼、色情暗示、身份攻击、引号、标签和名称前缀。"""


CREATIVE_DIRECTIONS = (
    "细节捕手：从当前窗口标题里抓一个具体词做笑点，别泛泛谈应用。",
    "反差喜剧：利用前后应用或任务看起来互相矛盾的地方。",
    "新闻快讯：把普通切换当成重大新闻，但不要使用固定的播报开场白。",
    "游戏系统：把当前操作写成任务失败、技能触发或成就解锁，别真的给建议。",
    "迷你法庭：像宣读判词一样给这次操作定性，罪名要可爱又具体。",
    "假装客服：用过度体贴的口吻关怀用户的小失误，暗暗露出坏笑。",
    "史诗旁白：把微不足道的窗口切换写成命运转折，夸张但要简短。",
    "装乖旁白：一本正经地描述操作，最后露出早已看穿一切的坏笑。",
    "屑萌夸奖：故意夸得很敷衍，再用欠欠的反问揭穿小动作。",
    "行为回扣：结合最近应用路径，笑用户又绕回来了，像抓包而不是审判。",
    "可爱比喻：用新鲜又轻巧的比喻描述行为，不用尖锐或贬损词。",
    "应用串通：把前后两个应用写成偷偷交接、互相告状或一起看热闹。",
    "预言揭晓：假装早就猜到用户会切来这里，得意地宣布预言成真。",
    "舞台报幕：把新窗口当成抢到 C 位的演员，聚光灯只照一个具体笑点。",
    "小恶魔反问：用明知故问的方式戳破借口，语气屑屑的但点到为止。",
    "低频暧昧：只基于真实停留时长或切换速度玩一句含蓄的长短双关，例如耐心太短、黏得太久或让人受不了；成人式调侃，不露骨。",
)


class _WorkerSignals(QObject):
    finished = Signal(str, str)


class _RoastWorker(QRunnable):
    def __init__(self, config: AppConfig, payload: dict) -> None:
        super().__init__()
        # PySide may delete an auto-deleting QRunnable before its queued signal
        # is delivered. RoastService owns the worker until _finish instead.
        self.setAutoDelete(False)
        self.config = config
        self.payload = payload
        self.signals = _WorkerSignals()

    def run(self) -> None:
        text = ""
        error = ""
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
            content = response.json()["choices"][0]["message"]["content"]
            text = _clean(content)
        except httpx.HTTPStatusError as exc:
            message = _response_error(exc.response)
            error = f"HTTP {exc.response.status_code}：{message}"
        except httpx.RequestError as exc:
            error = f"网络错误：{str(exc)[:100]}"
        except Exception as exc:
            error = f"响应异常：{type(exc).__name__}"
        self._emit_finished(text, error)

    def _emit_finished(self, text: str, error: str) -> None:
        try:
            self.signals.finished.emit(text, error)
        except RuntimeError:
            # The application can close while an HTTP request is still running.
            # At that point Qt has already destroyed the signal source, so there
            # is no UI left to receive the result and the worker should exit quietly.
            pass


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
        "recent_sessions": [
            {
                "app": str(item.get("app", "")),
                "title": str(item.get("title", ""))[:80],
                "stay": _duration_label(int(item.get("duration", 0))),
            }
            for item in activity[-8:]
        ],
        "previous_stay": _duration_label(event.previous_duration)
        if event.previous_duration
        else None,
        "current_stay": _duration_label(event.dwell_duration)
        if event.dwell_duration
        else None,
    }
    payload["creative_direction"] = creative_direction
    payload["avoid_openings"] = [roast[:10] for roast in recent_roasts[-8:]]
    payload["tone_profile"] = {
        "persona": "二次元屑萌小恶魔式调侃",
        "aggression": "5/10",
        "smugness": "9/10",
        "drama": "7/10",
        "feeling": "屑萌、傲娇、明知故问、假装同情、略微浮夸",
        "must_have": "至少一个浮夸叙事、得意反问、假装同情或颜文字点缀",
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
        self.closing = False

    def generate(self, event: ActivityEvent) -> None:
        if self.busy or self.closing:
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

    def shutdown(self) -> None:
        self.closing = True

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
                f"耐心大赛进入第{minutes}分钟，{event.to_app}暂时领先哦～",
                f"你和{event.to_app}对视{minutes}分钟，胜负仍未揭晓♡",
                f"还在这一页哦？真拿你没办法呢♡",
                f"本庭宣判：盯住{event.to_app}{minutes}分钟，执着过量啦。",
                f"你和{event.to_app}感情真好，舍不得走啦？",
                f"这页陪了你{minutes}分钟，杂鱼操作被看光啦♡",
                f"停留成就已解锁：和{event.to_app}一起发呆{minutes}分钟～",
                f"客服温馨提醒：{event.to_app}不会因为久看就自己完成哦。",
                f"和{event.to_app}黏了{minutes}分钟，是想让我先受不了呀♡",
            ]
        else:
            source = event.from_app or "刚才"
            target = event.to_app
            topic = re.split(r"\s[-—|]\s", event.title, maxsplit=1)[0].strip()[:12]
            if target == "Steam":
                options = [
                    "聚光灯就位，Steam 抢在项目之前登场啦♡",
                    "这么快就到 Steam，手指比借口诚实嘛～",
                    "工作刚有难度，Steam 救援队就精准抵达啦～",
                    "逃课技能发动成功，目的地：Steam。熟练度满分呢♡",
                    "本庭宣布，项目败诉，Steam 当场接管休庭时间。",
                    "我就知道下一站是 Steam，预言也太容易了吧～",
                    "工作耐心短短的也很可爱，Steam 一叫就跑啦♡",
                ]
            elif target in {"Chrome", "Edge", "Firefox"}:
                options = [
                    f"{source}才卡一下，互联网救援队就全员出动啦～",
                    f"浏览器客服已上线，专门照顾这位小迷糊♡",
                    f"{source}负责出题，浏览器负责哄你是吧？",
                    f"答案还没来，杂鱼操作倒是很熟练嘛♡",
                    f"求助技能触发成功，浏览器获得临时 C 位。",
                    f"我就知道你会来浏览器，预言简单得没成就感～",
                    f"才卡这么一下就求助，耐心短短的也很可爱嘛♡",
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
                    f"思路还在路上，{target}已经抢先空降现场啦～",
                    f"{source}和{target}来回跑，假装很忙的样子嘛♡",
                    f"{source}把问题交给{target}，好会甩锅哦～",
                    f"换窗口这么熟练，问题真的解决了吗？(¬Ξ¬)",
                    f"聚光灯转向{target}，这次不会又只是看看吧？",
                    f"切换成就已解锁：问题没动，窗口先走一步。",
                    f"我就知道你会来{target}，这点小心思太好猜啦～",
                    f"才待这么短就换到{target}，这点耐心够谁用呀♡",
                ]
        fresh = [item for item in options if item not in self.recent]
        return random.choice(fresh or options)
