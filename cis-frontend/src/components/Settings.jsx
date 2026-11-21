import { useEffect, useRef } from "react";
import { useDismiss } from "../useDismiss.js";

export const GearIcon = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
    <path d="M3 6h9M15 6h2M3 14h2M8 14h9" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
    <circle cx="13.5" cy="6" r="1.7" stroke="currentColor" strokeWidth="1.5" />
    <circle cx="6.5" cy="14" r="1.7" stroke="currentColor" strokeWidth="1.5" />
  </svg>
);

function Segmented({ label, value, options, onChange }) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map(([v, text]) => (
        <button key={v} type="button" role="radio" aria-checked={value === v} onClick={() => onChange(v)}>
          {text}
        </button>
      ))}
    </div>
  );
}

function Toggle({ label, hint, checked, onChange }) {
  return (
    <label className="toggle">
      <span>
        <b>{label}</b>
        {hint && <small>{hint}</small>}
      </span>
      <input type="checkbox" role="switch" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span className="track" aria-hidden="true" />
    </label>
  );
}

export default function Settings({ prefs, onChange, onClose }) {
  const ref = useRef(null);
  useDismiss(true, onClose, ref);

  // Move focus into the dialog, and keep Tab inside it while open.
  useEffect(() => {
    const el = ref.current;
    el.querySelector("button")?.focus();
    const trap = (e) => {
      if (e.key !== "Tab") return;
      const f = [...el.querySelectorAll("button, input")];
      const first = f[0], last = f[f.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    el.addEventListener("keydown", trap);
    return () => el.removeEventListener("keydown", trap);
  }, []);

  return (
    <div className="settings" role="dialog" aria-label="Settings" ref={ref}>
      <header>
        <h2>Settings</h2>
        <button type="button" className="icon-btn" aria-label="Close settings" onClick={onClose}>
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
            <path d="M2 2l10 10M12 2L2 12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </button>
      </header>

      <h3>Appearance</h3>
      <Segmented label="Theme" value={prefs.theme} onChange={(theme) => onChange({ theme })}
        options={[["light", "Light"], ["dark", "Dark"], ["system", "System"]]} />

      <h3>Accessibility</h3>
      <Toggle label="Larger text" checked={prefs.largeText} onChange={(largeText) => onChange({ largeText })} />
      <Toggle label="High contrast" checked={prefs.highContrast} onChange={(highContrast) => onChange({ highContrast })} />
      <Toggle label="Reduce motion" checked={prefs.reduceMotion} onChange={(reduceMotion) => onChange({ reduceMotion })} />

      <h3>Analysis preferences</h3>
      <Segmented label="Response detail" value={prefs.detail} onChange={(detail) => onChange({ detail })}
        options={[["concise", "Concise"], ["balanced", "Balanced"], ["detailed", "Detailed"]]} />
      <Toggle label="Require evidence"
        hint="Ask for direct quotations and label each point as an observation or an interpretation."
        checked={prefs.evidence} onChange={(evidence) => onChange({ evidence })} />
      <p className="hint">Analysis preferences apply to your next message.</p>
    </div>
  );
}
