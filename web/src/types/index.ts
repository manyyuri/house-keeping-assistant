/** 与后端 server/models.py 对齐的 TS 类型。 */

export interface Attachment {
  photoId: number;
  path: string;
}

export interface Message {
  id: number;
  conversation_id: number;
  role: 'user' | 'assistant' | 'tool';
  content: string;
  attachments: Attachment[];
  created_at?: string;
}

export interface Conversation {
  id: number;
  title: string;
  room?: string | null;
  created_at?: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}

export interface PhotoUploadResult {
  photoId: number;
  path: string;
  url: string;
}

export type KeepStatus = 'keep' | 'donate' | 'discard' | 'hesitate' | 'unjudged';
export type TaskType = 'clean' | 'organize' | 'store' | 'discard';
export type TaskStatus = 'todo' | 'doing' | 'done' | 'skipped';

export interface Item {
  id: number;
  photo_id?: number | null;
  name: string;
  category?: string | null;
  quantity: number;
  keep_status: KeepStatus;
  reason?: string | null;
  last_used?: string | null;
  quarantine_until?: string | null;
  created_at?: string;
}

export interface Task {
  id: number;
  plan_id: number;
  type: TaskType | string;
  title: string;
  steps: string[];
  est_minutes?: number | null;
  due_date?: string | null;
  status: TaskStatus | string;
  plan_room?: string | null;
  created_at?: string;
}

export interface Plan {
  id: number;
  conversation_id?: number | null;
  room: string;
  summary?: string | null;
  danshari_score?: number | null;
  discard_count: number;
  donate_count: number;
  keep_count: number;
  status: string;
  created_at?: string;
  tasks?: Task[];
}

export interface Stats {
  discard_count: number;
  donate_count: number;
  keep_count: number;
  hesitate_count: number;
  done_tasks: number;
  avg_danshari_score: number | null;
  active_hesitate: Item[];
  expired_quarantine: Item[];
}

// ---------- LLM 模型设置 ----------

export interface LLMEndpointView {
  provider: string; // 'ollama' | 'openai'
  base_url: string;
  model: string;
  /** 恒为空串（后端永不回显明文） */
  api_key: string;
  api_key_masked: string;
}

export interface LLMProviderPreset {
  label: string;
  base_url: string;
  vision_model: string;
  agent_model: string;
}

export interface LLMSettingsView {
  vision: LLMEndpointView;
  agent: LLMEndpointView;
  /** 环境变量锁定的字段路径（"vision.model" 等），UI 对应输入 disabled */
  readonly: Record<string, boolean>;
  provider_options: LLMProviderPreset[];
  /** 保存时：被环境变量覆盖而未生效的字段提示 */
  notices?: string[];
}

export interface LLMEndpointPayload {
  provider: string;
  base_url?: string;
  api_key?: string;
  model?: string;
}

export interface LLMTestResult {
  ok: boolean;
  message: string;
  latency_ms?: number;
}

// ---------- SSE 事件负载 ----------

export interface VisionDonePayload {
  photoId: number;
  room: string;
  messiness: 'low' | 'medium' | 'high';
  items: { name: string; category: string; quantity: number }[];
  degraded: boolean;
}

export interface PlanCreatedPayload {
  planId: number;
  danshariScore: number;
  taskCount: number;
}

export type ChatSSEEvent =
  | { event: 'vision_start'; data: { photoIds: number[] } }
  | { event: 'vision_done'; data: VisionDonePayload }
  | { event: 'thought'; data: { node: string; status?: string } }
  | { event: 'tool_call'; data: { name: string; args: Record<string, unknown> } }
  | { event: 'tool_result'; data: { name: string; ok: boolean; summary: string } }
  | { event: 'message_delta'; data: { delta: string } }
  | { event: 'plan_created'; data: PlanCreatedPayload }
  | { event: 'done'; data: { messageId: number | null } }
  | { event: 'error'; data: { message: string; stage: string } };

// ---------- 对话页内部状态 ----------

export interface ThoughtNode {
  key: string;
  title: string;
  status: 'loading' | 'success' | 'error';
  description?: string;
}

export interface ChatMessage {
  id: string | number;
  role: 'user' | 'assistant';
  content: string;
  /** 用户消息：已上传照片 */
  photos?: { photoId: number; url: string }[];
  /** 助手消息：识别结果摘要 */
  vision?: VisionDonePayload[];
  /** 助手消息：计划卡片 */
  plan?: PlanCreatedPayload;
  thoughts: ThoughtNode[];
  status: 'loading' | 'streaming' | 'done' | 'error' | 'stopped';
  error?: string;
}
