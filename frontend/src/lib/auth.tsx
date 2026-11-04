import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, setActiveCompany } from "./api";
import type { Me } from "./types";

interface AuthCtx {
  me: Me | null;
  loading: boolean;
  companyId: number | null;
  company: Me["companies"][number] | null;
  isAdmin: boolean;
  switchCompany: (id: number) => Promise<void>;
  reload: () => Promise<void>;
  logout: () => Promise<void>;
}

const Ctx = createContext<AuthCtx | null>(null);
const LS_KEY = "naklady.company";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [companyId, setCompanyId] = useState<number | null>(null);
  const qc = useQueryClient();

  const reload = useCallback(async () => {
    try {
      let stored: number | null = null;
      try {
        stored = Number(localStorage.getItem(LS_KEY)) || null;
      } catch {
        /* storage unavailable */
      }
      const m = await api.get<Me>("/api/auth/me");
      let cid = m.company_id;
      if (stored && m.companies.some((c) => c.id === stored)) cid = stored;
      setActiveCompany(cid);
      setCompanyId(cid);
      setMe(m);
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const switchCompany = useCallback(
    async (id: number) => {
      setActiveCompany(id);
      setCompanyId(id);
      try {
        localStorage.setItem(LS_KEY, String(id));
      } catch {
        /* ignore */
      }
      await api.post("/api/auth/company", { company_id: id });
      qc.clear();
    },
    [qc],
  );

  const logout = useCallback(async () => {
    await api.post("/api/auth/logout");
    setMe(null);
    qc.clear();
    location.href = "/prihlasenie";
  }, [qc]);

  const company = me?.companies.find((c) => c.id === companyId) ?? null;
  return (
    <Ctx.Provider
      value={{ me, loading, companyId, company, isAdmin: me?.role === "admin", switchCompany, reload, logout }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  const c = useContext(Ctx);
  if (!c) throw new Error("AuthProvider missing");
  return c;
}
