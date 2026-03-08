/**
 * BattlefieldStatsPanel — Full-featured right-side panel with unit roster,
 * objective capture bars, and a scrolling combat log.
 */
import { useState } from 'react';
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
  if (fraction > 0.6) return '#44FF44';
  if (fraction > 0.3) return '#FFCC00';
  return '#FF4444';
}

function MiniHpBar({ value, max, color }: { value: number; max: number; color?: string }) {
  const pct = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  const barColor = color ?? hpBarColor(pct / 100);
  return (
    <div className="w-full h-1.5 bg-white/10 rounded-full overflow-hidden">
      <div
        className="h-full rounded-full transition-all duration-300"
        style={{ width: `${pct}%`, backgroundColor: barColor }}
      />
    </div>
  );
}

export default function BattlefieldStatsPanel({ state, visible }: BattlefieldStatsPanelProps) {
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
    <div className="fixed top-4 right-4 z-40 select-none"
         style={{ width: 320, maxHeight: 'calc(100vh - 6rem)' }}>
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

      <div className="overflow-y-auto rounded-lg" style={{
        background: 'rgba(8,12,16,0.92)',
        border: '1px solid rgba(0,255,136,0.18)',
        fontFamily: 'monospace',
        fontSize: 11,
        color: '#c8d8c8',
        boxShadow: '0 0 12px rgba(0,255,136,0.08)',
        maxHeight: 'calc(100vh - 7rem)',
      }}>
        {/* Header + tick */}
        <div className="px-3 py-2 border-b border-white/5 flex items-center justify-between sticky top-0 z-10"
             style={{ background: 'rgba(8,12,16,0.95)' }}>
          <span style={{ color: 'rgba(0,255,136,0.6)', fontSize: 9, letterSpacing: 2 }}>
            BATTLEFIELD STATUS
          </span>
          <span style={{ color: 'rgba(0,255,136,0.5)', fontSize: 9 }}>
            TICK {state.tick}/{state.max_ticks}
          </span>
        </div>

        {/* Tick progress bar */}
        <div className="px-3 pt-2 pb-1">
          <div className="w-full h-1 bg-white/10 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500"
              style={{ width: `${tickPct}%`, background: 'rgba(0,255,136,0.5)' }}
            />
          </div>
        </div>

        {/* Side summary */}
        <div className="px-3 py-2 grid grid-cols-2 gap-x-3 border-b border-white/5">
          {/* Attacker */}
          <div>
            <div className="mb-1" style={{ color: '#FF6666', fontSize: 10, letterSpacing: 1 }}>
              ATTACKER
            </div>
            <div className="flex justify-between mb-0.5">
              <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 9 }}>UNITS</span>
              <span style={{ color: '#FF8888', fontSize: 9 }}>{attAlive}/{attackerUnits.length}</span>
            </div>
            <MiniHpBar value={attTotalHp} max={attMaxHp} color="#FF6666" />
            <div className="flex justify-between mt-1">
              <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 9 }}>RES</span>
              <span style={{ color: '#FFAA66', fontSize: 9 }}>{state.attacker_resources ?? '–'}</span>
            </div>
          </div>
          {/* Defender */}
          <div style={{ borderLeft: '1px solid rgba(0,255,136,0.08)', paddingLeft: 10 }}>
            <div className="mb-1" style={{ color: '#6699FF', fontSize: 10, letterSpacing: 1 }}>
              DEFENDER
            </div>
            <div className="flex justify-between mb-0.5">
              <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 9 }}>UNITS</span>
              <span style={{ color: '#88AAFF', fontSize: 9 }}>{defAlive}/{defenderUnits.length}</span>
            </div>
            <MiniHpBar value={defTotalHp} max={defMaxHp} color="#4488FF" />
            <div className="flex justify-between mt-1">
              <span style={{ color: 'rgba(255,255,255,0.5)', fontSize: 9 }}>RES</span>
              <span style={{ color: '#FFAA66', fontSize: 9 }}>{state.defender_resources ?? '–'}</span>
            </div>
          </div>
        </div>

        {/* Objectives */}
        {state.objectives.length > 0 && (
          <div className="px-3 py-2 border-b border-white/5">
            <div className="text-[8px] tracking-widest uppercase mb-1.5" style={{ color: 'rgba(0,255,136,0.5)' }}>
              Objectives
            </div>
            {state.objectives.map(obj => {
              let col = '#FFD700';
              let sideLabel = 'NEUTRAL';
              if (obj.controlling_side === 'attacker') { col = '#FF4444'; sideLabel = 'ATT'; }
              else if (obj.controlling_side === 'defender') { col = '#4488FF'; sideLabel = 'DEF'; }
              const capPct = Math.round((obj.capture_progress ?? 0) * 100);
              return (
                <div key={obj.objective_id} className="mb-1.5">
                  <div className="flex justify-between items-center mb-0.5">
                    <span style={{ fontSize: 10, color: col }}>
                      {obj.name || obj.objective_id}
                    </span>
                    <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.4)' }}>
                      {sideLabel} {capPct > 0 && capPct < 100 ? `${capPct}%` : ''}
                    </span>
                  </div>
                  <div className="w-full h-1 bg-white/10 rounded-full overflow-hidden">
                    <div className="h-full rounded-full transition-all duration-300"
                         style={{ width: `${capPct}%`, backgroundColor: col }} />
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Unit Roster */}
        <div className="border-b border-white/5">
          <div
            className="px-3 py-1.5 flex items-center justify-between cursor-pointer hover:bg-white/5"
            onClick={() => setRosterOpen(!rosterOpen)}
          >
            <span className="text-[8px] tracking-widest uppercase" style={{ color: 'rgba(0,255,136,0.5)' }}>
              Unit Roster
            </span>
            <span className="text-[9px] text-wv-muted">{rosterOpen ? '▼' : '▶'}</span>
          </div>
          {rosterOpen && (
            <div className="px-3 pb-2 max-h-48 overflow-y-auto">
              {/* Attacker units */}
              {attackerUnits.filter(u => u.status !== 'destroyed').map(u => {
                const hpFrac = u.max_health > 0 ? u.health / u.max_health : 0;
                return (
                  <div key={u.unit_id} className="flex items-center gap-2 py-0.5">
                    <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: '#FF4444' }} />
                    <span className="flex-1 truncate" style={{ fontSize: 9, color: '#FF8888' }}>
                      {TYPE_NAMES[u.unit_type] ?? u.unit_type}
                    </span>
                    <span style={{ fontSize: 8, color: u.dug_in ? '#44FF44' : 'rgba(255,255,255,0.3)', minWidth: 36, textAlign: 'right' }}>
                      {u.dug_in ? 'DUG IN' : u.status === 'retreating' ? 'RETR' : ''}
                    </span>
                    <div className="w-14 flex-shrink-0">
                      <MiniHpBar value={u.health} max={u.max_health} color={hpBarColor(hpFrac)} />
                    </div>
                    <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.4)', minWidth: 28, textAlign: 'right' }}>
                      {Math.round(u.health)}
                    </span>
                  </div>
                );
              })}

              {/* Divider between sides */}
              {attackerUnits.some(u => u.status !== 'destroyed') && defenderUnits.some(u => u.status !== 'destroyed') && (
                <div className="border-t border-white/5 my-1" />
              )}

              {/* Defender units */}
              {defenderUnits.filter(u => u.status !== 'destroyed').map(u => {
                const hpFrac = u.max_health > 0 ? u.health / u.max_health : 0;
                return (
                  <div key={u.unit_id} className="flex items-center gap-2 py-0.5">
                    <span className="w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: '#4488FF' }} />
                    <span className="flex-1 truncate" style={{ fontSize: 9, color: '#88AAFF' }}>
                      {TYPE_NAMES[u.unit_type] ?? u.unit_type}
                    </span>
                    <span style={{ fontSize: 8, color: u.dug_in ? '#44FF44' : 'rgba(255,255,255,0.3)', minWidth: 36, textAlign: 'right' }}>
                      {u.dug_in ? 'DUG IN' : u.status === 'retreating' ? 'RETR' : ''}
                    </span>
                    <div className="w-14 flex-shrink-0">
                      <MiniHpBar value={u.health} max={u.max_health} color={hpBarColor(hpFrac)} />
                    </div>
                    <span style={{ fontSize: 8, color: 'rgba(255,255,255,0.4)', minWidth: 28, textAlign: 'right' }}>
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
            className="px-3 py-1.5 flex items-center justify-between cursor-pointer hover:bg-white/5"
            onClick={() => setLogOpen(!logOpen)}
          >
            <span className="text-[8px] tracking-widest uppercase" style={{ color: 'rgba(0,255,136,0.5)' }}>
              Combat Log
            </span>
            <span className="text-[9px] text-wv-muted">{logOpen ? '▼' : '▶'}</span>
          </div>
          {logOpen && (
            <div className="px-3 pb-2 max-h-32 overflow-y-auto">
              {state.combat_log.length === 0 ? (
                <div style={{ fontSize: 9, color: 'rgba(255,255,255,0.2)' }}>No events yet</div>
              ) : (
                [...state.combat_log].reverse().slice(0, 20).map((entry, i) => {
                  const sideCol = entry.side === 'attacker' ? '#FF8888' : entry.side === 'defender' ? '#88AAFF' : 'rgba(255,255,255,0.4)';
                  return (
                    <div key={`log-${i}`} className="py-0.5 text-[9px] leading-tight flex gap-1.5">
                      <span style={{ color: sideCol, flexShrink: 0, minWidth: 20 }}>
                        {entry.side === 'attacker' ? 'ATT' : entry.side === 'defender' ? 'DEF' : '---'}
                      </span>
                      <span style={{ color: 'rgba(255,255,255,0.6)' }}>{entry.description}</span>
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
