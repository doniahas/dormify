import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// Deliberately separate from vite.config.mjs. The production config loads
// environment files from the repository root and carries dev-server and
// build settings that tests must not inherit; envDir:false keeps the test
// run free of any dotenv loading.
export default defineConfig({
  root: fileURLToPath(new URL('./', import.meta.url)),
  envDir: false,
  plugins: [react()],
  test: {
    environment: 'jsdom',
    environmentOptions: {
      jsdom: {
        url: 'http://localhost:3001/',
      },
    },
    globals: false,
    setupFiles: ['./src/shared/test/setup.ts'],
    include: ['src/**/*.test.{js,jsx,ts,tsx}'],
    css: false,
    clearMocks: true,
    restoreMocks: true,
    unstubEnvs: true,
    unstubGlobals: true,
  },
});
