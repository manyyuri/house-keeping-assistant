"""Pydantic 请求/响应模型（与前端 web/src/types 对齐）。"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------- conversations ----------

class ConversationCreate(BaseModel):
    title: str = "新整理对话"
    room: Optional[str] = None


class Attachment(BaseModel):
    photoId: int
    path: str


class Message(BaseModel):
    id: int
    conversation_id: int
    role: str
    content: str
    attachments: List[Attachment] = []


class Conversation(BaseModel):
    id: int
    title: str
    room: Optional[str] = None
    created_at: Optional[str] = None


class ConversationDetail(Conversation):
    messages: List[Message] = []


# ---------- photos ----------

class PhotoOut(BaseModel):
    photoId: int
    path: str
    url: str


# ---------- items ----------

class ItemPatch(BaseModel):
    keep_status: Optional[str] = None
    last_used: Optional[str] = None
    reason: Optional[str] = None


class Item(BaseModel):
    id: int
    photo_id: Optional[int] = None
    name: str
    category: Optional[str] = None
    quantity: int = 1
    keep_status: str = "unjudged"
    reason: Optional[str] = None
    last_used: Optional[str] = None
    quarantine_until: Optional[str] = None
    created_at: Optional[str] = None


# ---------- plans / tasks ----------

class PlanPatch(BaseModel):
    status: str = Field(pattern="^(active|completed|archived)$")


class TaskPatch(BaseModel):
    status: str = Field(pattern="^(todo|doing|done|skipped)$")


class TaskOut(BaseModel):
    id: int
    plan_id: int
    type: str
    title: str
    steps: List[str] = []
    est_minutes: Optional[int] = None
    due_date: Optional[str] = None
    status: str = "todo"
    plan_room: Optional[str] = None
    created_at: Optional[str] = None


class PlanOut(BaseModel):
    id: int
    conversation_id: Optional[int] = None
    room: str
    summary: Optional[str] = None
    danshari_score: Optional[int] = None
    discard_count: int = 0
    donate_count: int = 0
    keep_count: int = 0
    status: str = "active"
    created_at: Optional[str] = None
    tasks: List[Dict[str, Any]] = []


# ---------- LLM 模型设置 ----------

class LLMEndpointIn(BaseModel):
    """api_key 为空串 = 保持已存值。"""

    provider: str = "ollama"
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class LLMSettingsIn(BaseModel):
    vision: Optional[LLMEndpointIn] = None
    agent: Optional[LLMEndpointIn] = None


class LLMTestIn(BaseModel):
    scope: str  # vision | agent
    endpoint: Optional[LLMEndpointIn] = None
