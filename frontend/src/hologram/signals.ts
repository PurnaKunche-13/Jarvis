export type AssistantState = 'idle' | 'listening' | 'thinking' | 'speaking';

/**
 * Mutable frame-rate data shared between the audio pipeline and the renderer.
 *
 * This deliberately bypasses React state: the render loop reads it directly, so
 * a talkative microphone never triggers a re-render (the main cause of jank in
 * naive audio-reactive visualisers).
 */
export interface HologramSignals {
  state: AssistantState;
  /** Smoothed microphone / playback loudness in 0..1. */
  level: number;
  /** Rises while tokens stream in, decays afterwards. */
  activity: number;
}

export function createSignals(): HologramSignals {
  return { state: 'idle', level: 0, activity: 0 };
}
