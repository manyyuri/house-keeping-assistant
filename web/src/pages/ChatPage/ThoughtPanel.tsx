/** ThoughtChain 面板：SSE thought/tool 事件 → 逐节点点亮。 */

import { LoadingOutlined } from '@ant-design/icons';
import { ThoughtChain } from '@ant-design/x';
import type { ThoughtNode } from '../../types';

export default function ThoughtPanel({ nodes }: { nodes: ThoughtNode[] }) {
  if (!nodes.length) return null;
  const items = nodes.map((n) => ({
    key: n.key,
    title: n.title,
    icon: n.status === 'loading' ? <LoadingOutlined spin /> : undefined,
    status:
      n.status === 'loading' ? ('loading' as const) : n.status === 'error' ? ('error' as const) : ('success' as const),
    description: n.description,
  }));
  return (
    <div style={{ maxWidth: 420, marginBottom: 8 }}>
      <ThoughtChain items={items} />
    </div>
  );
}
