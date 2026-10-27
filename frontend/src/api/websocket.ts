// LifeLink Real-Time WebSocket Client with Secure Ticket Handshake

import { API_BASE_URL } from './client';
import { RealtimeEvent } from '../types';

export type EventListener = (event: RealtimeEvent) => void;

class RealtimeWebSocketClient {
  private socket: WebSocket | null = null;
  private listeners: Set<EventListener> = new Set();
  private reconnectTimer: any = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private shouldReconnect = true;

  private getWsUrl(): string {
    const token = localStorage.getItem('lifelink_token');
    const base = API_BASE_URL.replace(/^http/, 'ws');
    return `${base}/ws${token ? `?token=${encodeURIComponent(token)}` : ''}`;
  }

  public connect() {
    const token = localStorage.getItem('lifelink_token');
    if (!token) return;

    this.shouldReconnect = true;
    if (this.socket && (this.socket.readyState === WebSocket.OPEN || this.socket.readyState === WebSocket.CONNECTING)) {
      return;
    }

    const wsUrl = this.getWsUrl();

    try {
      this.socket = new WebSocket(wsUrl);

      this.socket.onopen = () => {
        this.reconnectAttempts = 0;
      };

      this.socket.onmessage = (messageEvent) => {
        try {
          const data: RealtimeEvent = JSON.parse(messageEvent.data);
          this.listeners.forEach((listener) => listener(data));
        } catch {
          // Non-JSON ping or heartbeat
        }
      };

      this.socket.onclose = () => {
        if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
          const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), 15000);
          this.reconnectTimer = setTimeout(() => {
            this.reconnectAttempts++;
            this.connect();
          }, delay);
        }
      };

      this.socket.onerror = () => {
        this.socket?.close();
      };
    } catch {
      // Failed to instantiate socket
    }
  }

  public disconnect() {
    this.shouldReconnect = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.socket) {
      this.socket.close();
      this.socket = null;
    }
  }

  public subscribe(listener: EventListener): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  public isConnected(): boolean {
    return this.socket?.readyState === WebSocket.OPEN;
  }
}

export const realtimeWs = new RealtimeWebSocketClient();
