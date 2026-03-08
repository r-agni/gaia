import { useEffect, useMemo, useRef, useState } from 'react';
import type { AudioControls } from '../../hooks/useAudio';
import type { SoundEffect } from '../../lib/audio';

interface SplashScreenProps {
  onComplete: () => void;
  audio?: AudioControls;
}

type BootStage = {
  id: string;
  label: string;
  detail: string;
  sound: SoundEffect;
};

const STAGES: BootStage[] = [
  { id: 'grid', label: 'Map Matrix', detail: 'Vector tiles aligned', sound: 'bootSweep' },
  { id: 'link', label: 'Signal Link', detail: 'Telemetry tunnel opened', sound: 'bootConnect' },
  { id: 'rules', label: 'Oversight', detail: 'Reliability monitors armed', sound: 'bootLoad' },
  { id: 'ready', label: 'Mission Ready', detail: 'Pilot control granted', sound: 'bootReady' },
];

export default function SplashScreen({ onComplete, audio }: SplashScreenProps) {
  const [stageIndex, setStageIndex] = useState(0);
  const [interactive, setInteractive] = useState(false);
  const played = useRef<Set<number>>(new Set());

  const progress = useMemo(() => ((stageIndex + 1) / STAGES.length) * 100, [stageIndex]);

  useEffect(() => {
    if (stageIndex >= STAGES.length) return;
    if (!played.current.has(stageIndex)) {
      played.current.add(stageIndex);
      audio?.play(STAGES[stageIndex].sound);
    }
  }, [stageIndex, audio]);

  useEffect(() => {
    if (stageIndex >= STAGES.length - 1) {
      const t = setTimeout(() => {
        setInteractive(true);
        audio?.play('bootOk');
      }, 450);
      return () => clearTimeout(t);
    }

    const t = setTimeout(() => {
      setStageIndex((s) => Math.min(s + 1, STAGES.length - 1));
    }, 620);
    return () => clearTimeout(t);
  }, [stageIndex, audio]);

  useEffect(() => {
    if (!interactive) return;
    const enter = () => onComplete();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') enter();
    };
    window.addEventListener('click', enter);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('click', enter);
      window.removeEventListener('keydown', onKey);
    };
  }, [interactive, onComplete]);

  return (
    <div className="fixed inset-0 z-[100] overflow-hidden bg-[#070b12] text-[#e9eef7]">
      <div className="absolute inset-0 splash-bg-grid" />
      <div className="absolute -top-24 -left-24 h-80 w-80 rounded-full bg-[#5ea1ff22] blur-3xl" />
      <div className="absolute -bottom-24 -right-24 h-96 w-96 rounded-full bg-[#f5b84e1f] blur-3xl" />

      <div className="relative h-full w-full px-5 py-6 md:px-10 md:py-10">
        <div className="mx-auto flex h-full w-full max-w-6xl flex-col justify-between rounded-3xl border border-[#233247] bg-[#0b1320cc] p-5 backdrop-blur md:p-8">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-['Space_Grotesk'] text-[11px] uppercase tracking-[0.28em] text-[#84b5ff]">GAIA OPERATIONS</p>
              <h1 className="mt-2 font-['Space_Grotesk'] text-2xl font-semibold leading-tight md:text-4xl">
                GEO-REASONING
                <span className="block text-[#f6bc57]">MISSION CONTROL</span>
              </h1>
            </div>
            <div className="rounded-full border border-[#294363] px-3 py-1 font-['IBM_Plex_Mono'] text-[10px] uppercase tracking-[0.24em] text-[#9ab5d9]">
              boot sequence
            </div>
          </div>

          <div className="grid grid-cols-1 items-center gap-6 md:grid-cols-[1.2fr_1fr]">
            <div className="relative mx-auto h-56 w-56 md:h-72 md:w-72">
              <div className="absolute inset-0 rounded-full border border-[#27415f] splash-spin-slow" />
              <div className="absolute inset-4 rounded-full border border-dashed border-[#4c7eb844] splash-spin-rev" />
              <div className="absolute inset-10 rounded-full border border-[#f6bc574d]" />
              <div className="absolute left-1/2 top-1/2 h-24 w-24 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle,#8cb9ff_0%,#35527a_55%,#0e1b2a_100%)] shadow-[0_0_50px_rgba(130,180,255,0.45)]" />
              <div className="absolute left-1/2 top-4 h-2 w-2 -translate-x-1/2 rounded-full bg-[#f6bc57] shadow-[0_0_14px_rgba(246,188,87,0.8)]" />
              <div className="absolute bottom-6 right-10 h-2 w-2 rounded-full bg-[#84b5ff] shadow-[0_0_12px_rgba(132,181,255,0.8)]" />
            </div>

            <div className="space-y-3">
              {STAGES.map((s, i) => {
                const done = i < stageIndex || (i === stageIndex && interactive);
                const active = i === stageIndex && !interactive;
                return (
                  <div
                    key={s.id}
                    className={`rounded-xl border px-3 py-2 transition ${
                      done
                        ? 'border-[#3e6ea7] bg-[#122239]'
                        : active
                          ? 'border-[#f6bc57] bg-[#2c2415]'
                          : 'border-[#223248] bg-[#0e1828]'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-['Space_Grotesk'] text-sm">{s.label}</span>
                      <span className="font-['IBM_Plex_Mono'] text-[10px] uppercase tracking-[0.16em] text-[#9ab5d9]">
                        {done ? 'ok' : active ? 'loading' : 'pending'}
                      </span>
                    </div>
                    <p className="mt-1 font-['IBM_Plex_Mono'] text-[11px] text-[#9ab5d9]">{s.detail}</p>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="space-y-3">
            <div className="h-2 overflow-hidden rounded-full bg-[#1c2a3d]">
              <div
                className="h-full bg-[linear-gradient(90deg,#6ca7ff,#f6bc57)] transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="flex flex-col items-start justify-between gap-3 md:flex-row md:items-center">
              <p className="font-['IBM_Plex_Mono'] text-[11px] uppercase tracking-[0.18em] text-[#8ca9d1]">
                {interactive ? 'Tap anywhere or press Enter to deploy' : 'Initializing geospatial command systems'}
              </p>
              {interactive && (
                <button
                  type="button"
                  onClick={onComplete}
                  className="rounded-full border border-[#f6bc57] bg-[#241d10] px-5 py-2 font-['Space_Grotesk'] text-xs uppercase tracking-[0.2em] text-[#f6bc57] transition hover:bg-[#362810]"
                >
                  Enter
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
