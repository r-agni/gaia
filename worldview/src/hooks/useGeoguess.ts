/**
 * useGeoguess — WebSocket hook for GeoGuessEnv state.
 * Mirrors the structure of useBattlefield.ts but for the GeoGuessr game.
 */
import { useCallback, useEffect, useRef, useState } from 'react';

export interface GeoGuessGuess {
  lat: number;
  lon: number;
  distance_km: number;
  score: number;
  correct_country: boolean;
  correct_region: boolean;
  step: number;
}

export interface GeoGuessToolCall {
  tool_name: string;
  step: number;
  result: string;
}

export interface RoundSummary {
  round_number: number;
  score: number;
  distance_km: number | null;
  secret_lat: number;
  secret_lon: number;
  guess_lat: number | null;
  guess_lon: number | null;
  secret_country: string;
  secret_region: string;
}

export interface GeoGuessState {
  episode_id: string;
  current_round: number;
  total_rounds: number;
  is_terminal: boolean;
  episode_score: number;
  // Secret location (null = still hidden during active round)
  secret_lat: number | null;
  secret_lon: number | null;
  secret_country: string;
  secret_region: string;
  // Agent's latest guess pin
  current_guess_lat: number | null;
  current_guess_lon: number | null;
  guesses: GeoGuessGuess[];
  tool_calls: GeoGuessToolCall[];
  round_history: RoundSummary[];
  training_mode?: boolean;
  episode?: number;
  // Oversight agent
  oversight_flags: string[];
  oversight_summary?: {
    total_flags: number;
    assessment: 'CLEAN' | 'CAUTION' | 'UNRELIABLE';
    most_common_issue: string | null;
    issue_counts?: Record<string, number>;
    rounds_with_issues?: number;
    detail?: string;
  };
}

const RECONNECT_DELAY = 3000;

export function useGeoguess(enabled: boolean): {
  state: GeoGuessState | null;
  connected: boolean;
  connect: () => void;
  disconnect: () => void;
  error: string | null;
} {
  const [state, setState] = useState<GeoGuessState | null>(null);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const shouldReconnect = useRef(false);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    shouldReconnect.current = true;

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const isDev = host.includes('5173');
    const url = isDev
      ? `ws://${window.location.hostname}:3001/ws/geoguess`
      : `${proto}//${host}/ws/geoguess`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setError(null);
    };

    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (
          msg.type === 'state_update' ||
          msg.type === 'episode_start' ||
          msg.type === 'round_end' ||
          msg.type === 'episode_end' ||
          msg.type === 'round_start' ||
          msg.type === 'oversight_flag'
        ) {
          const { type: _t, ...rest } = msg;
          setState(rest as GeoGuessState);
        }
      } catch { /* ignore */ }
    };

    ws.onerror = () => setError('WebSocket error');

    ws.onclose = () => {
      setConnected(false);
      wsRef.current = null;
      if (shouldReconnect.current) {
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY);
      }
    };
  }, []);

  const disconnect = useCallback(() => {
    shouldReconnect.current = false;
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    wsRef.current?.close();
    wsRef.current = null;
    setState(null);
    setConnected(false);
  }, []);

  useEffect(() => {
    if (enabled) connect();
    return () => { shouldReconnect.current = false; wsRef.current?.close(); };
  }, [enabled, connect]);

  return { state, connected, connect, disconnect, error };
}
