import { useState } from "react";
import { api, json, orgPath } from "../../lib/api";
import { Feedback, QueryState, useResource } from "../../lib/useResource";

type Analysis = {
  id: string;
  status: string;
  summary: string | null;
  possible_causes: string[];
  suggested_checks: string[];
  corrective_actions: string[];
  evidence_ids: string[];
  limitation: string | null;
};
export function AnalysisPanel({
  organizationId,
  findingId,
  canRequest,
}: {
  organizationId: string;
  findingId: string;
  canRequest: boolean;
}) {
  const [analysisId, setAnalysisId] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const analysis = useResource<Analysis>(
    ["analysis", analysisId],
    orgPath(organizationId, `/ai/analyses/${analysisId}`),
    Boolean(analysisId),
    analysisId ? 3000 : undefined,
  );
  async function request() {
    setError("");
    setBusy(true);
    try {
      const result = await api<{ analysis_id: string }>(
        orgPath(organizationId, "/ai/analyses"),
        json(
          "POST",
          { finding_id: findingId },
          { "Idempotency-Key": crypto.randomUUID() },
        ),
      );
      setAnalysisId(result.analysis_id);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Não foi possível solicitar a análise",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card">
      <p className="eyebrow">APOIO OPCIONAL</p>
      <h2>Explicação com IA local</h2>
      <p className="muted">
        A IA sugere verificações. A decisão continua com a equipe e a auditoria
        funciona sem ela.
      </p>
      {canRequest && !analysisId && (
        <button
          className="button secondary"
          disabled={busy}
          onClick={() => void request()}
        >
          {busy ? "Solicitando…" : "Gerar explicação"}
        </button>
      )}
      <Feedback error={error} />
      {analysisId && (
        <>
          <QueryState loading={analysis.isLoading} error={analysis.error} />
          {analysis.data &&
            (analysis.data.status === "queued" ||
            analysis.data.status === "running" ? (
              <p role="status" className="muted">
                Análise em processamento…
              </p>
            ) : (
              <>
                <p className="notice">
                  {analysis.data.limitation ||
                    "Análise auxiliar; confira as evidências antes de decidir."}
                </p>
                {analysis.data.summary && <p>{analysis.data.summary}</p>}
                <AnalysisList
                  title="Possíveis causas"
                  items={analysis.data.possible_causes}
                />
                <AnalysisList
                  title="Verificações sugeridas"
                  items={analysis.data.suggested_checks}
                />
                <AnalysisList
                  title="Ações corretivas"
                  items={analysis.data.corrective_actions}
                />
              </>
            ))}
        </>
      )}
    </section>
  );
}
function AnalysisList({ title, items }: { title: string; items: string[] }) {
  return items.length ? (
    <div>
      <h3>{title}</h3>
      <ul>
        {items.map((item, index) => (
          <li key={index}>{item}</li>
        ))}
      </ul>
    </div>
  ) : null;
}
