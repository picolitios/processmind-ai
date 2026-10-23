import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { api, json } from "../../lib/api";
import { Feedback } from "../../lib/useResource";
import { useAuth } from "../auth/AuthProvider";

const storageKey = "processmind-pending-invite";

// The emailed token is removed from the address bar before any API call.
export function InviteAcceptPage() {
  const { session, refresh, logout } = useAuth();
  const navigate = useNavigate();
  const [token] = useState(() => {
    const fragment = window.location.hash.slice(1);
    if (fragment) {
      sessionStorage.setItem(storageKey, fragment);
      window.history.replaceState(window.history.state, "", "/invite");
    }
    return fragment || sessionStorage.getItem(storageKey) || "";
  });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function accept() {
    setBusy(true);
    setError("");
    try {
      const membership = await api<{ organization_id: string }>(
        "/auth/invitations/accept", json("POST", { token }),
      );
      sessionStorage.removeItem(storageKey);
      await refresh();
      navigate(`/organizations/${membership.organization_id}/dashboard`, { replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível aceitar o convite");
    } finally {
      setBusy(false);
    }
  }
  return <main className="auth-page"><section className="auth-panel"><div className="auth-card">
    <p className="eyebrow">CONVITE PARA EQUIPE</p><h1>Entrar na organização</h1>
    {!token ? <p>O link de convite está incompleto. Solicite um novo convite ao proprietário.</p> : !session ? <><p>Entre ou crie uma conta com o e-mail que recebeu o convite.</p><Link className="button primary" to="/login?invite=1">Entrar ou criar conta</Link></> : <><p>Confirme que deseja entrar na organização com {session.user.email}.</p><div className="invite-actions"><button className="button primary" disabled={busy} onClick={() => void accept()}>{busy ? "Confirmando…" : "Confirmar convite"}</button><button className="button secondary" disabled={busy} onClick={() => void logout().then(() => navigate("/login?invite=1"))}>Usar outro e-mail</button></div><Feedback error={error} /></>}
    {error && <Link to="/">Voltar às organizações</Link>}
  </div></section></main>;
}
