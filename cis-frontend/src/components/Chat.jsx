import { useEffect, useRef, useState } from "react";

const MAX = 4000;

/* ---------- tiny markdown renderer (headings, lists, quotes, bold/italic) ---------- */
function inline(text, key) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`)/g).filter(Boolean);
  return parts.map((p, i) => {
    if (p.startsWith("**")) return <strong key={key + i}>{p.slice(2, -2)}</strong>;
    if (p.startsWith("`")) return <code key={key + i}>{p.slice(1, -1)}</code>;
    if (p.startsWith("*")) return <em key={key + i}>{p.slice(1, -1)}</em>;
    return p;
  });
}

function Markdown({ text }) {
  const lines = text.split("\n");
  const out = [];
  let list = null;
  const flush = () => { if (list) { out.push(list); list = null; } };
  lines.forEach((raw, i) => {
    const l = raw.trimEnd();
    let m;
    if ((m = l.match(/^(#{1,4})\s+(.*)/))) {
      flush();
      out.push(m[1].length <= 2 ? <h3 key={i}>{inline(m[2], i)}</h3> : <h4 key={i}>{inline(m[2], i)}</h4>);
    } else if ((m = l.match(/^\s*([-*]|\d+\.)\s+(.*)/))) {
      const ordered = /\d/.test(m[1]);
      if (!list || list.ordered !== ordered) { flush(); list = { ordered, items: [] }; }
      list.items.push(<li key={i}>{inline(m[2], i)}</li>);
      list = { ...list, type: ordered ? "ol" : "ul" };
    } else if ((m = l.match(/^>\s?(.*)/))) {
      flush(); out.push(<blockquote key={i}>{inline(m[1], i)}</blockquote>);
    } else if (l.trim() === "") {
      flush();
    } else {
      flush(); out.push(<p key={i}>{inline(l, i)}</p>);
    }
  });
  flush();
  return (
    <div className="prose">
      {out.map((n, i) =>
        n && n.items ? (n.ordered ? <ol key={i}>{n.items}</ol> : <ul key={i}>{n.items}</ul>) : n
      )}
    </div>
  );
}

/* ---------- abstract assistant glyph: three linked nodes ---------- */
function Glyph({ spin }) {
  return (
    <span className="glyph" aria-hidden="true">
      <svg viewBox="0 0 36 36" fill="none">
        <g className={spin ? "ring" : ""}>
          <line x1="11" y1="22" x2="18" y2="11" stroke="#C8B9A9" />
          <line x1="18" y1="11" x2="26" y2="21" stroke="#C8B9A9" />
          <line x1="11" y1="22" x2="26" y2="21" stroke="#C8B9A9" />
          <circle cx="11" cy="22" r="2.6" fill="#A9B4A0" />
          <circle cx="18" cy="11" r="3" fill="#B97859" />
          <circle cx="26" cy="21" r="2.6" fill="#B9CDD0" />
        </g>
      </svg>
    </span>
  );
}

const Chevron = () => (
  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
    <path d="M4 2l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

/* ---------- per-response metadata (never fabricated: missing fields show "Not stored") ----------
   A compact, always-visible line carries the five headline fields; key and fallback
   attempts sit behind a quiet "More" toggle. */
function Metadata({ meta }) {
  const [open, setOpen] = useState(false);
  const has = (v) => v !== undefined && v !== null;
  const show = (v, unit = "") => (has(v) ? `${v}${unit}` : "Not stored");
  const source = meta.resolution_source;
  const partial = !has(meta.model) || !has(meta.latency_ms) || !has(meta.fallback_attempts);
  return (
    <div className="details">
      <div className="strip">
        <span data-testid="meta-source">
          {has(source) ? <span className={`tag ${source === "LLM_CACHE" ? "cache" : "live"}`}>{source}</span> : "Source not stored"}
        </span>
        <span data-testid="meta-model">{show(meta.model)}</span>
        <span data-testid="meta-latency">{show(meta.latency_ms, " ms")}</span>
        <span><span data-testid="meta-input-tokens">{show(meta.input_tokens)}</span> in</span>
        <span><span data-testid="meta-output-tokens">{show(meta.output_tokens)}</span> out</span>
        <button type="button" className="more" aria-expanded={open} onClick={() => setOpen(!open)}>
          <Chevron /> More
        </button>
      </div>
      {open && (
        <dl className="meta">
          <div><dt>Key</dt><dd data-testid="meta-key">{has(meta.key_id) ? meta.key_id : source === "LLM_CACHE" ? "None (cache hit)" : "Not stored"}</dd></div>
          <div><dt>Fallback attempts</dt><dd data-testid="meta-fallback">{show(meta.fallback_attempts)}</dd></div>
          {partial && <p className="note">Reloaded from history, which did not include every field.</p>}
        </dl>
      )}
    </div>
  );
}

/* ---------- main chat view ---------- */
export default function Chat({
  analyst, messages, loading, loadingHistory, error, systemPrompt, promptEdited,
  onPrompt, onResetPrompt, onSend, onDismissError, onOpenMenu,
}) {
  const [text, setText] = useState("");
  const [showPrompt, setShowPrompt] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); },
    [messages.length, loading]);

  // Grow the textarea with its content.
  useEffect(() => {
    const el = inputRef.current;
    if (el) { el.style.height = "auto"; el.style.height = Math.min(el.scrollHeight, 220) + "px"; }
  }, [text]);

  const trimmed = text.trim();
  const tooLong = trimmed.length > MAX;
  const canSend = trimmed.length > 0 && !tooLong && !loading && !loadingHistory;

  const submit = () => {
    if (!canSend) return;
    setText("");
    Promise.resolve(onSend(trimmed)).then((ok) => {
      if (ok === false) setText((cur) => cur || trimmed); // restore after a failed send
    });
  };
  const onKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  };

  return (
    <div className="main">
      <header className="top">
        <button type="button" className="btn btn-quiet menu" onClick={onOpenMenu} aria-label="Open navigation">
          Menu
        </button>
        <div className="who">
          <Glyph />
          <div style={{ minWidth: 0 }}>
            <div className="name">{analyst.name}<span className="sfx"> Analyst</span></div>
            <div className="sub">{analyst.short}</div>
          </div>
        </div>
        <button type="button" className="btn btn-quiet" aria-expanded={showPrompt}
          onClick={() => setShowPrompt(!showPrompt)}>
          Instructions{promptEdited ? " (edited)" : ""}
        </button>
      </header>

      {showPrompt && (
        <section className="instr" aria-label="Analyst instructions">
          <div className="instr-inner">
            <label htmlFor="sp">System prompt</label>
            <p>
              The analyst’s instructions, sent with each message. Edit them to change how it
              responds.{messages.length > 0 && " Changes apply to your next message in this session."}
            </p>
            <textarea id="sp" data-testid="system-prompt-input" value={systemPrompt}
              onChange={(e) => onPrompt(e.target.value)} disabled={loading} />
            <button type="button" className="btn btn-quiet" onClick={onResetPrompt}
              disabled={!promptEdited || loading} style={{ marginTop: 6 }}>
              Reset to preset
            </button>
          </div>
        </section>
      )}

      <div className="scroll" aria-live="polite">
        <div className="thread">
          {messages.length === 0 && !loading && !loadingHistory && (
            <div className="empty-state">
              <h2>Paste a conversation to begin.</h2>
              <p>{analyst.description} Anonymise names first if you can.</p>
              {analyst.starters.map((s) => (
                <button key={s} type="button" className="starter" onClick={() => setText(s + "\n\n")}>{s}</button>
              ))}
            </div>
          )}

          {loadingHistory && (
            <div className="thinking"><Glyph spin /> Loading this session…</div>
          )}

          {messages.map((m, i) =>
            m.role === "user" ? (
              <div key={i} className="msg user" data-testid="user-message">{m.content}</div>
            ) : (
              <div key={i} className="msg assistant" data-testid="assistant-message">
                <Glyph />
                <div>
                  <Markdown text={m.content} />
                  {m.metadata && <Metadata meta={m.metadata} />}
                </div>
              </div>
            )
          )}

          {loading && (
            <div className="thinking" role="status"><Glyph spin /> Reading the conversation…</div>
          )}

          {error && (
            <div className="alert" role="alert">
              <div><strong>Couldn’t complete that request</strong>{error}</div>
              <button type="button" className="btn btn-quiet" onClick={onDismissError}>Dismiss</button>
            </div>
          )}
          <div ref={endRef} />
        </div>
      </div>

      <div className="composer">
        <div className="composer-box">
          <label className="sr" htmlFor="msg">Message</label>
          <textarea id="msg" ref={inputRef} data-testid="chat-input" rows={1} value={text}
            placeholder="Paste a conversation, or ask a question…" disabled={loading || loadingHistory}
            onChange={(e) => setText(e.target.value)} onKeyDown={onKey} />
          <button type="button" className="btn btn-primary send" data-testid="send-button"
            onClick={submit} disabled={!canSend} aria-label={loading ? "Sending" : "Send message"}>
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path d="M10 16V4M5 9l5-5 5 5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </button>
        </div>
        <div className="foot">
          <span>Enter sends. Shift+Enter adds a line.</span>
          <span className={tooLong ? "over" : ""}>{trimmed.length}/{MAX}</span>
        </div>
      </div>
    </div>
  );
}
