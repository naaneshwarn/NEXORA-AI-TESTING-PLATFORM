/**
 * Client-side mirror of the backend redaction rules (`backend/app/core/redaction.py`).
 *
 * The backend already redacts tool parameters before they are stored and
 * streamed, but the viewer applies the same rules defensively so sensitive
 * values are never rendered even if an event arrives unredacted.
 */
export const REDACTED = '[REDACTED]';

const SENSITIVE_KEYS = new Set(
  [
    'password',
    'passwd',
    'pwd',
    'token',
    'access_token',
    'refresh_token',
    'id_token',
    'auth_token',
    'api_key',
    'apikey',
    'api_secret',
    'secret',
    'secret_key',
    'client_secret',
    'authorization',
    'auth',
    'credit_card',
    'card_number',
    'cvv',
    'cvc',
    'ssn',
    'private_key',
    'session_id',
    'cookie',
    'set_cookie'
  ].map((key) => key.replace(/[^a-z0-9]/gi, '').toLowerCase())
);

const BEARER_PATTERN = /\b(bearer)\s+[A-Za-z0-9\-._~+/]+=*/gi;
const BASIC_PATTERN = /\b(basic)\s+[A-Za-z0-9+/=]{4,}/gi;
const ASSIGNMENT_PATTERN =
  /\b(password|passwd|pwd|token|access[_-]?token|refresh[_-]?token|api[_-]?key|apikey|secret|client[_-]?secret|authorization|credit[_-]?card|card[_-]?number|cvv|cvc|ssn)\b(\s*[=:]\s*)(?!\[REDACTED\])(?!bearer\b)(?!basic\b)([^\s,;&"']+)/gi;
const OPENAI_KEY_PATTERN = /\bsk-[A-Za-z0-9]{16,}\b/g;
const AWS_KEY_PATTERN = /\b(?:AKIA|ASIA)[0-9A-Z]{16}\b/g;
const JWT_PATTERN = /\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b/g;

export function isSensitiveKey(key: string): boolean {
  return SENSITIVE_KEYS.has(key.replace(/[^a-z0-9]/gi, '').toLowerCase());
}

function scrubString(value: string): string {
  return value
    .replace(BEARER_PATTERN, '$1 [REDACTED]')
    .replace(BASIC_PATTERN, '$1 [REDACTED]')
    .replace(ASSIGNMENT_PATTERN, '$1$2[REDACTED]')
    .replace(OPENAI_KEY_PATTERN, REDACTED)
    .replace(AWS_KEY_PATTERN, REDACTED)
    .replace(JWT_PATTERN, REDACTED);
}

export function redactSensitiveData(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(redactSensitiveData);
  }
  if (value !== null && typeof value === 'object') {
    const result: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      result[key] = isSensitiveKey(key) ? REDACTED : redactSensitiveData(item);
    }
    return result;
  }
  if (typeof value === 'string') {
    return scrubString(value);
  }
  return value;
}
