/** 整理计划：家的地图。
 * 列表 = 一眼看清每间房的「下一步」（照片 + 一句话），不堆数据；
 * 点卡片 = 抽屉「走进一个房间」：三层筛子判定（舍弃/观察期/保留）展开物品名，
 * 任务按时限分组、就地打勾完成（诚实记账，非打卡）。生成/补照片退为次要动作。
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  App as AntApp,
  Button,
  Drawer,
  Empty,
  Form,
  Grid,
  Image,
  Input,
  Modal,
  Row,
  Col,
  Typography,
} from 'antd';
import {
  CheckOutlined,
  PlusOutlined,
  ReloadOutlined,
  RightOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import * as api from '../../api';
import { useBusinessStore } from '../../stores';
import { TASK_TYPE_META } from '../TasksPage';
import type { Item, Plan, Task } from '../../types';

const { Text, Title } = Typography;
const { useBreakpoint } = Grid;

function photoUrl(path: string): string {
  const relative = path.startsWith('photos/') ? path.slice('photos/'.length) : path;
  return `/api/photos/${relative}`;
}

/* ---------- 派生：卡片「下一步」一句话 + 任务分组（信息即结构，用省力语汇） ---------- */

function pendingOf(tasks: Task[]): Task[] {
  return tasks.filter((t) => t.status !== 'done' && t.status !== 'skipped');
}

function nextStepLine(plan: Plan): string {
  const tasks = plan.tasks ?? [];
  const pending = pendingOf(tasks);

  // 还没生成：无总结/无计数/无任务
  const hasData =
    plan.danshari_score != null ||
    (plan.discard_count ?? 0) > 0 ||
    (plan.donate_count ?? 0) > 0 ||
    (plan.keep_count ?? 0) > 0 ||
    (plan.hesitate_count ?? 0) > 0 ||
    tasks.length > 0;
  if (!hasData) return '还没生成计划，点进去按一下';

  // 全部干完（加分制：不消失，如实说干完了）
  if (tasks.length && !pending.length) {
    return tasks.length > 1 ? `这间房的 ${tasks.length} 件小事都做完了` : '这间房的活儿都干完了';
  }

  const today = pending.filter((t) => t.due_date === 'today');
  const todayMin = today.reduce((a, t) => a + (t.est_minutes ?? 0), 0);
  const parts: string[] = [];
  if (today.length) parts.push(`今天可做 ${today.length} 件小事（约 ${todayMin} 分钟）`);
  else if (pending.length) {
    const min = pending.reduce((a, t) => a + (t.est_minutes ?? 0), 0);
    parts.push(`还有 ${pending.length} 件待办（约 ${min} 分钟）`);
  }
  if (plan.hesitate_count) {
    const due = earliestQuarantine(plan.items ?? []);
    parts.push(due ? `${plan.hesitate_count} 件在观察期 · ${due} 到期` : `${plan.hesitate_count} 件在观察期`);
  }
  if (!parts.length) return '已判定，点进去看看';
  return parts.join(' · ');
}

/** 观察期最早到期日（MM-DD），给「再看一眼」一个锚点 */
function earliestQuarantine(items: Item[]): string | null {
  let earliest: string | null = null;
  for (const it of items) {
    if (!it.quarantine_until) continue;
    if (!earliest || it.quarantine_until < earliest) earliest = it.quarantine_until;
  }
  if (!earliest) return null;
  const [, m, d] = earliest.split('-');
  return m && d ? `${Number(m)}-${Number(d)}` : null;
}

const DUE_LABEL: Record<string, string> = { today: '今天', weekend: '周末', later: '之后', week: '之后' };

