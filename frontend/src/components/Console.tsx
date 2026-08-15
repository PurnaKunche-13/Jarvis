import { useState, type FormEvent } from 'react';

import type { Jarvis } from '../lib/useJarvis';

const STATE_LABEL: Record<Jarvis['state'], string> = {
  idle: 'standing by',
  listening: 'listening',
  thinking: 'thinking',
  speaking: 'speaking',
};

export function Console({ jarvis }: { jarvis: Jarvis }) {
  const [draft, setDraft] = useState('');

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    jarvis.send(draft);
    setDraft('');
  };

  const offline = jarvis.connection !== 'open';

  return (
    <section className="console">
      <header className="console__head">
        <span className={`badge badge--${jarvis.state}`}>{STATE_LABEL[jarvis.state]}</span>
        <span className={`badge badge--link${offline ? ' badge--warn' : ''}`}>
          {offline ? jarvis.connection : (jarvis.config?.chat_model ?? 'core online')}
        </span>
        {jarvis.mode !== 'off' && <span className="badge">{jarvis.mode}</span>}
      </header>

      {jarvis.error && <p className="console__error">{jarvis.error}</p>}

      <form className="console__form" onSubmit={onSubmit}>
        <input
          className="console__input"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={offline ? 'reconnecting to core…' : 'speak, or type a command'}
          aria-label="Command"
          autoComplete="off"
        />
        <button className="button" type="submit" disabled={offline || !draft.trim()}>
          send
        </button>
      </form>

      <div className="console__controls">
        <button
          className={`button button--mic${jarvis.listening ? ' is-active' : ''}`}
          type="button"
          onClick={jarvis.toggleListening}
          aria-pressed={jarvis.listening}
        >
          {jarvis.listening ? (jarvis.mode === 'push-to-talk' ? 'send recording' : 'stop mic') : 'talk'}
        </button>
        <button className="button" type="button" onClick={jarvis.stop}>
          silence
        </button>
        <button className="button" type="button" onClick={jarvis.reset}>
          clear
        </button>
        <label className="toggle">
          <input
            type="checkbox"
            checked={jarvis.wakeWordRequired}
            onChange={(event) => jarvis.setWakeWordRequired(event.target.checked)}
          />
          require “{jarvis.config?.wake_word ?? 'jarvis'}”
        </label>
      </div>
    </section>
  );
}
