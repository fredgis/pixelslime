/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** `'true'` runs the app entirely against the MSW mock; `'false'` hits the real API. */
  readonly VITE_USE_MOCK?: string;
  /** Base URL for the real API when the mock is off. Defaults to same-origin `''`. */
  readonly VITE_API_BASE?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module '*.png' {
  const src: string;
  export default src;
}
declare module '*.webp' {
  const src: string;
  export default src;
}
declare module '*.svg' {
  const src: string;
  export default src;
}
