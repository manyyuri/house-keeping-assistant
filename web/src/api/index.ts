/** fetch 封装 + SSE 解析（@ant-design/x v2 已移除 XStream，降级手写解析）。 */

import type {
  ChatSSEEvent,
  Conversation,
  ConversationDetail,
  DayMeals,
  EnergyLevel,
  GrocerySummary,
  HomePayload,
  Item,
  KeepStatus,
  LLMEndpointPayload,
  LLMSettingsView,
  LLMTestResult,
  MealPlan,
  MealStatus,
  MealType,
  Plan,
  PhotoUploadResult,
  Stats,
  Task,
  TaskType,
  TimelinePayload,
  WeekDay,
} from '../types';

const BASE = '/api';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...init,
  });
  if (!resp.ok) {
    let detail = `${resp.status}`;
    try {
      const body = await resp.json();
      detail = body.detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(String(detail));
  }
  return resp.json();
}

// ---------- conversations ----------

export const listConversations = () => request<Conversation[]>('/conversations');

export const createConversation = (title?: string, room?: string) =>
  request<Conversation>('/conversations', {
    method: 'POST',
    body: JSON.stringify({ title, room }),
  });

export const getConversation = (id: number) =>
  request<ConversationDetail>(`/conversations/${id}`);

export const deleteConversation = (id: number) =>
  request<{ ok: boolean }>(`/conversations/${id}`, { method: 'DELETE' });

// ---------- upload ----------

export async function uploadPhotos(files: File[], room?: string): Promise<PhotoUploadResult[]> {
  const form = new FormData();
  files.forEach((f) => form.append('files', f));
  if (room) form.append('room', room);
  const resp = await fetch(`${BASE}/upload`, { method: 'POST', body: form });
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(body.detail ?? `上传失败（${resp.status}）`);
  }
  return resp.json();
}

export async function fetchQrcode(): Promise<string> {
  const resp = await fetch(`${BASE}/qrcode`, { method: 'POST' });
  if (!resp.ok) throw new Error('二维码生成失败');
  return URL.createObjectURL(await resp.blob());
}

// ---------- plans / tasks / items / stats ----------

export const listPlans = (status?: string) =>
  request<Plan[]>(`/plans${status ? `?status=${status}` : ''}`);

export const createPlan = (body: { room: string; summary?: string }) =>
  request<Plan>('/plans', { method: 'POST', body: JSON.stringify(body) });

export const getPlan = (id: number) => request<Plan>(`/plans/${id}`);

