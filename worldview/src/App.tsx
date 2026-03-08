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

  const [viewerReady, setViewerReady] = useState(false);

  const [battlefieldScenario, setBattlefieldScenario] = useState('crossing_at_korzha');
  const [battlefieldAutoPlaying, setBattlefieldAutoPlaying] = useState(false);
  const [battlefieldError, setBattlefieldError] = useState<string | null>(null);

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
    setViewerReady(true);
  }, []);

  // Tracks whether the camera has flown to the battlefield yet (reset on re-connect)
  const hasFlewToBattlefield = useRef(false);

  // Wrap connect so that re-connecting always allows one fresh fly-to
  const handleBattlefieldConnect = useCallback(() => {
    hasFlewToBattlefield.current = false;
    battlefieldConnect();
  }, [battlefieldConnect]);

  // Auto-connect to battlefield on boot
  const hasAutoConnected = useRef(false);
  useEffect(() => {
    if (booted && !hasAutoConnected.current) {
      hasAutoConnected.current = true;
      handleBattlefieldConnect();
    }
  }, [booted, handleBattlefieldConnect]);

  // Fly to battlefield once on first connect/state arrival.
  // Does NOT re-fly on every new training episode — camera stays where user left it.
  // Re-runs when viewerReady flips, in case state arrived before the viewer was initialised.
  useEffect(() => {
    if (!battlefieldState) return;
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    if (hasFlewToBattlefield.current) return;  // only fly once per connect
    hasFlewToBattlefield.current = true;
    const anchor = battlefieldState.geo_anchor;
    const lat0 = (anchor?.lat0 != null) ? anchor.lat0 : 48.5;
    const lon0 = (anchor?.lon0 != null) ? anchor.lon0 : 22.2;
    const scale = anchor?.scale_m_per_cell ?? 100;
    const mapW = anchor?.map_width_cells ?? 300;
    const mapH = anchor?.map_height_cells ?? 300;

    // Compute geographic center of the battlefield (geo_anchor is the grid x=0,y=0 origin)
    const cosLat = Math.cos(lat0 * Math.PI / 180) || 0.0001;
    const centerLat = lat0 + (mapH / 2 * scale) / 111320;
    const centerLon = lon0 + (mapW / 2 * scale) / (111320 * cosLat);

    // Altitude: fit the battlefield diagonal in view with 1.5× padding, clamped to 40–120 km
    const mapDiagMeters = Math.sqrt((mapW * scale) ** 2 + (mapH * scale) ** 2);
    const altitude = Math.max(40_000, Math.min(120_000, mapDiagMeters * 1.5));

    viewer.trackedEntity = undefined;
    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(centerLon, centerLat, altitude),
      orientation: {
        heading: CesiumMath.toRadians(0),
        pitch: CesiumMath.toRadians(-55),
        roll: 0,
      },
      duration: 2,
    });
    if (!viewer.isDestroyed()) viewer.scene.requestRender();
  }, [battlefieldState, viewerReady]); // viewerReady in deps so we retry if viewer wasn't ready

  // Auto-play handlers
  const handleBattlefieldAutoPlayStart = useCallback(async () => {
    setBattlefieldError(null);
    try {
      const res = await fetch('/api/battlefield/auto_play/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario_id: battlefieldScenario, tick_delay_ms: 800 }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setBattlefieldError(body?.error ?? `Server error ${res.status}`);
        return;
      }
      setBattlefieldAutoPlaying(true);
    } catch (err) {
      setBattlefieldError('Backend unavailable — ensure the battlefield service is running.');
    }
  }, [battlefieldScenario]);

  const handleBattlefieldAutoPlayStop = useCallback(async () => {
    try {
      await fetch('/api/battlefield/auto_play/stop', { method: 'POST' });
      setBattlefieldAutoPlaying(false);
      setBattlefieldError(null);
    } catch { /* ignore */ }
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
        onBattlefieldConnect={handleBattlefieldConnect}
        onBattlefieldDisconnect={battlefieldDisconnect}
        battlefieldTick={battlefieldState?.tick}
        battlefieldMaxTicks={battlefieldState?.max_ticks}
        battlefieldWinner={battlefieldState?.winner}
        battlefieldAutoPlaying={battlefieldAutoPlaying}
        onBattlefieldAutoPlayStart={handleBattlefieldAutoPlayStart}
        onBattlefieldAutoPlayStop={handleBattlefieldAutoPlayStop}
        battlefieldError={battlefieldError}
        battlefieldTrainingMode={battlefieldState?.training_mode}
        battlefieldEpisode={battlefieldState?.episode}
      />
      <BattlefieldStatsPanel state={battlefieldState} visible={true} />
      <IntelFeed items={allFeedItems} isMobile={isMobile} />
      <StatusBar
        camera={camera}
        shaderMode={shaderMode}
        isMobile={isMobile}
        battlefieldTick={battlefieldState?.tick}
        battlefieldUnits={battlefieldState?.units.length}
      />
      <AudioToggle muted={audio.muted} onToggle={audio.toggleMute} isMobile={isMobile} />
    </div>
  );
}

export default App;
