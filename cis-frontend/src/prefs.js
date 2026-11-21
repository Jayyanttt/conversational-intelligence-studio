// User preferences: persisted in localStorage, applied as data-* attributes on <html>,
// and (analysis preferences) appended to the system prompt at send time.
const KEY = "cis.prefs.v1";
const osReduces = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export const loadPrefs = () => {
  let stored = {};
  try { stored = JSON.parse(localStorage.getItem(KEY)) || {}; } catch { /* unreadable: use defaults */ }
  return {
    theme: "system", largeText: false, highContrast: false,
    reduceMotion: osReduces(), detail: "balanced", evidence: false,
    ...stored,
  };
};

export const savePrefs = (p) => {
  try { localStorage.setItem(KEY, JSON.stringify(p)); } catch { /* storage unavailable */ }
};

// Sets data-theme (resolved to light|dark), data-text, data-contrast, data-motion.
// Returns a cleanup that stops following the OS colour scheme.
export const applyPrefs = (p) => {
  const root = document.documentElement;
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  const setTheme = () => {
    const dark = p.theme === "dark" || (p.theme === "system" && mq.matches);
    root.dataset.theme = dark ? "dark" : "light";
    root.style.colorScheme = dark ? "dark" : "light";
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", dark ? "#1b1915" : "#F4F1EA");
  };
  setTheme();
  root.dataset.text = p.largeText ? "large" : "normal";
  root.dataset.contrast = p.highContrast ? "high" : "normal";
  root.dataset.motion = p.reduceMotion ? "reduce" : "normal";
  mq.addEventListener("change", setTheme);
  return () => mq.removeEventListener("change", setTheme);
};

// Analysis preferences travel inside system_prompt, so the API contract is unchanged.
// Defaults (balanced, evidence off) add nothing, keeping the prompt identical to the preset.
export const withPreferences = (base, p) => {
  const extra = [];
  if (p.detail === "concise")
    extra.push("Response detail: keep the answer concise. Lead with the key findings in short bullets and skip preamble.");
  if (p.detail === "detailed")
    extra.push("Response detail: be thorough. Explain your reasoning and cover secondary patterns and caveats.");
  if (p.evidence)
    extra.push("Evidence rule: support every finding with a direct quotation (under 25 words) from the supplied text, and label each point as either Observation (stated in the text) or Interpretation (your inference). If no quotation supports a point, say so instead of asserting it.");
  return extra.length ? `${base}\n\n${extra.join("\n")}` : base;
};
