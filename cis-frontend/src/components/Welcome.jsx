import { ANALYSTS } from "../data/analysts.js";

// Abstract motif: participant nodes joined by fine lines. Decorative only.
function Constellation() {
  const nodes = [
    [150, 190], [300, 120], [430, 230], [250, 340], [380, 410], [120, 400],
  ];
  const links = [[0, 1], [1, 2], [0, 3], [3, 2], [3, 4], [2, 4], [0, 5], [5, 3]];
  return (
    <svg viewBox="0 0 560 560" aria-hidden="true" fill="none">
      {links.map(([a, b]) => (
        <line key={a + "-" + b} x1={nodes[a][0]} y1={nodes[a][1]} x2={nodes[b][0]} y2={nodes[b][1]}
          stroke="#C8B9A9" strokeWidth="1" />
      ))}
      {nodes.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={i === 1 ? 9 : 6} fill={i === 1 ? "#B97859" : "#FAF8F4"}
          stroke={i === 1 ? "#B97859" : "#A9B4A0"} strokeWidth="1.5" />
      ))}
      {/* quiet waveform */}
      <g stroke="#A9B4A0" strokeWidth="2" strokeLinecap="round">
        {[0, 1, 2, 3, 4, 5, 6, 7, 8].map((i) => {
          const h = [6, 14, 24, 12, 30, 16, 8, 20, 10][i];
          return <line key={i} x1={210 + i * 14} y1={500 - h} x2={210 + i * 14} y2={500 + h} />;
        })}
      </g>
    </svg>
  );
}

export default function Welcome({ analystId, onSelect, onEnter }) {
  return (
    <main className="welcome">
      <div className="welcome-head wordmark">
        <b>Conversational Intelligence</b> Studio
      </div>

      <section>
        <h1>There’s more to every conversation.</h1>
        <p className="lede">
          Understand the conversations behind your business. Paste a transcript, choose an
          analyst, and ask what is really going on in it.
        </p>

        <div className="picker" role="radiogroup" aria-label="Choose an analyst">
          {ANALYSTS.map((a) => (
            <button
              key={a.id}
              type="button"
              role="radio"
              aria-checked={analystId === a.id}
              className="pick"
              onClick={() => onSelect(a.id)}
            >
              <span className="t">{a.name}</span>
              <span className="d">{a.description}</span>
              <span className="radio" aria-hidden="true" />
            </button>
          ))}
        </div>

        <button type="button" className="btn btn-primary" onClick={onEnter}>
          Open workspace
        </button>
        <p className="privacy">
          Paste anonymised text only, and make sure you have permission to share it.
        </p>
      </section>

      <div className="stage" aria-hidden="true">
        <div className="glow" />
        <Constellation />
        <div className="glass g1"><small>Example question</small>Who asked, and who answered?</div>
        <div className="glass g2"><small>Example question</small>What is still unresolved?</div>
      </div>
    </main>
  );
}
