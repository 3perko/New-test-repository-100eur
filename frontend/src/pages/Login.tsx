import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Spinner } from "@/components/ui";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const { reload } = useAuth();
  const nav = useNavigate();
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr("");
    try {
      await api.post("/api/auth/login", { email, password });
      await reload();
      nav("/");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="flex min-h-full items-center justify-center p-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4 p-6">
        <div>
          <h1 className="text-lg font-semibold">Náklady zákaziek</h1>
          <p className="text-sm text-slate-500">Prihláste sa svojím e-mailom a heslom.</p>
        </div>
        <div>
          <label className="label" htmlFor="email">E-mail</label>
          <input id="email" className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} autoFocus required />
        </div>
        <div>
          <label className="label" htmlFor="pwd">Heslo</label>
          <input id="pwd" className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </div>
        {err && <p className="text-sm text-red-600">{err}</p>}
        <button className="btn-primary w-full" disabled={busy}>{busy && <Spinner />} Prihlásiť</button>
      </form>
    </div>
  );
}
