import { useState, memo } from 'react';
import type { ShaderMode } from '../../shaders/postprocess';
import MobileModal from './MobileModal';

const BATTLEFIELD_SCENARIOS = [
  { id: 'crossing_at_korzha', label: 'Korzha Bridge' },
  { id: 'urban_stronghold', label: 'Urban Stronghold' },
  { id: 'desert_armored_thrust', label: 'Desert Thrust' },
];

const SHADER_OPTIONS: { value: ShaderMode; label: string }[] = [
  { value: 'none', label: 'Standard' },
  { value: 'crt', label: 'CRT' },
  { value: 'nvg', label: 'NVG' },
  { value: 'flir', label: 'FLIR' },
];

interface OperationsPanelProps {
  shaderMode: ShaderMode;
  onShaderChange: (mode: ShaderMode) => void;
  isMobile: boolean;
  battlefieldConnected?: boolean;
  battlefieldScenario?: string;
  onBattlefieldScenarioChange?: (id: string) => void;
  onBattlefieldConnect?: () => void;
  onBattlefieldDisconnect?: () => void;
  battlefieldTick?: number;
  battlefieldMaxTicks?: number;
  battlefieldWinner?: string | null;
  battlefieldAutoPlaying?: boolean;
  onBattlefieldAutoPlayStart?: () => void;
  onBattlefieldAutoPlayStop?: () => void;
}

const S = {
  panel: {
    background: '#161b27',
    border: '1px solid #252d3d',
    borderLeft: '2px solid #E8A045',
  } as React.CSSProperties,
  header: {
    padding: '8px 12px',
    borderBottom: '1px solid #252d3d',
    display: 'flex',
    alignItems: 'center',
    gap: 8,
  } as React.CSSProperties,
  headerLabel: {
    fontSize: 11,
    fontWeight: 600,
    letterSpacing: '0.12em',
    color: '#E8A045',
    textTransform: 'uppercase' as const,
  },
  sectionLabel: {
    fontSize: 10,
    color: '#5a6478',
    textTransform: 'uppercase' as const,
    letterSpacing: '0.12em',
    marginBottom: 6,
  },
  section: {
    padding: '10px 12px',
    borderBottom: '1px solid #252d3d',
  } as React.CSSProperties,
  select: {
    width: '100%',
    background: '#0f1117',
    border: '1px solid #252d3d',
    color: '#d4dbe8',
    fontSize: 11,
    padding: '5px 8px',
    borderRadius: 3,
    marginBottom: 8,
    outline: 'none',
  } as React.CSSProperties,
  btn: (active: boolean, variant: 'connect' | 'disconnect' | 'run' | 'stop' | 'shader') => {
    const colors: Record<string, { color: string; border: string }> = {
      connect: { color: '#4CAF7D', border: '#4CAF7D' },
      disconnect: { color: '#D64045', border: '#D64045' },
      run: { color: '#E8A045', border: '#E8A045' },
      stop: { color: '#5a6478', border: '#5a6478' },
      shader: { color: active ? '#E8A045' : '#5a6478', border: active ? '#E8A045' : '#252d3d' },
    };
    const c = colors[variant];
    return {
      width: '100%',
      background: active ? `${c.color}18` : '#0f1117',
      border: `1px solid ${active ? c.border : '#252d3d'}`,
      color: active ? c.color : '#5a6478',
      fontSize: 11,
      fontWeight: 600,
      letterSpacing: '0.08em',
      padding: '6px 10px',
      borderRadius: 3,
      cursor: 'pointer',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 6,
      marginBottom: 6,
    } as React.CSSProperties;
  },
};

