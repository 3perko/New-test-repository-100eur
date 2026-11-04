import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/lib/auth";
import { ToastProvider } from "@/components/ui";
import App from "./App";
import "./index.css";

try {
  const t = localStorage.getItem("naklady.theme");
  const dark = t ? t === "dark" : window.matchMedia?.("(prefers-color-scheme: dark)").matches;
  document.documentElement.classList.toggle("dark", !!dark);
} catch {
  /* ignore */
}

const qc = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <ToastProvider>
          <AuthProvider>
            <App />
          </AuthProvider>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
