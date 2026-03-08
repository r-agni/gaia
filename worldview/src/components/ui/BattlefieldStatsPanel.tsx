/**
 * BattlefieldStatsPanel — Real-time attacker vs defender statistics overlay.
 * Displays live unit counts, health, resources, objectives, and tick progress.
 */
import type { BattlefieldState } from '../../hooks/useBattlefield';

interface BattlefieldStatsPanelProps {
  state: BattlefieldState | null;
  visible: boolean;
}

function HealthBar({ value, max, color }: { value: number; max: number; color: string }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-300"
        style={{ width: `${pct}%`, backgroundColor: color }}
      />
    </div>
  );
}

export default function BattlefieldStatsPanel({ state, visible }: BattlefieldStatsPanelProps) {
  if (!visible || !state) return null;

  const attackerUnits = state.units.filter(u => u.side === 'attacker');
  const defenderUnits = state.units.filter(u => u.side === 'defender');

  const attAlive = attackerUnits.filter(u => u.status !== 'destroyed').length;
  const defAlive = defenderUnits.filter(u => u.status !== 'destroyed').length;

  const attTotalHp = attackerUnits.reduce((s, u) => s + u.health, 0);
  const attMaxHp = attackerUnits.reduce((s, u) => s + u.max_health, 0);
  const defTotalHp = defenderUnits.reduce((s, u) => s + u.health, 0);
  const defMaxHp = defenderUnits.reduce((s, u) => s + u.max_health, 0);

  const attObjs = state.objectives.filter(o => o.controlling_side === 'attacker').length;
  const defObjs = state.objectives.filter(o => o.controlling_side === 'defender').length;
  const neutObjs = state.objectives.length - attObjs - defObjs;

  const tickPct = state.max_ticks > 0 ? Math.min(100, (state.tick / state.max_ticks) * 100) : 0;

  return (
    <div className="fixed bottom-10 left-1/2 -translate-x-1/2 z-40 pointer-events-none select-none"
         style={{ minWidth: 360 }}>
      {/* Winner banner */}
      {state.winner && (
        <div className="mb-2 text-center">
          <span className="px-4 py-1 text-xs font-bold tracking-widest uppercase rounded"
                style={{
                  background: state.winner === 'attacker' ? 'rgba(255,68,68,0.85)' : 'rgba(68,136,255,0.85)',
                  color: '#fff',
                  fontFamily: 'monospace',
                  border: '1px solid rgba(255,255,255,0.2)',
                }}>
            {state.winner.toUpperCase()} VICTORY
          </span>
        </div>
      )}

      <div style={{
        background: 'rgba(8,12,16,0.88)',
        border: '1px solid rgba(0,255,136,0.18)',
        borderRadius: 4,
        fontFamily: 'monospace',
        fontSize: 11,
        color: '#c8d8c8',
        padding: '8px 12px',
        boxShadow: '0 0 12px rgba(0,255,136,0.08)',
      }}>
        {/* Header */}
        <div className="flex items-center justify-between mb-2">
          <span style={{ color: 'rgba(0,255,136,0.6)', fontSize: 9, letterSpacing: 2 }}>
            BATTLEFIELD STATUS
          </span>
          <span style={{ color: 'rgba(0,255,136,0.5)', fontSize: 9 }}>
            TICK {state.tick}/{state.max_ticks}
          </span>
        </div>

        {/* Tick progress bar */}
        <div className="mb-3">
          <div className="w-full h-1 bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${tickPct}%`, background: 'rgba(0,255,136,0.5)' }}
            />
          </div>
        </div>

        {/* Main stats grid */}
        <div className="grid grid-cols-2 gap-x-4">
          {/* Attacker column */}
          <div>
            <div className="mb-1.5" style={{ color: '#FF6666', fontSize: 10, letterSpacing: 1 }}>
              ATTACKER
            </div>
            <div className="flex justify-between mb-0.5">
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>UNITS</span>
              <span style={{ color: '#FF8888' }}>{attAlive}/{attackerUnits.length}</span>
            </div>
            <div className="mb-1.5">
              <HealthBar value={attTotalHp} max={attMaxHp} color="#FF6666" />
            </div>
            <div className="flex justify-between mb-0.5">
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>RESOURCES</span>
              <span style={{ color: '#FFAA66' }}>{state.attacker_resources ?? '–'}</span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>OBJECTIVES</span>
              <span style={{ color: '#FF8888' }}>{attObjs}</span>
            </div>
          </div>

          {/* Divider */}
          <div style={{ borderLeft: '1px solid rgba(0,255,136,0.12)', paddingLeft: 12 }}>
            <div className="mb-1.5" style={{ color: '#6699FF', fontSize: 10, letterSpacing: 1 }}>
              DEFENDER
            </div>
            <div className="flex justify-between mb-0.5">
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>UNITS</span>
              <span style={{ color: '#88AAFF' }}>{defAlive}/{defenderUnits.length}</span>
            </div>
            <div className="mb-1.5">
              <HealthBar value={defTotalHp} max={defMaxHp} color="#4488FF" />
            </div>
            <div className="flex justify-between mb-0.5">
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>RESOURCES</span>
              <span style={{ color: '#FFAA66' }}>{state.defender_resources ?? '–'}</span>
            </div>
            <div className="flex justify-between">
              <span style={{ color: 'rgba(255,255,255,0.5)' }}>OBJECTIVES</span>
              <span style={{ color: '#88AAFF' }}>{defObjs}</span>
            </div>
          </div>
        </div>

        {/* Objectives summary */}
        {state.objectives.length > 0 && (
          <div className="mt-2 pt-2" style={{ borderTop: '1px solid rgba(0,255,136,0.1)' }}>
            <div className="flex items-center gap-2 justify-center" style={{ fontSize: 9, color: 'rgba(255,255,255,0.4)' }}>
              <span style={{ color: '#FF6666' }}>■ {attObjs} ATT</span>
              <span style={{ color: '#FFD700' }}>■ {neutObjs} NEUTRAL</span>
              <span style={{ color: '#4488FF' }}>■ {defObjs} DEF</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
