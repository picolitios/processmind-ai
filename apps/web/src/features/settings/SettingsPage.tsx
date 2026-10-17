import { useEffect, useState } from "react";
import { useOutletContext } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { api, json, orgPath } from "../../lib/api";
import type { Organization, Page, Role } from "../../lib/api";
import { Feedback, QueryState, useResource } from "../../lib/useResource";
import type { ShellContext } from "../shell/Shell";
import { canAdmin, roleLabel } from "../shell/Shell";
import { CopilotSettings } from "../copilot/CopilotSettings";

type Member = {
  organization_id: string;
  user_id: string;
  role: Role;
  status: string;
};
export function SettingsPage() {
  const { organizationId, role, current } = useOutletContext<ShellContext>();
  const client = useQueryClient();
  const members = useResource<Page<Member>>(
    ["members", organizationId],
    orgPath(organizationId, "/users"),
    canAdmin(role),
  );
  const [delay, setDelay] = useState(90);
  const [currency, setCurrency] = useState("BRL");
  const [amount, setAmount] = useState("");
  const [email, setEmail] = useState("");
  const [memberRole, setMemberRole] = useState<Role>("viewer");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (current) {
      setDelay(current.settings.delay_window_days || 90);
      setAmount(current.settings.amount_limits?.[currency] || "");
    }
  }, [current, currency]);
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      const limits = { ...current?.settings.amount_limits };
      if (amount) limits[currency] = amount;
      else delete limits[currency];
      await api<Organization>(
        orgPath(organizationId),
        json("PATCH", {
          delay_window_days: delay,
          amount_limits: limits,
        }),
      );
      await client.invalidateQueries({ queryKey: ["organizations"] });
      setSuccess("Configurações salvas.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao salvar");
    } finally {
      setBusy(false);
    }
  }
  async function invite(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      await api(
        orgPath(organizationId, "/users"),
        json("POST", { email, role: memberRole }),
      );
      setEmail("");
      await members.refetch();
      setSuccess("Usuário adicionado.");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Falha ao adicionar usuário",
      );
    } finally {
      setBusy(false);
    }
  }
  async function changeMember(
    userId: string,
    changes: { role?: Role; status?: string },
  ) {
    setError("");
    setSuccess("");
    try {
      await api(
        orgPath(organizationId, `/users/${userId}`),
        json("PATCH", changes),
      );
      await members.refetch();
      setSuccess("Acesso atualizado. A sessão do usuário foi revogada.");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Falha ao alterar acesso",
      );
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ADMINISTRAÇÃO</p>
          <h1>Configurações</h1>
          <p className="muted">
            Parâmetros de auditoria e acesso à organização.
          </p>
        </div>
      </div>
      <div className="two-columns">
        <section className="card">
          <h2>Parâmetros da organização</h2>
          <p className="muted">
            Versão atual: {current?.settings_version || "—"}
          </p>
          {canAdmin(role) ? (
            <form onSubmit={save}>
              <label>
                Janela de atraso (dias)
                <input
                  type="number"
                  min="1"
                  max="3650"
                  required
                  value={delay}
                  onChange={(e) => setDelay(Number(e.target.value))}
                />
              </label>
              <label>
                Moeda
                <select
                  value={currency}
                  onChange={(e) => setCurrency(e.target.value)}
                >
                  <option value="BRL">BRL</option>
                  <option value="USD">USD</option>
                  <option value="EUR">EUR</option>
                </select>
              </label>
              <label>
                Limite de valor
                <input
                  inputMode="decimal"
                  pattern="[0-9]+(\.[0-9]{1,2})?"
                  placeholder="Ex.: 10000.00"
                  value={amount}
                  onChange={(e) => setAmount(e.target.value)}
                />
              </label>
              <button className="button primary" disabled={busy}>
                Salvar configurações
              </button>
            </form>
          ) : (
            <p className="empty">
              Somente administradores podem alterar configurações.
            </p>
          )}
        </section>
        <section className="card">
          <h2>Usuários</h2>
          {canAdmin(role) ? (
            <>
              <QueryState loading={members.isLoading} error={members.error} />
              {members.data?.items.map((member) => (
                <div className="member-row" key={member.user_id}>
                  <code>{member.user_id.slice(0, 8)}</code>
                  {role === "owner" ? (
                    <>
                      <select
                        aria-label={`Perfil de ${member.user_id.slice(0, 8)}`}
                        value={member.role}
                        onChange={(event) =>
                          void changeMember(member.user_id, {
                            role: event.target.value as Role,
                          })
                        }
                      >
                        <option value="owner">Proprietário</option>
                        <option value="admin">Administrador</option>
                        <option value="analyst">Analista</option>
                        <option value="viewer">Visualizador</option>
                      </select>
                      <select
                        aria-label={`Status de ${member.user_id.slice(0, 8)}`}
                        value={member.status}
                        onChange={(event) =>
                          void changeMember(member.user_id, {
                            status: event.target.value,
                          })
                        }
                      >
                        <option value="active">Ativo</option>
                        <option value="inactive">Inativo</option>
                      </select>
                    </>
                  ) : (
                    <>
                      <span>{roleLabel(member.role)}</span>
                      <small>{member.status}</small>
                    </>
                  )}
                </div>
              ))}
              {role === "owner" && (
                <form onSubmit={invite}>
                  <h3>Adicionar usuário existente</h3>
                  <label>
                    E-mail
                    <input
                      type="email"
                      required
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                    />
                  </label>
                  <label>
                    Perfil
                    <select
                      value={memberRole}
                      onChange={(e) => setMemberRole(e.target.value as Role)}
                    >
                      <option value="viewer">Visualizador</option>
                      <option value="analyst">Analista</option>
                      <option value="admin">Administrador</option>
                    </select>
                  </label>
                  <button className="button secondary" disabled={busy}>
                    Adicionar usuário
                  </button>
                </form>
              )}
            </>
          ) : (
            <p className="empty">Usuários visíveis para administradores.</p>
          )}
        </section>
      </div>
      {canAdmin(role) && <CopilotSettings organizationId={organizationId} />}
      <Feedback error={error} success={success} />
    </>
  );
}
