/** 盒马买菜清单抽屉：按盒马五分区分组，同名合并、覆盖餐次标签。 */

import { useEffect, useState } from 'react';
import { App as AntApp, Button, Checkbox, Drawer, Empty, Grid, Skeleton, Space, Typography } from 'antd';
import { CheckSquareOutlined } from '@ant-design/icons';
import { useMealStore } from '../../stores';

const { Text } = Typography;

export default function GroceryDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { message } = AntApp.useApp();
  const isMobile = !Grid.useBreakpoint().md;
  const { grocery, loading, toggleGroceryItem, clearBought, fetchGrocery } = useMealStore();
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) void fetchGrocery();
  }, [open, fetchGrocery]);

  const checkAll = async () => {
    if (!grocery) return;
    const pendingIds = grocery.groups
      .flatMap((g) => g.items)
      .filter((it) => !it.checked)
      .flatMap((it) => it.ids);
    if (!pendingIds.length) return;
    setBusy(true);
    try {
      await toggleGroceryItem(pendingIds, true);
    } finally {
      setBusy(false);
    }
  };

  const finish = async () => {
    setBusy(true);
    try {
      const deleted = await clearBought();
      message.success(deleted ? `采购完成，已清空 ${deleted} 项` : '还没有已勾选的食材');
    } catch (e) {
      message.error(e instanceof Error ? e.message : '操作失败');
    } finally {
      setBusy(false);
    }
  };

  return (
    <Drawer
      title={grocery ? `买菜清单 · 未来 ${grocery.days} 天 · ${grocery.total} 项` : '买菜清单'}
      placement={isMobile ? 'bottom' : 'right'}
      height={isMobile ? '72%' : undefined}
      width={isMobile ? undefined : 380}
      open={open}
      onClose={onClose}
      styles={{ body: { padding: '8px 0 88px' } }}
      footer={
        <div className="grocery-footer">
          <Button type="text" icon={<CheckSquareOutlined />} onClick={checkAll} disabled={busy}>
            全部勾选
          </Button>
          <Button type="primary" onClick={finish} disabled={busy || !grocery?.pending}>
            采购完成，清空已勾选
          </Button>
        </div>
      }
    >
      {loading && !grocery ? (
        <div style={{ padding: '0 16px' }}>
          <Skeleton active paragraph={{ rows: 8 }} />
        </div>
      ) : !grocery || grocery.total === 0 ? (
        <Empty description="暂无待购食材，清单会随菜单自动生成" style={{ marginTop: 48 }} />
      ) : (
        grocery.groups.map((g) => (
          <div key={g.category} className="grocery-group">
            <div className="grocery-cat">{g.category}</div>
            {g.items.map((it) => (
              <div key={it.name} className="grocery-row">
                <Checkbox
                  checked={it.checked}
                  disabled={busy}
                  onChange={(e) => void toggleGroceryItem(it.ids, e.target.checked)}
                />
                <div className="grocery-row-body">
                  <Space size={6} wrap>
                    <Text delete={it.checked} style={it.checked ? { color: 'rgba(38,51,44,.45)' } : undefined}>
                      {it.name}
                    </Text>
                    <Text type="secondary" style={{ fontSize: 12 }}>
                      {it.amounts.join(' / ')}
                    </Text>
                  </Space>
                  <div className="grocery-meals">{it.meals.join(' · ')}</div>
                </div>
              </div>
            ))}
          </div>
        ))
      )}
    </Drawer>
  );
}
