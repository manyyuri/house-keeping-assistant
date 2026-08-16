"""FastAPI 入口：挂载 REST 路由、静态图目录、CORS、二维码。

启动（局域网可访问）：
    uvicorn server.main:app --host 0.0.0.0 --port 8000
"""

import io
import logging
import re
import socket
import uuid
from datetime import date
from pathlib import Path
from typing import List, Optional

import qrcode
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

from server import db, rules
from server.models import (
    ConversationCreate,
    ItemPatch,
    PlanPatch,
    TaskPatch,
)
from server.prompts import SYSTEM_PROMPT

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
    logger.info(
        "系统提示词拼装完成：长度 %d 字符（含断舍离速查表）", len(SYSTEM_PROMPT)
    )


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
