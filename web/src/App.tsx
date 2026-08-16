/** 布局：桌面 Sider(会话列表) + Tabs；移动端 Drawer + 底部 Tabs。 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { App as AntApp, Button, Drawer, Grid, Layout, Popover, Space, Tabs, Typography } from 'antd';
import {
  DeleteOutlined,
  MessageOutlined,
  PlusOutlined,
  QrcodeOutlined,
  MenuOutlined,
  BarChartOutlined,
  ContainerOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { Conversations } from '@ant-design/x';
import * as api from './api';
import ChatPage from './pages/ChatPage';
import TasksPage from './pages/TasksPage';
import ItemsPage from './pages/ItemsPage';
import StatsPage from './pages/StatsPage';
import { useBusinessStore, useConversationStore } from './stores';

const { Sider, Header, Content } = Layout;
const { useBreakpoint } = Grid;

function QrEntry() {
  const [url, setUrl] = useState<string | null>(null);
  return (
    <Popover
      title="iPhone 扫码直达"
      trigger="click"
      onOpenChange={async (open) => {
        if (open && !url) {
          try {
            setUrl(await api.fetchQrcode());
          } catch {
            /* ignore */
          }
        }
      }}
      content={
        url ? (
          <img src={url} width={180} height={180} alt="局域网访问二维码" />
        ) : (
          <Typography.Text type="secondary">生成中…</Typography.Text>
        )
      }
    >
      <Button icon={<QrcodeOutlined />} block>
        iPhone 扫码访问
      </Button>
    </Popover>
  );
}

function ConversationList() {
  const { message, modal } = AntApp.useApp();
  const { list, activeId, create, remove, setActive } = useConversationStore();
  const items = useMemo(() => list.map((c) => ({ key: String(c.id), label: c.title })), [list]);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', padding: 12, gap: 12 }}>
      <Button
        type="primary"
        icon={<PlusOutlined />}
        onClick={() => {
          void create('新整理对话').catch((e) => message.error(`新建失败：${e.message}`));
        }}
      >
        新建对话
      </Button>
      <div style={{ flex: 1, minHeight: 0, overflow: 'auto' }}>
        <Conversations
          items={items}
          activeKey={activeId != null ? String(activeId) : undefined}
          onActiveChange={(key) => setActive(Number(key))}
          menu={(item) => ({
            items: [
              {
                key: 'delete',
                label: '删除对话',
                icon: <DeleteOutlined />,
                danger: true,
                onClick: () => {
                  modal.confirm({
                    title: '删除这个对话？',
                    content: '对话消息将被删除，物品与计划不受影响。',
                    okText: '删除',
                    okButtonProps: { danger: true },
                    onOk: () =>
                      remove(Number(item.key)).catch((e) => message.error(`删除失败：${e.message}`)),
                  });
                },
              },
            ],
          })}
        />
      </div>
      <QrEntry />
    </div>
  );
}

export default function App() {
  const { fetchList, create, list } = useConversationStore();
  const fetchAll = useBusinessStore((s) => s.fetchAll);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [tab, setTab] = useState('chat');
  const didInit = useRef(false);
  const screens = useBreakpoint();
  const isMobile = !screens.md;

  useEffect(() => {
    if (didInit.current) return;
    didInit.current = true;
    void (async () => {
      await fetchList();
      const { list: l } = useConversationStore.getState();
      if (!l.length) {
        await create('新整理对话').catch(() => undefined);
      }
    })();
    void fetchAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const tabs = [
    { key: 'chat', label: '对话', icon: <MessageOutlined />, children: <ChatPage onGoTasks={() => setTab('tasks')} /> },
    { key: 'tasks', label: '任务看板', icon: <UnorderedListOutlined />, children: <TasksPage /> },
    { key: 'items', label: '物品库', icon: <ContainerOutlined />, children: <ItemsPage /> },
    { key: 'stats', label: '成果统计', icon: <BarChartOutlined />, children: <StatsPage /> },
  ];

  return (
    <Layout style={{ height: '100vh' }}>
      {isMobile ? (
        <>
          <Header
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              background: '#fff',
              padding: '0 12px',
              height: 48,
              lineHeight: '48px',
            }}
          >
            <Button type="text" icon={<MenuOutlined />} onClick={() => setDrawerOpen(true)} />
            <Typography.Text strong>断舍离整理助手</Typography.Text>
          </Header>
          <Drawer
            placement="left"
            width={280}
            open={drawerOpen}
            onClose={() => setDrawerOpen(false)}
            title={
              <Space>
                <Typography.Text strong>对话</Typography.Text>
                <Typography.Text type="secondary" style={{ fontWeight: 400, fontSize: 12 }}>
                  当前 {list.length} 个
                </Typography.Text>
              </Space>
            }
            styles={{ body: { padding: 0 } }}
          >
            <ConversationList />
          </Drawer>
        </>
      ) : (
        <Sider width={260} theme="light" style={{ borderRight: '1px solid #f0f0f0' }}>
          <ConversationList />
        </Sider>
      )}
      <Layout>
        <Content style={{ display: 'flex', flexDirection: 'column', minHeight: 0, background: '#fff' }}>
          <Tabs
            activeKey={tab}
            onChange={setTab}
            items={tabs}
            tabBarStyle={{ margin: 0, padding: '0 16px' }}
            style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
            tabPosition={isMobile ? 'bottom' : 'top'}
            destroyOnHidden={false}
          />
        </Content>
      </Layout>
    </Layout>
  );
}
