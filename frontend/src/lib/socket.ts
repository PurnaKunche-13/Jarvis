import type { ClientMessage, ServerMessage } from './protocol';

export type ConnectionState = 'connecting' | 'open' | 'closed';

interface Handlers {
  onMessage: (message: ServerMessage) => void;
  onConnection: (state: ConnectionState) => void;
}

const HEARTBEAT_MS = 20_000;
const MAX_BACKOFF_MS = 8_000;

/** Auto-reconnecting websocket client for the Jarvis backend. */
export class JarvisSocket {
  private socket: WebSocket | null = null;
  private heartbeat = 0;
  private retry = 0;
  private reconnectTimer = 0;
  private closed = false;

  constructor(
    private readonly url: string,
    private readonly handlers: Handlers,
  ) {}

  connect(): void {
    this.closed = false;
    this.handlers.onConnection('connecting');
    const socket = new WebSocket(this.url);
    this.socket = socket;

    socket.onopen = () => {
      this.retry = 0;
      this.handlers.onConnection('open');
      this.heartbeat = window.setInterval(() => this.send({ type: 'ping' }), HEARTBEAT_MS);
    };

    socket.onmessage = (event) => {
      try {
        this.handlers.onMessage(JSON.parse(event.data as string) as ServerMessage);
      } catch {
        // A malformed frame is not worth tearing the connection down for.
      }
    };

    socket.onclose = () => {
      window.clearInterval(this.heartbeat);
      this.handlers.onConnection('closed');
      if (!this.closed) this.scheduleReconnect();
    };

    socket.onerror = () => socket.close();
  }

  send(message: ClientMessage): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify(message));
    return true;
  }

  close(): void {
    this.closed = true;
    window.clearInterval(this.heartbeat);
    window.clearTimeout(this.reconnectTimer);
    this.socket?.close();
    this.socket = null;
  }

  private scheduleReconnect(): void {
    this.retry += 1;
    const delay = Math.min(500 * 2 ** (this.retry - 1), MAX_BACKOFF_MS);
    this.reconnectTimer = window.setTimeout(() => this.connect(), delay);
  }
}

export function backendUrl(): string {
  const override = import.meta.env.VITE_JARVIS_WS as string | undefined;
  if (override) return override;
  const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${protocol}://${window.location.host}/ws`;
}
