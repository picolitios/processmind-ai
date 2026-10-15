import { useState } from "react";
import { Link, useOutletContext } from "react-router";
import { orgPath, query } from "../../lib/api";
import type { Finding, Page } from "../../lib/api";
import { QueryState, useResource } from "../../lib/useResource";
import type { ShellContext } from "../shell/Shell";
import { Status } from "../imports/ImportsPage";

export function FindingsPage() {
  const { organizationId } = useOutletContext<ShellContext>();
  const [severity, setSeverity] = useState("");
  const [review, setReview] = useState("");
  const [cursor, setCursor] = useState("");
  const findings = useResource<Page<Finding>>(
    ["findings", organizationId, severity, review, cursor],
    orgPath(
      organizationId,
      `/findings${query({ severity, review_state: review, cursor })}`,
    ),
    Boolean(organizationId),
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CENTRAL DE ALERTAS</p>
          <h1>Achados</h1>
          <p className="muted">
            Revise sinais detectados pelas regras de auditoria.
          </p>
        </div>
      </div>
      <div className="filter-bar">
        <label>
          Severidade
          <select
            value={severity}
            onChange={(e) => {
              setSeverity(e.target.value);
              setCursor("");
            }}
          >
            <option value="">Todas</option>
            {["critical", "high", "medium", "low"].map((value) => (
              <option key={value} value={value}>
                {value}
              </option>
            ))}
          </select>
        </label>
        <label>
          Revisão
          <select
            value={review}
            onChange={(e) => {
              setReview(e.target.value);
              setCursor("");
            }}
          >
            <option value="">Todos</option>
            <option value="unreviewed">Não revisado</option>
            <option value="in_review">Em revisão</option>
            <option value="resolved">Resolvido</option>
            <option value="dismissed">Descartado</option>
          </select>
        </label>
      </div>
      <section className="card">
        <QueryState loading={findings.isLoading} error={findings.error} />
        {findings.data?.items.length ? (
          <div className="list">
            {findings.data.items.map((item) => (
              <Link
                className="list-row"
                key={item.id}
                to={`/organizations/${organizationId}/findings/${item.id}`}
              >
                <span>
                  <span className={`severity severity-${item.severity}`}>
                    {item.severity}
                  </span>
                  <strong>{item.rule_code}</strong>
                  <small>{item.explanation}</small>
                </span>
                <span>
                  <Status value={item.review_state} /> →
                </span>
              </Link>
            ))}
          </div>
        ) : (
          findings.data && (
            <p className="empty">Nenhum achado para os filtros selecionados.</p>
          )
        )}
        {findings.data?.next_cursor && (
          <button
            className="button secondary"
            onClick={() => setCursor(findings.data!.next_cursor!)}
          >
            Próxima página
          </button>
        )}
      </section>
    </>
  );
}
