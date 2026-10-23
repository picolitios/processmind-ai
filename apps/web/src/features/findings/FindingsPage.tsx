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
  const [activeItem, setActiveItem] = useState("");
  const findings = useResource<Page<Finding>>(
    ["findings", organizationId, severity, review, cursor],
    orgPath(
      organizationId,
      `/findings${query({ severity, review_state: review, cursor, limit: "100" })}`,
    ),
    Boolean(organizationId),
  );
  const items = findings.data?.items || [];
  const groups = Array.from(
    new Map(items.map((item) => [item.subject_key, item.subject_label])).entries(),
  );
  const selectedItem = groups.some(([key]) => key === activeItem) ? activeItem : "";
  const visibleItems = selectedItem
    ? items.filter((item) => item.subject_key === selectedItem)
    : items;
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
      {groups.length > 0 && (
        <div className="item-tabs" role="tablist" aria-label="Alertas por item analisado">
          <button
            type="button"
            role="tab"
            aria-selected={!selectedItem}
            className={!selectedItem ? "active" : ""}
            onClick={() => setActiveItem("")}
          >
            Todos ({items.length})
          </button>
          {groups.map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={selectedItem === key}
              className={selectedItem === key ? "active" : ""}
              onClick={() => setActiveItem(key)}
            >
              {label} ({items.filter((item) => item.subject_key === key).length})
            </button>
          ))}
        </div>
      )}
      <section className="card">
        <QueryState loading={findings.isLoading} error={findings.error} />
        {visibleItems.length ? (
          <div className="list">
            {visibleItems.map((item) => (
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
                  <small>{item.subject_label}</small>
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
