import { useState } from 'react';
import type { ShaderMode } from '../../shaders/postprocess';
import MobileModal from './MobileModal';

interface OperationsPanelProps {
  shaderMode: ShaderMode;
  onShaderChange: (mode: ShaderMode) => void;
  mapTiles: 'google' | 'osm';
  onMapTilesChange: (tile: 'google' | 'osm') => void;
  onResetView: () => void;
  isMobile: boolean;
  geoConnected?: boolean;
  onStartGame?: () => void;
  startGameLoading?: boolean;
  startGameError?: string | null;
  onClearStartError?: () => void;
}

export default function OperationsPanel({
  onResetView,
  isMobile,
  geoConnected = false,
  onStartGame,
  startGameLoading = false,
  startGameError = null,
  onClearStartError,
  // kept for App compatibility; Optics/Map UI removed for simplicity
  shaderMode: _shaderMode,
  onShaderChange: _onShaderChange,
  mapTiles: _mapTiles,
  onMapTilesChange: _onMapTilesChange,
}: OperationsPanelProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  const panelContent = (
    <>
      <div className="px-3 py-2 border-b border-wv-border flex items-center gap-2">
        <div className={`w-1.5 h-1.5 rounded-full ${geoConnected ? 'bg-wv-green animate-pulse' : 'bg-wv-muted'}`} />
        <span className="text-[10px] text-wv-muted">
          {geoConnected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      {onStartGame && (
        <div className="p-2 border-b border-wv-border">
          <button
            onClick={onStartGame}
            disabled={startGameLoading}
            className={`w-full px-3 py-2 rounded text-[11px] text-wv-green bg-wv-green/10 hover:bg-wv-green/20 transition-colors disabled:opacity-60 disabled:cursor-not-allowed ${isMobile ? 'min-h-[44px]' : ''}`}
          >
            {startGameLoading ? 'Starting…' : 'Start game'}
          </button>
          {startGameError && (
            <div className="mt-1.5 flex items-start gap-1">
              <span className="text-[9px] text-wv-red flex-1">{startGameError}</span>
              {onClearStartError && (
                <button type="button" onClick={onClearStartError} className="text-[9px] text-wv-muted hover:text-wv-text shrink-0" aria-label="Dismiss">×</button>
              )}
            </div>
          )}
        </div>
      )}

      <div className="p-2">
        <button
          onClick={onResetView}
          className={`w-full px-3 py-2 rounded text-[11px] text-wv-muted hover:bg-white/5 transition-colors ${isMobile ? 'min-h-[44px]' : ''}`}
        >
          Reset view
        </button>
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
          {geoConnected && (
            <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-wv-green animate-pulse" />
          )}
        </button>

        <MobileModal
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          title="Controls"
          icon="⚙"
          accent="bg-wv-green"
        >
          {panelContent}
        </MobileModal>
      </>
    );
  }

  return (
    <div className="fixed top-4 left-4 w-40 panel-glass rounded-lg overflow-hidden z-40 select-none">
      <div className="px-3 py-2 border-b border-wv-border">
        <span className="text-[10px] text-wv-muted">Controls</span>
      </div>
      {panelContent}
    </div>
  );
}
