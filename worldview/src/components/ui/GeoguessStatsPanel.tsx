/**
 * GeoguessStatsPanel — bottom-centre overlay showing GeoGuessr game status.
 */
import type { GeoGuessState } from '../../hooks/useGeoguess';

const ACCENT = '#67E8F9';
const MUTED = '#6B7280';
const BG = 'rgba(15,17,23,0.94)';
const BORDER = '#1F2937';
const GREEN = '#22C55E';
const ORANGE = '#F97316';
const RED = '#EF4444';

interface Props {
  state: GeoGuessState | null;
  visible: boolean;
}

function scoreColor(score: number): string {
  if (score >= 0.7) return GREEN;
  if (score >= 0.4) return ORANGE;
  return RED;
}

export default function GeoguessStatsPanel({ state, visible }: Props) {
  if (!visible || !state) return null;

  const currentRound = state.current_round + 1;
  const totalRounds = state.total_rounds;
  const lastGuess = state.guesses.length > 0 ? state.guesses[state.guesses.length - 1] : null;
  const toolsUsed = state.tool_calls.length;
  const episodeScoreColor = scoreColor(state.episode_score);

  return (
    <div style={{
      position: 'fixed',
      bottom: 48,
      left: '50%',
      transform: 'translateX(-50%)',
      background: BG,
      border: `1px solid ${BORDER}`,
      borderRadius: 4,
      padding: '10px 16px',
      minWidth: 320,
      maxWidth: 480,
      fontFamily: 'monospace',
      fontSize: 11,
      color: '#D1D5DB',
      zIndex: 200,
      backdropFilter: 'blur(8px)',
      pointerEvents: 'none',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8, alignItems: 'center' }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: ACCENT, letterSpacing: '0.1em', textTransform: 'uppercase' }}>
          GeoGuessr
        </span>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          {state.training_mode && state.episode !== undefined && (
            <span style={{ fontSize: 9, color: ORANGE, fontWeight: 700, letterSpacing: '0.1em' }}>
              TRAINING EP {state.episode}
            </span>
          )}
          <span style={{ fontSize: 10, color: MUTED }}>
            Round {currentRound} / {totalRounds}
          </span>
        </div>
      </div>

      {/* Episode score bar */}
      <div style={{ marginBottom: 8 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
          <span style={{ color: MUTED, fontSize: 9, letterSpacing: '0.08em' }}>EPISODE SCORE</span>
          <span style={{ color: episodeScoreColor, fontWeight: 700 }}>
            {(state.episode_score * 100).toFixed(1)}%
          </span>
        </div>
        <div style={{ height: 3, background: '#1F2937', borderRadius: 2 }}>
          <div style={{
            height: '100%',
            width: `${state.episode_score * 100}%`,
            background: episodeScoreColor,
            borderRadius: 2,
            transition: 'width 0.4s ease',
          }} />
        </div>
      </div>

      {/* Current round stats */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 8, fontSize: 10 }}>
        <span style={{ color: MUTED }}>Tools used: <span style={{ color: '#D1D5DB' }}>{toolsUsed}</span></span>
        {lastGuess && (
          <span style={{ color: MUTED }}>
            Last guess: <span style={{ color: scoreColor(lastGuess.score) }}>
              {lastGuess.distance_km.toFixed(0)} km
            </span>
          </span>
        )}
        {state.secret_country !== '??' && (
          <span style={{ color: GREEN, fontSize: 9 }}>
            {state.secret_country}, {state.secret_region}
          </span>
        )}
      </div>

      {/* Round history dots */}
      {totalRounds > 1 && (
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <span style={{ color: MUTED, fontSize: 9 }}>ROUNDS:</span>
          {Array.from({ length: totalRounds }, (_, i) => {
            const rh = state.round_history.find(r => r.round_number === i);
            const isCurrent = i === state.current_round;
            const color = rh ? scoreColor(rh.score) : (isCurrent ? ACCENT : MUTED);
            return (
              <div key={i} title={rh ? `R${i+1}: ${(rh.score*100).toFixed(0)}%` : `R${i+1}`}
                style={{
                  width: isCurrent ? 10 : 8,
                  height: isCurrent ? 10 : 8,
                  borderRadius: '50%',
                  background: color,
                  opacity: rh || isCurrent ? 1 : 0.3,
                  border: isCurrent ? `1px solid ${ACCENT}` : 'none',
                }}
              />
            );
          })}
          {state.round_history.length > 0 && (
            <span style={{ color: MUTED, fontSize: 9, marginLeft: 4 }}>
              avg {(state.round_history.reduce((s, r) => s + r.score, 0) / state.round_history.length * 100).toFixed(0)}%
            </span>
          )}
        </div>
      )}
    </div>
  );
}
