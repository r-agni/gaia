import { useState, useEffect, useRef, useCallback } from 'react';
import type { IntelFeedItem } from '../components/ui/IntelFeed';

export interface BattlefieldUnit {
  unit_id: string;
  unit_type: string;
  side: 'attacker' | 'defender';
  position: { lat: number; lon: number };
  health: number;
  max_health: number;
  status: string;
  heading_deg: number;
  dug_in: boolean;
  cooldown_ticks_remaining?: number;
}

export interface BattlefieldObjective {
  objective_id: string;
  name: string;
  position: { lat: number; lon: number };
  controlling_side: string | null;
  capture_progress: number;
}

export interface BattlefieldState {
  tick: number;
  max_ticks: number;
  is_terminal: boolean;
  winner: string | null;
  scenario_name: string;
  units: BattlefieldUnit[];
  objectives: BattlefieldObjective[];
  combat_log: {
    event_type: string;
    side: string;
    description: string;
    position: { lat: number; lon: number } | null;
  }[];
  attacker_resources: number;
  defender_resources: number;
  geo_anchor?: { lat0: number; lon0: number; scale_m_per_cell: number };
}

const RECONNECT_DELAY = 3000;

export function useBattlefield(enabled: boolean): {
  state: BattlefieldState | null;
  feedItems: IntelFeedItem[];
  isConnected: boolean;
  connect: () => void;
  disconnect: () => void;
} {
  const [state, setState] = useState<BattlefieldState | null>(null);
  const [feedItems, setFeedItems] = useState<IntelFeedItem[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const enabledRef = useRef(enabled);
  const manualDisconnectRef = useRef(false);

  // Keep enabledRef in sync
  useEffect(() => {
    enabledRef.current = enabled;
  }, [enabled]);

  const clearReconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const openSocket = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState <= WebSocket.OPEN) return;

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/battlefield`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      console.info('[BTL] WebSocket connected');
    };

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        // Server spreads state at top level: {"type": "state_update", tick: N, units: [...], ...}
        if (msg.type === 'state_update' || msg.type === 'episode_start') {
          const { type: _t, ...rest } = msg;
          const newState: BattlefieldState = rest as BattlefieldState;
          setState(newState);

          // Emit feed items for each new combat log entry
          if (newState.combat_log && newState.combat_log.length > 0) {
            const items: IntelFeedItem[] = newState.combat_log.map((entry, i) => ({
              id: `btl-${newState.tick}-${i}-${Date.now()}`,
              time: new Date().toISOString().slice(11, 19),
              type: 'battle' as const,
              message: entry.description,
            }));
            setFeedItems(prev => [...prev, ...items].slice(-150));
          }
        } else if (msg.type === 'episode_end') {
          // Patch winner into current state
          setState(prev => prev ? { ...prev, winner: msg.winner ?? prev.winner, is_terminal: true } : prev);
        }
      } catch (err) {
        console.warn('[BTL] Failed to parse WebSocket message', err);
      }
    };

    ws.onerror = (err) => {
      console.warn('[BTL] WebSocket error', err);
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;
      console.info('[BTL] WebSocket closed');

      // Auto-reconnect unless manually disconnected or layer disabled
      if (!manualDisconnectRef.current && enabledRef.current) {
        reconnectTimerRef.current = setTimeout(() => {
          if (enabledRef.current && !manualDisconnectRef.current) {
            openSocket();
          }
        }, RECONNECT_DELAY);
      }
    };
  }, []);

  const connect = useCallback(() => {
    manualDisconnectRef.current = false;
    clearReconnect();
    openSocket();
  }, [openSocket, clearReconnect]);

  const disconnect = useCallback(() => {
    manualDisconnectRef.current = true;
    clearReconnect();
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setState(null);
    setIsConnected(false);
  }, [clearReconnect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      manualDisconnectRef.current = true;
      clearReconnect();
      if (wsRef.current) {
        try { wsRef.current.close(); } catch { /* ok */ }
        wsRef.current = null;
      }
    };
  }, [clearReconnect]);

  return { state, feedItems, isConnected, connect, disconnect };
}
