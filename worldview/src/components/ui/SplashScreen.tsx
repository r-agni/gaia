import { useState, useEffect, useCallback } from 'react';
import type { AudioControls } from '../../hooks/useAudio';

interface SplashScreenProps {
  onComplete: () => void;
  audio?: AudioControls;
}

export default function SplashScreen({ onComplete, audio }: SplashScreenProps) {
  const [progress, setProgress] = useState(0);
  const [ready, setReady] = useState(false);

  // Simulate loading progress
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

  // Listen for any key or click to enter
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
    <div className="fixed inset-0 bg-[#040608] z-[100] flex flex-col items-center justify-center select-none">
      {/* Subtle scan lines overlay */}
      <div className="absolute inset-0 pointer-events-none opacity-[0.03]"
        style={{
          backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,255,136,0.1) 2px, rgba(0,255,136,0.1) 4px)',
        }}
      />

      {/* Main content */}
      <div className="relative z-10 flex flex-col items-center gap-6">
        {/* Title */}
        <div className="text-center">
          <h1
            className="text-6xl font-bold tracking-[0.3em] mb-2"
            style={{
              color: '#00FF88',
              textShadow: '0 0 40px rgba(0,255,136,0.3), 0 0 80px rgba(0,255,136,0.1)',
              fontFamily: 'monospace',
            }}
          >
            GAIA
          </h1>
          <div
            className="text-[11px] tracking-[0.5em] uppercase"
            style={{ color: 'rgba(0,255,136,0.4)' }}
          >
            Battlefield Tactical System
          </div>
        </div>

        {/* Progress bar */}
        <div className="w-72 flex flex-col items-center gap-2">
          <div className="w-full h-[2px] bg-white/5 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-100"
              style={{
                width: `${progress}%`,
                background: 'linear-gradient(90deg, rgba(0,255,136,0.6), rgba(0,255,136,0.9))',
                boxShadow: '0 0 12px rgba(0,255,136,0.4)',
              }}
            />
          </div>
          <div className="text-[9px] tracking-[0.3em]" style={{ color: 'rgba(0,255,136,0.3)' }}>
            {!ready ? (
              <>INITIALIZING... {progress}%</>
            ) : (
              <span style={{ color: 'rgba(0,255,136,0.5)' }}>SYSTEMS READY</span>
            )}
          </div>
        </div>

        {/* Press any key prompt */}
        {ready && (
          <div
            className="mt-4 text-[12px] tracking-[0.4em] uppercase animate-pulse cursor-pointer"
            style={{
              color: 'rgba(0,255,136,0.7)',
              textShadow: '0 0 20px rgba(0,255,136,0.3)',
            }}
            onClick={handleEnter}
          >
            Press any key to enter
          </div>
        )}
      </div>

      {/* Bottom version */}
      <div
        className="absolute bottom-4 text-[9px] tracking-[0.3em]"
        style={{ color: 'rgba(255,255,255,0.1)' }}
      >
        v1.0.0
      </div>
    </div>
  );
}
