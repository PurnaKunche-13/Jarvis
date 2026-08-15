import { useMemo, useState } from 'react';

import { Console } from './components/Console';
import { HologramStage } from './components/HologramStage';
import { Transcript } from './components/Transcript';
import { createSignals } from './hologram/signals';
import { useJarvis } from './lib/useJarvis';

export default function App() {
  // Created once: the renderer mutates this object every frame.
  const signals = useMemo(createSignals, []);
  const [showStats, setShowStats] = useState(true);
  const jarvis = useJarvis(signals);

  return (
    <main className="shell">
      <HologramStage signals={signals} showStats={showStats} />
      <div className="overlay">
        <header className="overlay__head">
          <h1 className="title">J.A.R.V.I.S.</h1>
          <button
            className="button button--ghost"
            type="button"
            onClick={() => setShowStats((value) => !value)}
          >
            {showStats ? 'hide stats' : 'show stats'}
          </button>
        </header>
        <Transcript turns={jarvis.turns} interim={jarvis.interim} />
        <Console jarvis={jarvis} />
      </div>
    </main>
  );
}
