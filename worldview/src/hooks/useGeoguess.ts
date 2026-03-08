/**
 * useGeoguess — Polls GeoGuessEnv state from the backend.
 * Replaces the fragile WebSocket chain with simple HTTP polling.
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
  scene_description: string;
  secret_lat: number | null;
  secret_lon: number | null;
  secret_country: string;
  secret_region: string;
  current_guess_lat: number | null;
  current_guess_lon: number | null;
  guesses: GeoGuessGuess[];
  tool_calls: GeoGuessToolCall[];
  round_history: RoundSummary[];
  training_mode?: boolean;
  episode?: number;
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

const POLL_INTERVAL = 600;

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
  const polling = useRef(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const poll = useCallback(async () => {
    if (!polling.current) return;
    try {
      const r = await fetch('/api/geoguess/state');
      if (r.ok) {
        const data = await r.json();
        if (data && data.episode_id) {
          setState(data as GeoGuessState);
        }
        setConnected(true);
        setError(null);
      } else {
        setConnected(false);
      }
    } catch {
      setConnected(false);
      setError('Cannot reach server');
    }
    if (polling.current) {
      timerRef.current = setTimeout(poll, POLL_INTERVAL);
    }
  }, []);

  const connect = useCallback(() => {
    if (polling.current) return;
    polling.current = true;
    poll();
  }, [poll]);

  const disconnect = useCallback(() => {
    polling.current = false;
    if (timerRef.current) clearTimeout(timerRef.current);
    setState(null);
    setConnected(false);
  }, []);

  useEffect(() => {
    if (enabled) connect();
    return () => { polling.current = false; if (timerRef.current) clearTimeout(timerRef.current); };
  }, [enabled, connect]);

  return { state, connected, connect, disconnect, error };
}
