/**
 * Thin wrappers over the browser speech APIs.
 *
 * They are the zero-config path: Jarvis can hear and talk with no API key at all,
 * and the backend providers take over when one is configured.
 */

interface SpeechRecognitionAlternative {
  transcript: string;
}
interface SpeechRecognitionResult {
  readonly length: number;
  readonly isFinal: boolean;
  item: (index: number) => SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
}
interface SpeechRecognitionResultList {
  readonly length: number;
  [index: number]: SpeechRecognitionResult;
}
interface SpeechRecognitionEventLike extends Event {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}
interface SpeechRecognitionLike extends EventTarget {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onend: (() => void) | null;
  onerror: ((event: Event & { error?: string }) => void) | null;
}
type SpeechRecognitionCtor = new () => SpeechRecognitionLike;

function recognitionCtor(): SpeechRecognitionCtor | null {
  const scope = window as unknown as {
    SpeechRecognition?: SpeechRecognitionCtor;
    webkitSpeechRecognition?: SpeechRecognitionCtor;
  };
  return scope.SpeechRecognition ?? scope.webkitSpeechRecognition ?? null;
}

export const browserRecognitionSupported = (): boolean => recognitionCtor() !== null;

export interface DictationHandlers {
  onInterim: (text: string) => void;
  onFinal: (text: string) => void;
  onEnd: () => void;
  onError: (message: string) => void;
}

/** Continuous browser dictation with automatic restart while enabled. */
export class Dictation {
  private recognition: SpeechRecognitionLike | null = null;
  private wanted = false;

  constructor(private readonly handlers: DictationHandlers) {}

  get running(): boolean {
    return this.recognition !== null;
  }

  start(lang = 'en-US'): boolean {
    const Ctor = recognitionCtor();
    if (!Ctor) return false;
    if (this.recognition) return true;

    const recognition = new Ctor();
    recognition.lang = lang;
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onresult = (event) => {
      let interim = '';
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        if (!result) continue;
        const text = result[0]?.transcript ?? '';
        if (result.isFinal) {
          const final = text.trim();
          if (final) this.handlers.onFinal(final);
        } else {
          interim += text;
        }
      }
      if (interim) this.handlers.onInterim(interim.trim());
    };

    recognition.onerror = (event) => {
      const error = event.error ?? 'unknown';
      if (error !== 'no-speech' && error !== 'aborted') {
        this.handlers.onError(`speech recognition: ${error}`);
      }
    };

    recognition.onend = () => {
      this.recognition = null;
      if (this.wanted) {
        // Chrome ends the session every ~60s; restart to stay always-on.
        this.start(lang);
      } else {
        this.handlers.onEnd();
      }
    };

    this.wanted = true;
    this.recognition = recognition;
    try {
      recognition.start();
    } catch {
      this.recognition = null;
      return false;
    }
    return true;
  }

  stop(): void {
    this.wanted = false;
    const recognition = this.recognition;
    this.recognition = null;
    recognition?.stop();
    this.handlers.onEnd();
  }
}

/** Strips a leading wake word, returning null when it is absent. */
export function afterWakeWord(text: string, wakeWord: string): string | null {
  const lowered = text.toLowerCase();
  const index = lowered.indexOf(wakeWord.toLowerCase());
  if (index === -1) return null;
  return text.slice(index + wakeWord.length).replace(/^[\s,.:!?-]+/, '').trim();
}

export const speechSynthesisSupported = (): boolean => 'speechSynthesis' in window;

/** Speaks text with the browser voice, resolving when playback finishes. */
export function speak(text: string, onLevel?: (level: number) => void): Promise<void> {
  if (!speechSynthesisSupported() || !text) return Promise.resolve();
  window.speechSynthesis.cancel();
  return new Promise<void>((resolve) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.03;
    utterance.pitch = 0.85;
    // The synthesizer output is not routed through our AudioContext, so drive the
    // hologram from boundary events instead of a real analyser.
    utterance.onboundary = () => onLevel?.(0.45 + Math.random() * 0.4);
    const done = () => {
      onLevel?.(0);
      resolve();
    };
    utterance.onend = done;
    utterance.onerror = done;
    window.speechSynthesis.speak(utterance);
  });
}

export function cancelSpeech(): void {
  if (speechSynthesisSupported()) window.speechSynthesis.cancel();
}
