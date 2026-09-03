/** 单餐卡片：拳头餐盘 + 打卡/换菜 + 上班族语境（带饭模式、顺手做便当）。 */

import { Button, Card, Collapse, Tooltip, Typography } from 'antd';
import { CheckOutlined, RedoOutlined } from '@ant-design/icons';
import type { MealPlan } from '../../types';
import { localISO } from '../../utils/date';
import FistPlate from './FistPlate';

const { Text } = Typography;

const TOOL_LABEL: Record<string, string> = { cook5: 'Cook5', stove: '平底锅', none: '免烹饪' };

/** 卡片眉行：谁 / 在哪 / 多久。 */
function eyebrow(plan: MealPlan): string {
  const r = plan.recipe;
  if (plan.meal_type === 'breakfast') return '出门前 · 10 分钟内';
  if (plan.meal_type === 'lunch') {
    return plan.mode === 'bento'
      ? '公司 · 微波 3 分钟'
      : `周末现做 · ${TOOL_LABEL[r?.cook_tool ?? 'cook5']} ${r?.cook_minutes ?? ''}′`;
  }
  const tool = TOOL_LABEL[r?.cook_tool ?? 'stove'];
  return `19:00 到家 · ${tool} ${r?.cook_minutes ?? ''}′ 上桌`;
}

/** 便当锁：制作日（前一天）19:00 后不可换菜。 */
export function bentoLocked(plan: MealPlan): boolean {
  if (plan.mode !== 'bento') return false;
  const lock = new Date(`${plan.plan_date}T19:00:00`);
  lock.setDate(lock.getDate() - 1);
  return new Date() >= lock;
}

interface MealCardProps {
  plan: MealPlan;
  rerolling?: boolean;
  onReroll: (plan: MealPlan) => void;
  onStatus: (plan: MealPlan) => void;
}

export default function MealCard({ plan, rerolling, onReroll, onStatus }: MealCardProps) {
  const recipe = plan.recipe;
  if (!recipe) return null;
  const eaten = plan.status === 'eaten';
  const locked = bentoLocked(plan);
  const bentoReady = plan.mode === 'bento' && plan.plan_date <= localISO(); // 当日=已装盒，未来=今晚做

  return (
    <Card size="small" className={`meal-card${eaten ? ' meal-card-done' : ''}`} styles={{ body: { padding: '12px 14px' } }}>
      <div className="meal-eyebrow">{eyebrow(plan)}</div>

      <div className="meal-main">
        <FistPlate slots={recipe.slots} stamped={eaten} />
        <div className="meal-main-info">
          <div className="meal-name">
            {recipe.cuisine ? <span className={`meal-cuisine c-${recipe.cuisine}`}>{recipe.cuisine}</span> : null}
            {recipe.name}
          </div>
          <div className="meal-chips">
            {recipe.slots.map((s) => (
              <span key={s.slot} className={`meal-chip kind-${s.kind}`}>
                {s.slot}
                {s.fists}拳
              </span>
            ))}
          </div>
          {recipe.satiety_hint && <div className="meal-satiety">{recipe.satiety_hint}</div>}
        </div>
      </div>

      <div className="meal-ing">
        <Text type="secondary">食材：{recipe.ingredients.map((i) => `${i.name} ${i.amount}`).join(' · ')}</Text>
      </div>

      {plan.mode === 'bento' && (
        <div className="meal-bento-tag">{bentoReady ? '已备 · 昨晚 Cook5 顺手做 · 装盒冷藏' : '今晚晚餐后顺手做 · 装盒冷藏'}</div>
      )}

      {plan.meal_type === 'dinner' && plan.bento_preview && (
        <div className="bento-banner">
          ⚑ 晚餐后顺手做 · 明日便当：{plan.bento_preview.name}（+{plan.bento_preview.cook_minutes}′，免洗锅）
        </div>
      )}

      {plan.meal_type === 'dinner' && plan.note && <div className="meal-tip">营养师：{plan.note}</div>}

      <Collapse
        ghost
        size="small"
        className="meal-steps"
        items={[{
          key: 'steps',
          label: <span style={{ fontSize: 13 }}>做法 · {recipe.steps.length} 步</span>,
          children: (
            <ol className="meal-step-list">
              {recipe.steps.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
          ),
        }]}
      />

      <div className="meal-actions">
        <Button
          size="small"
          type={eaten ? 'text' : 'primary'}
          icon={<CheckOutlined />}
          onClick={() => onStatus(plan)}
        >
          {eaten ? '撤销' : '吃了'}
        </Button>
        <Tooltip title={locked ? '便当昨晚已做好，明天再换' : ''}>
          <Button
            size="small"
            type="text"
            icon={<RedoOutlined spin={rerolling} />}
            disabled={locked || rerolling}
            onClick={() => onReroll(plan)}
          >
            换一个
          </Button>
        </Tooltip>
      </div>
    </Card>
  );
}
