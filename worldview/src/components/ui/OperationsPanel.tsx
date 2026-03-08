import { useState } from 'react';
import type { ShaderMode } from '../../shaders/postprocess';
import MobileModal from './MobileModal';

const BATTLEFIELD_SCENARIOS = [
  { id: 'crossing_at_korzha', label: 'Korzha Bridge' },
  { id: 'urban_stronghold', label: 'Urban Stronghold' },
  { id: 'desert_armored_thrust', label: 'Desert Thrust' },
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

const SHADER_OPTIONS: { value: ShaderMode; label: string; colour: string }[] = [
  { value: 'none', label: 'STANDARD', colour: 'text-wv-text' },
  { value: 'crt', label: 'CRT', colour: 'text-wv-cyan' },
  { value: 'nvg', label: 'NVG', colour: 'text-wv-green' },
  { value: 'flir', label: 'FLIR', colour: 'text-wv-amber' },
];

export default function OperationsPanel({
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
      {/* Optics Section */}
      <div className="p-3 border-b border-wv-border">
        <div className="text-[9px] text-wv-muted tracking-widest uppercase mb-2">Optics Mode</div>
        <div className="grid grid-cols-2 gap-1">
          {SHADER_OPTIONS.map(({ value, label, colour }) => (
            <button
              key={value}
              onClick={() => onShaderChange(value)}
              className={`
                px-2 py-1.5 rounded text-[10px] font-bold tracking-wider
                transition-all duration-200
                ${isMobile ? 'min-h-[44px]' : ''}
                ${shaderMode === value
                  ? `${colour} bg-white/10 ring-1 ring-white/20`
                  : 'text-wv-muted hover:text-wv-text hover:bg-white/5'
                }
              `}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Battlefield Controls */}
      <div className="p-3 border-b border-wv-border">
        <div className="text-[9px] text-wv-muted tracking-widest uppercase mb-2">Battlefield Sim</div>

        <select
          value={battlefieldScenario}
          onChange={(e) => onBattlefieldScenarioChange?.(e.target.value)}
          disabled={battlefieldConnected}
          className="w-full mb-2 px-2 py-1.5 rounded text-[10px] tracking-wider
            bg-wv-black/60 border border-wv-border text-wv-text
            disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {BATTLEFIELD_SCENARIOS.map(({ id, label }) => (
            <option key={id} value={id}>{label}</option>
          ))}
        </select>

        <button
          onClick={battlefieldConnected ? onBattlefieldDisconnect : onBattlefieldConnect}
          className={`
            w-full px-3 py-1.5 rounded text-[10px] font-bold tracking-wider mb-2
            transition-all duration-200 flex items-center justify-center gap-2
            ${isMobile ? 'min-h-[44px]' : ''}
            ${battlefieldConnected
              ? 'text-wv-red bg-wv-red/10 hover:bg-wv-red/20'
              : 'text-wv-green bg-wv-green/10 hover:bg-wv-green/20'
            }
          `}
        >
          <span className={`w-1.5 h-1.5 rounded-full ${battlefieldConnected ? 'bg-wv-red animate-pulse' : 'bg-wv-muted/30'}`} />
          <span>{battlefieldConnected ? 'DISCONNECT' : 'CONNECT'}</span>
        </button>

        {battlefieldConnected && (
          <button
            onClick={battlefieldAutoPlaying ? onBattlefieldAutoPlayStop : onBattlefieldAutoPlayStart}
            className={`
              w-full px-3 py-1.5 rounded text-[10px] font-bold tracking-wider mb-2
              transition-all duration-200 flex items-center justify-center gap-2
              ${isMobile ? 'min-h-[44px]' : ''}
              ${battlefieldAutoPlaying
                ? 'text-wv-amber bg-wv-amber/10 hover:bg-wv-amber/20'
                : 'text-wv-cyan bg-wv-cyan/10 hover:bg-wv-cyan/20'
              }
            `}
          >
            <span>{battlefieldAutoPlaying ? '⏹' : '▶'}</span>
            <span>{battlefieldAutoPlaying ? 'STOP SIM' : 'RUN SIM'}</span>
            {battlefieldAutoPlaying && <span className="w-1.5 h-1.5 rounded-full bg-wv-amber animate-pulse" />}
          </button>
        )}

        {battlefieldTick !== undefined && battlefieldMaxTicks !== undefined && (
          <div className="text-[9px] text-wv-muted tracking-wider text-center mb-1">
            TICK{' '}
            <span className="text-wv-cyan font-bold">{battlefieldTick}</span>
            {' / '}
            <span className="text-wv-text">{battlefieldMaxTicks}</span>
          </div>
        )}

        {battlefieldWinner && (
          <div className={`
            text-center text-[10px] font-bold tracking-widest py-1 rounded
            ${battlefieldWinner === 'attacker' ? 'text-wv-red bg-wv-red/20' : 'text-[#4488FF] bg-[#4488FF]/20'}
          `}>
            WINNER: {battlefieldWinner.toUpperCase()}
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
          className="fixed top-3 left-3 z-40 w-11 h-11 rounded-lg panel-glass
                     flex items-center justify-center
                     text-wv-green hover:bg-white/10 transition-colors
                     select-none active:scale-95"
          aria-label="Open operations panel"
        >
          <span className="text-lg">⚙</span>
        </button>

        <MobileModal
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          title="Operations"
          icon="⚙"
          accent="bg-wv-green"
        >
          {panelContent}
        </MobileModal>
      </>
    );
  }

  return (
    <div className="fixed top-4 left-4 w-56 panel-glass rounded-lg overflow-hidden z-40 select-none max-h-[calc(100vh-2rem)] overflow-y-auto">
      <div className="px-3 py-2 border-b border-wv-border flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-wv-green animate-pulse" />
        <span className="text-[10px] text-wv-muted tracking-widest uppercase">Operations</span>
      </div>
      {panelContent}
    </div>
  );
}
