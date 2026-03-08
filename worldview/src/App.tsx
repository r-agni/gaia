import { useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { Viewer as CesiumViewer, Cartesian3, Math as CesiumMath } from 'cesium';
import GlobeViewer from './components/globe/GlobeViewer';
import BattlefieldLayer from './components/layers/BattlefieldLayer';
import OperationsPanel from './components/ui/OperationsPanel';
import StatusBar from './components/ui/StatusBar';
import IntelFeed from './components/ui/IntelFeed';
import AudioToggle from './components/ui/AudioToggle';
import Crosshair from './components/ui/Crosshair';
import SplashScreen from './components/ui/SplashScreen';
import BattlefieldStatsPanel from './components/ui/BattlefieldStatsPanel';
import { useBattlefield } from './hooks/useBattlefield';
import { useIsMobile } from './hooks/useIsMobile';
import { useAudio } from './hooks/useAudio';
import type { ShaderMode } from './shaders/postprocess';
import type { IntelFeedItem } from './components/ui/IntelFeed';

function App() {
  const isMobile = useIsMobile();
  const audio = useAudio();
  const viewerRef = useRef<CesiumViewer | null>(null);

  const [booted, setBooted] = useState(false);
  const [shaderMode, setShaderMode] = useState<ShaderMode>('none');

  const [battlefieldScenario, setBattlefieldScenario] = useState('crossing_at_korzha');
  const [battlefieldAutoPlaying, setBattlefieldAutoPlaying] = useState(false);

  const [camera, setCamera] = useState({
    latitude: 48.5,
    longitude: 22.2,
    altitude: 50000,
    heading: 0,
    pitch: -45,
  });

  const {
    state: battlefieldState,
    feedItems: battlefieldFeedItems,
    isConnected: battlefieldConnected,
    connect: battlefieldConnect,
    disconnect: battlefieldDisconnect,
  } = useBattlefield(true);

  const handleViewerReady = useCallback((viewer: CesiumViewer) => {
    viewerRef.current = viewer;
  }, []);

  // Auto-connect to battlefield on boot
  const hasAutoConnected = useRef(false);
  useEffect(() => {
    if (booted && !hasAutoConnected.current) {
      hasAutoConnected.current = true;
      battlefieldConnect();
    }
  }, [booted, battlefieldConnect]);

  // Fly to battlefield when first state arrives or when a new episode starts (e.g. Run Sim)
  const hasFlewToBattlefield = useRef(false);
  useEffect(() => {
    if (!battlefieldState) return;
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    const isNewEpisode = battlefieldState.tick === 0;
    if (!hasFlewToBattlefield.current || isNewEpisode) {
      hasFlewToBattlefield.current = true;
      const anchor = battlefieldState.geo_anchor;
      const lon = anchor ? anchor.lon0 : 22.2;
      const lat = anchor ? anchor.lat0 : 48.5;
      viewer.trackedEntity = undefined;
      viewer.camera.flyTo({
        destination: Cartesian3.fromDegrees(lon, lat, 12_000),
        orientation: {
          heading: CesiumMath.toRadians(0),
          pitch: CesiumMath.toRadians(-60),
          roll: 0,
        },
        duration: 2,
      });
    }
  }, [battlefieldState]);

  // Auto-play handlers
  const handleBattlefieldAutoPlayStart = useCallback(async () => {
    try {
      await fetch('/api/battlefield/auto_play/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario_id: battlefieldScenario, tick_delay_ms: 800 }),
      });
      setBattlefieldAutoPlaying(true);
    } catch { /* server not running */ }
  }, [battlefieldScenario]);

  const handleBattlefieldAutoPlayStop = useCallback(async () => {
    try {
      await fetch('/api/battlefield/auto_play/stop', { method: 'POST' });
      setBattlefieldAutoPlaying(false);
    } catch { /* server not running */ }
  }, []);

  const allFeedItems = useMemo<IntelFeedItem[]>(
    () => [...battlefieldFeedItems],
    [battlefieldFeedItems]
  );

  const onShaderChange = useCallback((mode: ShaderMode) => {
    audio.play('shaderSwitch');
    setShaderMode(mode);
  }, [audio]);

  const cameraThrottleRef = useRef(0);
  const handleCameraChange = useCallback(
    (lat: number, lon: number, alt: number, heading: number, pitch: number) => {
      const now = Date.now();
      if (now - cameraThrottleRef.current < 150) return;
      cameraThrottleRef.current = now;
      setCamera({ latitude: lat, longitude: lon, altitude: alt, heading, pitch });
    },
    []
  );

  const handleBootComplete = useCallback(() => {
    audio.play('bootComplete');
    audio.startAmbient();
    setBooted(true);
  }, [audio]);

  if (!booted) {
    return <SplashScreen onComplete={handleBootComplete} audio={audio} />;
  }

  return (
    <div className="w-screen h-screen overflow-hidden" style={{ background: '#0f1117' }}>
      <GlobeViewer
        shaderMode={shaderMode}
        mapTiles="google"
        onCameraChange={handleCameraChange}
        onTrackEntity={() => {}}
        onViewerReady={handleViewerReady}
      >
        <BattlefieldLayer
          state={battlefieldState}
          visible={true}
          isTracking={false}
        />
      </GlobeViewer>

      <Crosshair />
      <OperationsPanel
        shaderMode={shaderMode}
        onShaderChange={onShaderChange}
        isMobile={isMobile}
        battlefieldConnected={battlefieldConnected}
        battlefieldScenario={battlefieldScenario}
        onBattlefieldScenarioChange={setBattlefieldScenario}
        onBattlefieldConnect={battlefieldConnect}
        onBattlefieldDisconnect={battlefieldDisconnect}
        battlefieldTick={battlefieldState?.tick}
        battlefieldMaxTicks={battlefieldState?.max_ticks}
        battlefieldWinner={battlefieldState?.winner}
        battlefieldAutoPlaying={battlefieldAutoPlaying}
        onBattlefieldAutoPlayStart={handleBattlefieldAutoPlayStart}
        onBattlefieldAutoPlayStop={handleBattlefieldAutoPlayStop}
      />
      <BattlefieldStatsPanel state={battlefieldState} visible={true} />
      <IntelFeed items={allFeedItems} isMobile={isMobile} />
      <StatusBar
        camera={camera}
        shaderMode={shaderMode}
        isMobile={isMobile}
        battlefieldTick={battlefieldState?.tick}
        battlefieldUnits={battlefieldState?.units.length ?? 0}
      />
      <AudioToggle muted={audio.muted} onToggle={audio.toggleMute} isMobile={isMobile} />
    </div>
  );
}

export default App;
