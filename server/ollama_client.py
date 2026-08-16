"""模型访问路由层（保持旧签名，vision.py / agent.py 调用方零改动）。

视觉与调度分离铁律不变：任何 provider 下都是 vision_generate（图→文本）+
agent_chat（文本→tool calls）两条独立通道。按运行时配置
（llm_providers.get_config）分发到 ollama_provider / openai_provider。
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from server import llm_providers, ollama_provider, openai_provider
from server.llm_providers import LLMConfig, LLMUnavailable, RemoteLLMError
from server.ollama_provider import OllamaUnavailable  # 向后兼容 re-export

__all__ = [
    "vision_generate",
    "agent_chat",
    "check_health",
    "check_models",
    "get_config",
    "LLMUnavailable",
    "RemoteLLMError",
    "OllamaUnavailable",
]

logger = logging.getLogger("danshari.llm")


async def vision_generate(images: List[bytes], prompt: str) -> str:
    cfg = llm_providers.get_config()
    if cfg.vision.provider == llm_providers.PROVIDER_OPENAI:
        return await openai_provider.vision_generate(cfg.vision, images, prompt)
    return await ollama_provider.vision_generate(cfg.vision, images, prompt)


async def agent_chat(
    messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    cfg = llm_providers.get_config()
    if cfg.agent.provider == llm_providers.PROVIDER_OPENAI:
        return await openai_provider.agent_chat(cfg.agent, messages, tools)
    return await ollama_provider.agent_chat(cfg.agent, messages, tools)


async def check_health(scope: str) -> Dict[str, Any]:
    """测试当前配置下指定通道（vision/agent）的连通性。"""
    cfg = llm_providers.get_config()
    ep = cfg.vision if scope == "vision" else cfg.agent
    if ep.provider == llm_providers.PROVIDER_OPENAI:
        return await openai_provider.check_health(ep, scope)
    return await ollama_provider.check_health(ep)


async def check_models() -> Dict[str, bool]:
    """旧接口兼容：探测当前配置下两通道健康度。"""
    out = {}
    for scope in ("vision", "agent"):
        result = await check_health(scope)
        out[scope] = bool(result.get("ok"))
    return out


if __name__ == "__main__":
    print(asyncio.run(check_models()))
