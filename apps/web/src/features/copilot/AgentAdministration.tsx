import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, json, orgPath, query } from "../../lib/api";
import type { Page } from "../../lib/api";
import { Feedback, QueryState, useResource } from "../../lib/useResource";
import { GithubPublicForm } from "./GithubPublicForm";
import type { GithubSource } from "./GithubPublicForm";

type Configuration = { agent_enabled: boolean; purchasing_enabled: boolean };
type KnowledgeSource = {
  id: string;
  title: string;
  content?: string;
  type: "managed_knowledge" | "github_public";
  enabled: boolean;
  revision: number;
  updated_at?: string;
  github_owner?: string;
  github_repo?: string;
  github_path?: string;
  github_blob_sha?: string;
  github_checked_at?: string;
  github_url?: string;
};

// Managers control the new agent and each authorized source without exposing document text in lists.
export function AgentAdministration({ organizationId }: { organizationId: string }) {
  const client = useQueryClient();
  const base = orgPath(organizationId);
  const configuration = useResource<Configuration>(
    ["agent-configuration", organizationId], `${base}/agent/configuration`,
  );
  const [cursor, setCursor] = useState("");
  const sources = useResource<Page<KnowledgeSource>>(
    ["knowledge-sources", organizationId, cursor],
    `${base}/integrations/knowledge${query({ cursor })}`,
  );
  const [agentEnabled, setAgentEnabled] = useState(false);
  const [purchasingEnabled, setPurchasingEnabled] = useState(true);
  const [selectedId, setSelectedId] = useState("");
  const [selectedType, setSelectedType] = useState<KnowledgeSource["type"]>("managed_knowledge");
  const [githubOrigin, setGithubOrigin] = useState<KnowledgeSource | null>(null);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [sourceEnabled, setSourceEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  useEffect(() => {
    if (configuration.data) {
      setAgentEnabled(configuration.data.agent_enabled);
      setPurchasingEnabled(configuration.data.purchasing_enabled);
    }
  }, [configuration.data]);

  async function saveConfiguration(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api(`${base}/agent/configuration`, {
        method: "PUT", body: JSON.stringify({
          agent_enabled: agentEnabled, purchasing_enabled: purchasingEnabled,
        }),
      });
      await Promise.all([
        client.invalidateQueries({ queryKey: ["agent-configuration", organizationId] }),
        client.invalidateQueries({ queryKey: ["agent-capabilities", organizationId] }),
      ]);
      setSuccess("Configuração do agente salva.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao salvar configuração.");
    } finally {
      setBusy(false);
    }
  }

  async function selectSource(id: string) {
    setBusy(true);
    setError("");
    try {
      const source = await api<KnowledgeSource>(`${base}/integrations/knowledge/${id}`);
      setSelectedId(source.id);
      setSelectedType(source.type);
      setGithubOrigin(source.type === "github_public" ? source : null);
      setTitle(source.title);
      setContent(source.content || "");
      setSourceEnabled(source.enabled);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Não foi possível abrir a fonte.");
    } finally {
      setBusy(false);
    }
  }

  function clearSource() {
    setSelectedId("");
    setSelectedType("managed_knowledge");
    setGithubOrigin(null);
    setTitle("");
    setContent("");
    setSourceEnabled(false);
  }

  async function saveSource(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setSuccess("");
    try {
      const source = await api<KnowledgeSource>(
        selectedId ? `${base}/integrations/knowledge/${selectedId}` : `${base}/integrations/knowledge`,
        json(selectedId ? "PATCH" : "POST", selectedType === "github_public"
          ? { title, enabled: sourceEnabled }
          : { title, content, enabled: sourceEnabled }),
      );
      setSelectedId(source.id);
      if (source.type === "github_public") setGithubOrigin(source);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["knowledge-sources", organizationId] }),
        client.invalidateQueries({ queryKey: ["agent-capabilities", organizationId] }),
      ]);
      setSuccess(`Fonte ${selectedId ? "atualizada" : "criada"}.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao salvar fonte.");
    } finally {
      setBusy(false);
    }
  }

  async function refreshGithub() {
    if (!selectedId || selectedType !== "github_public") return;
    setBusy(true);
    setError("");
    try {
      const source = await api<KnowledgeSource>(
        `${base}/integrations/github-public/documents/${selectedId}/refresh`,
        { method: "POST" },
      );
      setGithubOrigin(source);
      setContent(source.content || "");
      await client.invalidateQueries({ queryKey: ["knowledge-sources", organizationId] });
      setSuccess("Cópia do GitHub verificada.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao atualizar do GitHub.");
    } finally {
      setBusy(false);
    }
  }

  function importedGithub(source: GithubSource) {
    void client.invalidateQueries({ queryKey: ["knowledge-sources", organizationId] });
    void client.invalidateQueries({ queryKey: ["agent-capabilities", organizationId] });
    setSelectedId(source.id);
    setSelectedType("github_public");
    setGithubOrigin(source);
    setTitle(source.title);
    setContent(source.content);
    setSourceEnabled(source.enabled);
    setSuccess("Documento público verificado e importado.");
  }

  return <div className="agent-administration">
    <section className="card">
      <h2>Agente da empresa</h2>
      <p className="muted">Habilite o agente e a análise de compras separadamente para esta empresa.</p>
      <QueryState loading={configuration.isLoading} error={configuration.error} />
      {configuration.data && <form onSubmit={saveConfiguration}>
        <label className="copilot-checkbox"><input type="checkbox" checked={agentEnabled}
          onChange={(event) => setAgentEnabled(event.target.checked)} /> Agente flutuante ativo</label>
        <label className="copilot-checkbox"><input type="checkbox" checked={purchasingEnabled}
          onChange={(event) => setPurchasingEnabled(event.target.checked)} /> Ferramenta de análise de compras</label>
        <button className="button primary" disabled={busy}>Salvar capacidades</button>
      </form>}
    </section>
    <section className="card">
      <h2>Documentação autorizada</h2>
      <p className="muted">Adicione texto de procedimentos da empresa. O agente consulta somente fontes habilitadas e cita cada documento usado.</p>
      <QueryState loading={sources.isLoading} error={sources.error} />
      {sources.data?.items.length ? <ul className="knowledge-list">{sources.data.items.map((source) =>
        <li key={source.id}><button className="button secondary" type="button" disabled={busy}
          onClick={() => void selectSource(source.id)}>{source.title} · {source.type === "github_public" ? "GitHub" : "Gerenciada"} · v{source.revision} · {source.enabled ? "Ativa" : "Desativada"}</button></li>
      )}</ul> : sources.data && <p className="empty">Nenhuma fonte configurada.</p>}
      {sources.data?.next_cursor && <button className="button secondary" type="button"
        onClick={() => setCursor(sources.data!.next_cursor!)}>Próxima página</button>}
      {cursor && <button className="button secondary" type="button"
        onClick={() => setCursor("")}>Voltar ao início</button>}
      <hr />
      <h3>{selectedId ? "Editar fonte" : "Nova fonte gerenciada"}</h3>
      {selectedId && <button className="button secondary" type="button" onClick={clearSource}>Nova fonte</button>}
      {githubOrigin && <div className="notice">
        <p>Origem: {githubOrigin.github_owner}/{githubOrigin.github_repo}/{githubOrigin.github_path}</p>
        <p>SHA: {githubOrigin.github_blob_sha} · verificado em {new Date(githubOrigin.github_checked_at!).toLocaleString("pt-BR")}</p>
        <button className="button secondary" type="button" disabled={busy} onClick={() => void refreshGithub()}>Atualizar do GitHub</button>
      </div>}
      <form onSubmit={saveSource}>
        <label>Título<input value={title} required maxLength={160}
          onChange={(event) => setTitle(event.target.value)} /></label>
        <label>Procedimento ou documentação<textarea value={content} required maxLength={20000} rows={8}
          readOnly={selectedType === "github_public"}
          onChange={(event) => setContent(event.target.value)} /></label>
        <label className="copilot-checkbox"><input type="checkbox" checked={sourceEnabled}
          onChange={(event) => setSourceEnabled(event.target.checked)} /> Fonte habilitada</label>
        <button className="button primary" disabled={busy || !title.trim() || !content.trim()}>Salvar fonte</button>
      </form>
      <Feedback error={error} success={success} />
    </section>
    <GithubPublicForm organizationId={organizationId} onImported={importedGithub} />
  </div>;
}
