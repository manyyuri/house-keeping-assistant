/** 成果统计：舍弃/捐赠/任务/均分 + 观察期到期复查。 */

import { useEffect } from 'react';
import { App as AntApp, Card, Col, Empty, Progress, Row, Select, Statistic, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import * as api from '../../api';
import { useBusinessStore } from '../../stores';
import type { Item } from '../../types';

const { Text, Title } = Typography;

export default function StatsPage() {
  const { message } = AntApp.useApp();
  const { stats, fetchStats, fetchItems, version } = useBusinessStore();

  useEffect(() => {
    void fetchStats();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);

  if (!stats) {
    return (
      <div style={{ padding: 16 }}>
        <Card size="small" loading style={{ minHeight: 200 }} />
      </div>
    );
  }

  const rejudge = async (item: Item, keep_status: string) => {
    try {
      await api.patchItem(item.id, { keep_status: keep_status as never });
      await Promise.all([fetchStats(), fetchItems()]);
      message.success('复查完成——"现在的我"的答案最重要');
    } catch (e) {
      message.error(`改判失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const expiredColumns: ColumnsType<Item> = [
    { title: '物品', dataIndex: 'name', key: 'name' },
    { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 70 },
    {
      title: '观察期至',
      dataIndex: 'quarantine_until',
      key: 'quarantine_until',
      width: 120,
      render: (v: string) => <Tag color="red">{v}</Tag>,
    },
    {
      title: '重新判定',
      key: 'action',
      width: 160,
      render: (_, record) => (
        <Select
          size="small"
          placeholder="只问：现在还想用吗"
          style={{ width: 150 }}
          onChange={(v) => void rejudge(record, v)}
          options={[
            { value: 'keep', label: '想念 → 保留' },
            { value: 'donate', label: '仍犹豫 → 捐赠' },
            { value: 'discard', label: '不需要 → 丢弃' },
          ]}
        />
      ),
    },
  ];

  const avg = stats.avg_danshari_score ?? 0;

  return (
    <div style={{ padding: 16, maxWidth: 860, margin: '0 auto' }}>
      <Title level={5}>断舍离成果</Title>
      <Text type="secondary">
        物品是流动的，"出"之后才有空间呼吸。每完成一步，都是离开执念的一步。
      </Text>
      <Row gutter={12} style={{ marginTop: 16 }}>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="累计丢弃（件）" value={stats.discard_count} styles={{ content: { color: '#cf1322' } }} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="累计捐赠（件）" value={stats.donate_count} styles={{ content: { color: '#d46b08' } }} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small">
            <Statistic title="已完成任务" value={stats.done_tasks} styles={{ content: { color: '#389e0d' } }} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card size="small" style={{ textAlign: 'center' }}>
            <Progress
              type="circle"
              size={64}
              percent={avg}
              strokeColor={avg <= 40 ? '#cf1322' : avg <= 70 ? '#d46b08' : '#52c41a'}
              format={() => <span style={{ fontSize: 16 }}>{avg || '—'}</span>}
            />
            <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>断舍离均分</div>
          </Card>
        </Col>
      </Row>

      <Card size="small" title="观察期到期复查（心的保质期）" style={{ marginTop: 16 }}>
        {stats.expired_quarantine.length ? (
          <>
            <Text type="secondary">
              以下物品 90 天观察期已到。只问自己："现在的我还想用吗？"仍犹豫 → 建议捐赠（先扔再发愁）。
            </Text>
            <Table<Item>
              rowKey="id"
              size="small"
              style={{ marginTop: 12 }}
              columns={expiredColumns}
              dataSource={stats.expired_quarantine}
              pagination={false}
            />
          </>
        ) : (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无到期物品，观察中的物品请留意物品库倒计时" />
        )}
      </Card>
    </div>
  );
}
