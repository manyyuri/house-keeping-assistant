/** 整理计划中心：新建计划 + 点计划补照片 + 按批次回看照片、计划结论与任务完成度。 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  App as AntApp,
  Button,
  Card,
  Empty,
  Form,
  Image,
  Input,
  List,
  Modal,
  Progress,
  Space,
  Tag,
  Typography,
} from 'antd';
import { PlusOutlined, ThunderboltOutlined, UploadOutlined } from '@ant-design/icons';
import * as api from '../../api';
import { useBusinessStore } from '../../stores';
import type { Plan } from '../../types';

const { Text, Title } = Typography;

function photoUrl(path: string): string {
  const relative = path.startsWith('photos/') ? path.slice('photos/'.length) : path;
  return `/api/photos/${relative}`;
}

/** 计划详情弹窗：查看照片/结论/任务进度，上传照片挂到该计划，并手动触发生成。 */
function PlanDetailModal({
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
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const tasks = plan.tasks ?? [];
  const done = tasks.filter((task) => task.status === 'done').length;
  const percent = tasks.length ? Math.round((done / tasks.length) * 100) : 0;
  const photos = plan.photos ?? [];

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
      message.success(`已添加 ${updated.added} 张照片到「${plan.room}」`);
      onUploaded(updated.plan);
    } catch (e) {
      message.error(`添加失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setUploading(false);
    }
  };

  return (
    <Modal
      title={`${plan.room} · 整理计划`}
      open
      onCancel={onClose}
      footer={null}
      destroyOnHidden
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {plan.created_at ?? '未记录时间'}
        </Text>
        <Tag color={plan.status === 'completed' ? 'green' : 'blue'}>
          {plan.status === 'completed' ? '已完成' : '进行中'}
        </Tag>
      </div>

      {plan.summary && <Text style={{ display: 'block', marginTop: 10 }}>{plan.summary}</Text>}

      <div style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <Text strong>照片（{photos.length} 张）</Text>
          <Button
            size="small"
            type="primary"
            ghost
            icon={<UploadOutlined />}
            loading={uploading}
            onClick={() => fileRef.current?.click()}
          >
            上传照片
          </Button>
        </div>
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
        {photos.length ? (
          <Space size={8} wrap style={{ marginTop: 10 }}>
            {photos.map((p) => (
              <Image
                key={p.id}
                src={photoUrl(p.path)}
                alt={`计划照片 ${p.id}`}
                width={80}
                height={80}
                preview
                style={{ objectFit: 'cover', borderRadius: 8 }}
              />
            ))}
          </Space>
        ) : (
          <Text type="secondary" style={{ display: 'block', marginTop: 8 }}>
            还没有照片——拍一组或从相册选，点右上角「上传照片」挂进来。
          </Text>
        )}
      </div>

      <div style={{ marginTop: 16 }}>
        <Button
          type="primary"
          icon={<ThunderboltOutlined />}
          disabled={!photos.length}
          loading={genId === plan.id}
          onClick={() => onGenerate(plan)}
        >
          {photos.length ? (genId === plan.id ? '生成中…' : '生成整理计划') : '先上传照片'}
        </Button>
        {genId === plan.id && (
          <Button size="small" style={{ marginLeft: 8 }} onClick={onStopGenerate}>
            停止
          </Button>
        )}
        <Text type="secondary" style={{ display: 'block', fontSize: 12, marginTop: 6 }}>
          {photos.length
            ? '按照片重新识别物品并生成/更新计划（保留已完成任务与账本）'
            : '需要至少一张照片才能生成'}
        </Text>
      </div>

      <div style={{ marginTop: 16 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
          <Text type="secondary">任务进度</Text>
          <Text type="secondary">
            {done}/{tasks.length} 已完成
          </Text>
        </div>
        <Progress percent={percent} size="small" showInfo={false} />
        {tasks.length === 0 && (
          <Text type="secondary" style={{ fontSize: 12 }}>
            还没有任务，去对话里说「帮我按断舍离整理」生成。
          </Text>
        )}
      </div>
    </Modal>
  );
}

function PlanEntry({ plan, genId, onClick, onGenerate }: {
  plan: Plan;
  genId: number | null;
  onClick: (p: Plan) => void;
  onGenerate: (plan: Plan) => void;
}) {
  const tasks = plan.tasks ?? [];
  const done = tasks.filter((task) => task.status === 'done').length;
  const percent = tasks.length ? Math.round((done / tasks.length) * 100) : 0;

  return (
    <Card size="small" className="plan-history-card" onClick={() => onClick(plan)}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
        <div>
          <Title level={5} style={{ margin: 0 }}>
            {plan.room} · 整理计划
          </Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {plan.created_at ?? '未记录时间'} · {plan.photos?.length ?? 0} 张照片
          </Text>
        </div>
        <Space>
          <Tag color={plan.status === 'completed' ? 'green' : 'blue'}>
            {plan.status === 'completed' ? '已完成' : '进行中'}
          </Tag>
          <Button
            size="small"
            type="link"
            icon={<ThunderboltOutlined />}
            disabled={!plan.photos?.length}
            loading={genId === plan.id}
            onClick={(e) => {
              e.stopPropagation();
              onGenerate(plan);
            }}
          >
            {plan.photos?.length ? '生成' : '无照片'}
          </Button>
        </Space>
      </div>

      {plan.photos?.length ? (
        <Space size={8} style={{ marginTop: 12 }}>
          {plan.photos.map((photo) => (
            <span key={photo.id} onClick={(e) => e.stopPropagation()}>
              <Image
                src={photoUrl(photo.path)}
                alt={`计划照片 ${photo.id}`}
                width={64}
                height={64}
                preview
                style={{ objectFit: 'cover', borderRadius: 8 }}
              />
            </span>
          ))}
        </Space>
      ) : (
        <Text type="secondary" style={{ display: 'block', marginTop: 12 }}>
          此计划还没有照片，点卡片上传
        </Text>
      )}

      {plan.summary && <Text style={{ display: 'block', marginTop: 12 }}>{plan.summary}</Text>}
      <div style={{ marginTop: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
          <Text type="secondary">任务进度</Text>
          <Text type="secondary">
            {done}/{tasks.length} 已完成
          </Text>
        </div>
        <Progress percent={percent} size="small" showInfo={false} />
      </div>
    </Card>
  );
}

export default function PlansPage() {
  const { message } = AntApp.useApp();
  const { plans, fetchPlans, version, bumpVersion } = useBusinessStore();
  const [form] = Form.useForm();
  const [open, setOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<Plan | null>(null);
  // 正在生成/重新生成的计划 id（一次只生成一个）
  const [genId, setGenId] = useState<number | null>(null);
  const genAbortRef = useRef<AbortController | null>(null);

  const generatePlan = useCallback(
    async (plan: Plan) => {
      if (genId !== null) return;
      if (!plan.photos?.length) {
        message.warning('该计划还没有照片，先上传照片再触发生成');
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
              message.success(
                `「${plan.room}」已生成：评分 ${ev.data.danshariScore} · ${ev.data.taskCount} 个任务`,
              );
            } else if (ev.event === 'error') {
              message.error(ev.data.message);
            }
          },
        });
        bumpVersion(); // 刷新列表
        const fresh = await api.getPlan(plan.id);
        setSelected((s) => (s && s.id === plan.id ? fresh : s)); // 弹窗同步刷新
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

  useEffect(() => {
    void fetchPlans();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);

  const onCreate = async () => {
    let values: { room: string; summary?: string };
    try {
      values = await form.validateFields();
    } catch {
      return; // 校验失败，不关闭
    }
    setCreating(true);
    try {
      await api.createPlan({ room: values.room.trim(), summary: values.summary?.trim() || undefined });
      bumpVersion();
      message.success('计划已创建，去对话里补充照片和任务吧');
      setOpen(false);
      form.resetFields();
    } catch (e) {
      message.error(`创建失败：${e instanceof Error ? e.message : e}`);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div style={{ padding: 16, maxWidth: 760, margin: '0 auto' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
        <div>
          <Title level={4} style={{ marginTop: 0 }}>
            整理计划
          </Title>
          <Text type="secondary">点计划卡片即可补照片；每个计划都保留它的照片和下一步。</Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setOpen(true)}>
          新建计划
        </Button>
      </div>
      <List
        style={{ marginTop: 16 }}
        dataSource={plans}
        rowKey="id"
        locale={{ emptyText: <Empty description="还没有整理计划，先建一个或拍一组照片吧" /> }}
        renderItem={(plan) => (
          <List.Item style={{ paddingInline: 0 }}>
            <PlanEntry
              plan={plan}
              genId={genId}
              onClick={(p) => setSelected(p)}
              onGenerate={generatePlan}
            />
          </List.Item>
        )}
      />
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
        <PlanDetailModal
          plan={selected}
          genId={genId}
          onClose={() => setSelected(null)}
          onUploaded={(updated) => {
            setSelected(updated);
            bumpVersion();
          }}
          onGenerate={generatePlan}
          onStopGenerate={stopGenerate}
        />
      )}
    </div>
  );
}
