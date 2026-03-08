import { useState, memo } from 'react';
import type { BattlefieldState } from '../../hooks/useBattlefield';

interface BattlefieldStatsPanelProps {
  state: BattlefieldState | null;
  visible: boolean;
}

const TYPE_NAMES: Record<string, string> = {
  infantry_squad: 'Infantry',
  sniper_team: 'Sniper',
  mortar_team: 'Mortar',
  light_vehicle: 'Light Veh',
  armored_vehicle: 'Armor',
  helicopter: 'Helo',
  uav_drone: 'UAV',
  artillery_battery: 'Artillery',
  aa_emplacement: 'AA',
  fortified_position: 'Fortified',
};

function hpBarColor(fraction: number): string {
  if (fraction > 0.6) return '#4CAF7D';
  if (fraction > 0.3) return '#E8A045';
  return '#D64045';
}

function HpBar({ value, max, color }: { value: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  const barColor = color ?? hpBarColor(pct / 100);
  return (
    <div style={{ width: '100%', height: 3, background: '#252d3d', borderRadius: 2, overflow: 'hidden' }}>
      <div style={{ width: `${pct}%`, height: '100%', backgroundColor: barColor, borderRadius: 2, transition: 'width 0.3s' }} />
    </div>
  );
}

const SURFACE = '#161b27';
const BORDER = '#252d3d';
const MUTED = '#5a6478';
const TEXT = '#d4dbe8';
const ACCENT = '#E8A045';
const ATT = '#D64045';
const DEF = '#5B8DB8';

function BattlefieldStatsPanel({ state, visible }: BattlefieldStatsPanelProps) {
  const [rosterOpen, setRosterOpen] = useState(true);
  const [logOpen, setLogOpen] = useState(true);

  if (!visible || !state) return null;

  const attackerUnits = state.units.filter(u => u.side === 'attacker');
  const defenderUnits = state.units.filter(u => u.side === 'defender');
  const attAlive = attackerUnits.filter(u => u.status !== 'destroyed').length;
  const defAlive = defenderUnits.filter(u => u.status !== 'destroyed').length;
  const attTotalHp = attackerUnits.reduce((s, u) => s + u.health, 0);
  const attMaxHp = attackerUnits.reduce((s, u) => s + u.max_health, 0);
  const defTotalHp = defenderUnits.reduce((s, u) => s + u.health, 0);
  const defMaxHp = defenderUnits.reduce((s, u) => s + u.max_health, 0);
  const tickPct = state.max_ticks > 0 ? Math.min(100, (state.tick / state.max_ticks) * 100) : 0;

  return (
    <div style={{
      position: 'fixed', top: 16, right: 16, zIndex: 40,
      width: 300, maxHeight: 'calc(100vh - 6rem)',
      display: 'flex', flexDirection: 'column', gap: 6,
      userSelect: 'none',
    }}>
      {/* Winner banner */}
      {state.winner && (
        <div style={{
          padding: '6px 12px',
          background: state.winner === 'attacker' ? `${ATT}20` : `${DEF}20`,
          borderLeft: `2px solid ${state.winner === 'attacker' ? ATT : DEF}`,
          border: `1px solid ${state.winner === 'attacker' ? ATT : DEF}`,
          borderRadius: 4,
          fontSize: 12, fontWeight: 700, letterSpacing: '0.1em',
          color: state.winner === 'attacker' ? ATT : DEF,
          textTransform: 'uppercase',
          textAlign: 'center',
        }}>
          {state.winner} Victory
        </div>
      )}

      {/* Main panel */}
      <div style={{
        background: SURFACE,
        border: `1px solid ${BORDER}`,
        borderLeft: `2px solid ${ACCENT}`,
        borderRadius: 4,
        overflow: 'hidden',
        overflowY: 'auto',
        maxHeight: 'calc(100vh - 7rem)',
        fontSize: 11,
        color: TEXT,
      }}>
        {/* Header */}
        <div style={{
          padding: '7px 12px',
          borderBottom: `1px solid ${BORDER}`,
          background: SURFACE,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          position: 'sticky', top: 0, zIndex: 1,
        }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: ACCENT, letterSpacing: '0.1em', textTransform: 'uppercase' }}>
            Battlefield
          </span>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {state.episode !== undefined && (
              <span style={{ fontSize: 9, color: ACCENT, letterSpacing: '0.08em', fontWeight: 600 }}>
                EP {state.episode}
              </span>
            )}
            <span style={{ fontSize: 10, color: MUTED }}>
              Tick {state.tick} / {state.max_ticks}
            </span>
          </div>
        </div>

        {/* Tick bar */}
        <div style={{ padding: '6px 12px 4px' }}>
          <div style={{ height: 2, background: BORDER, borderRadius: 1, overflow: 'hidden' }}>
            <div style={{ width: `${tickPct}%`, height: '100%', background: ACCENT, borderRadius: 1, transition: 'width 0.5s' }} />
          </div>
        </div>

        {/* Side summary */}
        <div style={{
          padding: '8px 12px',
          borderBottom: `1px solid ${BORDER}`,
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10,
        }}>
          {/* Attacker */}
          <div style={{ borderLeft: `2px solid ${ATT}`, paddingLeft: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: ATT, marginBottom: 4, letterSpacing: '0.08em' }}>
              Attacker
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ color: MUTED, fontSize: 10 }}>Units</span>
              <span style={{ color: ATT, fontSize: 10 }}>{attAlive}/{attackerUnits.length}</span>
            </div>
            <HpBar value={attTotalHp} max={attMaxHp} color={ATT} />
            {state.attacker_resources !== undefined && (
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
                <span style={{ color: MUTED, fontSize: 10 }}>Res</span>
                <span style={{ color: TEXT, fontSize: 10 }}>{state.attacker_resources}</span>
              </div>
            )}
          </div>
          {/* Defender */}
          <div style={{ borderLeft: `2px solid ${DEF}`, paddingLeft: 8 }}>
            <div style={{ fontSize: 10, fontWeight: 700, color: DEF, marginBottom: 4, letterSpacing: '0.08em' }}>
              Defender
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
              <span style={{ color: MUTED, fontSize: 10 }}>Units</span>
              <span style={{ color: DEF, fontSize: 10 }}>{defAlive}/{defenderUnits.length}</span>
            </div>
            <HpBar value={defTotalHp} max={defMaxHp} color={DEF} />
            {state.defender_resources !== undefined && (
              <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 4 }}>
                <span style={{ color: MUTED, fontSize: 10 }}>Res</span>
                <span style={{ color: TEXT, fontSize: 10 }}>{state.defender_resources}</span>
              </div>
            )}
          </div>
        </div>

        {/* Objectives */}
        {state.objectives.length > 0 && (
          <div style={{ padding: '8px 12px', borderBottom: `1px solid ${BORDER}` }}>
            <div style={{ fontSize: 10, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6, fontWeight: 600 }}>
              Objectives
            </div>
            {state.objectives.map(obj => {
              let col = ACCENT;
              let sideLabel = 'Neutral';
              if (obj.controlling_side === 'attacker') { col = ATT; sideLabel = 'Att'; }
              else if (obj.controlling_side === 'defender') { col = DEF; sideLabel = 'Def'; }
              const capPct = Math.round((obj.capture_progress ?? 0) * 100);
              return (
                <div key={obj.objective_id} style={{ marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                    <span style={{ fontSize: 10, color: col, fontWeight: 600 }}>
                      {obj.name || obj.objective_id}
                    </span>
                    <span style={{ fontSize: 9, color: MUTED }}>
                      {sideLabel}{capPct > 0 && capPct < 100 ? ` ${capPct}%` : ''}
                    </span>
                  </div>
                  <div style={{ height: 3, background: BORDER, borderRadius: 2, overflow: 'hidden' }}>
                    <div style={{ width: `${capPct}%`, height: '100%', backgroundColor: col, borderRadius: 2, transition: 'width 0.3s' }} />
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Unit Roster */}
        <div style={{ borderBottom: `1px solid ${BORDER}` }}>
          <div
            style={{
              padding: '6px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              cursor: 'pointer',
            }}
            onClick={() => setRosterOpen(!rosterOpen)}
          >
            <span style={{ fontSize: 10, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 600 }}>
              Roster
            </span>
            <span style={{ fontSize: 9, color: MUTED }}>{rosterOpen ? '▲' : '▼'}</span>
          </div>
          {rosterOpen && (
            <div style={{ padding: '0 12px 8px', maxHeight: 192, overflowY: 'auto' }}>
              {attackerUnits.filter(u => u.status !== 'destroyed').map(u => {
                const hpFrac = u.max_health > 0 ? u.health / u.max_health : 0;
                return (
                  <div key={u.unit_id} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0' }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: ATT, flexShrink: 0 }} />
                    <span style={{ flex: 1, fontSize: 10, color: ATT, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {TYPE_NAMES[u.unit_type] ?? u.unit_type}
                    </span>
                    {(u.dug_in || u.status === 'retreating') && (
                      <span style={{ fontSize: 9, color: u.dug_in ? '#4CAF7D' : MUTED, flexShrink: 0 }}>
                        {u.dug_in ? 'Dug' : 'Ret'}
                      </span>
                    )}
                    <div style={{ width: 48, flexShrink: 0 }}>
                      <HpBar value={u.health} max={u.max_health} color={hpBarColor(hpFrac)} />
                    </div>
                    <span style={{ fontSize: 9, color: MUTED, minWidth: 24, textAlign: 'right' }}>
                      {Math.round(u.health)}
                    </span>
                  </div>
                );
              })}

              {attackerUnits.some(u => u.status !== 'destroyed') && defenderUnits.some(u => u.status !== 'destroyed') && (
                <div style={{ borderTop: `1px solid ${BORDER}`, margin: '4px 0' }} />
              )}

              {defenderUnits.filter(u => u.status !== 'destroyed').map(u => {
                const hpFrac = u.max_health > 0 ? u.health / u.max_health : 0;
                return (
                  <div key={u.unit_id} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '2px 0' }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: DEF, flexShrink: 0 }} />
                    <span style={{ flex: 1, fontSize: 10, color: DEF, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {TYPE_NAMES[u.unit_type] ?? u.unit_type}
                    </span>
                    {(u.dug_in || u.status === 'retreating') && (
                      <span style={{ fontSize: 9, color: u.dug_in ? '#4CAF7D' : MUTED, flexShrink: 0 }}>
                        {u.dug_in ? 'Dug' : 'Ret'}
                      </span>
                    )}
                    <div style={{ width: 48, flexShrink: 0 }}>
                      <HpBar value={u.health} max={u.max_health} color={hpBarColor(hpFrac)} />
                    </div>
                    <span style={{ fontSize: 9, color: MUTED, minWidth: 24, textAlign: 'right' }}>
                      {Math.round(u.health)}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Combat Log */}
        <div>
          <div
            style={{
              padding: '6px 12px', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              cursor: 'pointer',
            }}
            onClick={() => setLogOpen(!logOpen)}
          >
            <span style={{ fontSize: 10, color: MUTED, textTransform: 'uppercase', letterSpacing: '0.1em', fontWeight: 600 }}>
              Combat Log
            </span>
            <span style={{ fontSize: 9, color: MUTED }}>{logOpen ? '▲' : '▼'}</span>
          </div>
          {logOpen && (
            <div style={{ padding: '0 12px 8px', maxHeight: 128, overflowY: 'auto' }}>
              {state.combat_log.length === 0 ? (
                <div style={{ fontSize: 10, color: MUTED }}>No events yet</div>
              ) : (
                [...state.combat_log].reverse().slice(0, 20).map((entry, i) => {
                  const sideCol = entry.side === 'attacker' ? ATT : entry.side === 'defender' ? DEF : MUTED;
                  return (
                    <div key={`log-${i}`} style={{ display: 'flex', gap: 8, padding: '2px 0', fontSize: 10, lineHeight: 1.5 }}>
                      <span style={{ color: sideCol, flexShrink: 0, minWidth: 24, fontWeight: 600 }}>
                        {entry.side === 'attacker' ? 'Att' : entry.side === 'defender' ? 'Def' : '—'}
                      </span>
                      <span style={{ color: '#a0a8b8' }}>{entry.description}</span>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default memo(BattlefieldStatsPanel);