export const patchPlan = (id: number, status: string) =>
  request<Plan>(`/plans/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) });

export const attachPlanPhotos = (id: number, photoIds: number[]) =>
  request<{ ok: boolean; added: number; plan: Plan }>(`/plans/${id}/photos`, {
    method: 'POST',
    body: JSON.stringify({ photo_ids: photoIds }),
  });

export const listTasks = (params: { status?: string; type?: TaskType | string; plan_id?: number } = {}) => {
  const qs = new URLSearchParams();
  if (params.status) qs.set('status', params.status);
  if (params.type) qs.set('type', params.type);
  if (params.plan_id != null) qs.set('plan_id', String(params.plan_id));
  const q = qs.toString();
  return request<Task[]>(`/tasks${q ? `?${q}` : ''}`);
};

export const patchTask = (id: number, status: string) =>
  request<Task>(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) });

export const listItems = (params: { keep_status?: KeepStatus | string; category?: string; keyword?: string } = {}) => {
  const qs = new URLSearchParams();
  if (params.keep_status) qs.set('keep_status', params.keep_status);
  if (params.category) qs.set('category', params.category);
  if (params.keyword) qs.set('keyword', params.keyword);
  const q = qs.toString();
  return request<Item[]>(`/items${q ? `?${q}` : ''}`);
};

export const patchItem = (id: number, body: { keep_status?: KeepStatus; last_used?: string; reason?: string }) =>
  request<Item>(`/items/${id}`, { method: 'PATCH', body: JSON.stringify(body) });

export const getStats = () => request<Stats>('/stats');

// ---------- 三格电首页 / 时间轴账本（省力）----------

export const getHome = (energy: EnergyLevel) => request<HomePayload>(`/home?energy=${energy}`);

export const getTimeline = () => request<TimelinePayload>('/timeline');

// ---------- LLM 模型设置 ----------

export const getLLMSettings = () => request<LLMSettingsView>('/settings/llm');

export const saveLLMSettings = (body: { vision?: LLMEndpointPayload; agent?: LLMEndpointPayload }) =>
  request<LLMSettingsView>('/settings/llm', {
    method: 'PUT',
    body: JSON.stringify(body),
  });

export const testLLMConnection = (scope: 'vision' | 'agent', endpoint?: LLMEndpointPayload) =>
  request<LLMTestResult>('/settings/llm/test', {
    method: 'POST',
    body: JSON.stringify({ scope, endpoint }),
  });

// ---------- meals（三餐）----------

export const getMeals = (date?: string) =>
  request<DayMeals>(`/meals${date ? `?date=${date}` : ''}`);

export const getWeekMeals = () => request<WeekDay[]>('/meals/week');

export const rerollMeal = (date: string, meal_type: MealType) =>
  request<MealPlan>('/meals/reroll', {
    method: 'POST',
    body: JSON.stringify({ date, meal_type }),
  });

export const patchMealStatus = (id: number, status: MealStatus) =>
  request<MealPlan>(`/meals/${id}`, { method: 'PATCH', body: JSON.stringify({ status }) });

// ---------- grocery（盒马买菜清单）----------

export const getGrocery = (days = 3) => request<GrocerySummary>(`/grocery?days=${days}`);

export const patchGrocery = (id: number, checked: boolean) =>
  request<{ ok: boolean }>(`/grocery/${id}`, { method: 'PATCH', body: JSON.stringify({ checked }) });

export const clearBoughtGrocery = () =>
  request<{ ok: boolean; deleted: number }>('/grocery?bought=true', { method: 'DELETE' });

// ---------- SSE /api/chat ----------

export interface StreamChatOptions {
  conversationId: number;
  message: string;
  photoIds?: number[];
  signal?: AbortSignal;
  onEvent: (ev: ChatSSEEvent) => void;
}

/** GET /api/chat SSE 流解析：按空行分块，提取 event:/data: 行。 */
export async function streamChat(opts: StreamChatOptions): Promise<void> {
  const qs = new URLSearchParams({
    conversation_id: String(opts.conversationId),
    message: opts.message,
  });
  if (opts.photoIds?.length) qs.set('photo_ids', opts.photoIds.join(','));

  const resp = await fetch(`${BASE}/chat?${qs.toString()}`, { signal: opts.signal });
  await consumeSSE(resp, opts.onEvent);
}

/** POST /api/plans/{id}/generate SSE：手动触发生成/重新生成计划。 */
export interface StreamPlanGenerateOptions {
  planId: number;
  signal?: AbortSignal;
  onEvent: (ev: ChatSSEEvent) => void;
}

export async function streamPlanGenerate(opts: StreamPlanGenerateOptions): Promise<void> {
  const resp = await fetch(`${BASE}/plans/${opts.planId}/generate`, {
    method: 'POST',
    signal: opts.signal,
  });
  await consumeSSE(resp, opts.onEvent);
}

/** 共用 SSE 消费：校验响应 + 按空行分块解析 event:/data: 行。 */
async function consumeSSE(resp: Response, onEvent: (ev: ChatSSEEvent) => void): Promise<void> {
  if (!resp.ok || !resp.body) {
    let detail = `${resp.status}`;
    try {
      detail = (await resp.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(String(detail));
  }

  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const handleBlock = (block: string) => {
    let event = 'message';
    const dataLines: string[] = [];
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
    }
    if (!dataLines.length) return;
    try {
      onEvent({ event, data: JSON.parse(dataLines.join('\n')) } as ChatSSEEvent);
    } catch {
      /* 非 JSON data 忽略 */
    }
  };

  // eslint-disable-next-line no-constant-condition
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx: number;
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const block = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 2);
      if (block) handleBlock(block);
    }
  }
  const rest = buffer.trim();
  if (rest) handleBlock(rest);
}

// ---------- 图片压缩（上传前，最长边 1280 JPEG）----------

export function compressImage(file: File, maxSide = 1280, quality = 0.85): Promise<File> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      URL.revokeObjectURL(url);
      const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
      const canvas = document.createElement('canvas');
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        resolve(file);
        return;
      }
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            resolve(file);
            return;
          }
          const name = file.name.replace(/\.[^.]+$/, '') || 'photo';
          resolve(new File([blob], `${name}.jpg`, { type: 'image/jpeg' }));
        },
        'image/jpeg',
        quality,
      );
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('图片解码失败（可能为不支持的格式）'));
    };
    img.src = url;
  });
}
