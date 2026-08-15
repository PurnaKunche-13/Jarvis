export interface QualityTier {
  name: 'ultra' | 'high' | 'balanced' | 'lite';
  /** Icosahedron subdivision for the orb. */
  detail: number;
  particles: number;
  maxPixelRatio: number;
}

export const TIERS: readonly QualityTier[] = [
  { name: 'ultra', detail: 6, particles: 2600, maxPixelRatio: 2 },
  { name: 'high', detail: 5, particles: 1800, maxPixelRatio: 1.75 },
  { name: 'balanced', detail: 4, particles: 1100, maxPixelRatio: 1.35 },
  { name: 'lite', detail: 3, particles: 600, maxPixelRatio: 1 },
];

/** Initial guess from the device before any frame has been measured. */
export function initialTierIndex(): number {
  const cores = navigator.hardwareConcurrency ?? 4;
  const mobile = /Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
  if (mobile) return 3;
  if (cores >= 12 && window.devicePixelRatio <= 2) return 0;
  if (cores >= 8) return 1;
  if (cores >= 4) return 2;
  return 3;
}

/**
 * Watches frame times and reports when the renderer should change tier.
 *
 * Downgrades quickly (two bad windows in a row) and upgrades reluctantly, so the
 * hologram never sits in a visible oscillation between tiers.
 */
export class PerfGuard {
  private frames = 0;
  private elapsed = 0;
  private slowWindows = 0;
  private fastWindows = 0;
  private fps = 60;

  constructor(
    private readonly windowSeconds = 1,
    private readonly downgradeBelow = 50,
    private readonly upgradeAbove = 58,
  ) {}

  get currentFps(): number {
    return this.fps;
  }

  /** Returns -1 to lower quality, +1 to raise it, 0 to stay put. */
  sample(delta: number): -1 | 0 | 1 {
    this.frames += 1;
    this.elapsed += delta;
    if (this.elapsed < this.windowSeconds) return 0;

    this.fps = this.frames / this.elapsed;
    this.frames = 0;
    this.elapsed = 0;

    if (this.fps < this.downgradeBelow) {
      this.fastWindows = 0;
      this.slowWindows += 1;
      if (this.slowWindows >= 2) {
        this.slowWindows = 0;
        return -1;
      }
      return 0;
    }

    this.slowWindows = 0;
    if (this.fps > this.upgradeAbove) {
      this.fastWindows += 1;
      if (this.fastWindows >= 6) {
        this.fastWindows = 0;
        return 1;
      }
    }
    return 0;
  }
}
