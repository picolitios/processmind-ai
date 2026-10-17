import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, json, orgPath, query } from "../../lib/api";
import type { Page } from "../../lib/api";
import { Feedback, QueryState, useResource } from "../../lib/useResource";
import type {
  CopilotConversation,
  CopilotDetail,
  CopilotMode,
  CopilotPolicy,
  CopilotTurn,
} from "./types";

type Props = {
  organizationId: string;
  findingId?: string;
  auditId?: string;
};

function citationUrl(organizationId: string, findingId: string, evidenceId: string) {
  return `/organizations/${organizationId}/findings/${findingId}#evidence-${evidenceId}`;
}

// Keep the temporary chat in page state; only normal chats are loaded from the saved list.
export function CopilotPanel({ organizationId, findingId, auditId }: Props) {
  const client = useQueryClient();
  const base = orgPath(organizationId, "/ai/copilot");
  const [mode, setMode] = useState<CopilotMode>("normal");
  const [modeTouched, setModeTouched] = useState(false);
  const [selectedId, setSelectedId] = useState("");
  const [cursors, setCursors] = useState<string[]>([""]);
  const [olderTurns, setOlderTurns] = useState<CopilotTurn[]>([]);
  const [olderCursor, setOlderCursor] = useState<string | null | undefined>(undefined);
  const [question, setQuestion] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const cursor = cursors.at(-1) || "";
  const target = findingId ? { finding_id: findingId } : { audit_id: auditId };
  const targetKey = findingId || auditId || "";
  const policy = useResource<CopilotPolicy>(
    ["copilot-policy", organizationId], `${base}/policy`, Boolean(targetKey),
  );
  const conversations = useResource<Page<CopilotConversation>>(
    ["copilot-list", organizationId, targetKey, cursor],
    `${base}/conversations${query({ finding_id: findingId, audit_id: auditId, cursor })}`,
    Boolean(targetKey),
  );
  const detail = useResource<CopilotDetail>(
    ["copilot-detail", organizationId, selectedId],
    `${base}/conversations/${selectedId}`,
    Boolean(selectedId), selectedId ? 3000 : undefined,
  );
  useEffect(() => {
    if (!modeTouched && policy.data) {
      setMode(policy.data.temporary_default ? "temporary" : "normal");
    }
  }, [modeTouched, policy.data]);

  // Reset messages and pagination whenever the user changes chats.
  function selectConversation(id: string) {
    setSelectedId(id);
    setOlderTurns([]);
    setOlderCursor(undefined);
    setError("");
    setSuccess("");
    setQuestion("");
  }

  // Start a chat for the current finding or audit and refresh the saved list if needed.
  async function createConversation() {
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      const created = await api<CopilotConversation>(
        `${base}/conversations`, json("POST", { ...target, mode }),
      );
      selectConversation(created.id);
      if (created.mode === "normal") {
        setCursors([""]);
        await client.invalidateQueries({ queryKey: ["copilot-list", organizationId, targetKey] });
      }
      if (created.status === "pending") {
        setSuccess("Chat criado. Aguarde a aprovação de um administrador.");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível criar o chat.");
    } finally {
      setBusy(false);
    }
  }

  // Submit one idempotent question; the detail query polls its worker result.
  async function sendQuestion(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedId || !question.trim()) return;
    setError("");
    setSuccess("");
    setBusy(true);
    try {
      await api(
        `${base}/conversations/${selectedId}/questions`,
        json("POST", { question: question.trim() }, { "Idempotency-Key": crypto.randomUUID() }),
      );
      setQuestion("");
      await detail.refetch();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível enviar a pergunta.");
    } finally {
      setBusy(false);
    }
  }

  // Remove the author's chat after an explicit UI confirmation.
  async function removeConversation() {
    if (!selectedId || !window.confirm("Excluir este chat e suas perguntas?")) return;
    setError("");
    setBusy(true);
    try {
      await api<void>(`${base}/conversations/${selectedId}`, { method: "DELETE" });
      selectConversation("");
      await client.invalidateQueries({ queryKey: ["copilot-list", organizationId, targetKey] });
      setSuccess("Chat excluído.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível excluir o chat.");
    } finally {
      setBusy(false);
    }
  }

  // Page backward without replacing newer turns received during polling.
  async function loadEarlier() {
    const nextCursor = olderCursor === undefined ? detail.data?.next_cursor : olderCursor;
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const page = await api<CopilotDetail>(
        `${base}/conversations/${selectedId}${query({ cursor: nextCursor })}`,
      );
      setOlderTurns((current) => [
        ...page.turns.filter((turn) => !current.some((saved) => saved.id === turn.id)),
        ...current,
      ]);
      setOlderCursor(page.next_cursor);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível carregar mensagens.");
    } finally {
      setLoadingMore(false);
    }
  }

  const latestTurns = detail.data?.turns || [];
  const turns = [
    ...olderTurns.filter((turn) => !latestTurns.some((latest) => latest.id === turn.id)),
    ...latestTurns,
  ];
  const waiting = turns.some((turn) => turn.status === "queued" || turn.status === "running");

  return (
    <section className="card copilot-panel" aria-label="Copiloto conversacional">
      <p className="eyebrow">APOIO OPCIONAL</p>
      <h2>Copiloto conversacional</h2>
      <p className="muted">
        Respostas auxiliares baseadas em evidências. Confira as citações antes de decidir;
        a auditoria e os casos não são alterados pelo chat.
      </p>
      <QueryState loading={policy.isLoading} error={policy.error} />
      <Feedback error={error} success={success} />
      {policy.data && (
        <div className="copilot-create">
          <label>
            Tipo de chat
            <select value={mode} onChange={(event) => {
              setMode(event.target.value as CopilotMode);
              setModeTouched(true);
            }}>
              <option value="normal">Normal, salvo no histórico da empresa</option>
              <option value="temporary">Temporário, somente este chat</option>
            </select>
          </label>
          <button className="button secondary" disabled={busy} onClick={() => void createConversation()}>
            Novo chat
          </button>
          {policy.data.temporary_default && mode === "normal" && (
            <small>Analistas precisam de aprovação para salvar este chat.</small>
          )}
        </div>
      )}
      <h3>Meus chats salvos</h3>
      <QueryState loading={conversations.isLoading} error={conversations.error} />
      {conversations.data?.items.length ? (
        <div className="copilot-chat-list">
          {conversations.data.items.map((item) => (
            <button
              className="button secondary"
              key={item.id}
              aria-current={item.id === selectedId ? "true" : undefined}
              onClick={() => selectConversation(item.id)}
            >
              {new Date(item.created_at).toLocaleString("pt-BR")} · {item.status === "pending" ? "Pendente" : "Ativo"}
            </button>
          ))}
        </div>
      ) : conversations.data && <p className="empty">Nenhum chat salvo para este alvo.</p>}
      {conversations.data && (cursors.length > 1 || conversations.data.next_cursor) && (
        <div className="copilot-pagination">
          <button className="button secondary" disabled={cursors.length === 1}
            onClick={() => setCursors((current) => current.slice(0, -1))}>Anterior</button>
          <button className="button secondary" disabled={!conversations.data.next_cursor}
            onClick={() => setCursors((current) => [...current, conversations.data!.next_cursor!])}>Próximo</button>
        </div>
      )}
      {selectedId && (
        <div className="copilot-conversation">
          <QueryState loading={detail.isLoading} error={detail.error} />
          {detail.data && (
            <>
              <div className="copilot-conversation-heading">
                <h3>{detail.data.conversation.mode === "temporary" ? "Chat temporário" : "Chat salvo"}</h3>
                <button className="button secondary" disabled={busy || waiting}
                  onClick={() => void removeConversation()}>Excluir chat</button>
              </div>
              {detail.data.conversation.mode === "temporary" && (
                <p className="notice">Este chat não reaparece após recarregar a página e expira após uma hora sem atividade.</p>
              )}
              {detail.data.conversation.status === "pending" && (
                <p role="status" className="notice">Aguardando aprovação para salvar este chat.</p>
              )}
              {detail.data.conversation.status === "rejected" && (
                <p role="status" className="notice">O pedido de chat salvo foi rejeitado.</p>
              )}
              {(olderCursor === undefined ? detail.data.next_cursor : olderCursor) && (
                <button className="button secondary" disabled={loadingMore}
                  onClick={() => void loadEarlier()}>Carregar mensagens anteriores</button>
              )}
              {turns.length ? (
                <ol className="copilot-turns">
                  {turns.map((turn) => <CopilotTurnView key={turn.id} turn={turn} organizationId={organizationId} />)}
                </ol>
              ) : <p className="empty">Faça a primeira pergunta sobre as evidências deste alvo.</p>}
              {detail.data.conversation.status === "active" && (
                <form onSubmit={sendQuestion}>
                  <label>
                    Sua pergunta
                    <textarea value={question} maxLength={1000} required
                      onChange={(event) => setQuestion(event.target.value)} />
                  </label>
                  <button className="button primary" disabled={busy || waiting || !question.trim()}>
                    {waiting ? "Aguardando resposta…" : "Enviar pergunta"}
                  </button>
                </form>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}

// Render only server-provided citation links; model text remains plain text.
function CopilotTurnView({ turn, organizationId }: { turn: CopilotTurn; organizationId: string }) {
  return (
    <li className="copilot-turn">
      <p><strong>Pergunta:</strong> {turn.question}</p>
      {(turn.status === "queued" || turn.status === "running") && (
        <p role="status" className="muted">Resposta em processamento…</p>
      )}
      {turn.answer && <p><strong>Copiloto:</strong> {turn.answer}</p>}
      {turn.limitation && <p className="notice">{turn.limitation}</p>}
      {turn.citations.length > 0 && (
        <ul aria-label="Citações de evidências">
          {turn.citations.map((item) => (
            <li key={item.evidence_id}>
              <Link to={citationUrl(organizationId, item.finding_id, item.evidence_id)}>
                Evidência {item.evidence_id.slice(0, 8)} · achado {item.finding_id.slice(0, 8)}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
