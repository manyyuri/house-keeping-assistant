/** zustand stores：会话 / 业务数据（计划·任务·物品·统计）/ 三餐。 */

import { create } from 'zustand';
import * as api from '../api';
import { addDays, localISO } from '../utils/date';
import type {
  Conversation,
  DayMeals,
  GrocerySummary,
  Item,
  KeepStatus,
  MealPlan,
  MealStatus,
  MealType,
  Plan,
  Stats,
  Task,
  TaskType,
  WeekDay,
} from '../types';

// ---------- 会话 ----------

interface ConversationState {
  list: Conversation[];
  activeId: number | null;
  loading: boolean;
  fetchList: () => Promise<void>;
  create: (title?: string, room?: string) => Promise<Conversation>;
  remove: (id: number) => Promise<void>;
  setActive: (id: number | null) => void;
}

export const useConversationStore = create<ConversationState>((set, get) => ({
  list: [],
  activeId: null,
  loading: false,
  fetchList: async () => {
    set({ loading: true });
    try {
      set({ list: await api.listConversations() });
    } finally {
      set({ loading: false });
    }
  },
  create: async (title, room) => {
    const conv = await api.createConversation(title, room);
    set({ list: [conv, ...get().list], activeId: conv.id });
    return conv;
  },
  remove: async (id) => {
    await api.deleteConversation(id);
    const list = get().list.filter((c) => c.id !== id);
    set({ list, activeId: get().activeId === id ? (list[0]?.id ?? null) : get().activeId });
  },
  setActive: (id) => set({ activeId: id }),
}));

// ---------- 业务数据（计划/任务/物品/统计）----------

interface BusinessState {
  plans: Plan[];
  tasks: Task[];
  items: Item[];
  stats: Stats | null;
  /** 对话产生新计划/任务后自增，供各页监听刷新 */
  version: number;
  tasksFilter: { status?: string; type?: TaskType | string };
  itemsFilter: { keep_status?: KeepStatus | string; keyword?: string };
  bumpVersion: () => void;
  fetchPlans: () => Promise<void>;
  fetchTasks: () => Promise<void>;
  fetchItems: () => Promise<void>;
  fetchStats: () => Promise<void>;
  fetchAll: () => Promise<void>;
  setTasksFilter: (f: { status?: string; type?: TaskType | string }) => void;
  setItemsFilter: (f: { keep_status?: KeepStatus | string; keyword?: string }) => void;
}

export const useBusinessStore = create<BusinessState>((set, get) => ({
  plans: [],
  tasks: [],
  items: [],
  stats: null,
  version: 0,
  tasksFilter: {},
  itemsFilter: {},
  bumpVersion: () => {
    set({ version: get().version + 1 });
    void get().fetchAll();
  },
  fetchPlans: async () => set({ plans: await api.listPlans() }),
  fetchTasks: async () => set({ tasks: await api.listTasks(get().tasksFilter) }),
  fetchItems: async () => set({ items: await api.listItems(get().itemsFilter) }),
  fetchStats: async () => set({ stats: await api.getStats() }),
  fetchAll: async () => {
    await Promise.allSettled([
      get().fetchPlans(),
      get().fetchTasks(),
      get().fetchItems(),
      get().fetchStats(),
    ]);
  },
  setTasksFilter: (f) => {
    set({ tasksFilter: f });
    void get().fetchTasks();
  },
  setItemsFilter: (f) => {
    set({ itemsFilter: f });
    void get().fetchItems();
  },
}));

// ---------- 三餐 ----------

export type MealView = 'today' | 'tomorrow' | 'week';

interface MealState {
  view: MealView;
  day: DayMeals | null;
  week: WeekDay[];
  grocery: GrocerySummary | null;
  loading: boolean;
  rerolling: MealType | null;
  setView: (v: MealView) => Promise<void>;
  fetchDay: (date?: string) => Promise<void>;
  fetchWeek: () => Promise<void>;
  fetchGrocery: () => Promise<void>;
  reroll: (mealType: MealType) => Promise<void>;
  setStatus: (plan: MealPlan, status: MealStatus) => Promise<void>;
  toggleGroceryItem: (ids: number[], checked: boolean) => Promise<void>;
  clearBought: () => Promise<number>;
}

export const useMealStore = create<MealState>((set, get) => ({
  view: 'today',
  day: null,
  week: [],
  grocery: null,
  loading: false,
  rerolling: null,
  setView: async (v) => {
    set({ view: v });
    if (v === 'week') {
      await get().fetchWeek();
    } else {
      await get().fetchDay(v === 'tomorrow' ? addDays(localISO(), 1) : undefined);
    }
  },
  fetchDay: async (date) => {
    set({ loading: true });
    try {
      set({ day: await api.getMeals(date) });
    } finally {
      set({ loading: false });
    }
  },
  fetchWeek: async () => {
    set({ loading: true });
    try {
      set({ week: await api.getWeekMeals() });
    } finally {
      set({ loading: false });
    }
  },
  fetchGrocery: async () => set({ grocery: await api.getGrocery() }),
  reroll: async (mealType) => {
    const day = get().day;
    if (!day) return;
    set({ rerolling: mealType });
    try {
      const updated = await api.rerollMeal(day.date, mealType);
      set({ day: { ...day, meals: { ...day.meals, [mealType]: updated } } });
      await get().fetchGrocery(); // 换菜同步买菜清单
    } finally {
      set({ rerolling: null });
    }
  },
  setStatus: async (plan, status) => {
    await api.patchMealStatus(plan.id, status);
    const day = get().day;
    if (day && day.meals[plan.meal_type]?.id === plan.id) {
      set({ day: { ...day, meals: { ...day.meals, [plan.meal_type]: { ...plan, status } } } });
    }
  },
  toggleGroceryItem: async (ids, checked) => {
    await Promise.all(ids.map((id) => api.patchGrocery(id, checked)));
    await get().fetchGrocery();
  },
  clearBought: async () => {
    const r = await api.clearBoughtGrocery();
    await get().fetchGrocery();
    return r.deleted;
  },
}));
