import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  envDir: fileURLToPath(new URL('../', import.meta.url)),
  plugins: [react()],
  server: {
    port: 3001,
    strictPort: true,
    watch: {
      usePolling: process.env.CHOKIDAR_USEPOLLING === 'true',
    },
  },
  build: {
    outDir: 'build',
    sourcemap: true,
  },
});
