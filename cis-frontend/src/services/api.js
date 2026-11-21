// The only module that talks to the backend. Contract: see context.md.
// Base URL comes from VITE_API_BASE_URL (build-time). The localhost fallback
// applies to `npm run dev` only; production builds must set the variable.
const BASE = (
  import.meta.env.VITE_API_BASE_URL ||
  (import.meta.env.DEV ? "http://localhost:8000" : "")
).replace(/\/$/, "");

export class ApiError extends Error {
  constructor(message, status) {
    super(message);
    this.status = status;
  }
}

// Turn FastAPI error bodies into something a person can act on.
function readableError(status, body) {
  const detail = body && body.detail;
  if (status === 422) {
    const first = Array.isArray(detail) ? detail[0] : null;
    const field = first && first.loc ? first.loc[first.loc.length - 1] : "";
    if (field === "message")
      return "Your message must be between 1 and 4000 characters. Shorten it or send it in parts.";
    return "The request was rejected as invalid. Check your message and instructions, then try again.";
  }
  if (status === 503)
    return "The analysis service is unavailable right now: every model provider failed. Try again in a moment.";
  if (typeof detail === "string") return detail;
  return `The server returned an unexpected error (HTTP ${status}).`;
}

async function request(path, options) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, options);
  } catch {
    throw new ApiError(
      "Can't reach the backend. Check your connection and that VITE_API_BASE_URL points to a running server.",
      0
    );
  }
  let body = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON body */
  }
  if (!res.ok) throw new ApiError(readableError(res.status, body), res.status);
  return body;
}

export const getHealth = () => request("/health");

// Sends only the latest message; the backend owns the history.
export const postChat = ({ session_id, message, system_prompt }) => {
  const payload = { session_id, message };
  if (system_prompt && system_prompt.trim()) payload.system_prompt = system_prompt;
  return request("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
};

export const getSessionMessages = async (sessionId) => {
  try {
    return await request(`/sessions/${encodeURIComponent(sessionId)}/messages`);
  } catch (e) {
    if (e.status === 404)
      throw new ApiError("This session could not be found on the server, so its messages can't be reloaded.", 404);
    throw e;
  }
};

export const newSessionId = () => `s-${crypto.randomUUID()}`;
