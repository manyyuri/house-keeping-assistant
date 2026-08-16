/** 物品库：状态/关键词筛选 + 行内改判 + 犹豫倒计时 + 捐赠清单导出。 */

import { useEffect, useMemo, useState } from 'react';
import { App as AntApp, Button, Card, Col, Input, Row, Select, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ExportOutlined } from '@ant-design/icons';
import * as api from '../../api';
import { useBusinessStore } from '../../stores';
import type { Item, KeepStatus } from '../../types';

const { Text } = Typography;

export const KEEP_STATUS_META: Record<string, { label: string; color: string }> = {
  keep: { label: '保留', color: 'green' },
  donate: { label: '捐赠', color: 'orange' },
  discard: { label: '丢弃', color: 'red' },
  hesitate: { label: '犹豫', color: 'purple' },
  unjudged: { label: '未判定', color: 'default' },
};

function daysLeft(until?: string | null): number | null {
  if (!until) return null;
  const diff = new Date(`${until}T00:00:00`).getTime() - new Date(new Date().toDateString()).getTime();
  return Math.ceil(diff / 86400000);
}

export default function ItemsPage() {
  const { message } = AntApp.useApp();
  const { items, itemsFilter, setItemsFilter, fetchItems, version } = useBusinessStore();
  const [selectedKeys, setSelectedKeys] = useState<React.Key[]>([]);
  const [search, setSearch] = useState('');

  useEffect(() => {
    void fetchItems();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);

  const rejudge = async (item: Item, keep_status: KeepStatus) => {
    try {
      await api.patchItem(item.id, { keep_status });
      await fetchItems();
      if (keep_status === 'hesitate') {
        message.info('已进入 90 天观察期（心的保质期）');
      }
    } catch (e) {
      message.error(`改判失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const selectedItems = useMemo(
    () => items.filter((it) => selectedKeys.includes(it.id)),
    [items, selectedKeys],
  );
  const donateCandidates = selectedItems.filter((it) => it.keep_status === 'donate');

  const exportDonateList = () => {
    const list = donateCandidates.length ? donateCandidates : items.filter((it) => it.keep_status === 'donate');
    if (!list.length) {
      message.warning('暂无捐赠物品——先在对话中评估，或行内改判为"捐赠"');
      return;
    }
    const lines = [
      '断舍离 · 捐赠清单',
      `生成时间：${new Date().toLocaleString('zh-CN')}`,
      `共 ${list.length} 件：`,
      '',
      ...list.map((it, i) => {
        const reason = it.reason ? `理由：${it.reason}` : '理由：未填写';
        const due = it.quarantine_until ? `（观察期至 ${it.quarantine_until}）` : '';
        return `${i + 1}. ${it.name} ×${it.quantity}${due}\n   ${reason}`;
      }),
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `捐赠清单-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    message.success(`已导出 ${list.length} 件捐赠物品清单`);
  };

  const columns: ColumnsType<Item> = [
    { title: '物品', dataIndex: 'name', key: 'name', ellipsis: true },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      width: 90,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    { title: '数量', dataIndex: 'quantity', key: 'quantity', width: 70 },
    {
      title: '判定',
      dataIndex: 'keep_status',
      key: 'keep_status',
      width: 110,
      render: (status: string, record) => (
        <Select
          size="small"
          value={status}
          onChange={(v) => void rejudge(record, v as KeepStatus)}
          style={{ width: 96 }}
          options={Object.entries(KEEP_STATUS_META).map(([value, m]) => ({ value, label: m.label }))}
        />
      ),
    },
    {
      title: '评估理由',
      dataIndex: 'reason',
      key: 'reason',
      ellipsis: true,
      render: (v: string | null) => (v ? <Text type="secondary">{v}</Text> : '-'),
    },
    {
      title: '观察期',
      dataIndex: 'quarantine_until',
      key: 'quarantine_until',
      width: 130,
      render: (until: string | null) => {
        if (!until) return '-';
        const d = daysLeft(until);
        if (d === null) return '-';
        if (d <= 0) return <Tag color="red">已到期，请复查</Tag>;
        return <Tag color="purple">剩 {d} 天</Tag>;
      },
    },
  ];

  return (
    <div style={{ padding: 16 }}>
      <Card size="small">
        <Row gutter={12} style={{ marginBottom: 12 }}>
          <Col>
            <Select
              allowClear
              placeholder="判定状态"
              style={{ width: 110 }}
              value={itemsFilter.keep_status || undefined}
              onChange={(v) => setItemsFilter({ ...itemsFilter, keep_status: v })}
              options={Object.entries(KEEP_STATUS_META).map(([value, m]) => ({ value, label: m.label }))}
            />
          </Col>
          <Col flex="auto" style={{ maxWidth: 280 }}>
            <Input.Search
              placeholder="按名称搜索，如：牛仔裤"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onSearch={(v) => setItemsFilter({ ...itemsFilter, keyword: v || undefined })}
              allowClear
            />
          </Col>
          <Col flex="auto" style={{ textAlign: 'right' }}>
            <Button icon={<ExportOutlined />} onClick={exportDonateList}>
              导出捐赠清单
            </Button>
          </Col>
        </Row>
        <Table<Item>
          rowKey="id"
          size="middle"
          columns={columns}
          dataSource={items}
          rowSelection={{
            selectedRowKeys: selectedKeys,
            onChange: setSelectedKeys,
          }}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
        />
      </Card>
    </div>
  );
}