function OperationsPanel({
  shaderMode,
  onShaderChange,
  isMobile,
  battlefieldConnected = false,
  battlefieldScenario = 'crossing_at_korzha',
  onBattlefieldScenarioChange,
  onBattlefieldConnect,
  onBattlefieldDisconnect,
  battlefieldTick,
  battlefieldMaxTicks,
  battlefieldWinner,
  battlefieldAutoPlaying = false,
  onBattlefieldAutoPlayStart,
  onBattlefieldAutoPlayStop,
}: OperationsPanelProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  const panelContent = (
    <>
      {/* Optics */}
      <div style={S.section}>
        <div style={S.sectionLabel}>View Mode</div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
          {SHADER_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => onShaderChange(value)}
              style={S.btn(shaderMode === value, 'shader')}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Battlefield */}
      <div style={S.section}>
        <div style={S.sectionLabel}>Battlefield Sim</div>

        <select
          value={battlefieldScenario}
          onChange={(e) => onBattlefieldScenarioChange?.(e.target.value)}
          disabled={battlefieldConnected}
          style={{ ...S.select, opacity: battlefieldConnected ? 0.5 : 1 }}
        >
          {BATTLEFIELD_SCENARIOS.map(({ id, label }) => (
            <option key={id} value={id}>{label}</option>
          ))}
        </select>

        <button
          onClick={battlefieldConnected ? onBattlefieldDisconnect : onBattlefieldConnect}
          style={S.btn(battlefieldConnected, battlefieldConnected ? 'disconnect' : 'connect')}
        >
          <span
            style={{
              width: 6, height: 6, borderRadius: '50%',
              background: battlefieldConnected ? '#D64045' : '#252d3d',
              flexShrink: 0,
            }}
          />
          {battlefieldConnected ? 'Disconnect' : 'Connect'}
        </button>

        {battlefieldConnected && (
          <button
            onClick={battlefieldAutoPlaying ? onBattlefieldAutoPlayStop : onBattlefieldAutoPlayStart}
            style={S.btn(battlefieldAutoPlaying, battlefieldAutoPlaying ? 'stop' : 'run')}
          >
            <span>{battlefieldAutoPlaying ? '■' : '▶'}</span>
            {battlefieldAutoPlaying ? 'Stop Sim' : 'Run Sim'}
          </button>
        )}

        {battlefieldTick !== undefined && battlefieldMaxTicks !== undefined && (
          <div style={{ fontSize: 10, color: '#5a6478', textAlign: 'center', marginTop: 4 }}>
            Tick{' '}
            <span style={{ color: '#E8A045', fontWeight: 600 }}>{battlefieldTick}</span>
            <span style={{ color: '#252d3d' }}> / </span>
            <span style={{ color: '#d4dbe8' }}>{battlefieldMaxTicks}</span>
          </div>
        )}

        {battlefieldWinner && (
          <div style={{
            marginTop: 8,
            padding: '5px 8px',
            borderLeft: `2px solid ${battlefieldWinner === 'attacker' ? '#D64045' : '#5B8DB8'}`,
            background: battlefieldWinner === 'attacker' ? '#D6404518' : '#5B8DB818',
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '0.1em',
            color: battlefieldWinner === 'attacker' ? '#D64045' : '#5B8DB8',
            textTransform: 'uppercase',
          }}>
            {battlefieldWinner} Victory
          </div>
        )}
      </div>
    </>
  );

  if (isMobile) {
    return (
      <>
        <button
          onClick={() => setMobileOpen(true)}
          style={{
            position: 'fixed', top: 12, left: 12, zIndex: 40,
            width: 44, height: 44, borderRadius: 6,
            background: '#161b27', border: '1px solid #252d3d',
            borderLeft: '2px solid #E8A045',
            color: '#E8A045', fontSize: 18, cursor: 'pointer',
          }}
          aria-label="Open operations panel"
        >
          ⚙
        </button>
        <MobileModal
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          title="Operations"
          icon="⚙"
          accent="bg-wv-amber"
        >
          {panelContent}
        </MobileModal>
      </>
    );
  }

  return (
    <div
      style={{
        position: 'fixed', top: 16, left: 16,
        width: 220, zIndex: 40,
        maxHeight: 'calc(100vh - 2rem)',
        overflowY: 'auto',
        ...S.panel,
        borderRadius: 4,
      }}
    >
      <div style={S.header}>
        <span style={S.headerLabel}>Ops</span>
        <span style={{
          fontSize: 9, color: '#5a6478',
          letterSpacing: '0.1em', textTransform: 'uppercase',
          marginLeft: 'auto',
        }}>
          {battlefieldConnected ? 'Live' : 'Offline'}
        </span>
        {battlefieldConnected && (
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#E8A045', flexShrink: 0 }} />
        )}
      </div>
      {panelContent}
    </div>
  );
}

export default memo(OperationsPanel);
