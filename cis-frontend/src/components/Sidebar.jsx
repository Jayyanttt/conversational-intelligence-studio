import { ANALYSTS } from "../data/analysts.js";

function relTime(ts) {
  const m = Math.round((Date.now() - ts) / 60000);
  if (m < 1) return "Just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function Sidebar({
  open, analystId, sessions, activeId, busy, health,
  onNew, onMode, onOpenSession, onClose,
}) {
  const label =
    health === "ok" ? "Backend connected" : health === "down" ? "Backend unreachable" : "Checking backend…";
  return (
    <aside className={`side${open ? " open" : ""}`} aria-label="Navigation">
      <div className="wordmark"><b>Conversational Intelligence</b> Studio</div>

      <button type="button" className="btn btn-secondary" onClick={onNew} disabled={busy}>
        + New conversation
      </button>

      <h2>Analyst</h2>
      {ANALYSTS.map((a) => (
        <button
          key={a.id}
          type="button"
          className="mode"
          aria-pressed={analystId === a.id}
          disabled={busy}
          onClick={() => onMode(a.id)}
        >
          {a.name}
        </button>
      ))}

      <h2>Recent sessions</h2>
      <nav className="recent" aria-label="Recent sessions">
        {sessions.length === 0 && <p className="empty">Sessions you start will appear here.</p>}
        {sessions.map((s) => (
          <button
            key={s.id}
            type="button"
            disabled={busy}
            aria-current={s.id === activeId}
            onClick={() => onOpenSession(s)}
          >
            {s.title}
            <span className="when">{relTime(s.updatedAt)}</span>
          </button>
        ))}
      </nav>

      <div className="health" role="status">
        <span className={`dot ${health === "ok" ? "ok" : health === "down" ? "bad" : ""}`} />
        {label}
        <button type="button" className="btn btn-quiet navclose" onClick={onClose}
          aria-label="Close navigation">
          Close
        </button>
      </div>
    </aside>
  );
}
