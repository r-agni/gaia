/**
 * GeoSidebar — right sidebar showing live agent activity, tool calls,
 * location reveal, and round history for the GeoGuess game.
 */
import { useState } from 'react';
import type { GeoGuessState, GeoGuessToolCall } from '../../hooks/useGeoguess';
import MobileModal from './MobileModal';

interface GeoSidebarProps {
  state: GeoGuessState | null;
  connected?: boolean;
  isMobile?: boolean;
}

const TOOL_ICONS: Record<string, string> = {
  street_view: '📷',
  terrain: '⛰',
  weather: '🌤',
  language_detection: '🔤',
  building_style: '🏛',
  sun_angle: '☀',
  guess: '📍',
  default: '🔍',
};

const TOOL_COLORS: Record<string, string> = {
  street_view: 'text-wv-cyan',
  terrain: 'text-wv-green',
  weather: 'text-wv-amber',
  language_detection: 'text-wv-text',
  building_style: 'text-wv-teal',
  sun_angle: 'text-wv-amber',
  guess: 'text-wv-green',
  default: 'text-wv-muted',
};

function toolIcon(name: string) {
  return TOOL_ICONS[name] ?? TOOL_ICONS.default;
}

function toolColor(name: string) {
  return TOOL_COLORS[name] ?? TOOL_COLORS.default;
}

function scoreColor(score: number): string {
  if (score >= 0.7) return 'text-wv-green';
  if (score >= 0.4) return 'text-wv-amber';
  return 'text-wv-red';
}

function scoreBg(score: number): string {
  if (score >= 0.7) return 'bg-wv-green';
  if (score >= 0.4) return 'bg-wv-amber';
  return 'bg-wv-red';
}

function ToolCallRow({ call }: { call: GeoGuessToolCall }) {
  const [expanded, setExpanded] = useState(false);
  const hasResult = call.result && call.result.length > 0;
  const shortResult = call.result?.slice(0, 80);
  const isLong = (call.result?.length ?? 0) > 80;

  return (
    <div className="border-b border-wv-border/40 py-1.5 px-2">
      <div
        className={`flex items-center gap-2 ${hasResult ? 'cursor-pointer' : ''}`}
        onClick={() => hasResult && setExpanded((e) => !e)}
      >
        <span className="text-sm shrink-0">{toolIcon(call.tool_name)}</span>
        <span className={`text-[9px] font-bold tracking-wider uppercase ${toolColor(call.tool_name)}`}>
          {call.tool_name.replace(/_/g, ' ')}
        </span>
        <span className="text-[8px] text-wv-muted ml-auto shrink-0">step {call.step}</span>
        {hasResult && (
          <span className="text-[8px] text-wv-muted shrink-0">{expanded ? '▲' : '▼'}</span>
        )}
      </div>
      {hasResult && !expanded && (
        <div className="text-[8px] text-wv-muted/70 mt-0.5 pl-6 leading-relaxed truncate">
          {shortResult}{isLong && '…'}
        </div>
      )}
      {hasResult && expanded && (
        <div className="text-[8px] text-wv-text/80 mt-1 pl-6 leading-relaxed max-h-32 overflow-y-auto whitespace-pre-wrap break-words">
          {call.result}
        </div>
      )}
    </div>
  );
}

