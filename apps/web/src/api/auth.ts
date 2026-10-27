/**
 * Authentication headers for NEXORA API requests.
 *
 * The backend accepts API keys via the `X-API-Key` header (or
 * `Authorization: Bearer`). A key can be provided:
 *
 * - at build time through the `VITE_API_KEY` environment variable, or
 * - at runtime through `sessionStorage` (`nexora_api_key`), which lets an
 *   operator enable auth on a deployed dashboard without rebuilding it.
 *
 * With no key configured every request is anonymous — the backend's default
 * `off` mode — so local development needs no setup.
 *
 * SSE caveat: the browser's `EventSource` cannot send custom headers, so the
 * live trace stream relies on the backend's read-open/write-protected mode
 * (the effective mode whenever keys are configured with `NEXORA_AUTH_MODE=auto`).
 * A token is never placed in a URL.
 */

/** `sessionStorage` key holding a runtime-provided API key. */
export const API_KEY_STORAGE_KEY = 'nexora_api_key';

/** Resolve the API key from runtime storage, falling back to build-time env. */
export function getApiKey(): string {
  try {
    if (typeof window !== 'undefined' && window.sessionStorage) {
      const runtime = window.sessionStorage.getItem(API_KEY_STORAGE_KEY);
      if (runtime) return runtime;
    }
  } catch {
    // Storage can be unavailable (private mode / SSR) — fall through to env.
  }
  const fromEnv = import.meta.env.VITE_API_KEY;
  return typeof fromEnv === 'string' && fromEnv.length > 0 ? fromEnv : '';
}

/** Header bag to spread into every authenticated `fetch` call. */
export function authHeaders(): Record<string, string> {
  const key = getApiKey();
  return key ? { 'X-API-Key': key } : {};
}
