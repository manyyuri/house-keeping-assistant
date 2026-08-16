"""OpenAI 兼容远程 Provider adapter（DashScope/DeepSeek/SiliconFlow 等）。

httpx 手写实现，不引入 openai SDK。请求/响应在协议边界做
Ollama 风格 ↔ OpenAI 风格转换，agent.py / vision.py 感知不到协议差异。
"""

import base64
import io
import json
import logging
import time
from typing import Any, Dict, List, Optional

import httpx

from server.llm_providers import Endpoint, RemoteLLMError

logger = logging.getLogger("danshari.openai")

_TIMEOUT_VISION = httpx.Timeout(300.0, connect=10.0)
_TIMEOUT_AGENT = httpx.Timeout(120.0, connect=10.0)
_TIMEOUT_TEST = httpx.Timeout(30.0, connect=10.0)


def _require(endpoint: Endpoint) -> None:
    if not endpoint.base_url or not endpoint.model or not endpoint.api_key:
        raise RemoteLLMError("云端端点未配置完整（base_url/api_key/model），请在模型设置中补全")


def _headers(endpoint: Endpoint) -> Dict[str, str]:
    return {"Authorization": f"Bearer {endpoint.api_key}", "Content-Type": "application/json"}


async def _post_chat(
    endpoint: Endpoint, payload: Dict[str, Any], timeout: httpx.Timeout
) -> Dict[str, Any]:
    _require(endpoint)
    url = endpoint.base_url.rstrip("/") + "/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            resp = await client.post(url, json=payload, headers=_headers(endpoint))
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        raise RemoteLLMError(f"无法连接 {endpoint.base_url}，请检查网络与地址") from e
    except httpx.TimeoutException as e:
        raise RemoteLLMError("云端 API 请求超时，请稍后重试") from e
    except httpx.HTTPError as e:
        raise RemoteLLMError(f"请求失败：{e.__class__.__name__}") from e

    if resp.status_code in (401, 403):
        raise RemoteLLMError("API key 无效或无权限")
    if resp.status_code == 429:
        raise RemoteLLMError("调用频率超限，请稍后重试（也可在模型设置切回本地 Ollama）")
    if resp.status_code == 404:
        raise RemoteLLMError(f"接口或模型 {endpoint.model} 不存在，请检查 base_url 与模型名")
    if resp.status_code >= 400:
        raise RemoteLLMError(f"云端 API 返回 {resp.status_code}: {resp.text[:200]}")
    try:
        return resp.json()
    except ValueError as e:
        raise RemoteLLMError("云端 API 返回了非 JSON 内容") from e


# ---------- 消息协议转换 ----------

def to_openai_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Ollama 风格 messages → OpenAI 风格。

    tool_call_id 规则（协议正确性关键）：assistant.tool_calls 按顺序生成
    确定性 id（call_{i}_{name}）；紧随其后的 role:"tool" 消息按 name+出现
    顺序回填对应 id。agent.py 的循环保证 tool 消息紧跟其 assistant 消息。
    """
    out: List[Dict[str, Any]] = []
    pending: List[Dict[str, str]] = []  # [{"name":…, "id":…}] 待回填的 id 队列
    for m in messages:
        role = m.get("role")
        if role == "tool":
            name = m.get("name") or ""
            tc_id = ""
            for i, p in enumerate(pending):
                if p["name"] == name:
                    tc_id = pending.pop(i)["id"]
                    break
            if not tc_id and pending:
                tc_id = pending.pop(0)["id"]
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": tc_id or f"call_0_{name}",
                    "content": m.get("content") or "",
                }
            )
        elif role == "assistant" and m.get("tool_calls"):
            calls = []
            pending = []
            for i, tc in enumerate(m["tool_calls"]):
                fn = tc.get("function") or {}
                name = fn.get("name", "")
                cid = f"call_{i}_{name}"
                args = fn.get("arguments")
                if not isinstance(args, str):  # Ollama 可能给 dict，OpenAI 要求字符串
                    args = json.dumps(args or {}, ensure_ascii=False)
                calls.append(
                    {
                        "id": cid,
                        "type": "function",
                        "function": {"name": name, "arguments": args or "{}"},
                    }
                )
                pending.append({"name": name, "id": cid})
            out.append(
                {"role": "assistant", "content": m.get("content") or "", "tool_calls": calls}
            )
        else:
            out.append({"role": role or "user", "content": m.get("content") or ""})
    return out


def normalize_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """OpenAI message → Ollama 风格（agent.py 消费的形态）。

    arguments 保持 JSON 字符串——agent.py::_normalize_args 已兼容 str/dict，
    勿提前 json.loads（防 None 崩溃）。
    """
    tool_calls = []
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        tool_calls.append(
            {"function": {"name": fn.get("name", ""), "arguments": fn.get("arguments") or "{}"}}
        )
    return {"role": "assistant", "content": msg.get("content") or "", "tool_calls": tool_calls}


# ---------- 对外接口（与 ollama_provider 对齐）----------

async def vision_generate(endpoint: Endpoint, images: List[bytes], prompt: str) -> str:
    """视觉模型：图 → 文本。image_url 内容块（data URI）。"""
    content: List[Dict[str, Any]] = [{"type": "text", "text": prompt}]
    for b in images:
        b64 = base64.b64encode(b).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    payload = {
        "model": endpoint.model,
        "stream": False,
        "temperature": 0.2,
        "messages": [{"role": "user", "content": content}],
    }
    data = await _post_chat(endpoint, payload, _TIMEOUT_VISION)
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError) as e:
        raise RemoteLLMError(
            f"云端视觉模型返回结构异常：{json.dumps(data, ensure_ascii=False)[:200]}"
        ) from e


async def agent_chat(
    endpoint: Endpoint,
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Agent：文本 → function calls。tools JSON Schema 与 OpenAI 同源，原样透传。"""
    payload: Dict[str, Any] = {
        "model": endpoint.model,
        "stream": False,
        "messages": to_openai_messages(messages),
    }
    if tools:
        payload["tools"] = tools
    data = await _post_chat(endpoint, payload, _TIMEOUT_AGENT)
    try:
        return normalize_message(data["choices"][0]["message"])
    except (KeyError, IndexError, TypeError) as e:
        raise RemoteLLMError(
            f"云端 Agent 模型返回结构异常：{json.dumps(data, ensure_ascii=False)[:200]}"
        ) from e


def _tiny_jpeg_b64() -> str:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1, 1), (255, 255, 255)).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


async def check_health(endpoint: Endpoint, scope: str = "agent") -> Dict[str, Any]:
    """最小探测请求测连通与鉴权（vision 带 1x1 图，agent 纯文本）。"""
    start = time.monotonic()
    if scope == "vision":
        content: Any = [
            {"type": "text", "text": "test"},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{_tiny_jpeg_b64()}"}},
        ]
    else:
        content = "hi"
    payload = {
        "model": endpoint.model,
        "stream": False,
        "max_tokens": 8,
        "messages": [{"role": "user", "content": content}],
    }
    try:
        await _post_chat(endpoint, payload, _TIMEOUT_TEST)
        return {"ok": True, "message": "ok", "latency_ms": int((time.monotonic() - start) * 1000)}
    except RemoteLLMError as e:
        return {"ok": False, "message": str(e)}
