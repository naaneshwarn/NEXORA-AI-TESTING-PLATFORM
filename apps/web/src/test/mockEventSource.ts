type Listener = (event: Event) => void;

/**
 * Minimal `EventSource` stand-in for tests.
 *
 * jsdom does not implement Server-Sent Events, so the hook/viewer tests install
 * this mock globally and drive it explicitly.
 */
export class MockEventSource {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSED = 2;

  static instances: MockEventSource[] = [];

  static reset(): void {
    MockEventSource.instances = [];
  }

  static get last(): MockEventSource {
    const instance = MockEventSource.instances.at(-1);
    if (!instance) {
      throw new Error('No MockEventSource instance has been created yet.');
    }
    return instance;
  }

  readonly url: string;
  readyState = MockEventSource.CONNECTING;
  closed = false;
  onopen: Listener | null = null;
  onerror: Listener | null = null;
  onmessage: Listener | null = null;

  private readonly listeners = new Map<string, Set<Listener>>();

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: Listener): void {
    const set = this.listeners.get(type) ?? new Set<Listener>();
    set.add(listener);
    this.listeners.set(type, set);
  }

  removeEventListener(type: string, listener: Listener): void {
    this.listeners.get(type)?.delete(listener);
  }

  close(): void {
    this.closed = true;
    this.readyState = MockEventSource.CLOSED;
  }

  /** Simulate a successful connection (`open`). */
  emitOpen(): void {
    this.readyState = MockEventSource.OPEN;
    this.onopen?.(new Event('open'));
  }

  /** Emit a named SSE event; object payloads are JSON-encoded. */
  emit(type: string, data: unknown, lastEventId = ''): void {
    this.emitRaw(type, typeof data === 'string' ? data : JSON.stringify(data), lastEventId);
  }

  /** Emit a named SSE event with a raw string payload. */
  emitRaw(type: string, data: string, lastEventId = ''): void {
    this.dispatch(type, new MessageEvent(type, { data, lastEventId }));
  }

  /** Simulate a transient drop; a real browser would retry automatically. */
  failTransiently(): void {
    this.readyState = MockEventSource.CONNECTING;
    this.onerror?.(new Event('error'));
  }

  /** Simulate a fatal failure such as an HTTP 404/403 response. */
  failFatally(): void {
    this.readyState = MockEventSource.CLOSED;
    this.onerror?.(new Event('error'));
  }

  private dispatch(type: string, event: Event): void {
    this.listeners.get(type)?.forEach((listener) => listener(event));
  }
}