function SidebarContent({ state, connected }: { state: GeoGuessState | null; connected?: boolean }) {
  if (!state) {
    return (
      <div className="flex flex-col items-center justify-center h-48 gap-3 p-4">
        <div className={`w-2 h-2 rounded-full ${connected ? 'bg-wv-green animate-pulse' : 'bg-wv-muted/40 animate-pulse'}`} />
        <span className="text-[10px] text-wv-muted tracking-wider text-center">
          {connected ? 'Agent connected' : 'Waiting for agent…'}
        </span>
        <span className="text-[9px] text-wv-muted/50 tracking-wider text-center">
          {connected ? 'Start a game to see activity' : 'Start the GeoGuess env server'}
        </span>
      </div>
    );
  }

  const currentRound = state.current_round + 1;
  const lastGuess = state.guesses.length > 0 ? state.guesses[state.guesses.length - 1] : null;
  const roundRevealed = state.secret_lat != null;

  return (
    <>
      {/* Round + score */}
      <div className="p-2 border-b border-wv-border">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-[11px] text-wv-text">
            Round {currentRound} / {state.total_rounds}
          </span>
          <span className={`text-[11px] font-medium ${scoreColor(state.episode_score)}`}>
            {(state.episode_score * 100).toFixed(0)}%
          </span>
        </div>
        <div className="h-1 bg-wv-border rounded-full overflow-hidden">
          <div
            className={`h-full ${scoreBg(state.episode_score)} rounded-full transition-all duration-500`}
            style={{ width: `${state.episode_score * 100}%` }}
          />
        </div>
      </div>

      {roundRevealed && (
        <div className="p-2 border-b border-wv-border bg-wv-green/5">
          <div className="text-[10px] text-wv-text">
            {state.secret_country !== '??' ? state.secret_country : '—'}
            {state.secret_region && state.secret_region !== '??' && `, ${state.secret_region}`}
          </div>
          <div className="text-[9px] text-wv-muted mt-0.5 font-mono">
            {state.secret_lat?.toFixed(3)}°, {state.secret_lon?.toFixed(3)}°
          </div>
          {lastGuess && (
            <div className="mt-1.5 flex items-center gap-2 text-[10px]">
              <span className="text-wv-muted">Distance</span>
              <span className={scoreColor(lastGuess.score)}>{lastGuess.distance_km.toFixed(0)} km</span>
              <span className={`ml-auto ${scoreColor(lastGuess.score)}`}>{(lastGuess.score * 100).toFixed(0)}%</span>
            </div>
          )}
        </div>
      )}

      {state.current_guess_lat != null && !roundRevealed && (
        <div className="px-2 py-1.5 border-b border-wv-border">
          <div className="text-[9px] text-wv-muted font-mono">
            Guess: {state.current_guess_lat.toFixed(3)}°, {state.current_guess_lon?.toFixed(3)}°
          </div>
        </div>
      )}

      {state.oversight_flags && state.oversight_flags.length > 0 && (
        <div className="border-b border-wv-border bg-wv-red/5 px-2 py-1.5">
          <div className="text-[9px] text-wv-red font-medium">
            Flags: {state.oversight_flags.length}
          </div>
          <div className="flex flex-col gap-0.5 mt-1">
            {state.oversight_flags.map((flag, i) => (
              <div key={i} className="text-[8px] text-wv-muted leading-snug">{flag}</div>
            ))}
          </div>
          {state.oversight_summary?.assessment && state.oversight_summary.assessment !== 'CLEAN' && (
            <div className={`mt-1 text-[8px] ${state.oversight_summary.assessment === 'UNRELIABLE' ? 'text-wv-red' : 'text-wv-amber'}`}>
              {state.oversight_summary.assessment}
            </div>
          )}
        </div>
      )}

      {/* Tool calls log */}
      <div className="flex-1">
        <div className="px-3 py-2 border-b border-wv-border">
          <div className="text-[8px] text-wv-muted tracking-widest uppercase">
            Agent Activity
            {state.tool_calls.length > 0 && (
              <span className="ml-2 text-wv-cyan">{state.tool_calls.length} calls</span>
            )}
          </div>
        </div>
        {state.tool_calls.length === 0 ? (
          <div className="px-3 py-4 text-[9px] text-wv-muted/50 text-center tracking-wider">
            No tool calls yet
          </div>
        ) : (
          <div className="overflow-y-auto max-h-64">
            {[...state.tool_calls].reverse().map((call, i) => (
              <ToolCallRow key={`${call.tool_name}-${call.step}-${i}`} call={call} />
            ))}
          </div>
        )}
      </div>

      {/* Round history dots */}
      {state.total_rounds > 1 && (
        <div className="p-3 border-t border-wv-border">
          <div className="text-[8px] text-wv-muted tracking-widest uppercase mb-2">Round History</div>
          <div className="flex gap-1.5 flex-wrap">
            {Array.from({ length: state.total_rounds }, (_, i) => {
              const rh = state.round_history.find((r) => r.round_number === i);
              const isCurrent = i === state.current_round;
              const dotBg = rh ? scoreBg(rh.score) : isCurrent ? 'bg-wv-cyan' : 'bg-wv-border';
              const opacity = rh || isCurrent ? 'opacity-100' : 'opacity-30';
              return (
                <div
                  key={i}
                  title={rh ? `R${i + 1}: ${(rh.score * 100).toFixed(0)}%` : `R${i + 1}`}
                  className={`rounded-full ${dotBg} ${opacity} transition-all duration-300 ${isCurrent ? 'ring-1 ring-wv-cyan' : ''}`}
                  style={{ width: isCurrent ? 10 : 8, height: isCurrent ? 10 : 8 }}
                />
              );
            })}
            {state.round_history.length > 0 && (
              <span className="text-[8px] text-wv-muted ml-1 self-center">
                avg {(state.round_history.reduce((s, r) => s + r.score, 0) / state.round_history.length * 100).toFixed(0)}%
              </span>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export default function GeoSidebar({ state, connected = false, isMobile = false }: GeoSidebarProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  if (isMobile) {
    return (
      <>
        <button
          onClick={() => setMobileOpen(true)}
          className="fixed top-3 right-3 z-40 w-11 h-11 rounded-lg panel-glass
                     flex items-center justify-center
                     text-wv-cyan hover:bg-white/10 transition-colors
                     select-none active:scale-95"
          aria-label="Open agent feed"
        >
          <span className="text-lg">📍</span>
          {(state || connected) && (
            <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-wv-cyan animate-pulse" />
          )}
        </button>

        <MobileModal
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          title="Agent"
          icon="📍"
          accent="bg-wv-cyan"
        >
          <SidebarContent state={state} connected={connected} />
        </MobileModal>
      </>
    );
  }

  return (
    <div className="fixed top-4 right-4 w-72 panel-glass rounded-lg overflow-hidden z-40 select-none flex flex-col max-h-[calc(100vh-2rem)]">
      {/* Header: connection status matches left panel */}
      <div className="px-3 py-2 border-b border-wv-border flex items-center gap-2 shrink-0">
        <div className={`w-2 h-2 rounded-full ${state || connected ? 'bg-wv-green animate-pulse' : 'bg-wv-muted/30'}`} />
        <span className="text-[10px] text-wv-muted tracking-widest uppercase">Agent</span>
        {state?.oversight_summary?.assessment && state.oversight_summary.assessment !== 'CLEAN' && (
          <span className={`text-[8px] font-bold tracking-wider px-1.5 py-0.5 rounded ${
            state.oversight_summary.assessment === 'UNRELIABLE'
              ? 'bg-wv-red/20 text-wv-red'
              : 'bg-wv-amber/20 text-wv-amber'
          }`}>
            {state.oversight_summary.assessment}
          </span>
        )}
        {state && (
          <span className="ml-auto text-[9px] text-wv-muted/60">
            ep {state.episode_id?.slice(0, 8) ?? '—'}
          </span>
        )}
      </div>
      <SidebarContent state={state} connected={connected} />
    </div>
  );
}
