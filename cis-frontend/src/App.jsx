import { useEffect, useRef, useState } from "react";
import Welcome from "./components/Welcome.jsx";
import Sidebar from "./components/Sidebar.jsx";
import Chat from "./components/Chat.jsx";
import { ANALYSTS, getAnalyst } from "./data/analysts.js";
import { getHealth, getSessionMessages, postChat, newSessionId } from "./services/api.js";

// The backend has no "list sessions" endpoint, so the frontend keeps a small
// index of sessions it started (id, title, analyst, prompt) in localStorage.
// Message content always comes from GET /sessions/{id}/messages.
const INDEX_KEY = "cis.sessions.v1";
const loadIndex = () => {
  try { return JSON.parse(localStorage.getItem(INDEX_KEY)) || []; } catch { return []; }
};
const saveIndex = (list) => {
  try { localStorage.setItem(INDEX_KEY, JSON.stringify(list.slice(0, 30))); } catch { /* storage unavailable */ }
};

export default function App() {
  const [view, setView] = useState("welcome");
  const [analystId, setAnalystId] = useState(ANALYSTS[0].id);
  const [sessionId, setSessionId] = useState(newSessionId);
  const [systemPrompt, setSystemPrompt] = useState(ANALYSTS[0].system_prompt);
  const [messages, setMessages] = useState([]);
  const [sessions, setSessions] = useState(loadIndex);
  const [loading, setLoading] = useState(false);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [error, setError] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const [health, setHealth] = useState("checking");
  const requestToken = useRef(0); // ignores late responses after the user switches session

  const analyst = getAnalyst(analystId);
  const promptEdited = systemPrompt !== analyst.system_prompt;

  useEffect(() => {
    if (view !== "workspace") return;
    getHealth().then(() => setHealth("ok")).catch(() => setHealth("down"));
  }, [view]);

  const startFresh = (id) => {
    requestToken.current++;
    const a = getAnalyst(id);
    setAnalystId(a.id);
    setSystemPrompt(a.system_prompt);
    setSessionId(newSessionId());
    setMessages([]);
    setError("");
    setLoading(false);
    setLoadingHistory(false);
    setMenuOpen(false);
  };

  // Changing analyst on an empty session just swaps the preset; on a session
  // with messages it starts a new one so a conversation never mixes analysts.
  const chooseMode = (id) => {
    if (id === analystId) return setMenuOpen(false);
    if (messages.length === 0) {
      const a = getAnalyst(id);
      setAnalystId(a.id); setSystemPrompt(a.system_prompt); setError(""); setMenuOpen(false);
    } else startFresh(id);
  };

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

  const send = async (text) => {
    const token = ++requestToken.current;
    const sid = sessionId;
    setError("");
    setMessages((m) => [...m, { role: "user", content: text }]);
    setLoading(true);
    try {
      const data = await postChat({ session_id: sid, message: text, system_prompt: systemPrompt });
      if (token !== requestToken.current) return true;
      setMessages((m) => [...m, { role: "assistant", content: data.reply, metadata: data.metadata }]);
      touchIndex(sid, text, analystId, systemPrompt);
      setHealth("ok");
    } catch (e) {
      // Failed requests are not stored by the backend, so drop the optimistic
      // user message; Chat restores the text to the composer when send returns false.
      if (token !== requestToken.current) return false;
      setMessages((m) => m.slice(0, -1));
      setError(e.message + " Your message is back in the box so you can try again.");
      if (e.status === 0) setHealth("down");
      return false;
    } finally {
      if (token === requestToken.current) setLoading(false);
    }
    return true;
  };

  const openSession = async (s) => {
    const token = ++requestToken.current;
    setAnalystId(s.analystId);
    setSystemPrompt(s.systemPrompt || getAnalyst(s.analystId).system_prompt);
    setSessionId(s.id);
    setMessages([]);
    setError("");
    setLoading(false);
    setLoadingHistory(true);
    setMenuOpen(false);
    try {
      const data = await getSessionMessages(s.id);
      if (token !== requestToken.current) return;
      setMessages(data.messages || []);
    } catch (e) {
      if (token !== requestToken.current) return;
      setError(e.message);
    } finally {
      if (token === requestToken.current) setLoadingHistory(false);
    }
  };

  if (view === "welcome") {
    return (
      <Welcome
        analystId={analystId}
        onSelect={(id) => { const a = getAnalyst(id); setAnalystId(a.id); setSystemPrompt(a.system_prompt); }}
        onEnter={() => setView("workspace")}
      />
    );
  }

  return (
    <div className="shell">
      <Sidebar
        open={menuOpen}
        analystId={analystId}
        sessions={sessions}
        activeId={sessionId}
        busy={loading || loadingHistory}
        health={health}
        onNew={() => startFresh(analystId)}
        onMode={chooseMode}
        onOpenSession={openSession}
        onClose={() => setMenuOpen(false)}
      />
      <button type="button" className={`scrim${menuOpen ? " open" : ""}`} aria-label="Close navigation"
        onClick={() => setMenuOpen(false)} tabIndex={menuOpen ? 0 : -1} />
      <Chat
        analyst={analyst}
        messages={messages}
        loading={loading}
        loadingHistory={loadingHistory}
        error={error}
        systemPrompt={systemPrompt}
        promptEdited={promptEdited}
        onPrompt={setSystemPrompt}
        onResetPrompt={() => setSystemPrompt(analyst.system_prompt)}
        onSend={send}
        onDismissError={() => setError("")}
        onOpenMenu={() => setMenuOpen(true)}
      />
    </div>
  );
}
