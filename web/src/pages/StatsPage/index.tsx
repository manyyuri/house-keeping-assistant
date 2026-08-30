/** 成果统计：加分制的努力轨迹 + 家的账与身体的账共用一条时间轴（CONCEPT §6.3 / §10 M2）。
 *  反打卡：不渲染连击/绿点；评分的对外表达从「扣分制」翻成「加分制」——
 *  用户看到的不是"房间只有 40 分"，而是"这周你完成了 N 件最小的事，比上周多 X 件"。 */

import { useEffect, useState } from 'react';
import { App as AntApp, Card, Col, Empty, Progress, Row, Select, Statistic, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import * as api from '../../api';
import { useBusinessStore } from '../../stores';
import type { Item, TimelineEvent, TimelinePayload } from '../../types';

const { Text, Title } = Typography;

function fmtTs(ts: string): string {
  const d = new Date(ts.replace(' ', 'T'));
  if (Number.isNaN(d.getTime())) return ts;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getMonth() + 1}/${d.getDate()} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

const KIND_META: Record<string, { label: string; color: string }> = {
  home: { label: '家的账', color: 'green' },
  body: { label: '身体的账', color: 'gold' },
};

const ICON_CHAR: Record<string, string> = {
  task: '✔',
  meal: '食',
  plan: '册',
};

export default function StatsPage() {
  const { message } = AntApp.useApp();
  const { stats, fetchStats, fetchItems, version } = useBusinessStore();
  const [timeline, setTimeline] = useState<TimelinePayload | null>(null);

  useEffect(() => {
    void fetchStats();
    void api.getTimeline().then(setTimeline).catch(() => setTimeline(null));
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
      message.success('看完了，定了就好——"现在的我"的答案最重要');
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
      title: '重新看看',
      key: 'action',
      width: 160,
      render: (_, record) => (
        <Select
          size="small"
          placeholder="只问：现在还想用吗"
          style={{ width: 150 }}
          onChange={(v) => void rejudge(record, v)}
          options={[
            { value: 'keep', label: '想用 → 保留' },
            { value: 'donate', label: '仍拿不准 → 捐赠' },
            { value: 'discard', label: '不需要 → 丢弃' },
          ]}
        />
      ),
    },
  ];

  const avg = stats.avg_danshari_score ?? 0;
  const tr = timeline?.trajectory;

  return (
    <div style={{ padding: 16, maxWidth: 860, margin: '0 auto' }}>
      <Title level={5}>断舍离成果</Title>
      <Text type="secondary">
        物品是流动的，"出"之后才有空间呼吸。每完成一步，都是离开执念的一步。
      </Text>

      {/* 加分制：努力轨迹是这一页的主角，不是分数 */}
      {tr && (
        <Card size="small" style={{ marginTop: 16, background: 'linear-gradient(135deg, #fffdf8 0%, #f6f3ea 100%)' }}>
          <Row align="middle" gutter={12}>
            <Col flex="none" style={{ textAlign: 'center', paddingRight: 8 }}>
              <div style={{ fontFamily: 'var(--serif)', fontSize: 40, lineHeight: 1, color: 'var(--pine)', fontWeight: 700 }}>
                {tr.this_week}
              </div>
              <div style={{ fontSize: 12, color: 'rgba(38,51,44,0.55)', marginTop: 4 }}>件最小的事</div>
            </Col>
            <Col flex="auto">
              <div style={{ fontFamily: 'var(--serif)', fontSize: 16, fontWeight: 600, color: 'var(--ink)' }}>
                这周，你完成了 {tr.this_week} 件最小的事
              </div>
              <Text type="secondary" style={{ fontSize: 12.5 }}>
                {tr.delta > 0 ? `比上周多 ${tr.delta} 件，慢慢在动。` : tr.delta < 0 ? `比上周少 ${-tr.delta} 件，没关系，这周还没过完。` : '和上周一样稳。'}
              </Text>
            </Col>
          </Row>
        </Card>
      )}

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
            <div style={{ fontSize: 12, color: '#888', marginTop: 4 }}>代谢率参考（内部口径）</div>
          </Card>
        </Col>
      </Row>

      {/* 时间轴账本：家的账 + 身体的账一条轴 */}
      <Card size="small" title="时间轴账本" style={{ marginTop: 16 }}>
        {timeline && timeline.events.length ? (
          <div style={{ maxHeight: 340, overflow: 'auto' }}>
            {timeline.events.map((e: TimelineEvent, i: number) => (
              <div key={`${e.ts}-${i}`} style={{ display: 'flex', alignItems: 'flex-start', gap: 10, padding: '7px 0' }}>
                <span
                  style={{
                    flex: 'none',
                    width: 24,
                    height: 24,
                    borderRadius: 6,
                    display: 'grid',
                    placeItems: 'center',
                    fontSize: 12,
                    color: '#fff',
                    background: e.kind === 'body' ? 'var(--grain)' : 'var(--pine)',
                  }}
                >
                  {ICON_CHAR[e.icon] ?? '·'}
                </span>
                <span style={{ flex: 1, minWidth: 0, fontSize: 13.5 }}>
                  <span
                    style={{
                      marginRight: 6,
                      fontSize: 11,
                      color: e.kind === 'body' ? 'var(--grain)' : 'var(--pine)',
                      fontWeight: 600,
                    }}
                  >
                    {KIND_META[e.kind]?.label}
                  </span>
                  {e.text}
                </span>
                <span style={{ flex: 'none', fontSize: 11.5, color: 'rgba(38,51,44,0.45)' }}>{fmtTs(e.ts)}</span>
              </div>
            ))}
          </div>
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="账本还空着——完成一件任务或吃上一餐，就会记在这里。"
          />
        )}
      </Card>

      <Card size="small" title="没急着决定的，到期了" style={{ marginTop: 16 }}>
        {stats.expired_quarantine.length ? (
          <>
            <Text type="secondary">
              以下物品 90 天前你没急着决定。现在只问一句："现在的我还想用吗？"仍拿不准 → 建议捐赠（先出去，再慢慢想）。
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
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有到期的东西；观察中的，就让它继续慢慢想" />
        )}
      </Card>
    </div>
  );
}
