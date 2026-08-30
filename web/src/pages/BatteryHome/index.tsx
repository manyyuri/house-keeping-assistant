/** 三格电首页（省力概念签名元素，CONCEPT §6.1 / §6.6）。
 *
 * 打开即问「今天还剩多少力气？」→ 满格/半格/没电。
 * 电量决定这一屏给什么（后端 /api/home 真的改变内容供给，不是 UI 装饰）：
 *   - 满格 → 一个 15 分钟任务 + 可选菜单
 *   - 半格 → 一个 5 分钟任务 + 直接告诉今天吃什么
 *   - 没电 → 一个 2 分钟任务（或「今天就歇着」）+ 一句不指责的话
 *
 * 反打卡：不设连击/绿点；兜底建议做了也不记账（诚实，不给云表扬）。
 */

import { useState } from 'react';
import { Button, Spin, Tag, Typography } from 'antd';
import { CheckOutlined, PictureOutlined, ReloadOutlined } from '@ant-design/icons';
import * as api from '../../api';
import type { EnergyLevel, HomePayload } from '../../types';

const { Text } = Typography;

export const ENERGY_OPTIONS: { key: EnergyLevel; label: string; sub: string; hint: string }[] = [
  { key: 'full', label: '满格', sub: '15 分钟', hint: '力气还够，做一件 15 分钟的事' },
  { key: 'half', label: '半格', sub: '5 分钟', hint: '只剩一点，5 分钟正好' },
  { key: 'empty', label: '没电', sub: '2 分钟', hint: '今天就歇着也行' },
];

const TYPE_LABEL: Record<string, string> = {
  clean: '清洁',
  organize: '整理',
  store: '收纳',
  discard: '舍弃',
};

const REST_COPY = '那就歇着吧。明天再来，不用愧疚。';

export default function BatteryHome({
  onOpenCamera,
  onOpenAlbum,
  onGoTasks,
  onGoMeals,
}: {
  onOpenCamera: () => void;
  onOpenAlbum: () => void;
  onGoTasks: () => void;
  onGoMeals: () => void;
}) {
  const [energy, setEnergy] = useState<EnergyLevel | null>(null);
  const [payload, setPayload] = useState<HomePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resting, setResting] = useState(false);

  const select = async (lv: EnergyLevel) => {
    setEnergy(lv);
    setLoading(true);
    setError(null);
    setResting(false);
    try {
      setPayload(await api.getHome(lv));
    } catch (e) {
      setError(e instanceof Error ? e.message : '加载失败');
      setPayload(null);
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    setEnergy(null);
    setPayload(null);
    setError(null);
    setResting(false);
  };

  return (
    <div className="battery-home">
      {energy === null ? (
        <>
          <p className="battery-ask">今天还剩多少力气？</p>
          <div className="battery-row" role="radiogroup" aria-label="选择今天的电量">
            {ENERGY_OPTIONS.map((opt) => (
              <button
                key={opt.key}
                type="button"
                role="radio"
                aria-checked={false}
                className="battery"
                data-level={opt.key}
                onClick={() => void select(opt.key)}
              >
                <span className="battery-fig" aria-hidden="true">
                  <span className="battery-body">
                    <i className="battery-cell" />
                    <i className="battery-cell" />
                    <i className="battery-cell" />
                  </span>
                  <span className="battery-nub" />
                </span>
                <span className="battery-label">{opt.label}</span>
                <span className="battery-sub">{opt.sub}</span>
              </button>
            ))}
          </div>
          <p className="battery-hint">不用想今天要干嘛——先告诉它你有多少电。</p>
        </>
      ) : loading ? (
        <div className="battery-loading">
          <Spin size="small" />
        </div>
      ) : error ? (
        <div className="battery-error">
          <Text type="secondary">这一格没拿到内容：{error}</Text>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => void select(energy)}>
            再试一次
          </Button>
        </div>
      ) : payload ? (
        <div className="battery-results" key={payload.energy}>
          <p className="battery-ask battery-ask-small">
            {payload.level.title}
            <span className="battery-reset" role="button" tabIndex={0} onClick={reset} onKeyDown={(e) => e.key === 'Enter' && reset()}>
              换个电量
            </span>
          </p>

          {/* 唯一的动作：这一格电只配这一件事 */}
          <div className="battery-action-card">
            <div className="battery-eyebrow">
              <Tag color="default" variant="filled" style={{ marginRight: 0 }}>
                {payload.task.source === 'task' ? TYPE_LABEL[payload.task.type] ?? '任务' : '最小行动'}
              </Tag>
              <span className="battery-minutes">约 {payload.task.est_minutes} 分钟</span>
            </div>
            <p className="battery-task-title">{payload.task.title}</p>
            {payload.task.source === 'task' && payload.task.room && (
              <Text type="secondary" style={{ fontSize: 12 }}>{payload.task.room}</Text>
            )}
            {payload.task.steps.length > 0 && (
              <ol className="battery-steps">
                {payload.task.steps.slice(0, 3).map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ol>
            )}
            {payload.task.source === 'task' ? (
              <button type="button" className="battery-cta" onClick={onGoTasks}>
                <CheckOutlined /> 去做这件小事
              </button>
            ) : (
              <Text type="secondary" className="battery-suggestion-note">
                做完不用打卡，就够好了。
              </Text>
            )}
            {payload.rest_allowed && !resting && (
              <button type="button" className="battery-rest" onClick={() => setResting(true)}>
                今天就歇着，明天再说
              </button>
            )}
            {resting && <Text type="secondary" className="battery-resting">{REST_COPY}</Text>}
          </div>

          {/* 身体：一餐，不用选 */}
          <div className="battery-meal">
            {payload.meal.give && payload.meal.meal ? (
              <>
                <p className="battery-meal-text">{payload.meal.text}</p>
                <p className="battery-meal-name">{payload.meal.meal.name}</p>
                <button type="button" className="battery-link" onClick={onGoMeals}>
                  去三餐页
                </button>
              </>
            ) : payload.meal.meals.length > 0 ? (
              <>
                <p className="battery-meal-text">{payload.meal.text}</p>
                <div className="battery-meal-chips">
                  {payload.meal.meals.map((m) => (
                    <span key={m.type} className="battery-meal-chip">
                      {m.name}
                      {m.cook_minutes ? ` · ${m.cook_minutes} 分钟` : ''}
                    </span>
                  ))}
                </div>
                <button type="button" className="battery-link" onClick={onGoMeals}>
                  去挑
                </button>
              </>
            ) : (
              <p className="battery-meal-text">{payload.meal.text}</p>
            )}
          </div>

          <p className="battery-encourage">{payload.encouragement}</p>
          <p className="battery-trajectory">{payload.trajectory.line}</p>
        </div>
      ) : null}

      {/* 拍照整理仍是主路径之一，退后一档，不抢电量风头 */}
      <div className="battery-shutter" role="note">
        <button
          type="button"
          className="battery-shutter-btn"
          onClick={onOpenCamera}
          aria-label="拍照开始整理"
        />
        <button type="button" className="battery-album" onClick={onOpenAlbum}>
          <PictureOutlined /> 从相册选照片整理
        </button>
      </div>
    </div>
  );
}
