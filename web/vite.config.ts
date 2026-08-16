import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// 允许局域网设备（iPhone Safari）访问 dev server，/api 代理到 FastAPI :8000
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