function groupTasks(tasks: Task[]): { groups: { key: string; label: string; items: Task[] }[]; done: Task[] } {
  const pending = pendingOf(tasks).slice().sort((a, b) => a.id - b.id);
  const groups = [
    { key: 'today', label: '今天', items: [] as Task[] },
    { key: 'weekend', label: '周末', items: [] as Task[] },
    { key: 'later', label: '之后', items: [] as Task[] },
  ];
  for (const t of pending) {
    const g = t.due_date && DUE_LABEL[t.due_date] ? (t.due_date === 'today' ? 'today' : t.due_date === 'weekend' ? 'weekend' : 'later') : 'later';
    const found = groups.find((x) => x.key === g);
    if (found) found.items.push(t);
    else groups[2].items.push(t);
  }
  const nonEmpty = groups.filter((g) => g.items.length);
  const done = tasks.filter((t) => t.status === 'done' || t.status === 'skipped').sort((a, b) => a.id - b.id);
  return { groups: nonEmpty, done };
}

/* ---------- 列表卡片：照片 + 房间名 + 下一步一句话（唯一的记忆点） ---------- */

function PlanCard({ plan, onClick }: { plan: Plan; onClick: () => void }) {
  const tasks = plan.tasks ?? [];
  const done = tasks.filter((t) => t.status === 'done').length;
  const percent = tasks.length ? Math.round((done / tasks.length) * 100) : 0;
  const photo = plan.photos?.[0];
  const chips: { cls: string; label: string }[] = [];
  if (plan.discard_count) chips.push({ cls: 'discard', label: `丢 ${plan.discard_count}` });
  if (plan.hesitate_count) chips.push({ cls: 'hesitate', label: `观察 ${plan.hesitate_count}` });
  if (plan.keep_count) chips.push({ cls: 'keep', label: `留 ${plan.keep_count}` });

  return (
    <button className="plan-card" onClick={onClick} aria-label={`打开「${plan.room}」的整理计划`}>
      {photo ? (
        <Image
          className="plan-card-thumb"
          src={photoUrl(photo.path)}
          alt={`${plan.room} 照片`}
          preview={false}
          width={72}
          height={72}
        />
      ) : (
        <span className="plan-card-thumb plan-card-thumb-empty">📷</span>
      )}
      <span className="plan-card-body">
        <span className="plan-card-title">
          <span className="plan-card-room">{plan.room}</span>
          <span className="plan-card-date">{plan.created_at ? plan.created_at.slice(5, 10) : ''} · {plan.photos?.length ?? 0} 张</span>
        </span>
        <span className="plan-next">{nextStepLine(plan)}</span>
        {chips.length ? (
          <span className="plan-chips">
            {chips.map((c) => (
              <span key={c.cls} className={`plan-chip ${c.cls}`}>{c.label}</span>
            ))}
          </span>
        ) : null}
        {tasks.length ? (
          <span className="plan-card-foot">
            <span className="plan-progress">
              <span className="plan-progress-fill" style={{ width: `${percent}%` }} />
            </span>
          </span>
        ) : null}
      </span>
      <RightOutlined className="plan-card-arrow" />
    </button>
  );
}

/* ---------- 抽屉：走进一个房间（判定三层筛子 + 任务就地打勾） ---------- */

const SIEVE_META = [
  { key: 'discard', label: '舍弃', cls: 'discard' },
  { key: 'hesitate', label: '观察期', cls: 'hesitate' },
  { key: 'keep', label: '保留', cls: 'keep' },
  { key: 'donate', label: '捐赠', cls: 'donate' },
] as const;

