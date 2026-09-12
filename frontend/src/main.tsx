import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

function App() {
  return (
    <main className="app-shell">
      <header>
        <span className="eyebrow">CODE INTELLIGENCE</span>
        <h1>CodeFlow</h1>
        <p>Understand how your code actually flows.</p>
      </header>
      <section className="status-card" aria-label="System status">
        <strong>V1 Foundation ready</strong>
        <span>Python analysis engine + strict TypeScript UI</span>
      </section>
    </main>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode><App /></StrictMode>,
);
