import { useState } from "react";
import { Link, useOutletContext } from "react-router";
import { orgPath, query } from "../../lib/api";
import type { Case, Page } from "../../lib/api";
import { QueryState, useResource } from "../../lib/useResource";
import type { ShellContext } from "../shell/Shell";
import { Status } from "../imports/ImportsPage";

export function CasesPage() {
  const { organizationId } = useOutletContext<ShellContext>();
  const [status, setStatus] = useState("");
  const [cursor, setCursor] = useState("");
  const cases = useResource<Page<Case>>(
    ["cases", organizationId, status, cursor],
    orgPath(organizationId, `/cases${query({ status, cursor })}`),
    Boolean(organizationId),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ACOMPANHAMENTO</p>
          <h1>Casos</h1>
          <p className="muted">
            Acompanhe responsáveis, conversas e decisões de cada achado.
          </p>
        </div>
      </div>
      <div className="filter-bar">
        <label>
          Status
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value);
              setCursor("");
            }}
          >
            <option value="">Todos</option>
            <option value="open">Abertos</option>
            <option value="in_review">Em revisão</option>
            <option value="resolved">Resolvidos</option>
            <option value="dismissed">Descartados</option>
          </select>
        </label>
      </div>
      <section className="card">
        <QueryState loading={cases.isLoading} error={cases.error} />
        {cases.data?.items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Caso</th>
                  <th>Status</th>
                  <th>Responsável</th>
                  <th>Aberto em</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {cases.data.items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      <code>{item.id.slice(0, 8)}</code>
                    </td>
                    <td>
                      <Status value={item.status} />
                    </td>
                    <td>
                      {item.assignee_user_id?.slice(0, 8) || "Não atribuído"}
                    </td>
                    <td>
                      {new Date(item.opened_at).toLocaleDateString("pt-BR")}
                    </td>
                    <td>
                      <Link
                        to={`/organizations/${organizationId}/cases/${item.id}`}
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
          cases.data && <p className="empty">Nenhum caso encontrado.</p>
        )}
        {cases.data?.next_cursor && (
          <button
            className="button secondary"
            onClick={() => setCursor(cases.data!.next_cursor!)}
          >
            Próxima página
          </button>
        )}
      </section>
    </>
  );
}
