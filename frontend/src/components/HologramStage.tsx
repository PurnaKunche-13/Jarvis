import { useEffect, useRef, useState } from 'react';

import { HologramScene } from '../hologram/scene';
import type { HologramSignals } from '../hologram/signals';

interface Props {
  signals: HologramSignals;
  showStats: boolean;
}

/**
 * Mounts the WebGL scene once and never re-renders it: the component only owns
 * the canvas element and an occasional stats update.
 */
export function HologramStage({ signals, showStats }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [stats, setStats] = useState({ fps: 0, tier: 'high' as string });

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const scene = new HologramScene(canvas, signals, (fps, tier) => setStats({ fps, tier }));
    scene.start();
    return () => scene.dispose();
  }, [signals]);

  return (
    <div className="stage">
      <canvas ref={canvasRef} className="stage__canvas" />
      <div className="stage__grid" aria-hidden="true" />
      {showStats && (
        <div className="stats" role="status">
          <span>{stats.fps} fps</span>
          <span>{stats.tier}</span>
        </div>
      )}
    </div>
  );
}
