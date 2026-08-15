import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { AssistantState, HologramSignals } from '../hologram/signals';
import { AudioBus, UtteranceRecorder, pickRecorderMime } from './audio';
import type { RuntimeConfig, ServerMessage } from './protocol';
import { JarvisSocket, backendUrl, type ConnectionState } from './socket';
import {
  Dictation,
  afterWakeWord,
  browserRecognitionSupported,
  cancelSpeech,
  speak,
} from './speech';

export interface Turn {
  id: number;
  role: 'user' | 'jarvis';
  text: string;
  streaming?: boolean;
}

export type ListenMode = 'off' | 'push-to-talk' | 'hands-free';

export interface Jarvis {
  connection: ConnectionState;
  config: RuntimeConfig | null;
  state: AssistantState;
  turns: Turn[];
  interim: string;
  error: string | null;
  listening: boolean;
  mode: ListenMode;
  wakeWordRequired: boolean;
  send: (text: string) => void;
  toggleListening: () => void;
  setWakeWordRequired: (value: boolean) => void;
  reset: () => void;
  stop: () => void;
}

let nextTurnId = 1;

export function useJarvis(signals: HologramSignals): Jarvis {
  const [connection, setConnection] = useState<ConnectionState>('connecting');
  const [config, setConfig] = useState<RuntimeConfig | null>(null);
  const [state, setStateValue] = useState<AssistantState>('idle');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [interim, setInterim] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [listening, setListening] = useState(false);
  const [wakeWordRequired, setWakeWordRequired] = useState(true);

  const socketRef = useRef<JarvisSocket | null>(null);
  const audioRef = useRef<AudioBus | null>(null);
  const recorderRef = useRef<UtteranceRecorder>(new UtteranceRecorder());
  const dictationRef = useRef<Dictation | null>(null);
  const streamingIdRef = useRef<number | null>(null);
  const configRef = useRef<RuntimeConfig | null>(null);

  const setState = useCallback(
    (value: AssistantState) => {
      signals.state = value;
      setStateValue(value);
    },
    [signals],
  );

  const mode: ListenMode = useMemo(() => {
    if (!listening) return 'off';
    return config?.server_stt && pickRecorderMime() ? 'push-to-talk' : 'hands-free';
  }, [config?.server_stt, listening]);

  const appendToken = useCallback((text: string) => {
    signals.activity = Math.min(signals.activity + 0.35, 1);
    setTurns((current) => {
      const id = streamingIdRef.current;
      if (id === null) return current;
      const index = current.findIndex((turn) => turn.id === id);
      if (index === -1) {
        return [...current, { id, role: 'jarvis', text, streaming: true }];
      }
      const next = current.slice();
      const existing = next[index]!;
      next[index] = { ...existing, text: existing.text + text };
      return next;
    });
  }, [signals]);

  const handleMessage = useCallback(
    (message: ServerMessage) => {
      switch (message.type) {
        case 'hello':
          setConfig(message.config);
          configRef.current = message.config;
          break;
        case 'state':
          setState(message.value);
          break;
        case 'transcript':
          setInterim('');
          setTurns((current) => [
            ...current,
            { id: nextTurnId++, role: 'user', text: message.text },
          ]);
          break;
        case 'token':
          if (streamingIdRef.current === null) streamingIdRef.current = nextTurnId++;
          appendToken(message.text);
          break;
        case 'reply_end': {
          const id = streamingIdRef.current;
          streamingIdRef.current = null;
          setTurns((current) =>
            current.map((turn) =>
              turn.id === id ? { ...turn, text: message.text, streaming: false } : turn,
            ),
          );
          if (message.speak) {
            setState('speaking');
            void speak(message.text, (level) => {
              signals.level = level;
            }).then(() => setState('idle'));
          }
          break;
        }
        case 'audio':
          void audioRef.current?.play(message.audio, message.mime).then(() => setState('idle'));
          break;
        case 'error':
          setError(message.message);
          break;
        case 'pong':
          break;
      }
    },
    [appendToken, setState, signals],
  );

  useEffect(() => {
    const audio = new AudioBus(signals);
    audioRef.current = audio;
    const socket = new JarvisSocket(backendUrl(), {
      onMessage: handleMessage,
      onConnection: setConnection,
    });
    socketRef.current = socket;
    socket.connect();

    return () => {
      socket.close();
      audio.dispose();
      cancelSpeech();
      socketRef.current = null;
      audioRef.current = null;
    };
  }, [handleMessage, signals]);

  const submit = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;
      setInterim('');
      setTurns((current) => [...current, { id: nextTurnId++, role: 'user', text: trimmed }]);
      if (!socketRef.current?.send({ type: 'user_text', text: trimmed })) {
        setError('Not connected to the Jarvis core.');
      }
    },
    [],
  );

  const startDictation = useCallback(() => {
    if (!browserRecognitionSupported()) {
      setError('This browser cannot transcribe speech; type instead or set JARVIS_API_KEY.');
      return false;
    }
    const dictation = new Dictation({
      onInterim: setInterim,
      onFinal: (text) => {
        const wakeWord = configRef.current?.wake_word ?? 'jarvis';
        if (wakeWordRequired) {
          const command = afterWakeWord(text, wakeWord);
          if (command === null) return;
          if (!command) {
            setState('listening');
            return;
          }
          submit(command);
          return;
        }
        submit(text);
      },
      onEnd: () => setInterim(''),
      onError: setError,
    });
    dictationRef.current = dictation;
    return dictation.start();
  }, [setState, submit, wakeWordRequired]);

  const toggleListening = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;

    if (listening) {
      dictationRef.current?.stop();
      dictationRef.current = null;
      void recorderRef.current.stop().then((recording) => {
        if (recording) {
          socketRef.current?.send({
            type: 'user_audio',
            audio: recording.base64,
            mime: recording.mime,
          });
        }
        audio.closeMicrophone();
      });
      setListening(false);
      if (state === 'listening') setState('idle');
      return;
    }

    setError(null);
    void (async () => {
      try {
        await audio.resume();
        const stream = await audio.openMicrophone();
        const mime = pickRecorderMime();
        if (configRef.current?.server_stt && mime) {
          recorderRef.current.start(stream, mime);
        } else if (!startDictation()) {
          audio.closeMicrophone();
          return;
        }
        setListening(true);
        setState('listening');
      } catch {
        setError('Microphone access was denied.');
      }
    })();
  }, [listening, setState, startDictation, state]);

  const reset = useCallback(() => {
    socketRef.current?.send({ type: 'reset' });
    setTurns([]);
    setInterim('');
    setError(null);
    streamingIdRef.current = null;
  }, []);

  const stop = useCallback(() => {
    cancelSpeech();
    audioRef.current?.stopPlayback();
    socketRef.current?.send({ type: 'cancel' });
    setState('idle');
  }, [setState]);

  return {
    connection,
    config,
    state,
    turns,
    interim,
    error,
    listening,
    mode,
    wakeWordRequired,
    send: submit,
    toggleListening,
    setWakeWordRequired,
    reset,
    stop,
  };
}
