import type { HologramSignals } from '../hologram/signals';

const FFT_SIZE = 512;

/**
 * Owns the single AudioContext and feeds loudness straight into the hologram
 * signals object.
 *
 * The meter is polled from the analyser inside its own animation frame and writes
 * to a plain object, so audio reactivity costs no React renders.
 */
export class AudioBus {
  private context: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private buffer = new Uint8Array(FFT_SIZE / 2);
  private meterHandle = 0;
  private micStream: MediaStream | null = null;
  private micSource: MediaStreamAudioSourceNode | null = null;
  private playbackSource: MediaElementAudioSourceNode | null = null;
  private readonly player = new Audio();

  constructor(private readonly signals: HologramSignals) {
    this.player.crossOrigin = 'anonymous';
    this.player.preload = 'auto';
  }

  private ensureContext(): AudioContext {
    if (!this.context) {
      const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      this.context = new Ctor();
      this.analyser = this.context.createAnalyser();
      this.analyser.fftSize = FFT_SIZE;
      this.analyser.smoothingTimeConstant = 0.75;
      this.buffer = new Uint8Array(this.analyser.frequencyBinCount);
    }
    return this.context;
  }

  async resume(): Promise<void> {
    const context = this.ensureContext();
    if (context.state === 'suspended') await context.resume();
  }

  /** Starts the microphone and returns its stream for optional recording. */
  async openMicrophone(): Promise<MediaStream> {
    if (this.micStream) return this.micStream;
    const context = this.ensureContext();
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.micStream = stream;
    this.micSource = context.createMediaStreamSource(stream);
    this.micSource.connect(this.analyser!);
    this.startMeter();
    return stream;
  }

  closeMicrophone(): void {
    this.micSource?.disconnect();
    this.micSource = null;
    this.micStream?.getTracks().forEach((track) => track.stop());
    this.micStream = null;
    if (!this.playbackSource) this.stopMeter();
  }

  /** Plays base64 audio from the backend and returns when playback ends. */
  async play(base64: string, mime: string): Promise<void> {
    const context = this.ensureContext();
    await this.resume();
    this.player.src = `data:${mime};base64,${base64}`;
    if (!this.playbackSource) {
      this.playbackSource = context.createMediaElementSource(this.player);
      this.playbackSource.connect(this.analyser!);
      this.analyser!.connect(context.destination);
    }
    this.startMeter();
    await this.player.play();
    await new Promise<void>((resolve) => {
      const done = () => {
        this.player.removeEventListener('ended', done);
        this.player.removeEventListener('error', done);
        resolve();
      };
      this.player.addEventListener('ended', done);
      this.player.addEventListener('error', done);
    });
    if (!this.micStream) this.stopMeter();
  }

  stopPlayback(): void {
    if (!this.player.paused) {
      this.player.pause();
      this.player.currentTime = 0;
    }
  }

  dispose(): void {
    this.stopMeter();
    this.stopPlayback();
    this.closeMicrophone();
    void this.context?.close();
    this.context = null;
    this.analyser = null;
  }

  private startMeter(): void {
    if (this.meterHandle) return;
    const tick = () => {
      const analyser = this.analyser;
      if (!analyser) return;
      analyser.getByteFrequencyData(this.buffer);
      let sum = 0;
      for (let i = 0; i < this.buffer.length; i += 1) sum += this.buffer[i]!;
      const mean = sum / this.buffer.length / 255;
      // Perceptual curve: quiet rooms should not make the orb twitch.
      const level = Math.min(Math.pow(mean, 0.7) * 1.8, 1);
      this.signals.level += (level - this.signals.level) * 0.35;
      this.meterHandle = requestAnimationFrame(tick);
    };
    this.meterHandle = requestAnimationFrame(tick);
  }

  private stopMeter(): void {
    cancelAnimationFrame(this.meterHandle);
    this.meterHandle = 0;
    this.signals.level = 0;
  }
}

const PREFERRED_MIMES = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg'];

export function pickRecorderMime(): string | null {
  if (typeof MediaRecorder === 'undefined') return null;
  return PREFERRED_MIMES.find((mime) => MediaRecorder.isTypeSupported(mime)) ?? null;
}

export interface Recording {
  base64: string;
  mime: string;
}

/** Records one utterance and resolves with base64 audio once stopped. */
export class UtteranceRecorder {
  private recorder: MediaRecorder | null = null;
  private chunks: Blob[] = [];

  get active(): boolean {
    return this.recorder?.state === 'recording';
  }

  start(stream: MediaStream, mime: string): void {
    this.chunks = [];
    this.recorder = new MediaRecorder(stream, { mimeType: mime });
    this.recorder.ondataavailable = (event) => {
      if (event.data.size > 0) this.chunks.push(event.data);
    };
    this.recorder.start(250);
  }

  async stop(): Promise<Recording | null> {
    const recorder = this.recorder;
    if (!recorder || recorder.state === 'inactive') return null;
    const finished = new Promise<void>((resolve) => {
      recorder.onstop = () => resolve();
    });
    recorder.stop();
    await finished;
    this.recorder = null;
    if (this.chunks.length === 0) return null;
    const blob = new Blob(this.chunks, { type: recorder.mimeType });
    this.chunks = [];
    return { base64: await toBase64(blob), mime: recorder.mimeType.split(';')[0] ?? 'audio/webm' };
  }
}

async function toBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = '';
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}
