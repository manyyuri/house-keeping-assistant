"""Provider 抽象层单测（无网络依赖，纯函数级）。

运行：.venv/bin/python -m server.test_llm_providers
（兼容 pytest：函数名 test_ 前缀 + 断言）

重点用例（实现提示词 §9.3）：OpenAI 协议下 assistant.tool_calls 生成的
确定性 id 必须与紧随其后的 role:"tool" 消息回填的 tool_call_id 一致，
否则云端 API 直接 400。
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List

from server import llm_providers
from server.openai_provider import normalize_message, to_openai_messages

# ---------- 异常体系 ----------


def test_exception_hierarchy() -> None:
    from server.ollama_provider import OllamaUnavailable

    assert issubclass(llm_providers.RemoteLLMError, llm_providers.LLMUnavailable)
    assert issubclass(OllamaUnavailable, llm_providers.LLMUnavailable)


# ---------- OpenAI 消息转换（§9.3 关键用例）----------


def _assistant_msg(calls: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"role": "assistant", "content": "", "tool_calls": calls}


def test_tool_call_ids_match_tool_messages() -> None:
    """同名多次调用按出现顺序 FIFO 回填，id 必须与生成时一致。"""
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        _assistant_msg([
            {"function": {"name": "save_items", "arguments": {"items": []}}},
            {"function": {"name": "judge_items", "arguments": {"ids": [1]}}},
            {"function": {"name": "save_items", "arguments": {"items": [2]}}},
        ]),
        {"role": "tool", "name": "save_items", "content": "{\"ok\": true}"},
        {"role": "tool", "name": "judge_items", "content": "{\"ok\": true}"},
        {"role": "tool", "name": "save_items", "content": "{\"ok\": true}"},
    ]
    out = to_openai_messages(messages)
    assistant = out[2]
    assert [c["id"] for c in assistant["tool_calls"]] == [
        "call_0_save_items",
        "call_1_judge_items",
        "call_2_save_items",
    ]
    # 同名 save_items 出现两次：第一条 tool 吃第 0 个 id，第二条吃第 2 个（FIFO）
    assert out[3]["tool_call_id"] == "call_0_save_items"
    assert out[4]["tool_call_id"] == "call_1_judge_items"
    assert out[5]["tool_call_id"] == "call_2_save_items"
    assert all(m["role"] == "tool" and m["content"] for m in out[3:6])


def test_multi_round_ids_regenerate_deterministically() -> None:
    """第二轮重新组装全量 messages 时，历史轮次的 id 重生成结果必须稳定。"""
    round1 = [
        _assistant_msg([{"function": {"name": "save_items", "arguments": "{}"}}]),
        {"role": "tool", "name": "save_items", "content": "{}"},
        {"role": "assistant", "content": "done", "tool_calls": []},
    ]
    first = to_openai_messages(round1)
    again = to_openai_messages(round1)
    assert first[0]["tool_calls"][0]["id"] == again[0]["tool_calls"][0]["id"]
    assert first[1]["tool_call_id"] == first[0]["tool_calls"][0]["id"]


def test_arguments_dict_serialized_to_string() -> None:
    """Ollama 风格 dict arguments → OpenAI 要求的 JSON 字符串。"""
    out = to_openai_messages([
        _assistant_msg([{"function": {"name": "t", "arguments": {"a": 1}}}]),
    ])
    call = out[0]["tool_calls"][0]
    assert call["function"]["arguments"] == '{"a": 1}' or call["function"]["arguments"] == '{"a":1}'
    assert json.loads(call["function"]["arguments"]) == {"a": 1}


def test_tool_message_without_matching_call_gets_fallback_id() -> None:
    """防御路径：tool 消息无对应 pending（不应发生）→ 生成兜底 id 而非空串。"""
    out = to_openai_messages([{"role": "tool", "name": "x", "content": "{}"}])
    assert out[0]["tool_call_id"] == "call_0_x"


def test_normalize_message_keeps_arguments_as_string() -> None:
    """OpenAI 响应归一化：arguments 保持字符串（勿提前 loads），None → "{}"。"""
    msg = normalize_message({
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"function": {"name": "save_items", "arguments": "{\"items\": []}"}},
            {"function": {"name": "query_items", "arguments": None}},
        ],
    })
    assert msg["content"] == ""
    assert msg["tool_calls"][0]["function"]["arguments"] == "{\"items\": []}"
    assert msg["tool_calls"][1]["function"]["arguments"] == "{}"


# ---------- 掩码与配置 ----------


def test_mask_key() -> None:
    assert llm_providers.mask_key("") == ""
    assert llm_providers.mask_key("sk-ab12") == "sk-****ab12"
    assert llm_providers.mask_key("sk-abcdefghijklmnop1234") == "sk-****1234"
    assert llm_providers.mask_key("k1") == "k1****k1"


class _ConfigSandbox:
    """临时 DATA_DIR/CONFIG_PATH + 环境变量快照，测完还原。"""

    _ENV_KEYS = [
        "OLLAMA_URL", "VISION_PROVIDER", "VISION_BASE_URL", "VISION_API_KEY",
        "VISION_MODEL", "AGENT_PROVIDER", "AGENT_BASE_URL", "AGENT_API_KEY",
        "AGENT_MODEL", "PI_MODELS_JSON",
    ]

    def __enter__(self) -> "_ConfigSandbox":
        self._saved_env = {k: os.environ.pop(k, None) for k in self._ENV_KEYS}
        self._tmp = tempfile.TemporaryDirectory()
        self._saved_path = llm_providers.CONFIG_PATH
        self._saved_dir = llm_providers.DATA_DIR
        llm_providers.CONFIG_PATH = Path(self._tmp.name) / "config.json"
        llm_providers.DATA_DIR = Path(self._tmp.name)
        # 隔离：默认不读真实 ~/.pi/agent/models.json
        os.environ["PI_MODELS_JSON"] = str(Path(self._tmp.name) / "models.json")
        llm_providers.invalidate_cache()
        return self

    def __exit__(self, *_: Any) -> None:
        llm_providers.CONFIG_PATH = self._saved_path
        llm_providers.DATA_DIR = self._saved_dir
        llm_providers.invalidate_cache()
        for k, v in self._saved_env.items():
            if v is not None:
                os.environ[k] = v
        self._tmp.cleanup()


def test_config_defaults() -> None:
    with _ConfigSandbox():
        cfg = llm_providers.get_config()
        assert cfg.vision.provider == "ollama"
        assert cfg.vision.model == "qwen3-vl:8b"
        assert cfg.agent.model == "qwen3-vl:8b"
        assert cfg.vision.base_url == "http://localhost:11434"
        assert cfg.vision.api_key == ""


def test_pi_models_json_opencode_luna() -> None:
    """models.json 的 opencode-luna 作为云端默认端点（优先级高于 config.json）。"""
    with _ConfigSandbox():
        # 写一个临时 pi 模型注册表
        llm_providers._pi_models_path().parent.mkdir(parents=True, exist_ok=True)
        llm_providers._pi_models_path().write_text(json.dumps({
            "providers": {
                "opencode-luna": {
                    "baseUrl": "https://opencode.ai/zen/go/v1",
                    "apiKey": "sk-pi-secret1234",
                    "models": [
                        {"id": "deepseek-v4-flash", "name": "DeepSeek V4 Flash", "reasoning": True},
                        {"id": "deepseek-v4-flash-vision-exp", "name": "Vision", "vision": True},
                    ],
                }
            }
        }), encoding="utf-8")
        llm_providers.invalidate_cache()
        cfg = llm_providers.get_config()
        assert cfg.vision.provider == "openai"
        assert cfg.vision.model == "deepseek-v4-flash-vision-exp"
        assert cfg.vision.base_url == "https://opencode.ai/zen/go/v1"
        assert cfg.vision.api_key == "sk-pi-secret1234"
        assert cfg.agent.model == "deepseek-v4-flash"
        assert cfg.agent.api_key == "sk-pi-secret1234"

        # 环境变量仍可覆盖 models.json
        os.environ["AGENT_MODEL"] = "env-model"
        llm_providers.invalidate_cache()
        assert llm_providers.get_config().agent.model == "env-model"

        # 掩码视图：明文 key 不出现在响应里
        view = llm_providers.settings_view()
        assert view["config_source"] == "models.json"
        assert "sk-pi-secret1234" not in json.dumps(view)
        assert view["agent"]["api_key_masked"] == "sk-****1234"


def test_config_file_and_env_precedence() -> None:
    with _ConfigSandbox():
        llm_providers.CONFIG_PATH.write_text(
            json.dumps({
                "vision": {"provider": "openai", "base_url": "https://a.example/v1",
                           "api_key": "sk-file1234", "model": "m1"},
                "agent": {"provider": "openai", "base_url": "https://b.example/v1",
                          "api_key": "sk-file5678", "model": "m2"},
            }),
            encoding="utf-8",
        )
        llm_providers.invalidate_cache()
        cfg = llm_providers.get_config()
        assert cfg.vision.model == "m1"
        assert cfg.vision.api_key == "sk-file1234"

        os.environ["AGENT_MODEL"] = "env-model"
        os.environ["AGENT_API_KEY"] = "sk-env9999"
        llm_providers.invalidate_cache()
        cfg = llm_providers.get_config()  # env > file
        assert cfg.agent.model == "env-model"
        assert cfg.agent.api_key == "sk-env9999"
        assert cfg.vision.model == "m1"


def test_save_config_semantics() -> None:
    with _ConfigSandbox():
        llm_providers.save_config({
            "vision": {"provider": "ollama", "model": "qwen3-vl:8b"},
            "agent": {
                "provider": "openai",
                "base_url": "https://api.deepseek.com/v1",
                "api_key": "sk-secret9999",
                "model": "deepseek-chat",
            },
        })
        cfg = llm_providers.get_config()
        assert cfg.agent.provider == "openai"
        assert cfg.agent.api_key == "sk-secret9999"

        # api_key 为空串 = 保持已存值
        llm_providers.save_config({"agent": {"provider": "openai", "model": "deepseek-reasoner"}})
        cfg = llm_providers.get_config()
        assert cfg.agent.api_key == "sk-secret9999"
        assert cfg.agent.model == "deepseek-reasoner"

        # 切回 ollama：清空 key/base_url
        llm_providers.save_config({"agent": {"provider": "ollama", "model": "needle"}})
        cfg = llm_providers.get_config()
        assert cfg.agent.provider == "ollama"
        assert cfg.agent.api_key == ""
        assert cfg.agent.base_url == "http://localhost:11434"

        # chmod 600
        mode = llm_providers.CONFIG_PATH.stat().st_mode & 0o777
        assert mode == 0o600


def test_save_config_validation_422() -> None:
    with _ConfigSandbox():
        for bad in (
            {"provider": "openai", "base_url": "ftp://x", "api_key": "sk-x", "model": "m"},
            {"provider": "openai", "base_url": "https://x/v1", "api_key": "", "model": "m"},
            {"provider": "openai", "base_url": "https://x/v1", "api_key": "sk-x", "model": ""},
        ):
            try:
                llm_providers.save_config({"agent": bad})
            except ValueError as e:
                assert str(e)
            else:
                raise AssertionError(f"应校验失败：{bad}")
        assert not llm_providers.CONFIG_PATH.exists()  # 校验失败不落盘


def test_settings_view_masks_key() -> None:
    with _ConfigSandbox():
        llm_providers.save_config({
            "agent": {"provider": "openai", "base_url": "https://x/v1",
                      "api_key": "sk-topsecret1234", "model": "m"},
        })
        view = llm_providers.settings_view()
        raw = json.dumps(view)
        assert "sk-topsecret1234" not in raw          # 明文永不出现
        assert view["agent"]["api_key"] == ""          # 恒为空串
        assert view["agent"]["api_key_masked"] == "sk-****1234"
        assert view["readonly"] == {f"{s}.{f}": False for s in ("vision", "agent")
                                    for f in ("provider", "base_url", "api_key", "model")}
        assert view["provider_options"]


def test_env_locked_fields_and_notices() -> None:
    with _ConfigSandbox():
        os.environ["AGENT_API_KEY"] = "sk-envlocked1234"
        os.environ["AGENT_MODEL"] = "env-model"
        llm_providers.invalidate_cache()
        locked = llm_providers.env_locked_fields()
        assert locked["agent.api_key"] is True
        assert locked["agent.model"] is True
        assert locked["vision.model"] is False

        notices = llm_providers.locked_notices({
            "agent": {"provider": "openai", "model": "ui-model", "api_key": "sk-ui"},
            "vision": {"provider": "ollama", "model": "ui-v"},
        })
        assert any("AGENT_API_KEY" in n for n in notices)
        assert any("AGENT_MODEL" in n for n in notices)
        assert all("VISION_" not in n for n in notices)


# ---------- 入口 ----------

if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failures += 1
                print(f"FAIL {name}: {e}")
    raise SystemExit(1 if failures else 0)
