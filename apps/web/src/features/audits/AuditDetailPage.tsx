import { Link, useOutletContext, useParams } from "react-router";
import { orgPath, query } from "../../lib/api";
import type { Audit, Finding, Page } from "../../lib/api";
import { QueryState, useResource } from "../../lib/useResource";
import type { ShellContext } from "../shell/Shell";
import { Status } from "../imports/ImportsPage";

export function AuditDetailPage() {
  const { organizationId } = useOutletContext<ShellContext>();
  const { auditId = "" } = useParams();
  const audit = useResource<Audit>(
    ["audit", auditId],
    orgPath(organizationId, `/audits/${auditId}`),
    Boolean(auditId),
    3000,
  );
  const findings = useResource<Page<Finding>>(
    ["audit-findings", auditId],
    orgPath(organizationId, `/findings${query({ audit_id: auditId })}`),
    audit.data?.status === "succeeded",
  );
  return (
    <>
      <Link
        className="back-link"
        to={`/organizations/${organizationId}/audits`}
      >
        ← Auditorias
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">EXECUÇÃO</p>
          <h1>Auditoria {auditId.slice(0, 8)}</h1>
          <p className="muted">
            {audit.data && (
              <>
                <Status value={audit.data.status} /> ·{" "}
                {audit.data.finding_count} achados · regras{" "}
                {audit.data.rule_set_version}
              </>
            )}
          </p>
        </div>
      </div>
      <QueryState loading={audit.isLoading} error={audit.error} />
      {audit.data?.limitation && (
        <p className="notice">{audit.data.limitation}</p>
      )}
      <section className="card">
        <h2>Achados desta auditoria</h2>
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
                  <strong>
                    {item.rule_code} · {item.severity}
                  </strong>
                  <small>{item.explanation}</small>
                </span>
                <span>→</span>
              </Link>
            ))}
          </div>
        ) : (
          findings.data && (
            <p className="empty">Nenhum achado nesta execução.</p>
          )
        )}
      </section>
    </>
  );
}
