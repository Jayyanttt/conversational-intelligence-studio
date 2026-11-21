import { useEffect } from "react";

// Calls onClose on Escape, or on a press outside `ref`, while `open` is true.
export function useDismiss(open, onClose, ref) {
  useEffect(() => {
    if (!open) return;
    const key = (e) => { if (e.key === "Escape") onClose(); };
    const press = (e) => { if (ref.current && !ref.current.contains(e.target)) onClose(); };
    document.addEventListener("keydown", key);
    document.addEventListener("mousedown", press);
    return () => { document.removeEventListener("keydown", key); document.removeEventListener("mousedown", press); };
  }, [open, onClose, ref]);
}
