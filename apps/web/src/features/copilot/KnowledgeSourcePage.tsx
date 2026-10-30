import { useOutletContext, useParams } from "react-router";
import { orgPath } from "../../lib/api";
import { QueryState, useResource } from "../../lib/useResource";
import type { ShellContext } from "../shell/Shell";

type Source = {
  id: string; title: string; content: string; enabled: boolean; revision: number;
  type: "managed_knowledge" | "github_public";
  github_owner?: string; github_repo?: string; github_path?: string;
  github_blob_sha?: string; github_checked_at?: string; github_url?: string;
};

// Citation destinations are fetched through the same tenant-scoped API as administration.
export function KnowledgeSourcePage() {
  const { organizationId } = useOutletContext<ShellContext>();
  const { sourceId } = useParams();
  const source = useResource<Source>(
    ["knowledge-source", organizationId, sourceId],
    `${orgPath(organizationId)}/integrations/knowledge/${sourceId}`, Boolean(sourceId),
  );
  return <>
    <div className="page-heading"><div><p className="eyebrow">FONTE DA EMPRESA</p>
      <h1>{source.data?.title || "Documentação"}</h1></div></div>
    <QueryState loading={source.isLoading} error={source.error} />
    {source.data && <section className="card">
      <p className="muted">Revisão {source.data.revision} · {source.data.enabled ? "Fonte ativa" : "Fonte desativada"}</p>
      {source.data.type === "github_public" && <p className="muted">
        Cópia de {source.data.github_owner}/{source.data.github_repo}/{source.data.github_path}
        {" · "}SHA {source.data.github_blob_sha}
        {" · "}verificada em {new Date(source.data.github_checked_at!).toLocaleString("pt-BR")}
        {" · "}<a href={source.data.github_url} target="_blank" rel="noopener noreferrer">Ver versão atual no GitHub</a>
      </p>}
      <div className="knowledge-content">{source.data.content}</div>
    </section>}
  </>;
}
