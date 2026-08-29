/** 整理计划中心：按批次回看照片、计划结论与任务完成度。 */

import { useEffect } from 'react';
import { Card, Empty, Image, List, Progress, Space, Tag, Typography } from 'antd';
import { useBusinessStore } from '../../stores';
import type { Plan } from '../../types';

const { Text, Title } = Typography;

function photoUrl(path: string): string {
  const relative = path.startsWith('photos/') ? path.slice('photos/'.length) : path;
  return `/api/photos/${relative}`;
}

function PlanEntry({ plan }: { plan: Plan }) {
  const tasks = plan.tasks ?? [];
  const done = tasks.filter((task) => task.status === 'done').length;
  const percent = tasks.length ? Math.round((done / tasks.length) * 100) : 0;

  return (
    <Card size="small" className="plan-history-card">
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12, alignItems: 'flex-start' }}>
        <div>
          <Title level={5} style={{ margin: 0 }}>{plan.room} · 整理计划</Title>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {plan.created_at ?? '未记录时间'} · {plan.photos?.length ?? 0} 张照片
          </Text>
        </div>
        <Tag color={plan.status === 'completed' ? 'green' : 'blue'}>
          {plan.status === 'completed' ? '已完成' : '进行中'}
        </Tag>
      </div>

      {plan.photos?.length ? (
        <Space size={8} style={{ marginTop: 12 }}>
          {plan.photos.map((photo) => (
            <Image
              key={photo.id}
              src={photoUrl(photo.path)}
              alt={`计划照片 ${photo.id}`}
              width={64}
              height={64}
              preview
              style={{ objectFit: 'cover', borderRadius: 8 }}
            />
          ))}
        </Space>
      ) : (
        <Text type="secondary" style={{ display: 'block', marginTop: 12 }}>此计划没有关联照片</Text>
      )}

      {plan.summary && <Text style={{ display: 'block', marginTop: 12 }}>{plan.summary}</Text>}
      <div style={{ marginTop: 12 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12 }}>
          <Text type="secondary">任务进度</Text>
          <Text type="secondary">{done}/{tasks.length} 已完成</Text>
        </div>
        <Progress percent={percent} size="small" showInfo={false} />
      </div>
    </Card>
  );
}

export default function PlansPage() {
  const { plans, fetchPlans, version } = useBusinessStore();

  useEffect(() => {
    void fetchPlans();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);

  return (
    <div style={{ padding: 16, maxWidth: 760, margin: '0 auto' }}>
      <Title level={4} style={{ marginTop: 0 }}>整理计划</Title>
      <Text type="secondary">每个批次都保留它的照片和下一步，不让整理成果散在对话里。</Text>
      <List
        style={{ marginTop: 16 }}
        dataSource={plans}
        rowKey="id"
        locale={{ emptyText: <Empty description="还没有整理计划，先拍一组照片吧" /> }}
        renderItem={(plan) => <List.Item style={{ paddingInline: 0 }}><PlanEntry plan={plan} /></List.Item>}
      />
    </div>
  );
}
