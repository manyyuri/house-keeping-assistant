import React from 'react';
import ReactDOM from 'react-dom/client';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';
import './index.css';

// 单个根 ConfigProvider（不做 i18n，locale 仅为antd 内置组件文案中文化）
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{ token: { colorPrimary: '#7FB77E', borderRadius: 10 } }}
    >
      <App />
    </ConfigProvider>
  </React.StrictMode>,
);
