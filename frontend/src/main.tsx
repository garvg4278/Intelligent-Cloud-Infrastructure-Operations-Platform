import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { ErrorBoundary } from "./app/ErrorBoundary";
import { Providers } from "./app/Providers";
import { loadConfig } from "./config/runtime";
import "./styles/index.css";

const container = document.getElementById("root");
if (!container) throw new Error("Missing #root element");

void loadConfig().then((config) => {
  createRoot(container).render(
    <StrictMode>
      <ErrorBoundary>
        <Providers config={config}>
          <App />
        </Providers>
      </ErrorBoundary>
    </StrictMode>,
  );
});
