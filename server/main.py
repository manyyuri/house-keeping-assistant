"""FastAPI 入口：挂载 REST 路由、静态图目录、CORS、二维码。

启动（局域网可访问）：
    uvicorn server.main:app --host 0.0.0.0 --port 8000
"""

import asyncio
import io
import logging
import re
import socket
import uuid
from datetime import date
from typing import AsyncIterator, List, Optional

import qrcode
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

from server import agent, db, llm_providers, meals, rules, vision
from server.models import (
    ConversationCreate,
    GroceryCheckPatch,
    ItemPatch,
    LLMSettingsIn,
    LLMTestIn,
    MealRerollIn,
    MealStatusPatch,
    PlanCreate,
    PlanPatch,
    TaskPatch,
)
from server.llm_providers import Endpoint, LLMUnavailable
from server.prompts import SYSTEM_PROMPT
from server.sse import sse_event
from server.tools import ToolContext

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("danshari")

# HEIC 支持注册（iPhone 默认格式）
register_heif_opener()

app = FastAPI(title="断舍离家务整理 Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态图目录：/api/photos/2026-08-16/xxx.jpg → server/data/photos/...
PHOTOS_DIR = db.DATA_DIR / db.PHOTOS_DIR_NAME
PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/api/photos", StaticFiles(directory=str(PHOTOS_DIR)), name="photos")


@app.on_event("startup")
async def startup() -> None:
    db.get_conn()  # 提前建表
    seeded = meals.seed_default_recipes()
    if seeded:
        logger.info("种子菜谱导入 %d 道（knowledge/recipes）", seeded)
    cfg = llm_providers.get_config()

    def _fmt(ep: llm_providers.Endpoint) -> str:
        key = f" {llm_providers.mask_key(ep.api_key)}" if ep.api_key else ""
        return f"{ep.provider}:{ep.model}{key}"

    logger.info(
        "系统提示词拼装完成：长度 %d 字符（含断舍离速查表）", len(SYSTEM_PROMPT)
    )
    logger.info("模型配置：vision=%s agent=%s", _fmt(cfg.vision), _fmt(cfg.agent))


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True}


# ---------- conversations ----------

@app.get("/api/conversations")
async def get_conversations():
    return db.list_conversations()


@app.post("/api/conversations")
async def post_conversation(body: ConversationCreate):
    return db.create_conversation(title=body.title, room=body.room)


@app.get("/api/conversations/{conversation_id}")
async def get_conversation_detail(conversation_id: int):
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(404, "会话不存在")
    conv["messages"] = db.list_messages(conversation_id)
    return conv


@app.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: int):
    if not db.delete_conversation(conversation_id):
        raise HTTPException(404, "会话不存在")
    return {"ok": True}


# ---------- upload（§5.2 转码规则）----------

MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 单图 15MB（HEIC 原图 3-8MB）
MAX_IMAGES_PER_REQUEST = 4
PHOTO_MAX_SIDE = 1024


