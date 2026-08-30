/** 今日三餐页：今天/明天/本周三视图；今天=三张餐卡，本周=7 天缩略横滑。 */

import { useEffect, useState } from 'react';
import { App as AntApp, Button, Segmented, Spin, Typography } from 'antd';
import type { MealPlan, MealType, WeekDay } from '../../types';
import { useMealStore, type MealView } from '../../stores';
import { fmtMD } from '../../utils/date';
import MealCard from './MealCard';
import GroceryBar from './GroceryBar';
import GroceryDrawer from './GroceryDrawer';

const { Text } = Typography;

const MEAL_ORDER: MealType[] = ['breakfast', 'lunch', 'dinner'];
const MEAL_CHAR: Record<MealType, string> = { breakfast: '早', lunch: '午', dinner: '晚' };

/** 常见加载错误转人话。 */
function friendlyError(err: string): string {
  if (err === 'Not Found') return '后端服务是旧版本（没有 /api/meals 路由），请重启：./start.sh stop && ./start.sh';
  if (err === 'Failed to fetch') return '连不上后端服务，请确认服务已启动';
  return err;
}

/** 加载失败占位：说明原因 + 一键重新生成。 */
function LoadError({ view, error, onRetry }: { view: MealView; error: string; onRetry: () => void }) {
  const label = view === 'week' ? '生成本周菜单' : view === 'tomorrow' ? '生成明日菜单' : '生成今日菜单';
  return (
    <div className="meal-error">
      <div className="meal-error-title">菜单还没生成</div>
      <div className="meal-error-desc">{friendlyError(error)}</div>
      <Button type="primary" size="small" onClick={onRetry}>
        {label}
      </Button>
    </div>
  );
}

function headerTitle(view: MealView, day: DayMealsLike | null): string {
  if (view === 'week') return '本周菜单';
  if (!day) return '三餐';
  return `${view === 'tomorrow' ? '明天' : '今天'} · ${Number(day.date.slice(5, 7))}月${Number(day.date.slice(8, 10))}日 ${day.weekday}`;
}
type DayMealsLike = { date: string; weekday: string };

function WeekRow({ week }: { week: WeekDay[] }) {
  return (
    <div className="week-scroll">
      {week.map((d) => (
        <div key={d.date} className={`week-card${d.is_today ? ' week-card-today' : ''}`}>
          <div className="week-card-head">
            <span className="week-card-date">{fmtMD(d.date)}</span>
            <span>{d.is_today ? '今天' : d.weekday}</span>
          </div>
          {MEAL_ORDER.map((mt) => {
            const m = d.meals[mt];
            return (
              <div key={mt} className="week-meal">
                <span className={`week-meal-dot${m?.status === 'eaten' ? ' week-meal-dot-done' : ''}`}>
                  {MEAL_CHAR[mt]}
                </span>
                <span className="week-meal-name" title={m?.name}>
                  {m ? `${m.name}${m.mode === 'bento' ? ' 🍱' : ''}` : '—'}
                </span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export default function MealsPage() {
  const { message } = AntApp.useApp();
  const { day, week, view, loading, error, rerolling, grocery, setView, reroll, setStatus, fetchGrocery } =
    useMealStore();
  const [drawerOpen, setDrawerOpen] = useState(false);

  useEffect(() => {
    if (!day) void setView('today');
    void fetchGrocery();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleReroll = async (plan: MealPlan) => {
    try {
      await reroll(plan.meal_type);
      message.success('已换菜，买菜清单同步更新');
    } catch (e) {
      const msg = e instanceof Error ? e.message : '';
      if (msg.includes('bento_locked')) message.info('便当昨晚已做好，明天再换');
      else message.error(msg || '换菜失败');
    }
  };

  const handleStatus = async (plan: MealPlan) => {
    const next = plan.status === 'eaten' ? 'planned' : 'eaten';
    try {
      await setStatus(plan, next);
      if (next === 'eaten') message.success('吃上了，不用操心的一餐 ✨');
    } catch (e) {
      message.error(e instanceof Error ? e.message : '操作失败');
    }
  };

  const tomorrow = day?.tomorrow_preview;
  const loadFailed = !!error && (view === 'week' ? week.length === 0 : !day);
  const initialLoading = loading && (view === 'week' ? week.length === 0 : !day);

  return (
    <div className="meal-page">
      <header className="meal-header">
        <div className="meal-title">{headerTitle(view, day)}</div>
        <Segmented<MealView>
          size="small"
          value={view}
          onChange={(v) => void setView(v)}
          options={[
            { value: 'today', label: '今天' },
            { value: 'tomorrow', label: '明天' },
            { value: 'week', label: '本周' },
          ]}
        />
      </header>

      {initialLoading ? (
        <div style={{ textAlign: 'center', padding: '64px 0' }}>
          <Spin />
        </div>
      ) : loadFailed ? (
        <LoadError view={view} error={error!} onRetry={() => void setView(view)} />
      ) : view === 'week' ? (
        <WeekRow week={week} />
      ) : (
        day && (
          <>
            <div className="meal-list">
              {MEAL_ORDER.map((mt) => {
                const plan = day.meals[mt];
                return plan ? (
                  <MealCard
                    key={mt}
                    plan={plan}
                    rerolling={rerolling === mt}
                    onReroll={handleReroll}
                    onStatus={handleStatus}
                  />
                ) : null;
              })}
            </div>

            {tomorrow && view === 'today' && (
              <div className="meal-tomorrow">
                <span className="meal-eyebrow">明天 · {fmtMD(tomorrow.date)}</span>
                <Text type="secondary" className="meal-tomorrow-names">
                  {MEAL_ORDER.map((mt) => tomorrow[mt]).filter(Boolean).join(' / ')}
                </Text>
                <button type="button" className="meal-tomorrow-btn" onClick={() => void setView('tomorrow')}>
                  查看 →
                </button>
              </div>
            )}
          </>
        )
      )}

      <GroceryBar grocery={grocery} onOpen={() => setDrawerOpen(true)} />
      <GroceryDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} />
    </div>
  );
}
