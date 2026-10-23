import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { api, json } from "../../lib/api";
import { Feedback } from "../../lib/useResource";
import { useAuth } from "./AuthProvider";
import { ThemeToggle } from "../theme/ThemeProvider";

export function AuthPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [register, setRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      if (register)
        await api("/auth/register", json("POST", { email, password, display_name: displayName }));
      await login(email, password);
      navigate(searchParams.has("invite") ? "/invite" : "/", { replace: true });
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Não foi possível entrar",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-page">
      <div className="auth-art">
        <div className="brand-mark">PM</div>
        <p className="eyebrow">PROCESSMIND AI</p>
        <h1>Clareza para cada decisão de compra.</h1>
        <p>
          Importe dados, execute auditorias e acompanhe cada achado até sua
          resolução.
        </p>
        <div className="art-grid" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
          <span />
          <span />
          <span />
          <span />
          <span />
        </div>
      </div>
      <section className="auth-panel">
        <div className="auth-theme"><ThemeToggle /></div>
        <div className="auth-card">
          <p className="eyebrow">ACESSO À PLATAFORMA</p>
          <h2>{register ? "Criar conta" : "Bem-vindo de volta"}</h2>
          <p className="muted">
            {register
              ? "Use seu e-mail de trabalho para começar."
              : "Entre para acompanhar suas auditorias."}
          </p>
          <form onSubmit={submit}>
            {register && <label>Seu nome<input value={displayName} minLength={2} maxLength={120} required autoComplete="name" onChange={(event) => setDisplayName(event.target.value)} /></label>}
            <label>
              E-mail
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </label>
            <label>
              Senha
              <input
                type="password"
                autoComplete={register ? "new-password" : "current-password"}
                minLength={register ? 12 : undefined}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {register && <p className="hint">Use pelo menos 12 caracteres.</p>}
            <Feedback error={error} />
            <button className="button primary full" disabled={busy}>
              {busy ? "Aguarde…" : register ? "Criar conta" : "Entrar"}
            </button>
          </form>
          <p className="auth-switch">
            {register ? "Já possui conta?" : "Novo por aqui?"}{" "}
            <button
              className="text-button"
              type="button"
              onClick={() => {
                setRegister(!register);
                setError("");
              }}
            >
              {register ? "Entrar" : "Criar conta"}
            </button>
          </p>
        </div>
      </section>
    </main>
  );
}
