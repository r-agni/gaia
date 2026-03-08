import { useCallback, useEffect, useRef, useState } from 'react';

interface EpisodeRecord {
  episode_id: string;
  episode_number: number;
  episode_score: number;
  total_rounds: number;
  avg_distance_km: number | null;
  min_distance_km: number | null;
  rounds: {
    round_number: number;
    score: number;
    distance_km: number | null;
    secret_country: string;
    secret_region: string;
  }[];
  timestamp: number;
}

interface TrainingHistory {
  episodes: EpisodeRecord[];
  total_episodes: number;
}

const ACCENT = '#67E8F9';
const GREEN = '#22C55E';
const ORANGE = '#F97316';
const RED = '#EF4444';
const MUTED = '#6B7280';
const BG = 'rgba(10,14,23,0.95)';
const CARD_BG = 'rgba(17,24,39,0.8)';
const BORDER = '#1F2937';

function scoreColor(score: number): string {
  if (score >= 0.7) return GREEN;
  if (score >= 0.4) return ORANGE;
  return RED;
}

function MiniLineChart({ data, width, height, color, label, formatY }: {
  data: number[];
  width: number;
  height: number;
  color: string;
  label: string;
  formatY: (v: number) => string;
}) {
  if (data.length === 0) {
    return (
      <div style={{ width, height, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <span style={{ color: MUTED, fontSize: 10 }}>No data yet</span>
      </div>
    );
  }

  const pad = { top: 20, right: 12, bottom: 24, left: 44 };
  const cw = width - pad.left - pad.right;
  const ch = height - pad.top - pad.bottom;

  const minY = Math.min(...data);
  const maxY = Math.max(...data);
  const rangeY = maxY - minY || 1;

  const toX = (i: number) => pad.left + (data.length === 1 ? cw / 2 : (i / (data.length - 1)) * cw);
  const toY = (v: number) => pad.top + ch - ((v - minY) / rangeY) * ch;

  const points = data.map((v, i) => `${toX(i)},${toY(v)}`).join(' ');
  const areaPoints = `${toX(0)},${pad.top + ch} ${points} ${toX(data.length - 1)},${pad.top + ch}`;

  const yTicks = [minY, minY + rangeY * 0.5, maxY];

  return (
    <svg width={width} height={height} style={{ display: 'block' }}>
      <text x={width / 2} y={14} textAnchor="middle" fill={MUTED} fontSize={9} fontFamily="monospace">
        {label}
      </text>

      {yTicks.map((v, i) => (
        <g key={i}>
          <line x1={pad.left} y1={toY(v)} x2={pad.left + cw} y2={toY(v)} stroke={BORDER} strokeDasharray="2,3" />
          <text x={pad.left - 4} y={toY(v) + 3} textAnchor="end" fill={MUTED} fontSize={8} fontFamily="monospace">
            {formatY(v)}
          </text>
        </g>
      ))}

      <polygon points={areaPoints} fill={color} opacity={0.1} />
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" />

      {data.length <= 50 && data.map((v, i) => (
        <circle key={i} cx={toX(i)} cy={toY(v)} r={2.5} fill={color} opacity={0.8} />
      ))}

      {data.length > 1 && (
        <text x={pad.left + cw / 2} y={height - 4} textAnchor="middle" fill={MUTED} fontSize={8} fontFamily="monospace">
          Episode 1 → {data.length}
        </text>
      )}
    </svg>
  );
}

interface Props {
  onClose: () => void;
}

export default function TrainingResultsView({ onClose }: Props) {
  const [history, setHistory] = useState<TrainingHistory | null>(null);
  const [error, setError] = useState<string | null>(null);
  const polling = useRef(true);

  const poll = useCallback(async () => {
    try {
      const r = await fetch('/api/geoguess/training/history');
      if (r.ok) {
        const data = await r.json();
        setHistory(data);
        setError(null);
      } else {
        setError('Could not fetch history');
      }
    } catch {
      setError('Server unreachable');
    }
  }, []);

  useEffect(() => {
    polling.current = true;
    poll();
    const id = setInterval(() => { if (polling.current) poll(); }, 3000);
    return () => { polling.current = false; clearInterval(id); };
  }, [poll]);

  const episodes = history?.episodes ?? [];
  const scores = episodes.map(e => e.episode_score);
  const distances = episodes.map(e => e.avg_distance_km).filter((d): d is number => d !== null);

  const totalEps = episodes.length;
  const avgScore = totalEps > 0 ? scores.reduce((a, b) => a + b, 0) / totalEps : 0;
  const bestScore = totalEps > 0 ? Math.max(...scores) : 0;
  const avgDist = distances.length > 0 ? distances.reduce((a, b) => a + b, 0) / distances.length : 0;
  const bestDist = distances.length > 0 ? Math.min(...distances) : 0;

  const recent = episodes.slice(-20).reverse();

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      zIndex: 500,
      background: BG,
      overflow: 'auto',
      fontFamily: 'monospace',
      color: '#D1D5DB',
    }}>
      {/* Header bar */}
      <div style={{
        position: 'sticky',
        top: 0,
        zIndex: 10,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 24px',
        background: 'rgba(10,14,23,0.98)',
        borderBottom: `1px solid ${BORDER}`,
        backdropFilter: 'blur(8px)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: ACCENT, letterSpacing: '0.1em' }}>
            TRAINING RESULTS
          </span>
          {totalEps > 0 && (
            <span style={{ fontSize: 10, color: MUTED }}>
              {totalEps} episode{totalEps !== 1 ? 's' : ''} recorded
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          style={{
            background: 'rgba(255,255,255,0.05)',
            border: `1px solid ${BORDER}`,
            borderRadius: 4,
            color: '#D1D5DB',
            padding: '6px 16px',
            fontSize: 11,
            fontFamily: 'monospace',
            cursor: 'pointer',
          }}
        >
          Back to Globe
        </button>
      </div>

      {error && (
        <div style={{ padding: '8px 24px', fontSize: 10, color: RED }}>{error}</div>
      )}

      <div style={{ padding: '20px 24px', maxWidth: 1100, margin: '0 auto' }}>
        {/* Stats cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 20 }}>
          {[
            { label: 'EPISODES', value: totalEps.toString(), color: ACCENT },
            { label: 'AVG SCORE', value: totalEps > 0 ? `${(avgScore * 100).toFixed(1)}%` : '—', color: scoreColor(avgScore) },
            { label: 'BEST SCORE', value: totalEps > 0 ? `${(bestScore * 100).toFixed(1)}%` : '—', color: scoreColor(bestScore) },
            { label: 'AVG DISTANCE', value: distances.length > 0 ? `${avgDist.toFixed(0)} km` : '—', color: ORANGE },
          ].map((card) => (
            <div key={card.label} style={{
              background: CARD_BG,
              border: `1px solid ${BORDER}`,
              borderRadius: 6,
              padding: '14px 16px',
            }}>
              <div style={{ fontSize: 9, color: MUTED, letterSpacing: '0.1em', marginBottom: 6 }}>{card.label}</div>
              <div style={{ fontSize: 20, fontWeight: 700, color: card.color }}>{card.value}</div>
            </div>
          ))}
        </div>

        {/* Charts */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
          <div style={{ background: CARD_BG, border: `1px solid ${BORDER}`, borderRadius: 6, padding: 12 }}>
            <MiniLineChart
              data={scores}
              width={500}
              height={200}
              color={GREEN}
              label="Episode Score"
              formatY={(v) => `${(v * 100).toFixed(0)}%`}
            />
          </div>
          <div style={{ background: CARD_BG, border: `1px solid ${BORDER}`, borderRadius: 6, padding: 12 }}>
            <MiniLineChart
              data={distances}
              width={500}
              height={200}
              color={ORANGE}
              label="Avg Distance (km)"
              formatY={(v) => `${v.toFixed(0)}`}
            />
          </div>
        </div>

        {/* Rolling averages */}
        {scores.length >= 5 && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 20 }}>
            <div style={{
              background: CARD_BG,
              border: `1px solid ${BORDER}`,
              borderRadius: 6,
              padding: '10px 16px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}>
              <span style={{ fontSize: 9, color: MUTED, letterSpacing: '0.08em' }}>LAST 5 AVG SCORE</span>
              <span style={{ fontSize: 14, fontWeight: 700, color: scoreColor(scores.slice(-5).reduce((a, b) => a + b, 0) / 5) }}>
                {(scores.slice(-5).reduce((a, b) => a + b, 0) / 5 * 100).toFixed(1)}%
              </span>
            </div>
            <div style={{
              background: CARD_BG,
              border: `1px solid ${BORDER}`,
              borderRadius: 6,
              padding: '10px 16px',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
            }}>
              <span style={{ fontSize: 9, color: MUTED, letterSpacing: '0.08em' }}>BEST DISTANCE</span>
              <span style={{ fontSize: 14, fontWeight: 700, color: GREEN }}>
                {bestDist > 0 ? `${bestDist.toFixed(0)} km` : '—'}
              </span>
            </div>
          </div>
        )}

        {/* Recent episodes table */}
        <div style={{ background: CARD_BG, border: `1px solid ${BORDER}`, borderRadius: 6, overflow: 'hidden' }}>
          <div style={{ padding: '10px 16px', borderBottom: `1px solid ${BORDER}` }}>
            <span style={{ fontSize: 10, color: MUTED, letterSpacing: '0.1em' }}>RECENT EPISODES</span>
          </div>
          {recent.length === 0 ? (
            <div style={{ padding: '24px 16px', textAlign: 'center', color: MUTED, fontSize: 11 }}>
              No episodes completed yet. Training will start automatically on deploy.
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
              <thead>
                <tr style={{ borderBottom: `1px solid ${BORDER}` }}>
                  {['#', 'Score', 'Avg Dist', 'Best Dist', 'Rounds', 'Locations'].map(h => (
                    <th key={h} style={{
                      padding: '8px 12px',
                      textAlign: 'left',
                      color: MUTED,
                      fontSize: 9,
                      fontWeight: 500,
                      letterSpacing: '0.08em',
                    }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recent.map((ep) => (
                  <tr key={ep.episode_id} style={{ borderBottom: `1px solid ${BORDER}` }}>
                    <td style={{ padding: '7px 12px', color: ACCENT }}>{ep.episode_number}</td>
                    <td style={{ padding: '7px 12px', color: scoreColor(ep.episode_score), fontWeight: 600 }}>
                      {(ep.episode_score * 100).toFixed(1)}%
                    </td>
                    <td style={{ padding: '7px 12px' }}>
                      {ep.avg_distance_km !== null ? `${ep.avg_distance_km.toFixed(0)} km` : '—'}
                    </td>
                    <td style={{ padding: '7px 12px', color: GREEN }}>
                      {ep.min_distance_km !== null ? `${ep.min_distance_km.toFixed(0)} km` : '—'}
                    </td>
                    <td style={{ padding: '7px 12px' }}>{ep.total_rounds}</td>
                    <td style={{ padding: '7px 12px', color: MUTED, maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {ep.rounds.map(r => `${r.secret_country}`).join(', ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
