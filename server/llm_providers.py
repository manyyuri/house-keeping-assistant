"""LLM 运行时配置与 Provider 抽象层。

双通道并存：本地 Ollama 与远程 OpenAI 兼容 API（DashScope/DeepSeek/SiliconFlow…），
视觉与 Agent 端点独立选路（允许混合部署，如"照片不出内网 + 云端 Agent"）。

配置优先级：环境变量 > server/data/config.json（UI 保存）> 代码默认值。
api_key 只落本机文件（server/data 已 gitignore），对外接口只回掩码。
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

DATA_DIR = Path(__file__).resolve().parent / "data"
CONFIG_PATH = DATA_DIR / "config.json"

PROVIDER_OLLAMA = "ollama"
PROVIDER_OPENAI = "openai"

OLLAMA_DEFAULT_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_VISION_MODEL = "qwen3-vl:8b"
DEFAULT_AGENT_MODEL = "qwen3-vl:8b"

# pi 的模型注册表（~/.pi/agent/models.json）：open code 外部 provider 密钥单点。
# 项目读取其中 opencode-luna 提供方的 baseUrl/apiKey/模型，作为云端默认端点
# （优先级：环境变量 > models.json > config.json > 代码默认值）。
# 路径可用 PI_MODELS_JSON 覆盖（测试用）。
PI_MODELS_DEFAULT = Path.home() / ".pi" / "agent" / "models.json"
PI_OPCODE_LUNA_PROVIDER = "opencode-luna"
PI_VISION_MODEL = "deepseek-v4-flash-vision-exp"
PI_AGENT_MODEL = "deepseek-v4-flash"

# 常用 OpenAI 兼容服务商预设（UI 下拉用；模型名仅占位建议，以各家文档为准）
PROVIDER_PRESETS = [
    {
        "label": "OpenCode Luna（opencode-luna）",
        "base_url": "https://opencode.ai/zen/go/v1",
        "vision_model": PI_VISION_MODEL,
        "agent_model": PI_AGENT_MODEL,
    },
    {
        "label": "阿里云百炼 DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "vision_model": "qwen-vl-plus",
        "agent_model": "qwen3-max",
    },
    {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "vision_model": "",
        "agent_model": "deepseek-chat",
    },
    {
        "label": "SiliconFlow 硅基流动",
        "base_url": "https://api.siliconflow.cn/v1",
        "vision_model": "Qwen/Qwen2.5-VL-32B-Instruct",
        "agent_model": "Qwen/Qwen3-32B",
    },
    {
        "label": "月之暗面 Moonshot",
        "base_url": "https://api.moonshot.cn/v1",
        "vision_model": "moonshot-v1-8k-vision-preview",
        "agent_model": "kimi-k2-0905-preview",
    },
    {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "vision_model": "gpt-4o-mini",
        "agent_model": "gpt-4o-mini",
    },
]


class LLMUnavailable(RuntimeError):
    """模型服务不可达/不可用——上层（SSE）统一捕获并降级提示。"""


class RemoteLLMError(LLMUnavailable):
    """远程 OpenAI 兼容 API 调用失败。"""


@dataclass
class Endpoint:
    provider: str = PROVIDER_OLLAMA
    base_url: str = ""
    api_key: str = ""
    model: str = ""


@dataclass
class LLMConfig:
    vision: Endpoint = field(default_factory=Endpoint)
    agent: Endpoint = field(default_factory=Endpoint)


_SCOPE_ENV = {"vision": "VISION", "agent": "AGENT"}


# ---------- 配置读写（ENV > config.json > 默认值）----------

def _read_json() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def _pi_models_path() -> Path:
    """pi 模型注册表路径：环境变量 PI_MODELS_JSON 可覆盖（测试/换机用）。"""
    return Path(os.environ.get("PI_MODELS_JSON") or PI_MODELS_DEFAULT)


def _opencode_luna() -> Optional[Dict[str, Any]]:
    """从 pi 模型注册表读取 opencode-luna 提供方（baseUrl/apiKey/模型）。

    文件缺失/损坏/无该提供方 → None（回退 config.json 与默认值）。
    返回：{"provider", "base_url", "api_key", "vision_model", "agent_model"}。
    """
    path = _pi_models_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    prov = (data.get("providers") or {}).get(PI_OPCODE_LUNA_PROVIDER)
    if not isinstance(prov, dict):
        return None
    base_url = str(prov.get("baseUrl") or "").strip()
    api_key = str(prov.get("apiKey") or "").strip()
    if not base_url or not api_key:
        return None
    models = prov.get("models") or []

    def _pick(preferred: str, want_vision: bool) -> str:
        for m in models:
            if isinstance(m, dict) and m.get("id") == preferred and bool(m.get("vision")) == want_vision:
                return str(m["id"])
        for m in models:
            if isinstance(m, dict) and bool(m.get("vision")) == want_vision:
                return str(m["id"])
        for m in models:
            if isinstance(m, dict) and not bool(m.get("vision")):
                return str(m["id"])
        return ""

    return {
        "provider": PROVIDER_OPENAI,
        "base_url": base_url,
        "api_key": api_key,
        "vision_model": _pick(PI_VISION_MODEL, True),
        "agent_model": _pick(PI_AGENT_MODEL, False),
    }


def _load_endpoint(scope: str, default_model: str) -> Endpoint:
    raw = _read_json().get(scope)
    raw = raw if isinstance(raw, dict) else {}
    p = _SCOPE_ENV[scope]
    env = os.environ
    pi = _opencode_luna() or {}
    pi_model_key = "vision_model" if scope == "vision" else "agent_model"
    provider = (env.get(f"{p}_PROVIDER") or pi.get("provider")
                or raw.get("provider") or PROVIDER_OLLAMA).strip()
    base_url = (env.get(f"{p}_BASE_URL") or pi.get("base_url")
                or raw.get("base_url") or "").strip()
    api_key = (env.get(f"{p}_API_KEY") or pi.get("api_key")
               or raw.get("api_key") or "").strip()
    model = (env.get(f"{p}_MODEL") or pi.get(pi_model_key)
             or raw.get("model") or default_model).strip()
    if provider == PROVIDER_OLLAMA and not base_url:
        base_url = OLLAMA_DEFAULT_URL
    return Endpoint(provider=provider, base_url=base_url, api_key=api_key, model=model)


_cache: Optional[LLMConfig] = None


def get_config() -> LLMConfig:
    """进程内缓存读取；save_config 后失效（写时失效，读多写少）。"""
    global _cache
    if _cache is None:
        _cache = LLMConfig(
            vision=_load_endpoint("vision", DEFAULT_VISION_MODEL),
            agent=_load_endpoint("agent", DEFAULT_AGENT_MODEL),
        )
    return _cache


def invalidate_cache() -> None:
    global _cache
    _cache = None


def save_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    """保存 UI 提交的配置到 config.json（chmod 600），返回落盘后的原始 dict。

    语义：api_key 为空串 = 保持已存值；provider 切回 ollama 时清空 key/base_url。
    """
    raw = _read_json()
    for scope in ("vision", "agent"):
        incoming = payload.get(scope)
        if not isinstance(incoming, dict):
            continue
        merged = dict(raw.get(scope) or {})
        provider = (incoming.get("provider") or PROVIDER_OLLAMA).strip()
        merged["provider"] = provider
        if incoming.get("model"):
            merged["model"] = str(incoming["model"]).strip()

        if provider == PROVIDER_OPENAI:
            if incoming.get("base_url"):
                merged["base_url"] = str(incoming["base_url"]).strip()
            if incoming.get("api_key"):
                merged["api_key"] = str(incoming["api_key"]).strip()
            if not (merged.get("base_url") or "").startswith(("http://", "https://")):
                raise ValueError(f"{scope} 端点 base_url 需以 http(s):// 开头")
            if not merged.get("api_key"):
                raise ValueError(f"{scope} 端点使用云端 API 需填写 api_key")
            if not merged.get("model"):
                raise ValueError(f"{scope} 端点缺少模型名")
        else:
            merged["base_url"] = ""
            merged["api_key"] = ""
        raw[scope] = merged

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        CONFIG_PATH.chmod(0o600)  # 密钥文件仅本机可读
    except OSError:
        pass
    invalidate_cache()
    return raw


# ---------- 视图与掩码 ----------

def mask_key(key: str) -> str:
    """sk-xxxx…xxxx1234 → sk-****1234（只留末 4 位）。"""
    if not key:
        return ""
    tail = key[-4:] if len(key) >= 4 else key
    return f"{key[:3]}****{tail}"


def env_locked_fields() -> Dict[str, bool]:
    """全部字段路径是否被环境变量锁定（UI 中 disabled，保存不会生效于运行时）。"""
    env = os.environ
    out: Dict[str, bool] = {}
    for scope, p in _SCOPE_ENV.items():
        for f in ("provider", "base_url", "api_key", "model"):
            out[f"{scope}.{f}"] = bool(env.get(f"{p}_{f.upper()}"))
    return out


def locked_notices(payload: Dict[str, Any]) -> List[str]:
    """UI 保存被环境变量覆盖的字段时的提示文案（§2.2）。"""
    env = os.environ
    notices: List[str] = []
    for scope, p in _SCOPE_ENV.items():
        incoming = payload.get(scope)
        if not isinstance(incoming, dict):
            continue
        for f, label in (
            ("provider", "服务商"),
            ("base_url", "接口地址"),
            ("api_key", "密钥"),
            ("model", "模型名"),
        ):
            var = f"{p}_{f.upper()}"
            if env.get(var) and incoming.get(f):
                notices.append(
                    f"{scope}.{f}（{label}）已由环境变量 {var} 锁定，本次保存的值不会生效"
                )
    return notices


def settings_view() -> Dict[str, Any]:
    """GET /api/settings/llm 响应体：掩码视图 + 只读标注 + 服务商预设。"""
    cfg = get_config()

    def scope_view(ep: Endpoint) -> Dict[str, Any]:
        return {
            "provider": ep.provider,
            "base_url": ep.base_url,
            "model": ep.model,
            "api_key": "",  # 恒不回显明文
            "api_key_masked": mask_key(ep.api_key),
        }

    return {
        "vision": scope_view(cfg.vision),
        "agent": scope_view(cfg.agent),
        "readonly": env_locked_fields(),
        "provider_options": PROVIDER_PRESETS,
        # 当前端点来源：models.json（opencode-luna）或 config（本地保存）
        "config_source": "models.json" if _opencode_luna() else "config",
    }
