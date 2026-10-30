import { useState } from "react";
import { api, json, orgPath } from "../../lib/api";
import { Feedback } from "../../lib/useResource";

export type GithubSource = {
  id: string;
  title: string;
  content: string;
  type: "github_public";
  enabled: boolean;
  revision: number;
  github_owner: string;
  github_repo: string;
  github_path: string;
  github_blob_sha: string;
  github_checked_at: string;
  github_url: string;
};

// Import a checked public snapshot; no token or arbitrary URL reaches the API.
export function GithubPublicForm({ organizationId, onImported }: {
  organizationId: string;
  onImported: (source: GithubSource) => void;
}) {
  const [owner, setOwner] = useState("");
  const [repo, setRepo] = useState("");
  const [path, setPath] = useState("");
  const [title, setTitle] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function importDocument(event: React.FormEvent) {
    event.preventDefault();
    setError("");
    setBusy(true);
    try {
      const source = await api<GithubSource>(
        `${orgPath(organizationId)}/integrations/github-public/documents`,
        json("POST", { owner, repo, path, title, enabled }),
      );
      onImported(source);
      setPath("");
      setTitle("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Falha ao consultar o GitHub.");
    } finally {
      setBusy(false);
    }
  }

  return <section className="card">
    <h2>GitHub público</h2>
    <p className="muted">Autorize um arquivo Markdown ou TXT de um repositório público. A cópia verificada mostra a revisão consultada; atualizações são manuais.</p>
    <form onSubmit={importDocument}>
      <label>Proprietário do repositório<input value={owner} required maxLength={39}
        placeholder="picolitios" onChange={(event) => setOwner(event.target.value)} /></label>
      <label>Repositório<input value={repo} required maxLength={100}
        placeholder="processmind-ai" onChange={(event) => setRepo(event.target.value)} /></label>
      <label>Caminho do arquivo<input value={path} required maxLength={240}
        placeholder="README.md" onChange={(event) => setPath(event.target.value)} /></label>
      <label>Título para o agente<input value={title} required maxLength={160}
        placeholder="Manual do ProcessMind" onChange={(event) => setTitle(event.target.value)} /></label>
      <label className="copilot-checkbox"><input type="checkbox" checked={enabled}
        onChange={(event) => setEnabled(event.target.checked)} /> Habilitar para o agente</label>
      <button className="button primary" disabled={busy || !owner || !repo || !path || !title}>
        {busy ? "Verificando…" : "Verificar e importar"}
      </button>
    </form>
    <Feedback error={error} />
  </section>;
}
