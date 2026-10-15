import { useState } from "react";
import { Link, useOutletContext } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { api, json, orgPath, query } from "../../lib/api";
import type { Audit, ImportBatch, Page } from "../../lib/api";
import { Feedback, QueryState, useResource } from "../../lib/useResource";
import type { ShellContext } from "../shell/Shell";
import { canWrite } from "../shell/Shell";
import { Status } from "../imports/ImportsPage";

export function AuditsPage() {
  const { organizationId, role } = useOutletContext<ShellContext>();
  const [cursor, setCursor] = useState("");
  const [selected, setSelected] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const client = useQueryClient();
  const imports = useResource<Page<ImportBatch>>(
    ["audit-imports", organizationId],
    orgPath(organizationId, "/imports"),
    Boolean(organizationId),
  );
  const audits = useResource<Page<Audit>>(
    ["audits", organizationId, cursor],
    orgPath(organizationId, `/audits${query({ cursor })}`),
    Boolean(organizationId),
    4000,
  );
  async function run(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      await api(
        orgPath(organizationId, "/audits"),
        json(
          "POST",
          { import_ids: selected },
          { "Idempotency-Key": crypto.randomUUID() },
        ),
      );
      setSelected([]);
      await client.invalidateQueries({ queryKey: ["audits", organizationId] });
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Falha ao iniciar auditoria",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ANÁLISE DE COMPRAS</p>
          <h1>Auditorias</h1>
          <p className="muted">
            Execute regras determinísticas sobre importações concluídas.
          </p>
        </div>
      </div>
      {canWrite(role) && (
        <section className="card">
          <h2>Nova auditoria</h2>
          <p className="muted">Selecione até 50 importações concluídas.</p>
          <form onSubmit={run}>
            <div className="choice-list">
              {imports.data?.items
                .filter((item) => item.status === "succeeded")
                .map((item) => (
                  <label className="choice" key={item.id}>
                    <input
                      type="checkbox"
                      checked={selected.includes(item.id)}
                      onChange={(e) =>
                        setSelected(
                          e.target.checked
                            ? [...selected, item.id]
                            : selected.filter((id) => id !== item.id),
                        )
                      }
                    />
                    <span>{item.filename}</span>
                    <small>{item.row_count} linhas</small>
                  </label>
                ))}
              {!imports.data?.items.some(
                (item) => item.status === "succeeded",
              ) && (
                <p className="empty">
                  Nenhuma importação concluída.{" "}
                  <Link to={`/organizations/${organizationId}/imports`}>
                    Importar dados
                  </Link>
                </p>
              )}
            </div>
            <Feedback error={error} />
            <button
              className="button primary"
              disabled={busy || !selected.length}
            >
              {busy ? "Iniciando…" : "Executar auditoria"}
            </button>
          </form>
        </section>
      )}
      <section className="card">
        <h2>Histórico de auditorias</h2>
        <QueryState loading={audits.isLoading} error={audits.error} />
        {audits.data?.items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Execução</th>
                  <th>Status</th>
                  <th>Achados</th>
                  <th>Versão das regras</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {audits.data.items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <code>{item.id.slice(0, 8)}</code>
                    </td>
                    <td>
                      <Status value={item.status} />
                    </td>
                    <td>{item.finding_count}</td>
                    <td>{item.rule_set_version}</td>
                    <td>
                      <Link
                        to={`/organizations/${organizationId}/audits/${item.id}`}
                      >
                        Abrir →
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          audits.data && <p className="empty">Nenhuma auditoria executada.</p>
        )}
        {audits.data?.next_cursor && (
          <button
            className="button secondary"
            onClick={() => setCursor(audits.data!.next_cursor!)}
          >
            Próxima página
          </button>
        )}
      </section>
    </>
  );
}
