import { useEffect, useState } from "react";
import { Link, useOutletContext, useParams } from "react-router";
import { api, json, orgPath, query } from "../../lib/api";
import type { Case, Comment, Page } from "../../lib/api";
import { Feedback, QueryState, useResource } from "../../lib/useResource";
import type { ShellContext } from "../shell/Shell";
import { canAdmin, canWrite } from "../shell/Shell";
import { Status } from "../imports/ImportsPage";
import { useAuth } from "../auth/AuthProvider";

type Member = { user_id: string; status: string };

export function CaseDetailPage() {
  const { organizationId, role } = useOutletContext<ShellContext>();
  const { session } = useAuth();
  const { caseId = "" } = useParams();
  const base = orgPath(organizationId, `/cases/${caseId}`);
  const [commentCursor, setCommentCursor] = useState("");
  const detail = useResource<Case>(["case", caseId], base, Boolean(caseId));
  const comments = useResource<Page<Comment>>(
    ["case-comments", caseId, commentCursor],
    `${base}/comments${query({ cursor: commentCursor })}`,
    Boolean(caseId),
  );
  const members = useResource<Page<Member>>(
    ["case-members", organizationId],
    orgPath(organizationId, "/users?limit=100"),
    canAdmin(role),
  );
  const [status, setStatus] = useState("in_review");
  const [assignee, setAssignee] = useState("");
  const [reason, setReason] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (detail.data?.status === "in_review") setStatus("resolved");
  }, [detail.data?.status]);
  async function assign(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      await api(base, json("PATCH", { assignee_user_id: assignee }));
      await detail.refetch();
      setSuccess("Responsável atualizado.");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Falha ao atribuir caso",
      );
    } finally {
      setBusy(false);
    }
  }
  async function update(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      await api(
        base,
        json("PATCH", { status, closure_reason: reason || undefined }),
      );
      await detail.refetch();
      setSuccess("Caso atualizado.");
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "Falha ao atualizar caso",
      );
    } finally {
      setBusy(false);
    }
  }
  async function addComment(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      await api(`${base}/comments`, json("POST", { body: comment }));
      setComment("");
      setCommentCursor("");
      await comments.refetch();
      setSuccess("Comentário registrado.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao comentar");
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <Link className="back-link" to={`/organizations/${organizationId}/cases`}>
        ← Casos
      </Link>
      <div className="page-heading">
        <div>
          <p className="eyebrow">DETALHE DO CASO</p>
          <h1>Caso {caseId.slice(0, 8)}</h1>
          <p className="muted">
            {detail.data && (
              <>
                <Status value={detail.data.status} /> · Aberto em{" "}
                {new Date(detail.data.opened_at).toLocaleString("pt-BR")}
              </>
            )}
          </p>
        </div>
        {detail.data && (
          <Link
            className="button secondary"
            to={`/organizations/${organizationId}/findings/${detail.data.finding_id}`}
          >
            Ver achado →
          </Link>
        )}
      </div>
      <QueryState loading={detail.isLoading} error={detail.error} />
      {detail.data && (
        <>
          <div className="two-columns">
            <section className="card">
              <h2>Decisão</h2>
              <p>
                <strong>Responsável:</strong>{" "}
                {detail.data.assignee_user_id || "Não atribuído"}
              </p>
              {canWrite(role) &&
                !["resolved", "dismissed"].includes(detail.data.status) && (
                  <form onSubmit={assign}>
                    <label>
                      Atribuir responsável
                      <select
                        required
                        value={assignee}
                        onChange={(e) => setAssignee(e.target.value)}
                      >
                        <option value="">Selecione um membro</option>
                        {session && (
                          <option value={session.user.id}>
                            Eu ({session.user.email})
                          </option>
                        )}
                        {members.data?.items
                          .filter(
                            (member) =>
                              member.status === "active" &&
                              member.user_id !== session?.user.id,
                          )
                          .map((member) => (
                            <option key={member.user_id} value={member.user_id}>
                              Membro {member.user_id.slice(0, 8)}
                            </option>
                          ))}
                      </select>
                    </label>
                    <button
                      className="button secondary"
                      disabled={busy || !assignee}
                    >
                      Atribuir
                    </button>
                  </form>
                )}
              {detail.data.closure_reason && (
                <p>
                  <strong>Justificativa:</strong> {detail.data.closure_reason}
                </p>
              )}
              {canWrite(role) &&
                !["resolved", "dismissed"].includes(detail.data.status) && (
                  <form onSubmit={update}>
                    <label>
                      Novo status
                      <select
                        value={status}
                        onChange={(e) => setStatus(e.target.value)}
                      >
                        {detail.data.status === "open" && (
                          <option value="in_review">Em revisão</option>
                        )}
                        <option value="resolved">Resolvido</option>
                        <option value="dismissed">Descartado</option>
                      </select>
                    </label>
                    <label>
                      Justificativa
                      <textarea
                        value={reason}
                        required={["resolved", "dismissed"].includes(status)}
                        maxLength={1000}
                        onChange={(e) => setReason(e.target.value)}
                      />
                    </label>
                    <button className="button primary" disabled={busy}>
                      Salvar decisão
                    </button>
                  </form>
                )}
            </section>
            <section className="card">
              <h2>Trilha do caso</h2>
              {detail.data.history?.length ? (
                detail.data.history.map((event, index) => (
                  <div className="history-event" key={index}>
                    <code>{String(event.action || "Alteração")}</code>
                    <small>
                      {new Date(String(event.occurred_at)).toLocaleString(
                        "pt-BR",
                      )}
                    </small>
                  </div>
                ))
              ) : (
                <p className="empty">Nenhuma alteração registrada.</p>
              )}
            </section>
          </div>
          <section className="card">
            <h2>Comentários</h2>
            <QueryState loading={comments.isLoading} error={comments.error} />
            {comments.data?.items.length
              ? comments.data.items.map((item) => (
                  <article className="comment" key={item.id}>
                    <p>{item.body}</p>
                    <small>
                      {item.author_user_id.slice(0, 8)} ·{" "}
                      {new Date(item.created_at).toLocaleString("pt-BR")}
                    </small>
                  </article>
                ))
              : comments.data && (
                  <p className="empty">Nenhum comentário ainda.</p>
                )}
            {canWrite(role) && (
              <form onSubmit={addComment}>
                <label>
                  Novo comentário
                  <textarea
                    required
                    maxLength={5000}
                    value={comment}
                    onChange={(e) => setComment(e.target.value)}
                  />
                </label>
                <button
                  className="button secondary"
                  disabled={busy || !comment.trim()}
                >
                  Adicionar comentário
                </button>
              </form>
            )}
            {comments.data?.next_cursor && (
              <button
                className="button secondary"
                onClick={() => setCommentCursor(comments.data!.next_cursor!)}
              >
                Comentários anteriores
              </button>
            )}
          </section>
          <Feedback error={error} success={success} />
        </>
      )}
    </>
  );
}
