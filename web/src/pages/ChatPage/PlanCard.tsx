/** Bubble 内嵌计划卡片：断舍离评分环 + 三列统计 + 任务跳转。 */

import { useEffect, useState } from 'react';
import { Button, Card, Col, Progress, Row, Statistic, Typography } from 'antd';
import { RightOutlined } from '@ant-design/icons';
import * as api from '../../api';
import type { PlanCreatedPayload, Plan } from '../../types';

const { Text } = Typography;

function scoreColor(score: number): string {
  if (score <= 40) return '#cf1322';
  if (score <= 70) return '#d46b08';
  return '#52c41a';
}

function scoreText(score: number): string {
  if (score <= 40) return '急需断舍离';
  if (score <= 70) return '有待整顿';
  return '状态良好';
}

export default function PlanCard({ plan: payload, onGoTasks }: { plan: PlanCreatedPayload; onGoTasks: () => void }) {
  const [detail, setDetail] = useState<Plan | null>(null);

  useEffect(() => {
    let alive = true;
    api
      .getPlan(payload.planId)
      .then((d) => alive && setDetail(d))
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [payload.planId]);

  const score = detail?.danshari_score ?? payload.danshariScore;

  return (
    <Card
      size="small"
      style={{ maxWidth: 380, marginBottom: 8 }}
      title={`整理计划 · ${detail?.room ?? ''}`}
      styles={{ header: { minHeight: 36 } }}
    >
      <Row gutter={12} align="middle">
        <Col style={{ textAlign: 'center' }}>
          <Progress
            type="circle"
            size={72}
            percent={score}
            strokeColor={scoreColor(score)}
            format={() => (
              <span style={{ fontSize: 18, fontWeight: 600, color: scoreColor(score) }}>{score}</span>
            )}
          />
          <div style={{ fontSize: 12, marginTop: 2, color: scoreColor(score) }}>{scoreText(score)}</div>
        </Col>
        <Col flex="auto">
          <Row gutter={8}>
            <Col span={8}>
              <Statistic title="丢弃" value={detail?.discard_count ?? 0} valueStyle={{ color: '#cf1322', fontSize: 18 }} />
            </Col>
            <Col span={8}>
              <Statistic title="捐赠" value={detail?.donate_count ?? 0} valueStyle={{ color: '#d46b08', fontSize: 18 }} />
            </Col>
            <Col span={8}>
              <Statistic title="保留" value={detail?.keep_count ?? 0} valueStyle={{ color: '#389e0d', fontSize: 18 }} />
            </Col>
          </Row>
        </Col>
      </Row>
      {detail?.summary && (
        <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 6 }}>
          {detail.summary}
        </Text>
      )}
      <Button size="small" type="link" onClick={onGoTasks} style={{ padding: 0, marginTop: 6 }}>
        查看 {detail?.tasks?.length ?? payload.taskCount} 个整理任务 <RightOutlined />
      </Button>
    </Card>
  );
}
