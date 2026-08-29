/** 布局：桌面 Sider(会话列表) + Tabs；移动端 Drawer + 底部 Tabs。 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { App as AntApp, Button, Drawer, Grid, Layout, Popover, Space, Tabs, Typography } from 'antd';
import {
  BarChartOutlined,
  CoffeeOutlined,
  ContainerOutlined,
  DeleteOutlined,
  MenuOutlined,
  MessageOutlined,
  PlusOutlined,
  ProjectOutlined,
  QrcodeOutlined,
  SettingOutlined,
  UnorderedListOutlined,
} from '@ant-design/icons';
import { Conversations } from '@ant-design/x';
import * as api from './api';
import ChatPage from './pages/ChatPage';
import MealsPage from './pages/MealsPage';
import TasksPage from './pages/TasksPage';
import ItemsPage from './pages/ItemsPage';
import StatsPage from './pages/StatsPage';
import PlansPage from './pages/PlansPage';
import LLMSettingsModal from './pages/SettingsPage/LLMSettingsModal';
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
      <Button icon={<QrcodeOutlined />} style={{ flex: 1, minWidth: 0 }}>
        iPhone 扫码
      </Button>
    </Popover>
  );
}

function ConversationList({ onOpenSettings }: { onOpenSettings: () => void }) {
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
      <div style={{ display: 'flex', gap: 8 }}>
        <QrEntry />
        <Button icon={<SettingOutlined />} onClick={onOpenSettings}>
          模型设置
        </Button>
      </div>
    </div>
  );
}

export default function App() {
  const { fetchList, create, list } = useConversationStore();
  const fetchAll = useBusinessStore((s) => s.fetchAll);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [tab, setTab] = useState('chat');
  const didInit = useRef(false);
  const screens = useBreakpoint();
  const isMobile = !screens.md;

  useEffect(() => {
    if (didInit.current) return;
    didInit.current = true;
    void (async () => {
      await fetchList();
      const { list: l, activeId: cur } = useConversationStore.getState();
      if (!l.length) {
        await create('新整理对话').catch(() => undefined);
      } else if (cur == null) {
        // 有历史会话但未选中（如手机端未点侧边栏）→ 自动选第一个，避免发送静默失败
        useConversationStore.getState().setActive(l[0].id);
      }
    })();
    void fetchAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const tabs = [
    { key: 'chat', label: '对话', icon: <MessageOutlined />, children: <ChatPage onGoTasks={() => setTab('tasks')} /> },
    { key: 'meals', label: isMobile ? '三餐' : '今日三餐', icon: <CoffeeOutlined />, children: <MealsPage /> },
    { key: 'tasks', label: isMobile ? '任务' : '任务看板', icon: <UnorderedListOutlined />, children: <TasksPage /> },
    { key: 'plans', label: isMobile ? '计划' : '整理计划', icon: <ProjectOutlined />, children: <PlansPage /> },
    { key: 'items', label: isMobile ? '物品' : '物品库', icon: <ContainerOutlined />, children: <ItemsPage /> },
    { key: 'stats', label: isMobile ? '成果' : '成果统计', icon: <BarChartOutlined />, children: <StatsPage /> },
  ];

  return (
    <Layout className="app-shell">
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
              borderBottom: '1px solid var(--mist)',
            }}
          >
            <Button type="text" icon={<MenuOutlined />} onClick={() => setDrawerOpen(true)} aria-label="对话列表" />
            <span className="brand">
              <i className="brand-seal">多</i>
              Dobby 小精灵
            </span>
            <span style={{ flex: 1 }} />
            <Button
              type="text"
              icon={<SettingOutlined />}
              onClick={() => setSettingsOpen(true)}
              aria-label="模型设置"
            />
          </Header>
          <Drawer
            placement="left"
            size="default"
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
            <ConversationList onOpenSettings={() => setSettingsOpen(true)} />
          </Drawer>
        </>
      ) : (
        <Sider width={260} theme="light" style={{ borderRight: '1px solid var(--mist)' }}>
          <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
            <div style={{ padding: '14px 16px 0' }}>
              <span className="brand">
                <i className="brand-seal">多</i>
                Dobby 小精灵
              </span>
            </div>
            <div style={{ flex: 1, minHeight: 0 }}>
              <ConversationList onOpenSettings={() => setSettingsOpen(true)} />
            </div>
          </div>
        </Sider>
      )}
      <Layout style={{ flex: 1, minHeight: 0 }}>
        <Content style={{ display: 'flex', flexDirection: 'column', minHeight: 0, background: 'transparent' }}>
          <Tabs
            activeKey={tab}
            onChange={setTab}
            items={tabs}
            className={isMobile ? 'mobile-tabs' : undefined}
            tabBarStyle={
              isMobile
                ? {
                    margin: 0,
                    padding: '2px 0 calc(4px + env(safe-area-inset-bottom))',
                    background: '#fff',
                    borderTop: '1px solid var(--mist)',
                  }
                : { margin: 0, padding: '0 16px' }
            }
            style={{ flex: 1, minHeight: 0, display: 'flex', flexDirection: 'column' }}
            tabPlacement={isMobile ? 'bottom' : 'top'}
            destroyOnHidden={false}
          />
        </Content>
      </Layout>
      <LLMSettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </Layout>
  );
}
