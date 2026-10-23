import { useState } from "react";
import { useNavigate, useOutletContext, useParams } from "react-router";
import { api, json, orgPath } from "../../lib/api";
import type { Finding, Case } from "../../lib/api";
import { Feedback, QueryState, useResource } from "../../lib/useResource";
import type { ShellContext } from "../shell/Shell";
import { canWrite } from "../shell/Shell";
import { Status } from "../imports/ImportsPage";
import { AnalysisPanel } from "./AnalysisPanel";
import { DuplicateComparison } from "./DuplicateComparison";
import { CopilotPanel } from "../copilot/CopilotPanel";

export function FindingDetailPage() {
  const { organizationId, role } = useOutletContext<ShellContext>();
  const { findingId = "" } = useParams();
  const navigate = useNavigate();
  const detail = useResource<Finding>(
    ["finding", findingId],
    orgPath(organizationId, `/findings/${findingId}`),
    Boolean(findingId),
  );
  const [state, setState] = useState("in_review");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  async function openCase() {
    setError("");
    setBusy(true);
    try {
      const item = await api<Case>(
        orgPath(organizationId, "/cases"),
        json("POST", { finding_id: findingId }),
      );
      navigate(`/organizations/${organizationId}/cases/${item.id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao abrir caso");
    } finally {
      setBusy(false);
    }
  }
  async function review(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      await api(
        orgPath(organizationId, `/findings/${findingId}`),
        json("PATCH", { review_state: state, reason: reason || undefined }),
      );
      setSuccess("Revisão registrada.");
      await detail.refetch();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao revisar");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">DETALHE DO ALERTA</p>
          <h1>{detail.data?.rule_code || "Achado"}</h1>
          <p className="muted">
            {detail.data && (
              <>
                <span className={`severity severity-${detail.data.severity}`}>
                  {detail.data.severity}
                </span>{" "}
                <Status value={detail.data.review_state} /> ·{" "}
                {new Date(detail.data.detected_at).toLocaleString("pt-BR")}
              </>
            )}
          </p>
        </div>
      </div>
      <QueryState loading={detail.isLoading} error={detail.error} />
      {detail.data && (
        <>
          <section className="card">
            <h2>Por que este alerta foi gerado</h2>
            {detail.data.rule_code === "DUPLICATE" ? (
              <DuplicateComparison evidence={detail.data.evidence} />
            ) : null}
            <p>{detail.data.explanation}</p>
          </section>
          <section className="card">
            <h2>Evidências</h2>
            {detail.data.evidence.length ? (
              detail.data.evidence.map((item) => (
                <div className="evidence" id={`evidence-${item.id}`} key={item.id}>
                  <strong>
                    {item.type === "purchase"
                      ? "Compra"
                      : "Linha da importação"}
                  </strong>
                  <pre>{JSON.stringify(item.data, null, 2)}</pre>
                </div>
              ))
            ) : (
              <p className="empty">Nenhuma evidência disponível.</p>
            )}
          </section>
          <AnalysisPanel
            organizationId={organizationId}
            findingId={findingId}
            canRequest={canWrite(role)}
          />
          {canWrite(role) && (
            <CopilotPanel
              key={`finding:${findingId}`}
              organizationId={organizationId}
              findingId={findingId}
            />
          )}
          {canWrite(role) &&
            !["resolved", "dismissed"].includes(detail.data.review_state) && (
              <section className="card">
                <h2>Acompanhar achado</h2>
                <p className="muted">
                  Abra um caso para atribuir responsável, comentar e manter a
                  trilha de decisões.
                </p>
                <button
                  className="button primary"
                  disabled={busy}
                  onClick={() => void openCase()}
                >
                  Abrir caso
                </button>
                <details className="review-details">
                  <summary>Revisar sem abrir caso</summary>
                  <form onSubmit={review}>
                    <label>
                      Decisão
                      <select
                        value={state}
                        onChange={(e) => setState(e.target.value)}
                      >
                        <option value="in_review">Em revisão</option>
                        <option value="resolved">Resolvido</option>
                        <option value="dismissed">Descartado</option>
                      </select>
                    </label>
                    <label>
                      Justificativa
                      <textarea
                        value={reason}
                        required={state !== "in_review"}
                        maxLength={1000}
                        onChange={(e) => setReason(e.target.value)}
                      />
                    </label>
                    <button className="button secondary" disabled={busy}>
                      Registrar revisão
                    </button>
                  </form>
                </details>
                <Feedback error={error} success={success} />
              </section>
            )}
        </>
      )}
    </>
  );
}
