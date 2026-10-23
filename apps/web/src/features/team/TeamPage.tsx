import { useState } from "react";
import { useOutletContext } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { api, json, orgPath, query } from "../../lib/api";
import type { Page, Role } from "../../lib/api";
import { Feedback, QueryState, useResource } from "../../lib/useResource";
import type { ShellContext } from "../shell/Shell";
import { canAdmin, roleLabel } from "../shell/Shell";

type Member = { user_id: string; email: string; display_name: string | null; role: Role; status: string };
type Invite = { id: string; email: string; role: Role; expires_at: string; accepted_at: string | null; cancelled_at: string | null };

// Team management keeps pending invitations separate from active memberships.
export function TeamPage() {
  const { organizationId, role } = useOutletContext<ShellContext>();
  const { session, refresh } = useAuth();
  const [cursor, setCursor] = useState("");
  const members = useResource<Page<Member>>(["team", organizationId, cursor], orgPath(organizationId, `/users${query({ cursor, limit: "100" })}`), canAdmin(role));
  const invites = useResource<Invite[]>(["invites", organizationId], orgPath(organizationId, "/invitations"), canAdmin(role));
  const [name, setName] = useState(session?.user.display_name || "");
  const [email, setEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"admin" | "analyst" | "viewer">("viewer");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function act(operation: () => Promise<unknown>, message: string) {
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      await operation();
      await Promise.all([members.refetch(), invites.refetch()]);
      setSuccess(message);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível concluir a ação");
    } finally {
      setBusy(false);
    }
  }

  return <>
    <div className="page-heading"><div><p className="eyebrow">ORGANIZAÇÃO</p><h1>Equipe</h1><p className="muted">Membros, cargos e convites por e-mail.</p></div></div>
    <Feedback error={error} success={success} />
    <section className="card">
      <h2>Seu perfil</h2>
      <form onSubmit={(event) => { event.preventDefault(); void act(async () => { await api("/auth/profile", json("PATCH", { display_name: name })); await refresh(); }, "Nome atualizado."); }}>
        <label>Nome exibido<input value={name} minLength={2} maxLength={120} required onChange={(event) => setName(event.target.value)} /></label>
        <button className="button secondary" disabled={busy}>Salvar nome</button>
      </form>
    </section>
    {canAdmin(role) && <section className="card">
      <h2>Membros</h2>
      <QueryState loading={members.isLoading} error={members.error} />
      {members.data?.items.map((member) => <div className="member-row" key={member.user_id}>
        <span><strong>{member.display_name || member.email}</strong><small> · {member.email}</small></span>
        {role === "owner" && member.role !== "owner" ? <>
          <select aria-label={`Cargo de ${member.email}`} value={member.role} disabled={busy} onChange={(event) => void act(() => api(orgPath(organizationId, `/users/${member.user_id}`), json("PATCH", { role: event.target.value })), "Cargo atualizado.")}>
            <option value="admin">Administrador</option><option value="analyst">Líder</option><option value="viewer">Funcionário</option>
          </select>
          <select aria-label={`Acesso de ${member.email}`} value={member.status} disabled={busy} onChange={(event) => void act(() => api(orgPath(organizationId, `/users/${member.user_id}`), json("PATCH", { status: event.target.value })), "Acesso atualizado.")}>
            <option value="active">Ativo</option><option value="inactive">Inativo</option>
          </select>
        </> : <span>{roleLabel(member.role)} · {member.status === "active" ? "Ativo" : "Inativo"}</span>}
      </div>)}
      {!members.data?.items.length && !members.isLoading && <p className="empty">Nenhum membro encontrado.</p>}
      {members.data?.next_cursor && <button className="button secondary" onClick={() => setCursor(members.data!.next_cursor!)}>Próximos membros</button>}
    </section>}
    {role === "owner" && <section className="card">
      <h2>Convidar por e-mail</h2>
      <p className="muted">O acesso só é ativado após a pessoa abrir o convite e entrar com o mesmo e-mail.{window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1" ? <> Na demo local, veja a mensagem em <a href={`http://${window.location.hostname}:${window.location.port === "5174" ? "8026" : "8025"}`} target="_blank" rel="noreferrer">Mailpit</a>.</> : null}</p>
      <form onSubmit={(event) => { event.preventDefault(); void act(async () => { await api(orgPath(organizationId, "/invitations"), json("POST", { email, role: inviteRole })); setEmail(""); }, "Convite enviado."); }}>
        <label>E-mail<input type="email" value={email} required onChange={(event) => setEmail(event.target.value)} /></label>
        <label>Cargo<select value={inviteRole} onChange={(event) => setInviteRole(event.target.value as typeof inviteRole)}><option value="viewer">Funcionário</option><option value="analyst">Líder</option><option value="admin">Administrador</option></select></label>
        <button className="button primary" disabled={busy || invites.isLoading}>Enviar convite</button>
      </form>
      <h3>Convites pendentes</h3>
      <QueryState loading={invites.isLoading} error={invites.error} />
      {invites.data?.filter((invite) => !invite.accepted_at && !invite.cancelled_at && new Date(invite.expires_at) > new Date()).map((invite) => <div className="member-row" key={invite.id}>
        <span>{invite.email} · {roleLabel(invite.role)}</span>
        <button className="button secondary" disabled={busy} onClick={() => void act(() => api(orgPath(organizationId, `/invitations/${invite.id}/cancel`), { method: "POST" }), "Convite cancelado.")}>Cancelar</button>
      </div>)}
      {!invites.data?.some((invite) => !invite.accepted_at && !invite.cancelled_at && new Date(invite.expires_at) > new Date()) && <p className="empty">Nenhum convite pendente.</p>}
    </section>}
  </>;
}
