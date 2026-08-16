"""Ollama HTTP 封装（视觉/Agent 两客户端）。

模型服务均通过 Ollama 本地服务暴露（默认 http://localhost:11434），
后端只发 HTTP 请求，便于单独替换升级任一模块。
"""

import asyncio
import base64
import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("danshari.ollama")

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
VISION_MODEL = os.environ.get("VISION_MODEL", "qwen3-vl:8b")
AGENT_MODEL = os.environ.get("AGENT_MODEL", "needle")

_TIMEOUT_VISION = httpx.Timeout(300.0, connect=10.0)  # 视觉推理较慢
_TIMEOUT_AGENT = httpx.Timeout(120.0, connect=10.0)


class OllamaUnavailable(RuntimeError):
    """Ollama 服务不可达——上层降级提示"请先启动 Ollama 并拉取模型"。"""


async def _request(
    path: str, payload: Dict[str, Any], timeout: httpx.Timeout
) -> Dict[str, Any]:
    async with httpx.AsyncClient(base_url=OLLAMA_URL, timeout=timeout) as client:
        try:
            resp = await client.post(path, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as e:
            raise OllamaUnavailable(
                f"无法连接 Ollama（{OLLAMA_URL}），请先启动 Ollama 并拉取模型"
            ) from e
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Ollama 返回 {e.response.status_code}: {e.response.text[:300]}"
            ) from e


async def vision_generate(images: List[bytes], prompt: str) -> str:
    """视觉模型：图 → 文本。POST /api/generate，images 为 base64 数组。"""
    payload = {
        "model": VISION_MODEL,
        "prompt": prompt,
        "images": [base64.b64encode(b).decode() for b in images],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    data = await _request("/api/generate", payload, _TIMEOUT_VISION)
    return data.get("response", "")


async def agent_chat(
    messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Agent（needle）：文本 → function calls。

    返回 message dict，可能含 tool_calls；stream:false 一次返回。
    """
    payload: Dict[str, Any] = {
        "model": AGENT_MODEL,
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
    data = await _request("/api/chat", payload, _TIMEOUT_AGENT)
    return data.get("message", {})


async def check_models() -> Dict[str, bool]:
    """探测视觉与 Agent 模型是否已拉取（供健康检查/降级提示）。"""
    available: Dict[str, bool] = {VISION_MODEL: False, AGENT_MODEL: False}
    try:
        async with httpx.AsyncClient(base_url=OLLAMA_URL, timeout=5.0) as client:
            resp = await client.get("/api/tags")
            resp.raise_for_status()
            for m in resp.json().get("models", []):
                name = m.get("name", "")
                for want in list(available):
                    if name == want or name.split(":")[0] == want:
                        available[want] = True
    except (httpx.HTTPError, OSError):
        logger.warning("Ollama 不可达：%s", OLLAMA_URL)
    return available


if __name__ == "__main__":
    print(asyncio.run(check_models()))
