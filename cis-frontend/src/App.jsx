import { useEffect, useRef, useState } from "react";
import Welcome from "./components/Welcome.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Chat from "./components/Chat.jsx";
import Settings from "./components/Settings.jsx";
import { ANALYSTS, getAnalyst } from "./data/analysts.js";
import { getHealth, getSessionMessages, postChat, newSessionId } from "./services/api.js";
import { loadPrefs, savePrefs, applyPrefs, withPreferences } from "./prefs.js";

// The backend has no "list sessions" endpoint, so the frontend keeps an index of the
// sessions it started in localStorage. Every entry carries its analystId, and each
// workspace only ever lists and opens entries for its own analyst.
// Message content always comes from GET /sessions/{id}/messages.
const INDEX_KEY = "cis.sessions.v1";
const loadIndex = () => {
  try { return JSON.parse(localStorage.getItem(INDEX_KEY)) || []; } catch { return []; }
};
const saveIndex = (list) => {
  try { localStorage.setItem(INDEX_KEY, JSON.stringify(list.slice(0, 90))); } catch { /* storage unavailable */ }
};

// One independent conversation slot per analyst. Switching analyst or going Home only
// changes which slot is shown, so nothing is erased.
const freshConvo = (aid) => ({
  sessionId: newSessionId(), messages: [], draft: "", systemPrompt: getAnalyst(aid).system_prompt,
  loading: false, loadingHistory: false, error: "",
});
const initialConvos = () => Object.fromEntries(ANALYSTS.map((a) => [a.id, freshConvo(a.id)]));

export default function App() {
  const [workspace, setWorkspace] = useState(null); // null = welcome screen, else an analyst id
  const [convos, setConvos] = useState(initialConvos);
  const [sessions, setSessions] = useState(loadIndex);
  const [prefs, setPrefs] = useState(loadPrefs);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [health, setHealth] = useState("checking");
  const tokens = useRef({}); // per analyst: ignores late responses after a new/reopened session
  const opener = useRef(null);

  useEffect(() => { savePrefs(prefs); return applyPrefs(prefs); }, [prefs]);

  useEffect(() => {
    if (workspace === null) return;
    getHealth().then(() => setHealth("ok")).catch(() => setHealth("down"));
  }, [workspace]);

  const patch = (aid, p) =>
    setConvos((c) => ({ ...c, [aid]: { ...c[aid], ...(typeof p === "function" ? p(c[aid]) : p) } }));
  const bump = (aid) => (tokens.current[aid] = (tokens.current[aid] || 0) + 1);

  const touchIndex = (id, title, aId, prompt) => {
    setSessions((prev) => {
      const existing = prev.find((s) => s.id === id);
      const entry = existing
        ? { ...existing, systemPrompt: prompt, updatedAt: Date.now() }
        : { id, title: title.replace(/\s+/g, " ").slice(0, 48), analystId: aId, systemPrompt: prompt, updatedAt: Date.now() };
      const next = [entry, ...prev.filter((s) => s.id !== id)];
      saveIndex(next);
      return next;
    });
  };

  const openWorkspace = (id) => { setWorkspace(id); setMenuOpen(false); };
  const goHome = () => { setWorkspace(null); setMenuOpen(false); };

  // Starting a new conversation only replaces this analyst's live slot. The previous
  // session was already indexed when its first message succeeded, so it is never lost.
  const newConversation = (aid) => {
    bump(aid);
    setConvos((c) => ({ ...c, [aid]: freshConvo(aid) }));
    setMenuOpen(false);
  };

  const send = async (aid, text) => {
    const c = convos[aid];
    const tok = bump(aid);
    const sid = c.sessionId;
    const base = c.systemPrompt;
    patch(aid, (x) => ({ error: "", loading: true, messages: [...x.messages, { role: "user", content: text }] }));
    try {
      const data = await postChat({
        session_id: sid, message: text, system_prompt: withPreferences(base, prefs), analyst_type: aid,
      });
      touchIndex(sid, text, aid, base); // index even if the user has since moved on
      setHealth("ok");
      if (tok !== tokens.current[aid]) return null;
      patch(aid, (x) => ({ messages: [...x.messages, { role: "assistant", content: data.reply, metadata: data.metadata }] }));
      return true;
    } catch (e) {
      if (tok !== tokens.current[aid]) return null;
      // Failed requests are not stored by the backend, so drop the optimistic message;
      // Chat restores the text to the composer when this returns false.
      patch(aid, (x) => ({
        messages: x.messages.slice(0, -1),
        error: e.message + " Your message is back in the box so you can try again.",
      }));
      if (e.status === 0) setHealth("down");
      return false;
    } finally {
      if (tok === tokens.current[aid]) patch(aid, { loading: false });
    }
  };

  const openSession = async (aid, s) => {
    if (s.analystId !== aid) return; // a workspace never opens another analyst's session
    const tok = bump(aid);
    setMenuOpen(false);
    patch(aid, {
      sessionId: s.id, messages: [], error: "", loading: false, loadingHistory: true,
      systemPrompt: s.systemPrompt || getAnalyst(aid).system_prompt,
    });
    try {
      const data = await getSessionMessages(s.id);
      if (tok !== tokens.current[aid]) return;
      patch(aid, { messages: data.messages || [] });
    } catch (e) {
      if (tok !== tokens.current[aid]) return;
      patch(aid, { error: e.message });
    } finally {
      if (tok === tokens.current[aid]) patch(aid, { loadingHistory: false });
    }
  };

  const openSettings = () => { opener.current = document.activeElement; setSettingsOpen(true); };
  const closeSettings = () => { setSettingsOpen(false); opener.current?.focus?.(); };
  const settings = settingsOpen && (
    <Settings prefs={prefs} onChange={(p) => setPrefs((x) => ({ ...x, ...p }))} onClose={closeSettings} />
  );

  if (workspace === null) {
    return (<><Welcome onOpen={openWorkspace} onSettings={openSettings} />{settings}</>);
  }

  const aid = workspace;
  const analyst = getAnalyst(aid);
  const c = convos[aid];
  const mine = sessions.filter((s) => s.analystId === aid);

  return (
    <div className="shell">
      <Sidebar
        open={menuOpen}
        analyst={analyst}
        sessions={mine}
        activeId={c.sessionId}
        busy={c.loading || c.loadingHistory}
        health={health}
        onNew={() => newConversation(aid)}
        onOpenSession={(s) => openSession(aid, s)}
        onClose={() => setMenuOpen(false)}
      />
      <button type="button" className={`scrim${menuOpen ? " open" : ""}`} aria-label="Close navigation"
        onClick={() => setMenuOpen(false)} tabIndex={menuOpen ? 0 : -1} />
      <Chat
        analyst={analyst}
        messages={c.messages}
        loading={c.loading}
        loadingHistory={c.loadingHistory}
        error={c.error}
        draft={c.draft}
        systemPrompt={c.systemPrompt}
        promptEdited={c.systemPrompt !== analyst.system_prompt}
        onDraft={(v) => patch(aid, (x) => ({ draft: typeof v === "function" ? v(x.draft) : v }))}
        onPrompt={(v) => patch(aid, { systemPrompt: v })}
        onResetPrompt={() => patch(aid, { systemPrompt: analyst.system_prompt })}
        onSend={(text) => send(aid, text)}
        onDismissError={() => patch(aid, { error: "" })}
        onOpenMenu={() => setMenuOpen(true)}
        onHome={goHome}
        onSwitch={openWorkspace}
        onOpenSettings={openSettings}
      />
      {settings}
    </div>
  );
}
