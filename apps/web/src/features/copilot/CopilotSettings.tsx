import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api, orgPath } from "../../lib/api";
import { Feedback, QueryState, useResource } from "../../lib/useResource";
import type { CopilotApproval, CopilotPolicy } from "./types";

// Owners and admins manage memory defaults and pending saved-chat requests here.
export function CopilotSettings({ organizationId }: { organizationId: string }) {
  const base = orgPath(organizationId, "/ai/copilot");
  const policy = useResource<CopilotPolicy>(
    ["copilot-policy", organizationId], `${base}/policy`,
  );
  const approvals = useResource<{ items: CopilotApproval[] }>(
    ["copilot-approvals", organizationId], `${base}/approvals?limit=50`,
  );
  const [temporaryDefault, setTemporaryDefault] = useState(false);
  const [memoryLimit, setMemoryLimit] = useState(10);
  const [busy, setBusy] = useState(false);
  const [decidingId, setDecidingId] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  useEffect(() => {
    if (policy.data) {
      setTemporaryDefault(policy.data.temporary_default);
      setMemoryLimit(policy.data.memory_turn_limit);
    }
  }, [policy.data]);

  // Persist the business-owned policy for this organization.
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      await api<CopilotPolicy>(`${base}/policy`, {
        method: "PUT",
        body: JSON.stringify({
          temporary_default: temporaryDefault,
          memory_turn_limit: memoryLimit,
        }),
      });
      await policy.refetch();
      setSuccess("Política do copiloto salva.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível salvar a política.");
    } finally {
      setBusy(false);
    }
  }

  // Approve or reject one analyst request, then refresh the pending queue.
  async function decide(id: string, decision: "approve" | "reject") {
    setError("");
    setSuccess("");
    setDecidingId(id);
    try {
      await api(`${base}/conversations/${id}/${decision}`, { method: "POST" });
      await approvals.refetch();
      setSuccess(decision === "approve" ? "Chat aprovado." : "Pedido rejeitado.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível registrar a decisão.");
    } finally {
      setDecidingId("");
    }
  }

  return (
    <section className="card copilot-settings">
      <h2>Copiloto conversacional</h2>
      <p className="muted">
        Chats normais podem compor a memória compartilhada desta organização.
        Evidências citadas são verificadas antes de cada resposta.
      </p>
      <QueryState loading={policy.isLoading} error={policy.error} />
      <Feedback error={error} success={success} />
      {policy.data && (
        <form onSubmit={save}>
          <label className="copilot-checkbox">
            <input type="checkbox" checked={temporaryDefault}
              onChange={(event) => setTemporaryDefault(event.target.checked)} />
            Iniciar chats no modo temporário por padrão
          </label>
          <p className="muted">
            Com esse padrão, um analista precisa de aprovação para criar um chat normal.
          </p>
          <label>
            Turnos de outros chats usados como memória (0 a 20)
            <input type="number" min="0" max="20" required value={memoryLimit}
              onChange={(event) => setMemoryLimit(Number(event.target.value))} />
          </label>
          <button className="button primary" disabled={busy}>Salvar política do copiloto</button>
        </form>
      )}
      <h3>Pedidos para salvar chats</h3>
      <QueryState loading={approvals.isLoading} error={approvals.error} />
      {approvals.data?.items.length ? (
        <ul className="copilot-approvals">
          {approvals.data.items.map((item) => {
            const path = item.finding_id
              ? `/findings/${item.finding_id}`
              : `/audits/${item.audit_id}`;
            return (
              <li key={item.id}>
                <div>
                  <strong>Solicitação de {item.author_id.slice(0, 8)}</strong>
                  <p className="muted">
                    <Link to={`/organizations/${organizationId}${path}`}>
                      {item.finding_id ? "Ver achado" : "Ver auditoria"}
                    </Link>{" "}· {new Date(item.created_at).toLocaleString("pt-BR")}
                  </p>
                </div>
                <div className="copilot-approval-actions">
                  <button className="button secondary" disabled={Boolean(decidingId)}
                    onClick={() => void decide(item.id, "approve")}>Aprovar</button>
                  <button className="button secondary" disabled={Boolean(decidingId)}
                    onClick={() => void decide(item.id, "reject")}>Rejeitar</button>
                </div>
              </li>
            );
          })}
        </ul>
      ) : approvals.data && <p className="empty">Nenhum pedido pendente.</p>}
    </section>
  );
}
