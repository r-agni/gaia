import { useState, useEffect, memo } from 'react';

interface CameraState {
  latitude: number;
  longitude: number;
  altitude: number;
  heading: number;
  pitch: number;
}

interface StatusBarProps {
  camera: CameraState;
  shaderMode: string;
  isMobile?: boolean;
  battlefieldTick?: number;
  battlefieldUnits?: number;
}

function formatCoord(value: number, posLabel: string, negLabel: string): string {
  const abs = Math.abs(value);
  const deg = Math.floor(abs);
  const min = Math.floor((abs - deg) * 60);
  const sec = ((abs - deg - min / 60) * 3600).toFixed(1);
  return `${deg}°${min}'${sec}" ${value >= 0 ? posLabel : negLabel}`;
}

function formatAltitude(metres: number): string {
  if (metres > 100000) return `${(metres / 1000).toFixed(0)} km`;
  if (metres > 1000) return `${(metres / 1000).toFixed(1)} km`;
  return `${metres.toFixed(0)} m`;
}

const barStyle: React.CSSProperties = {
  position: 'fixed',
  bottom: 0, left: 0, right: 0,
  background: '#161b27',
  borderTop: '1px solid #252d3d',
  borderLeft: 'none',
  zIndex: 50,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  userSelect: 'none',
};

const labelStyle: React.CSSProperties = { color: '#5a6478', fontSize: 11 };
const valStyle: React.CSSProperties = { color: '#d4dbe8', fontSize: 11 };
const sepStyle: React.CSSProperties = { color: '#252d3d', margin: '0 4px' };

function StatusBar({ camera, shaderMode, isMobile = false, battlefieldTick, battlefieldUnits }: StatusBarProps) {
  const [clock, setClock] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setClock(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const utcTime = clock.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
  const lat = formatCoord(camera.latitude, 'N', 'S');
  const lon = formatCoord(camera.longitude, 'E', 'W');
  const alt = formatAltitude(camera.altitude);
  const hdg = `${camera.heading.toFixed(1)}°`;

  const latShort = `${Math.abs(camera.latitude).toFixed(2)}°${camera.latitude >= 0 ? 'N' : 'S'}`;
  const lonShort = `${Math.abs(camera.longitude).toFixed(2)}°${camera.longitude >= 0 ? 'E' : 'W'}`;
  const utcShort = clock.toISOString().slice(11, 19) + 'Z';

  if (isMobile) {
    return (
      <div style={{ ...barStyle, height: 28, padding: '0 12px' }} className="mobile-safe-bottom">
        <span style={valStyle}>{latShort} {lonShort}</span>
        <span style={{ color: '#E8A045', fontSize: 11, fontWeight: 600 }}>{utcShort}</span>
        <span style={valStyle}>{alt}</span>
      </div>
    );
  }

  return (
    <div style={{ ...barStyle, height: 32, padding: '0 16px' }}>
      {/* Left: position */}
      <div style={{ display: 'flex', gap: 20 }}>
        <span>
          <span style={labelStyle}>Lat </span>
          <span style={valStyle}>{lat}</span>
        </span>
        <span>
          <span style={labelStyle}>Lon </span>
          <span style={valStyle}>{lon}</span>
        </span>
        <span style={sepStyle}>|</span>
        <span>
          <span style={labelStyle}>Alt </span>
          <span style={valStyle}>{alt}</span>
        </span>
        <span>
          <span style={labelStyle}>Hdg </span>
          <span style={valStyle}>{hdg}</span>
        </span>
      </div>

      {/* Center: UTC */}
      <div style={{ color: '#E8A045', fontSize: 11, fontWeight: 600, letterSpacing: '0.05em' }}>
        {utcTime}
      </div>

      {/* Right: battle stats + optics */}
      <div style={{ display: 'flex', gap: 16 }}>
        {battlefieldTick !== undefined && (
          <span>
            <span style={labelStyle}>Tick </span>
            <span style={valStyle}>{battlefieldTick}</span>
          </span>
        )}
        {battlefieldUnits !== undefined && (
          <span>
            <span style={labelStyle}>Units </span>
            <span style={{ ...valStyle, color: battlefieldUnits > 0 ? '#4CAF7D' : '#5a6478' }}>
              {battlefieldUnits}
            </span>
          </span>
        )}
        <span style={sepStyle}>|</span>
        <span>
          <span style={labelStyle}>View </span>
          <span style={valStyle}>{shaderMode === 'none' ? 'Standard' : shaderMode.toUpperCase()}</span>
        </span>
      </div>
    </div>
  );
}

export default memo(StatusBar);
