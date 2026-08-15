import { useEffect, useRef } from 'react';

import type { Turn } from '../lib/useJarvis';

interface Props {
  turns: Turn[];
  interim: string;
}

export function Transcript({ turns, interim }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' });
  }, [turns, interim]);

  return (
    <div className="transcript" aria-live="polite">
      {turns.length === 0 && !interim && (
        <p className="transcript__hint">
          Say the wake word or type below. Ask for the time, some arithmetic, or anything else.
        </p>
      )}
      {turns.map((turn) => (
        <p key={turn.id} className={`turn turn--${turn.role}`}>
          <span className="turn__who">{turn.role === 'user' ? 'you' : 'jarvis'}</span>
          <span className="turn__text">
            {turn.text}
            {turn.streaming && <span className="turn__caret" />}
          </span>
        </p>
      ))}
      {interim && (
        <p className="turn turn--user turn--interim">
          <span className="turn__who">you</span>
          <span className="turn__text">{interim}</span>
        </p>
      )}
      <div ref={endRef} />
    </div>
  );
}
