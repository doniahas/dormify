/// <reference types="vite/client" />

// Environment variables the application reads through import.meta.env.
// VITE_API_URL is the single public API setting (see shared/api/client.ts
// and the repository-root .env.example); every other variable is unknown
// to the frontend and intentionally left untyped.
interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
