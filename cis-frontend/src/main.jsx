import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import { applyPrefs, loadPrefs } from "./prefs.js";
import "./styles.css";

applyPrefs(loadPrefs()); // before first paint, so a saved theme never flashes the wrong colours

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
