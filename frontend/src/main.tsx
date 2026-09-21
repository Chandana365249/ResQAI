import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import { AnalysisProvider } from "./state/AnalysisContext";
import { SystemStatusProvider } from "./state/SystemStatusContext";
import "./index.css";

const container = document.getElementById("root");
if (!container) throw new Error("Root element #root not found.");

createRoot(container).render(
  <StrictMode>
    <BrowserRouter>
      <SystemStatusProvider>
        <AnalysisProvider>
          <App />
        </AnalysisProvider>
      </SystemStatusProvider>
    </BrowserRouter>
  </StrictMode>,
);
