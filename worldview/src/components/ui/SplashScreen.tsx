import { useState, useEffect, useCallback } from 'react';
import type { AudioControls } from '../../hooks/useAudio';

interface SplashScreenProps {
  onComplete: () => void;
  audio?: AudioControls;
}

export default function SplashScreen({ onComplete, audio }: SplashScreenProps) {
  const [progress, setProgress] = useState(0);
  const [ready, setReady] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (progress >= 100) {
      setReady(true);
      return;
    }
    const speed = progress < 60 ? 40 : progress < 85 ? 80 : 120;
    const increment = progress < 60 ? 3 : progress < 85 ? 2 : 1;
    const timer = setTimeout(() => {
      setProgress((p) => Math.min(100, p + increment));
    }, speed);
    return () => clearTimeout(timer);
  }, [progress]);

  const handleEnter = useCallback(() => {
    if (ready) {
      audio?.play('bootReady');
      onComplete();
    }
  }, [ready, onComplete, audio]);

  useEffect(() => {
    if (!ready) return;
    const handler = () => handleEnter();
    window.addEventListener('keydown', handler);
    window.addEventListener('click', handler);
    return () => {
      window.removeEventListener('keydown', handler);
      window.removeEventListener('click', handler);
    };
  }, [ready, handleEnter]);

  return (
    <div
      className="fixed inset-0 z-[100] flex flex-col items-center justify-center select-none"
      style={{
        background: '#0f1117',
        opacity: mounted ? 1 : 0,
        transition: 'opacity 0.4s ease',
      }}
    >
      <div className="flex flex-col items-center" style={{ gap: 20 }}>
        {/* Wordmark */}
        <h1
          style={{
            fontFamily: 'ui-sans-serif, system-ui, -apple-system, sans-serif',
            fontSize: '3.5rem',
            fontWeight: 200,
            letterSpacing: '0.55em',
            color: '#d4dbe8',
            margin: 0,
            lineHeight: 1,
          }}
        >
          GAIA
        </h1>

        {/* Horizontal rule */}
        <div style={{ width: 260, height: 1, background: '#252d3d' }} />

        {/* Subtitle */}
        <div
          style={{
            fontSize: 11,
            letterSpacing: '0.18em',
            color: '#5a6478',
            textTransform: 'uppercase',
          }}
        >
          Battlefield System
        </div>

        {/* Progress counter */}
        <div style={{ height: 20, display: 'flex', alignItems: 'center' }}>
          {!ready ? (
            <span style={{ fontSize: 12, color: '#E8A045', letterSpacing: '0.1em' }}>
              {progress}%
            </span>
          ) : (
            <span
              style={{ fontSize: 12, color: '#5a6478', letterSpacing: '0.15em', cursor: 'pointer' }}
              onClick={handleEnter}
            >
              Press any key to continue
            </span>
          )}
        </div>
      </div>

      {/* Version — bottom left */}
      <div
        className="absolute bottom-4 left-4"
        style={{ fontSize: 10, color: '#2e3848', letterSpacing: '0.08em' }}
      >
        v1.0.0
      </div>
    </div>
  );
}
