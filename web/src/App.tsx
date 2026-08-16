import { Layout, Typography } from 'antd';

const { Content } = Layout;

export default function App() {
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Content style={{ padding: 24 }}>
        <Typography.Title level={3}>断舍离整理助手</Typography.Title>
        <Typography.Text type="secondary">骨架搭建中——前后端联通检查页</Typography.Text>
      </Content>
    </Layout>
  );
}
