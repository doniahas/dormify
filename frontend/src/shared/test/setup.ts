import '@testing-library/jest-dom/vitest';

// globals is disabled in vitest.config.mjs, so the lifecycle hook and the
// Testing Library cleanup are imported explicitly rather than assumed.
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';

// Unmount first: teardown effects may still write to storage or the
// document, and those writes must be cleared too.
afterEach(() => {
  cleanup();

  localStorage.clear();
  sessionStorage.clear();

  document.documentElement.lang = '';
  document.documentElement.dir = '';
  document.body.dir = '';
  document.body.removeAttribute('style');

  window.history.replaceState(null, '', '/');
});
