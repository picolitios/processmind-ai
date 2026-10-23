import { useState } from "react";
import { Link } from "react-router";
import { orgPath, query } from "../../lib/api";
import type { Comment, Page } from "../../lib/api";
import { QueryState, useResource } from "../../lib/useResource";

type Activity = {
  id: string;
  action: string;
  actor_name: string | null;
  occurred_at: string;
  metadata: { from?: string; to?: string; reason?: string | null };
};
type ActivityPage = {
  case_id: string | null;
  items: Activity[];
  next_cursor: string | null;
};

const actionLabels: Record<string, string> = {
  "finding.reviewed": "Revisão do alerta",
  "case.opened": "Caso aberto",
  "case.status_changed": "Decisão do caso",
  "case.assigned": "Responsável alterado",
  "case.commented": "Comentário adicionado ao caso",
};
const stateLabels: Record<string, string> = {
  unreviewed: "Não revisado", in_review: "Em revisão", open: "Aberto",
  resolved: "Resolvido", dismissed: "Descartado",
};

// The activity tab renders existing append-only events, including direct review reasons.
export function FindingActivity({
  organizationId,
  findingId,
}: {
  organizationId: string;
  findingId: string;
}) {
  const [cursor, setCursor] = useState("");
  const [commentCursor, setCommentCursor] = useState("");
  const activity = useResource<ActivityPage>(
    ["finding-activity", organizationId, findingId, cursor],
    orgPath(organizationId, `/findings/${findingId}/activity${query({ cursor })}`),
  );
  const caseId = activity.data?.case_id;
  const comments = useResource<Page<Comment>>(
    ["finding-comments", organizationId, caseId, commentCursor],
    orgPath(organizationId, `/cases/${caseId}/comments${query({ cursor: commentCursor })}`),
    Boolean(caseId),
  );
  return (
    <section className="card" role="tabpanel">
      <h2>Justificativas e atividade</h2>
      <QueryState loading={activity.isLoading} error={activity.error} />
      {activity.data?.items.length ? (
        activity.data.items.map((item) => (
          <article className="history-event activity-entry" key={item.id}>
            <strong>{actionLabels[item.action] || item.action}</strong>
            {item.metadata.from && item.metadata.to && (
              <p>{stateLabels[item.metadata.from] || item.metadata.from} → {stateLabels[item.metadata.to] || item.metadata.to}</p>
            )}
            {item.metadata.reason && <p>Justificativa: {item.metadata.reason}</p>}
            <small>
              {item.actor_name || "Autor não identificado"} ·{" "}
              {new Date(item.occurred_at).toLocaleString("pt-BR")}
            </small>
          </article>
        ))
      ) : (
        activity.data && <p className="empty">Nenhuma revisão ou comentário registrado.</p>
      )}
      {activity.data?.case_id && (
        <>
          <h3>Comentários do caso</h3>
          <QueryState loading={comments.isLoading} error={comments.error} />
          {comments.data?.items.map((comment) => <article className="history-event activity-entry" key={comment.id}>
            <p>{comment.body}</p>
            <small>{comment.author_name || "Autor não identificado"} · {new Date(comment.created_at).toLocaleString("pt-BR")}</small>
          </article>)}
          {comments.data && !comments.data.items.length && <p className="empty">Nenhum comentário no caso.</p>}
          {comments.data?.next_cursor && <button className="button secondary" onClick={() => setCommentCursor(comments.data!.next_cursor!)}>Comentários anteriores</button>}
          <Link to={`/organizations/${organizationId}/cases/${activity.data.case_id}`}>Ver caso completo →</Link>
        </>
      )}
      {activity.data?.next_cursor && (
        <button className="button secondary" onClick={() => setCursor(activity.data!.next_cursor!)}>
          Atividade anterior
        </button>
      )}
    </section>
  );
}
