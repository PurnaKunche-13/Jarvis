import type { AssistantState } from '../hologram/signals';

export interface RuntimeConfig {
  wake_word: string;
  cloud_enabled: boolean;
  server_tts: boolean;
  server_stt: boolean;
  chat_model: string;
}

export type ServerMessage =
  | { type: 'hello'; config: RuntimeConfig }
  | { type: 'state'; value: AssistantState }
  | { type: 'transcript'; text: string }
  | { type: 'token'; text: string }
  | { type: 'reply_end'; text: string; speak: boolean }
  | { type: 'audio'; audio: string; mime: string }
  | { type: 'error'; message: string }
  | { type: 'pong' };

export type ClientMessage =
  | { type: 'user_text'; text: string }
  | { type: 'user_audio'; audio: string; mime: string }
  | { type: 'cancel' }
  | { type: 'reset' }
  | { type: 'ping' };
