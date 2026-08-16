"""FastAPI 入口：挂载路由与静态图目录、CORS、二维码。

启动（局域网可访问）：
    uvicorn server.main:app --host 0.0.0.0 --port 8000
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.prompts import SYSTEM_PROMPT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("danshari")

app = FastAPI(title="断舍离家务整理 Agent")

# 仅本机/局域网开发用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup() -> None:
    logger.info(
        "系统提示词拼装完成：长度 %d 字符（含断舍离速查表）", len(SYSTEM_PROMPT)
    )


@app.get("/api/health")
async def health() -> dict:
    """健康检查，供前端探测后端可达性。"""
    return {"ok": True}
