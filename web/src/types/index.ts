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

export interface PlanPhoto {
  id: number;
  path: string;
  room?: string | null;
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
  photos?: PlanPhoto[];
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

// ---------- 三格电首页（省力概念核心）----------

export type EnergyLevel = 'full' | 'half' | 'empty';

export interface HomeTask {
  source: 'task' | 'suggestion';
  id?: number | null;
  plan_id?: number | null;
  room?: string | null;
  type: string;
  title: string;
  est_minutes: number;
  steps: string[];
}

export interface HomeMealItem {
  type: MealType;
  name: string;
  cook_minutes: number | null;
}

export interface HomeMeal {
  give: boolean;
  meal?: HomeMealItem | null;
  meals: HomeMealItem[];
  text: string;
}

export interface HomeTrajectory {
  this_week: number;
  last_week: number;
  delta: number;
  line: string;
}

export interface HomePayload {
  energy: EnergyLevel;
  level: { key: EnergyLevel; max_min: number; label: string; title: string };
  task: HomeTask;
  rest_allowed: boolean;
  meal: HomeMeal;
  encouragement: string;
  trajectory: HomeTrajectory;
}

// ---------- 时间轴账本（家的账 + 身体的账）----------

export type TimelineKind = 'home' | 'body';
export type TimelineIcon = 'task' | 'meal' | 'plan';

export interface TimelineEvent {
  ts: string;
  kind: TimelineKind;
  icon: TimelineIcon;
  text: string;
}

export interface TimelinePayload {
  trajectory: HomeTrajectory;
  events: TimelineEvent[];
}

// ---------- 三餐 ----------

export type MealType = 'breakfast' | 'lunch' | 'dinner';
export type MealMode = 'cook' | 'bento';
export type MealStatus = 'planned' | 'eaten' | 'skipped';
export type FoodKind = 'staple' | 'protein' | 'veg' | 'seafood';

export interface RecipeSlot {
  slot: string;
  kind: FoodKind;
  fists: number;
  food: string;
}

export interface RecipeIngredient {
  name: string;
  amount: string;
  hima: string;
}

export interface Recipe {
  id: number;
  name: string;
  meal_type: MealType;
  slots: RecipeSlot[];
  ingredients: RecipeIngredient[];
  steps: string[];
  cook_tool: string;
  cook_minutes: number | null;
  tags: string[];
  satiety_hint: string | null;
}

export interface BentoPreview {
  name: string;
  cook_minutes: number;
}

export interface MealPlan {
  id: number;
  plan_date: string;
  meal_type: MealType;
  recipe_id: number | null;
  mode: MealMode;
  status: MealStatus;
  note: string | null;
  recipe: Recipe | null;
  /** 仅晚餐：明日便当摘要（顺手做区块） */
  bento_preview?: BentoPreview | null;
}

export interface TomorrowPreview {
  date: string;
  breakfast: string | null;
  lunch: string | null;
  dinner: string | null;
}

export interface DayMeals {
  date: string;
  weekday: string;
  meals: Record<MealType, MealPlan | null>;
  tomorrow_preview: TomorrowPreview | null;
}

export interface WeekMealLite {
  name: string;
  mode: MealMode;
  status: MealStatus;
}

export interface WeekDay {
  date: string;
  weekday: string;
  is_today: boolean;
  meals: Record<MealType, WeekMealLite | null>;
}

export interface GroceryItem {
  name: string;
  amounts: string[];
  meals: string[];
  ids: number[];
  checked: boolean;
}

export interface GroceryGroup {
  category: string;
  items: GroceryItem[];
}

export interface GrocerySummary {
  days: number;
  through_date: string;
  groups: GroceryGroup[];
  total: number;
  pending: number;
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
  /** 当前端点来源：models.json（opencode-luna）或 config（本地保存） */
  config_source?: string;
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
  suspected?: { name: string; category: string; quantity: number }[];
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
