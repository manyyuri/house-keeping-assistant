"""Ollama 本地 Provider adapter（自 ollama_client.py 平移，端点参数化）。"""

import base64
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from server.llm_providers import Endpoint, LLMUnavailable

logger = logging.getLogger("danshari.ollama")

_TIMEOUT_VISION = httpx.Timeout(300.0, connect=10.0)  # 视觉推理较慢
_TIMEOUT_AGENT = httpx.Timeout(120.0, connect=10.0)


class OllamaUnavailable(LLMUnavailable):
    """Ollama 服务不可达——请先启动 Ollama 并拉取模型。"""


async def _request(
    endpoint: Endpoint, path: str, payload: Dict[str, Any], timeout: httpx.Timeout
) -> Dict[str, Any]:
    url = endpoint.base_url.rstrip("/") + path
    # trust_env=False：绕过系统代理，本地 Ollama 直连
    async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
        try:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as e:
            raise OllamaUnavailable(
                f"无法连接 Ollama（{endpoint.base_url}），请先启动 Ollama 并拉取模型"
            ) from e
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"Ollama 返回 {e.response.status_code}: {e.response.text[:300]}"
            ) from e


async def vision_generate(endpoint: Endpoint, images: List[bytes], prompt: str) -> str:
    """视觉模型：图 → 文本。POST /api/generate，images 为 base64 数组。"""
    payload = {
        "model": endpoint.model,
        "prompt": prompt,
        "images": [base64.b64encode(b).decode() for b in images],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    data = await _request(endpoint, "/api/generate", payload, _TIMEOUT_VISION)
    return data.get("response", "")


async def agent_chat(
    endpoint: Endpoint,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Agent（needle）：文本 → function calls。返回 Ollama 风格 message。"""
    payload: Dict[str, Any] = {
        "model": endpoint.model,
        "messages": messages,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
    data = await _request(endpoint, "/api/chat", payload, _TIMEOUT_AGENT)
    return data.get("message", {})


async def check_health(endpoint: Endpoint) -> Dict[str, Any]:
    """探测 Ollama 可达性与模型是否已拉取（供测试连接）。"""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(base_url=endpoint.base_url, timeout=5.0, trust_env=False) as client:
            resp = await client.get("/api/tags")
            resp.raise_for_status()
    except (httpx.HTTPError, OSError) as e:
        return {
            "ok": False,
            "message": f"无法连接 Ollama（{endpoint.base_url}）：{e.__class__.__name__}",
        }
    names = [m.get("name", "") for m in resp.json().get("models", [])]
    has_model = any(n == endpoint.model or n.split(":")[0] == endpoint.model for n in names)
    if not has_model:
        return {
            "ok": False,
            "message": f"Ollama 可达，但模型 {endpoint.model} 未拉取（ollama pull {endpoint.model}）",
        }
    return {
        "ok": True,
        "message": "ok",
        "latency_ms": int((time.monotonic() - start) * 1000),
    }
