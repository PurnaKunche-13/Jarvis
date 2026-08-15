import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const backend = process.env.JARVIS_BACKEND ?? 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': { target: backend, changeOrigin: true },
      '/ws': { target: backend, ws: true },
    },
  },
  build: { target: 'es2022' },
});
