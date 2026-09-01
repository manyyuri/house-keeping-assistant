/** 任务看板：状态筛选 + 类型筛选 + 行内状态流转 + 步骤展开。 */

import { useEffect } from 'react';
import { App as AntApp, Card, Col, Row, Segmented, Select, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import * as api from '../../api';
import { useBusinessStore } from '../../stores';
import type { Task } from '../../types';

const { Text } = Typography;

export const TASK_TYPE_META: Record<string, { label: string; color: string }> = {
  clean: { label: '清洁', color: 'blue' },
  organize: { label: '整理', color: 'green' },
  store: { label: '收纳', color: 'purple' },
  discard: { label: '舍弃', color: 'red' },
};

export const TASK_STATUS_LABEL: Record<string, string> = {
  todo: '待开始',
  doing: '进行中',
  done: '已完成',
  skipped: '已跳过',
};

export default function TasksPage() {
  const { message } = AntApp.useApp();
  const { tasks, tasksFilter, setTasksFilter, fetchTasks, version } = useBusinessStore();

  useEffect(() => {
    void fetchTasks();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version]);

  const changeStatus = async (task: Task, status: string) => {
    try {
      await api.patchTask(task.id, status);
      await fetchTasks();
      if (status === 'done') {
        message.success('已完成的不仅是一件事，是离开执念的一步 ✨');
      }
    } catch (e) {
      message.error(`更新失败：${e instanceof Error ? e.message : e}`);
    }
  };

  const columns: ColumnsType<Task> = [
    { title: '标题', dataIndex: 'title', key: 'title', ellipsis: true },
    {
      title: '类型',
      dataIndex: 'type',
      key: 'type',
      width: 90,
      render: (t: string) => {
        const meta = TASK_TYPE_META[t];
        return meta ? <Tag color={meta.color}>{meta.label}</Tag> : <Tag>{t}</Tag>;
      },
    },
    { title: '计划来源', dataIndex: 'plan_room', key: 'plan_room', width: 100, render: (v) => v ?? '-' },
    {
      title: '预计耗时',
      dataIndex: 'est_minutes',
      key: 'est_minutes',
      width: 90,
      render: (v: number | null) => (v ? `约 ${v} 分钟` : '-'),
    },
    { title: '建议日期', dataIndex: 'due_date', key: 'due_date', width: 100, render: (v) => v ?? '-' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      width: 110,
      render: (status: string, record) => (
        <Select
          size="small"
          value={status}
          onChange={(v) => void changeStatus(record, v)}
          style={{ width: 96 }}
          options={Object.entries(TASK_STATUS_LABEL).map(([value, label]) => ({ value, label }))}
        />
      ),
    },
  ];

  return (
    <div style={{ padding: 16 }}>
      <Card size="small">
        <Row gutter={12} style={{ marginBottom: 12 }}>
          <Col>
            <Segmented
              value={tasksFilter.status ?? 'all'}
              onChange={(v) => setTasksFilter({ ...tasksFilter, status: v === 'all' ? undefined : String(v) })}
              options={[
                { value: 'all', label: '全部' },
                { value: 'todo', label: '待开始' },
                { value: 'doing', label: '进行中' },
                { value: 'done', label: '已完成' },
              ]}
            />
          </Col>
          <Col>
            <Select
              allowClear
              placeholder="按类型筛选"
              style={{ width: 120 }}
              value={tasksFilter.type || undefined}
              onChange={(v) => setTasksFilter({ ...tasksFilter, type: v })}
              options={Object.entries(TASK_TYPE_META).map(([value, m]) => ({ value, label: m.label }))}
            />
          </Col>
        </Row>
        <Table<Task>
          rowKey="id"
          size="middle"
          columns={columns}
          dataSource={tasks}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          expandable={{
            expandedRowRender: (record) =>
              record.steps?.length ? (
                <ol style={{ margin: 0, paddingLeft: 20 }}>
                  {record.steps.map((s, i) => (
                    <li key={i}>
                      <Text>{s}</Text>
                    </li>
                  ))}
                </ol>
              ) : (
                <Text type="secondary">无步骤说明</Text>
              ),
          }}
        />
      </Card>
    </div>
  );
}
