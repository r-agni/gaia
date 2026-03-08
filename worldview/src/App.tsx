import { useState, useCallback, useRef, useEffect } from 'react';
import { Viewer as CesiumViewer, Cartesian3, Math as CesiumMath } from 'cesium';
import GlobeViewer from './components/globe/GlobeViewer';
import GeoguessLayer from './components/layers/GeoguessLayer';
import OperationsPanel from './components/ui/OperationsPanel';
import StatusBar from './components/ui/StatusBar';
import GeoSidebar from './components/ui/GeoSidebar';
import AudioToggle from './components/ui/AudioToggle';
import Crosshair from './components/ui/Crosshair';
import SplashScreen from './components/ui/SplashScreen';
import GeoguessStatsPanel from './components/ui/GeoguessStatsPanel';
import FilmGrain from './components/ui/FilmGrain';
import TrainingResultsView from './components/ui/TrainingResultsView';
import { useGeoguess } from './hooks/useGeoguess';
import { useIsMobile } from './hooks/useIsMobile';
import { useAudio } from './hooks/useAudio';
import type { ShaderMode } from './shaders/postprocess';

function App() {
  const isMobile = useIsMobile();
  const audio = useAudio();
  const viewerRef = useRef<CesiumViewer | null>(null);

  const [booted, setBooted] = useState(false);
  const [shaderMode, setShaderMode] = useState<ShaderMode>('none');
  const [mapTiles, setMapTiles] = useState<'google' | 'osm'>('google');
  const [activeView, setActiveView] = useState<'globe' | 'training'>('globe');
  const [camera, setCamera] = useState({
    latitude: 0,
    longitude: 0,
    altitude: 15_000_000,
    heading: 0,
    pitch: -90,
  });

  const { state: geoState, connected: geoConnected } = useGeoguess(true);

  // Auto-fly to the agent's current guess location as it updates
  const lastGuessRef = useRef<{ lat: number; lon: number } | null>(null);
  useEffect(() => {
    if (!geoState?.current_guess_lat || !geoState?.current_guess_lon) return;
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;

    const { current_guess_lat: lat, current_guess_lon: lon } = geoState;

    const prev = lastGuessRef.current;
    if (prev && Math.abs(prev.lat - lat) < 0.0001 && Math.abs(prev.lon - lon) < 0.0001) return;
    lastGuessRef.current = { lat, lon };

    viewer.trackedEntity = undefined;
    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(lon, lat, 400_000),
      orientation: {
        heading: CesiumMath.toRadians(0),
        pitch: CesiumMath.toRadians(-45),
        roll: 0,
      },
      duration: 2.5,
    });
  }, [geoState?.current_guess_lat, geoState?.current_guess_lon]);

  // When secret location is revealed (round ends), fly to actual location
  const lastSecretRef = useRef<{ lat: number; lon: number } | null>(null);
  useEffect(() => {
    if (!geoState?.secret_lat || !geoState?.secret_lon) return;
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;

    const { secret_lat: lat, secret_lon: lon } = geoState;
    const prev = lastSecretRef.current;
    if (prev && Math.abs(prev.lat - lat) < 0.0001 && Math.abs(prev.lon - lon) < 0.0001) return;
    lastSecretRef.current = { lat, lon };

    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(lon, lat, 200_000),
      orientation: {
        heading: CesiumMath.toRadians(0),
        pitch: CesiumMath.toRadians(-60),
        roll: 0,
      },
      duration: 2,
    });
  }, [geoState?.secret_lat, geoState?.secret_lon]);

  const handleViewerReady = useCallback((viewer: CesiumViewer) => {
    viewerRef.current = viewer;
  }, []);

  const handleResetView = useCallback(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    viewer.trackedEntity = undefined;
    viewer.camera.flyTo({
      destination: Cartesian3.fromDegrees(0, 20, 20_000_000),
      orientation: {
        heading: CesiumMath.toRadians(0),
        pitch: CesiumMath.toRadians(-90),
        roll: 0,
      },
      duration: 2,
    });
  }, []);

  const handleCameraChange = useCallback(
    (lat: number, lon: number, alt: number, heading: number, pitch: number) => {
      setCamera({ latitude: lat, longitude: lon, altitude: alt, heading, pitch });
    },
    []
  );

  const handleBootComplete = useCallback(() => {
    audio.play('bootComplete');
    audio.startAmbient();
    setBooted(true);
  }, [audio]);

  const [startGameLoading, setStartGameLoading] = useState(false);
  const [startGameError, setStartGameError] = useState<string | null>(null);

  const gameInProgress = !!(geoState && !geoState.is_terminal && geoState.episode_id);

  const handleStartGame = useCallback(async () => {
    setStartGameError(null);
    setStartGameLoading(true);
    try {
      const r = await fetch('/api/geoguess/run_game', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ use_llm: false, step_delay_ms: 400 }),
      });
      if (!r.ok) {
        const text = await r.text();
        let msg = 'Could not start game.';
        try {
          const j = JSON.parse(text);
          if (j.error) msg = j.error;
          if (j.detail) msg += ` ${j.detail}`;
        } catch {
          if (text) msg = text.slice(0, 120);
        }
        setStartGameError(msg);
      }
    } catch {
      setStartGameError('Network error — are both servers running?');
    } finally {
      setStartGameLoading(false);
    }
  }, []);

  const handleToggleTrainingView = useCallback(() => {
    audio.play('click');
    setActiveView(v => v === 'globe' ? 'training' : 'globe');
  }, [audio]);

  if (!booted) {
    return <SplashScreen onComplete={handleBootComplete} audio={audio} />;
  }

  const showingTrainingView = activeView === 'training';

  return (
    <div className="w-screen h-screen bg-wv-black overflow-hidden">
      <FilmGrain opacity={0.04} />

      {!showingTrainingView && (
        <>
          <GlobeViewer
            shaderMode={shaderMode}
            mapTiles={mapTiles}
            onCameraChange={handleCameraChange}
            onViewerReady={handleViewerReady}
          >
            <GeoguessLayer state={geoState} visible={true} />
          </GlobeViewer>

          <Crosshair />

          <GeoSidebar state={geoState} connected={geoConnected} isMobile={isMobile} />
          <GeoguessStatsPanel state={geoState} visible={true} />

          <StatusBar
            camera={camera}
            shaderMode={shaderMode}
            isMobile={isMobile}
          />
        </>
      )}

      {showingTrainingView && (
        <TrainingResultsView onClose={() => setActiveView('globe')} />
      )}

      <OperationsPanel
        shaderMode={shaderMode}
        onShaderChange={(mode) => { audio.play('shaderSwitch'); setShaderMode(mode); }}
        mapTiles={mapTiles}
        onMapTilesChange={(t) => { audio.play('click'); setMapTiles(t); }}
        onResetView={() => { audio.play('click'); handleResetView(); }}
        onStartGame={() => { audio.play('click'); handleStartGame(); }}
        startGameLoading={startGameLoading}
        gameInProgress={gameInProgress}
        startGameError={startGameError}
        onClearStartError={() => setStartGameError(null)}
        onToggleTrainingView={handleToggleTrainingView}
        showingTrainingView={showingTrainingView}
        isMobile={isMobile}
        geoConnected={geoConnected}
      />

      <AudioToggle muted={audio.muted} onToggle={audio.toggleMute} isMobile={isMobile} />
    </div>
  );
}

export default App;