def transcode_to_jpeg(raw: bytes) -> bytes:
    """打开任意格式（含 HEIC）→ EXIF 转正 → RGB → 最长边 1024 → JPEG(85)。

    EXIF 转正必须在压缩之前，否则手机竖拍照片会旋转 90°。
    """
    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    if max(img.size) > PHOTO_MAX_SIDE:
        img.thumbnail((PHOTO_MAX_SIDE, PHOTO_MAX_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


@app.post("/api/upload")
async def upload_photos(
    files: List[UploadFile] = File(...),
    room: Optional[str] = Form(None),
):
    if len(files) > MAX_IMAGES_PER_REQUEST:
        raise HTTPException(413, f"单次最多上传 {MAX_IMAGES_PER_REQUEST} 张")

    out = []
    for f in files:
        raw = await f.read()
        if len(raw) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "单图超过 15MB 上限")
        try:
            jpeg = transcode_to_jpeg(raw)
        except Exception:
            raise HTTPException(400, f"无法解析图片文件：{f.filename}")

        day_dir = PHOTOS_DIR / date.today().isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        name = f"{uuid.uuid4().hex[:12]}.jpg"
        (day_dir / name).write_bytes(jpeg)

        rel = f"{db.PHOTOS_DIR_NAME}/{date.today().isoformat()}/{name}"
        photo = db.create_photo(path=rel, room=room)
        out.append(photo_url(photo))

    logger.info("上传 %d 张照片（room=%s）", len(out), room)
    return out


def photo_url(photo: dict) -> dict:
    """DB 相对路径 photos/yyyy-mm-dd/x.jpg → /api/photos/yyyy-mm-dd/x.jpg"""
    rel = photo["path"]
    rel = rel[len(db.PHOTOS_DIR_NAME) + 1:] if rel.startswith(db.PHOTOS_DIR_NAME + "/") else rel
    return {"photoId": photo["id"], "path": photo["path"], "url": f"/api/photos/{rel}"}


# ---------- qrcode ----------

def _lan_ip() -> str:
    """自动探测局域网 IP（UDP connect 技巧，不真正发包）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


@app.post("/api/qrcode")
async def qrcode_png():
    """生成 http://<局域网IP>:5173 的 PNG，供桌面端展示、iPhone 扫码直达。"""
    url = f"http://{_lan_ip()}:5173"
    img = qrcode.make(url, box_size=10, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png", headers={"X-Target-Url": url})


@app.get("/api/qrcode")
async def qrcode_png_get():
    return await qrcode_png()


# ---------- plans ----------

@app.get("/api/plans")
async def get_plans(status: Optional[str] = None):
    return db.list_plans(status=status)


@app.post("/api/plans")
async def post_plan(body: PlanCreate):
    """手动新建计划（不经 Agent）：仅填区域即可创建，后续再关联任务/照片。

    danshari_score 存 NULL（未评估），不伪造规则评分。
    """
    plan = db.create_plan(
        room=body.room.strip(),
        summary=(body.summary or "").strip(),
        danshari_score=None,
        discard_count=0,
        donate_count=0,
        keep_count=0,
    )
    return plan


@app.get("/api/plans/{plan_id}")
async def get_plan_detail(plan_id: int):
    plan = db.get_plan(plan_id)
    if not plan:
        raise HTTPException(404, "计划不存在")
    return plan


@app.patch("/api/plans/{plan_id}")
async def patch_plan(plan_id: int, body: PlanPatch):
    plan = db.update_plan_status(plan_id, body.status)
    if not plan:
        raise HTTPException(404, "计划不存在")
    return plan


# ---------- tasks ----------

@app.get("/api/tasks")
async def get_tasks(
    status: Optional[str] = None,
    type: Optional[str] = None,
    plan_id: Optional[int] = None,
):
    return db.list_tasks(status=status, type_=type, plan_id=plan_id)


@app.patch("/api/tasks/{task_id}")
async def patch_task(task_id: int, body: TaskPatch):
    task = db.update_task_status(task_id, body.status)
    if not task:
        raise HTTPException(404, "任务不存在")
    return task


# ---------- items ----------

@app.get("/api/items")
async def get_items(
    keep_status: Optional[str] = None,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
):
    return db.query_items(
        keep_status=keep_status, category=category, keyword=keyword
    )


@app.patch("/api/items/{item_id}")
async def patch_item(item_id: int, body: ItemPatch):
    if body.keep_status and not re.match(
        r"^(keep|donate|discard|hesitate|unjudged)$", body.keep_status
    ):
        raise HTTPException(422, "keep_status 取值非法")
    item = db.update_item(
        item_id,
        keep_status=body.keep_status,
        last_used=body.last_used,
        reason=body.reason,
        quarantine_until=(
            rules.quarantine_until_today() if body.keep_status == "hesitate" else None
        ),
    )
    if not item:
        raise HTTPException(404, "物品不存在")
    return item


# ---------- stats ----------

@app.get("/api/stats")
async def get_stats():
    return {
        "discard_count": db.count_items("discard"),
        "donate_count": db.count_items("donate"),
        "keep_count": db.count_items("keep"),
        "hesitate_count": db.count_items("hesitate"),
        "done_tasks": db.count_done_tasks(),
        "avg_danshari_score": db.avg_danshari_score(),
        "active_hesitate": db.active_hesitate_items(),
        "expired_quarantine": db.expired_quarantine_items(),
    }


# ---------- meals（三餐推荐）----------


@app.get("/api/meals")
async def get_meals(date: Optional[str] = None):
    """当日三餐（无则幂等生成）；今日晚餐首次生成时补一句 LLM 小贴士（可降级）。"""
    if date and not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        raise HTTPException(422, "date 格式应为 yyyy-mm-dd")
    try:
        day = meals.ensure_day(date)
    except ValueError as e:
        raise HTTPException(422, str(e))
    dinner = day["meals"].get("dinner")
    if not date and dinner and dinner.get("recipe") and dinner.get("note") is None:
        tip = await meals.dinner_tip(dinner["recipe"])
        db.update_meal_note(dinner["id"], tip)
        dinner["note"] = tip
    return day


@app.get("/api/meals/week")
async def get_meals_week(start: Optional[str] = None):
    try:
        return meals.week(start)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/meals/reroll")
async def post_meal_reroll(body: MealRerollIn):
    if body.meal_type not in meals.MEAL_ORDER:
        raise HTTPException(422, "meal_type 必须为 breakfast/lunch/dinner")
    try:
        return meals.reroll(body.date, body.meal_type)
    except meals.BentoLocked:
        raise HTTPException(409, "bento_locked")
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.patch("/api/meals/{meal_plan_id}")
async def patch_meal_status(meal_plan_id: int, body: MealStatusPatch):
    plan = db.update_meal_status(meal_plan_id, body.status)
    if not plan:
        raise HTTPException(404, "餐计划不存在")
    return plan


# ---------- grocery（盒马买菜清单）----------


@app.get("/api/grocery")
async def get_grocery(days: int = 3):
    if not 1 <= days <= 7:
        raise HTTPException(422, "days 取值 1~7")
    return meals.grocery(days)


@app.patch("/api/grocery/{item_id}")
async def patch_grocery(item_id: int, body: GroceryCheckPatch):
    if not db.toggle_grocery(item_id, body.checked):
        raise HTTPException(404, "清单项不存在")
    return {"ok": True, "id": item_id, "checked": body.checked}


@app.delete("/api/grocery")
async def delete_grocery(bought: bool = True):
    """采购完成：清空全部已勾选项。"""
    return {"ok": True, "deleted": db.clear_checked_grocery()}


# ---------- SSE：/api/chat（视觉→Agent→工具→事件流，§5.4）----------

DELTA_CHUNK = 80          # 最终文本分段推送粒度
HISTORY_LIMIT = 6         # needle 是 14MB 轻量模型，历史窗口要小


def _history_for_agent(conversation_id: int) -> List[dict]:
    rows = [
        m for m in db.list_messages(conversation_id)
        if m["role"] in ("user", "assistant")
    ]
    return [{"role": m["role"], "content": m["content"]} for m in rows[-HISTORY_LIMIT:]]


_PIPELINE_END = object()  # SSE 中继循环终止哨兵


async def _chat_stream(
    request: Request,
    conversation_id: int,
    message: str,
    photo_ids: List[int],
) -> AsyncIterator[str]:
    """SSE 中继：管道在后台任务中执行，客户端断开后仍继续跑完并落库。

    手机端锁屏/切后台会掐断 SSE（iOS Safari 行为），若管道随连接取消，
    已执行到一半的 Agent 轮次与最终总结将丢失。改为：断连仅停止事件转发，
    管道后台继续 → 用户重新打开会话即可看到完整回复。
    """
    photos = db.get_photos(photo_ids)
    attachments = [{"photoId": p["id"], "path": p["path"]} for p in photos]
    db.add_message(conversation_id, "user", message, attachments)

    queue: asyncio.Queue = asyncio.Queue()

    async def pipeline() -> None:
        summaries: List[str] = []
        messiness = "low"
        messiness_rank = {"low": 0, "medium": 1, "high": 2}

        # ① 视觉识别
        if photos:
            queue.put_nowait(sse_event("vision_start", {"photoIds": [p["id"] for p in photos]}))
            for p in photos:
                img_path = db.DATA_DIR / p["path"]
                try:
                    raw = img_path.read_bytes()
                except OSError as e:
                    queue.put_nowait(sse_event("error", {"message": f"照片文件缺失：{e}", "stage": "vision"}))
                    continue
                try:
                    result = await vision.recognize(raw, room_hint=p.get("room") or "")
                except LLMUnavailable as e:
                    queue.put_nowait(sse_event("error", {"message": str(e), "stage": "vision"}))
                    queue.put_nowait(sse_event("done", {"messageId": None}))
                    return
                except Exception as e:  # noqa: BLE001 — 模型超时/5xx 等不裸断流
                    logger.exception("视觉识别失败")
                    queue.put_nowait(sse_event("error", {"message": f"视觉识别失败：{e}", "stage": "vision"}))
                    queue.put_nowait(sse_event("done", {"messageId": None}))
                    return
                db.update_photo_vision(p["id"], result.room, result.vision_text)
                # 一个批次的混乱度取所有照片中的最高等级，避免后处理的整洁照片
                # 覆盖前面更混乱区域的信号。
                if messiness_rank.get(result.messiness, 0) > messiness_rank.get(messiness, 0):
                    messiness = result.messiness
                summaries.append(result.to_summary())
                queue.put_nowait(
                    sse_event(
                        "vision_done",
                        {
                            "photoId": p["id"],
                            "room": result.room,
                            "messiness": result.messiness,
                            "items": result.items,
                            "suspected": result.suspected,
                            "degraded": result.degraded,
                        },
                    )
                )
            queue.put_nowait(sse_event("thought", {"node": "识别完成→开始评估", "status": "done"}))

        # ② Agent 编排（工具事件经队列实时转发）
        ctx = ToolContext(
            conversation_id=conversation_id,
            photo_ids=[p["id"] for p in photos],
            messiness=messiness,
        )
        messages = agent.build_messages(
            _history_for_agent(conversation_id), message, summaries
        )

        async def on_event(ev: dict) -> None:
            if ev["type"] == "tool_call":
                queue.put_nowait(sse_event("tool_call", {"name": ev["name"], "args": ev["args"]}))
            elif ev["type"] == "tool_result":
                queue.put_nowait(
                    sse_event("tool_result", {"name": ev["name"], "ok": ev["ok"], "summary": ev["summary"]})
                )
            else:
                queue.put_nowait(sse_event("thought", ev))
        try:
            result = await agent.run_agent(messages, ctx, on_event)
        except LLMUnavailable as e:
            queue.put_nowait(sse_event("error", {"message": str(e), "stage": "agent"}))
            queue.put_nowait(sse_event("done", {"messageId": None}))
            return
        except Exception as e:  # noqa: BLE001 — 兑底，不让管道裸断
            logger.exception("Agent 编排失败")
            queue.put_nowait(sse_event("error", {"message": f"Agent 编排失败：{e}", "stage": "agent"}))
            queue.put_nowait(sse_event("done", {"messageId": None}))
            return

        # ③ 最终文本分段（推入队列；客户端在不在都照常落库）
        text = result.text.strip() or "本次整理已完成，请到任务看板查看可执行清单。"
        for i in range(0, len(text), DELTA_CHUNK):
            queue.put_nowait(sse_event("message_delta", {"delta": text[i : i + DELTA_CHUNK]}))

        # ④ 计划卡片事件 + 收尾
        if ctx.last_plan:
            queue.put_nowait(
                sse_event(
                    "plan_created",
                    {
                        "planId": ctx.last_plan["plan_id"],
                        "danshariScore": ctx.last_plan["danshari_score"],
                        "taskCount": ctx.last_plan.get("task_count", 0),
                    },
                )
            )
        saved = db.add_message(conversation_id, "assistant", text)
        queue.put_nowait(sse_event("done", {"messageId": saved["id"]}))

    task = asyncio.create_task(pipeline())
    task.add_done_callback(lambda _: queue.put_nowait(_PIPELINE_END))

    # SSE 中继：只转发事件，不取消管道
    while True:
        if await request.is_disconnected():
            logger.info("客户端断开，管道后台继续执行（conversation=%s）", conversation_id)
            return
        try:
            item = await asyncio.wait_for(queue.get(), timeout=0.25)
        except asyncio.TimeoutError:
            continue
        if item is _PIPELINE_END:
            return
        yield item


@app.get("/api/chat")
async def chat(
    request: Request,
    conversation_id: int,
    message: str = Query(..., min_length=1),
    photo_ids: str = Query(""),
):
    ids: List[int] = []
    if photo_ids.strip():
        try:
            ids = [int(x) for x in photo_ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(422, "photo_ids 格式应为逗号分隔的数字")
    if not db.get_conversation(conversation_id):
        raise HTTPException(404, "会话不存在")

    return StreamingResponse(
        _chat_stream(request, conversation_id, message, ids),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------- LLM 模型设置（§4：读取/保存/测试连接）----------

@app.get("/api/settings/llm")
async def get_llm_settings():
    """掩码视图：api_key 恒为空串，只回 api_key_masked。"""
    return llm_providers.settings_view()


@app.put("/api/settings/llm")
async def put_llm_settings(body: LLMSettingsIn):
    """保存即生效（进程内配置缓存写时失效，无需重启）。"""
    payload = body.model_dump()
    notices = llm_providers.locked_notices(payload)  # 环境变量覆盖的字段提示不生效
    try:
        llm_providers.save_config(payload)
    except ValueError as e:
        raise HTTPException(422, str(e))
    view = llm_providers.settings_view()
    if notices:
        view["notices"] = notices
        for n in notices:
            logger.warning("模型设置：%s", n)
    return view


@app.post("/api/settings/llm/test")
async def test_llm_settings(body: LLMTestIn):
    """测试连接：用表单当前值（缺省字段回退已存配置），支持"保存前先测"。"""
    if body.scope not in ("vision", "agent"):
        raise HTTPException(422, "scope 必须为 vision 或 agent")
    cfg = llm_providers.get_config()
    saved = cfg.vision if body.scope == "vision" else cfg.agent
    ep_in = body.endpoint.model_dump() if body.endpoint else {}
    endpoint = Endpoint(
        provider=(ep_in.get("provider") or saved.provider).strip(),
        base_url=(ep_in.get("base_url") or saved.base_url).strip(),
        api_key=(ep_in.get("api_key") or saved.api_key).strip(),
        model=(ep_in.get("model") or saved.model).strip(),
    )
    if endpoint.provider == llm_providers.PROVIDER_OLLAMA and not endpoint.base_url:
        endpoint.base_url = llm_providers.OLLAMA_DEFAULT_URL
    if endpoint.provider == llm_providers.PROVIDER_OPENAI:
        from server import openai_provider

        return await openai_provider.check_health(endpoint, body.scope)
    from server import ollama_provider

    return await ollama_provider.check_health(endpoint)
