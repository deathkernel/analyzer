import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

type Health = { status: string; service: string; version: string };

function App() {
  const health: Health = { status: "ready", service: "codeflow-analyzer", version: "0.2.0" };
  return <main className="app"><span className="eyebrow">CODE INTELLIGENCE</span><h1>CodeFlow</h1><p>V2 parser engine is online.</p><section><b>{health.status.toUpperCase()}</b><span>{health.service} · v{health.version}</span></section></main>;
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