function PlanDrawer({
  plan,
  genId,
  onClose,
  onUploaded,
  onGenerate,
  onStopGenerate,
}: {
  plan: Plan;
  genId: number | null;
  onClose: () => void;
  onUploaded: (updated: Plan) => void;
  onGenerate: (plan: Plan) => void;
  onStopGenerate: () => void;
}) {
  const { message } = AntApp.useApp();
  const screens = useBreakpoint();
  const isMobile = !screens.md;
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [openSieve, setOpenSieve] = useState<string[]>([]);
  const [openSteps, setOpenSteps] = useState<Set<number>>(new Set());
  const [toggling, setToggling] = useState<number | null>(null);

  const tasks = plan.tasks ?? [];
  const photos = plan.photos ?? [];
  const { groups, done } = groupTasks(tasks);

  const handleFiles = async (files: FileList | null) => {
    if (!files || !files.length) return;
    const images = Array.from(files).filter((f) => f.type.startsWith('image/'));
    if (!images.length) return;
    setUploading(true);
    try {
      const ids: number[] = [];
      for (const f of images) {
        const compressed = await api.compressImage(f);
        const [res] = await api.uploadPhotos([compressed]);
        ids.push(res.photoId);
      }
      const updated = await api.attachPlanPhotos(plan.id, ids);
      message.success(`已补 ${updated.added} 张照片到「${plan.room}」`);
      onUploaded(updated.plan);
    } catch (e) {
      message.error(`补照片失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setUploading(false);
    }
  };

  const toggleTask = async (task: Task) => {
    if (toggling !== null) return;
    const next = task.status === 'done' ? 'todo' : 'done';
    setToggling(task.id);
    try {
      await api.patchTask(task.id, next);
      const fresh = await api.getPlan(plan.id);
      onUploaded(fresh); // 复用：刷新抽屉 + 版本号由上层 bump
      if (next === 'done') message.success('记下了，这一件做完了');
      else message.info('改回待办了');
    } catch (e) {
      message.error(`更新失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setToggling(null);
    }
  };

  const toggleSieve = (key: string) =>
    setOpenSieve((s) => (s.includes(key) ? s.filter((k) => k !== key) : [...s, key]));

  const toggleSteps = (id: number) =>
    setOpenSteps((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const itemsByStatus = (key: string) => (plan.items ?? []).filter((it) => it.keep_status === key);

  const generating = genId === plan.id;

  return (
    <Drawer
      title={null}
      placement="right"
      width={isMobile ? '100%' : 440}
      open
      onClose={onClose}
      destroyOnHidden
      closable={false}
      styles={{ body: { padding: '0 20px 40px', overflowY: 'auto' } }}
    >
      {/* 头部：房间名 + 状态 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div className="plan-drawer-room">{plan.room}</div>
          <div className="plan-drawer-date">
            {plan.created_at ?? ''} · {photos.length} 张照片
          </div>
        </div>
        <button
          className="plan-drawer-close"
          onClick={onClose}
          aria-label="关闭"
        >
          ✕
        </button>
      </div>

      {/* 照片带 + 补照片 */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 14 }}>
        {photos.length ? (
          <div className="plan-drawer-photos">
            {photos.map((p) => (
              <Image
                key={p.id}
                className="plan-drawer-photo"
                src={photoUrl(p.path)}
                alt={`计划照片 ${p.id}`}
                width={64}
                height={64}
                preview
              />
            ))}
          </div>
        ) : (
          <Text type="secondary" style={{ fontSize: 12.5 }}>
            还没有照片
          </Text>
        )}
        <button
          className="plan-drawer-ghost"
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
        >
          <UploadOutlined /> {uploading ? '上传中…' : '补照片'}
        </button>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          style={{ display: 'none' }}
          onChange={(e) => {
            void handleFiles(e.target.files);
            e.target.value = '';
          }}
        />
      </div>

      {/* 一句结论 */}
      {plan.summary ? <div className="plan-verdict">{plan.summary}</div> : null}

      {/* 判定：三层筛子（舍弃 / 观察期 / 保留），展开看物品名 */}
      <div className="plan-section">
        <div className="plan-section-title">判定 <small>三层筛子，逐层过</small></div>
        {SIEVE_META.map((m) => {
          const items = itemsByStatus(m.key);
          if (!items.length) return null;
          const open = openSieve.includes(m.key);
          const due = m.key === 'hesitate' ? earliestQuarantine(items) : null;
          return (
            <div key={m.key} className={`sieve ${m.cls}`}>
              <button className="sieve-band" onClick={() => toggleSieve(m.key)} aria-expanded={open}>
                <span className="sieve-dot" />
                <span className="sieve-label">{m.label}</span>
                <span className="sieve-count">{items.length}</span>
                {m.key === 'hesitate' && due ? <span className="sieve-due">· {due} 到期</span> : null}
                <span style={{ flex: 1 }} />
                <span className={`sieve-chevron${open ? ' open' : ''}`}>▾</span>
              </button>
              {open ? (
                <div className="sieve-items">
                  {items.map((it) => (
                    <span key={it.id} className="sieve-chip">{it.name}{it.quantity > 1 ? ` ×${it.quantity}` : ''}</span>
                  ))}
                </div>
              ) : null}
            </div>
          );
        })}
      </div>

      {/* 任务：按时限分组，就地打勾 */}
      <div className="plan-section">
        <div className="plan-section-title">
          任务 <small>{groups.reduce((a, g) => a + g.items.length, 0) + done.length} 件</small>
        </div>

        {generating ? (
          <div className="plan-generating">
            <span className="plan-generating-spin" />
            <span>正在识别照片、编排任务…</span>
            <button className="plan-drawer-ghost" onClick={onStopGenerate}>停止</button>
          </div>
        ) : null}

        {!tasks.length ? (
          <div className="plan-empty">
            <Text>照片还在，计划还没长出来。</Text>
            <Button
              type="primary"
              ghost
              icon={<ReloadOutlined />}
              disabled={!photos.length || generating}
              loading={generating}
              onClick={() => onGenerate(plan)}
            >
              {photos.length ? '按一下，把照片变成任务' : '先补照片再生成'}
            </Button>
          </div>
        ) : (
          <>
            {groups.map((g) => (
              <div key={g.key}>
                <div className="task-group-title">{g.label}</div>
                {g.items.map((t) => {
                  const meta = TASK_TYPE_META[t.type] ?? { label: t.type, color: 'default' };
                  const expanded = openSteps.has(t.id);
                  return (
                    <div key={t.id} className="task-row">
                      <button
                        className="task-check"
                        onClick={() => void toggleTask(t)}
                        aria-label={`标记完成：${t.title}`}
                        disabled={toggling === t.id}
                      >
                        <CheckOutlined />
                      </button>
                      <div className="task-main" onClick={() => toggleSteps(t.id)}>
                        <div className="task-title">
                          <span className={`task-type ${t.type}`}>{meta.label}</span>
                          {t.title}
                        </div>
                        <div className="task-meta">
                          {t.est_minutes ? `约 ${t.est_minutes} 分钟` : ''}
                          {expanded && t.steps?.length ? (
                            <ol className="task-steps">
                              {t.steps.map((s, i) => (
                                <li key={i}>{s}</li>
                              ))}
                            </ol>
                          ) : (
                            <span className="task-expand">{expanded ? '' : '步骤 ▾'}</span>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ))}
            {done.length ? (
              <div key="done">
                <div className="task-group-title">已完成 <small style={{ fontWeight: 400 }}>{done.length} 件，做过了就留在账本里</small></div>
                {done.map((t) => (
                  <div key={t.id} className="task-row task-row-done">
                    <button
                      className="task-check done"
                      onClick={() => void toggleTask(t)}
                      aria-label={`改回待办：${t.title}`}
                      disabled={toggling === t.id}
                    >
                      <CheckOutlined />
                    </button>
                    <div className="task-main">
                      <div className="task-title done">{t.title}</div>
                      <div className="task-meta">已完成{t.status === 'skipped' ? '（跳过）' : ''}</div>
                    </div>
                  </div>
                ))}
              </div>
            ) : null}
          </>
        )}
      </div>

      {/* 次要动作：重新生成 */}
      {photos.length && tasks.length ? (
        <div className="plan-foot-actions">
          <button
            className="plan-drawer-ghost"
            onClick={() => onGenerate(plan)}
            disabled={generating}
          >
            <ReloadOutlined /> {generating ? '生成中…' : '重新识别照片，重排一遍'}
          </button>
        </div>
      ) : null}
    </Drawer>
  );
}

/* ---------- 页面：家的地图 ---------- */

export default function PlansPage() {
  const { message } = AntApp.useApp();
  const { plans, fetchPlans, version, bumpVersion } = useBusinessStore();
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<Plan | null>(null);
  const [genId, setGenId] = useState<number | null>(null);
  const genAbortRef = useRef<AbortController | null>(null);

  const generatePlan = useCallback(
    async (plan: Plan) => {
      if (genId !== null) return;
      if (!plan.photos?.length) {
        message.warning('该计划还没有照片，先补照片再生成');
        return;
      }
      setGenId(plan.id);
      const controller = new AbortController();
      genAbortRef.current = controller;
      try {
        await api.streamPlanGenerate({
          planId: plan.id,
          signal: controller.signal,
          onEvent: (ev) => {
            if (ev.event === 'plan_created') {
              message.success(`「${plan.room}」已生成：${ev.data.taskCount} 个任务`);
            } else if (ev.event === 'error') {
              message.error(ev.data.message);
            }
          },
        });
        bumpVersion();
        const fresh = await api.getPlan(plan.id);
        setSelected((s) => (s && s.id === plan.id ? fresh : s));
      } catch (e) {
        if (controller.signal.aborted) message.info('已停止生成');
        else message.error(`生成失败：${e instanceof Error ? e.message : e}`);
      } finally {
        setGenId(null);
        genAbortRef.current = null;
      }
    },
    [genId, message, bumpVersion],
  );

  const stopGenerate = useCallback(() => genAbortRef.current?.abort(), []);

  // 打开抽屉先拉详情（含物品清单，筛子需要）；失败则用列表数据兜底
  const openPlan = useCallback(async (plan: Plan) => {
    try {
      const detail = await api.getPlan(plan.id);
      setSelected(detail);
    } catch {
      setSelected(plan);
    }
  }, []);

  useEffect(() => {
    void fetchPlans();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);

  const refreshSelected = useCallback(
    (updated: Plan) => {
      setSelected(updated);
      bumpVersion();
    },
    [bumpVersion],
  );

  const onCreate = async () => {
    let values: { room: string; summary?: string };
    try {
      values = await form.validateFields();
    } catch {
      return;
    }
    setCreating(true);
    try {
      await api.createPlan({ room: values.room.trim(), summary: values.summary?.trim() || undefined });
      bumpVersion();
      message.success('计划已创建，去对话里拍照片挂进来');
      setOpen(false);
      form.resetFields();
    } catch (e) {
      message.error(`创建失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="plans-page">
      <div className="plans-head">
        <div>
          <Title level={4} className="plans-title">
            整理计划
          </Title>
          <Text type="secondary" className="plans-sub">
            一眼看清每间房，下一步是什么
          </Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          新建计划
        </Button>
      </div>

      <Row gutter={[14, 14]}>
        {plans.map((plan) => (
          <Col key={plan.id} xs={24} sm={12} lg={8}>
            <PlanCard plan={plan} onClick={() => void openPlan(plan)} />
          </Col>
        ))}
      </Row>

      {!plans.length ? (
        <div className="plans-empty">
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description={
              <span>
                还没有整理计划。拍一组照片，或先建一个房间。
              </span>
            }
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
            新建计划
          </Button>
        </div>
      ) : null}

      <Modal
        title="新建整理计划"
        open={open}
        onCancel={() => setOpen(false)}
        onOk={() => void onCreate()}
        confirmLoading={creating}
        okText="创建"
        destroyOnHidden
      >
        <Form form={form} layout="vertical" requiredMark={false}>
          <Form.Item name="room" label="区域" rules={[{ required: true, message: '请填写区域，如：衣柜' }]}>
            <Input placeholder="如：衣柜 / 客厅 / 厨房" maxLength={50} />
          </Form.Item>
          <Form.Item name="summary" label="目标 / 说明（可选）">
            <Input.TextArea rows={3} placeholder="一句话说明这次想整理什么" />
          </Form.Item>
        </Form>
      </Modal>

      {selected && (
        <PlanDrawer
          plan={selected}
          genId={genId}
          onClose={() => setSelected(null)}
          onUploaded={refreshSelected}
          onGenerate={generatePlan}
          onStopGenerate={stopGenerate}
        />
      )}
    </div>
  );
}
