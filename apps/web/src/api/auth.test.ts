import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { API_KEY_STORAGE_KEY, authHeaders, getApiKey } from './auth';

describe('authHeaders', () => {
  beforeEach(() => {
    window.sessionStorage.clear();
    vi.unstubAllGlobals();
    vi.stubEnv('VITE_API_KEY', '');
  });

  afterEach(() => {
    window.sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it('returns no headers when no key is configured (default anonymous mode)', () => {
    expect(authHeaders()).toEqual({});
    expect(getApiKey()).toBe('');
  });

  it('picks up a runtime key from sessionStorage', () => {
    window.sessionStorage.setItem(API_KEY_STORAGE_KEY, 'runtime-key-123');

    expect(authHeaders()).toEqual({ 'X-API-Key': 'runtime-key-123' });
  });

  it('falls back to the build-time VITE_API_KEY', () => {
    vi.stubEnv('VITE_API_KEY', 'build-time-key');

    expect(getApiKey()).toBe('build-time-key');
    expect(authHeaders()).toEqual({ 'X-API-Key': 'build-time-key' });
  });

  it('prefers the runtime key over the build-time key', () => {
    vi.stubEnv('VITE_API_KEY', 'build-time-key');
    window.sessionStorage.setItem(API_KEY_STORAGE_KEY, 'runtime-key-123');

    expect(getApiKey()).toBe('runtime-key-123');
  });
});
