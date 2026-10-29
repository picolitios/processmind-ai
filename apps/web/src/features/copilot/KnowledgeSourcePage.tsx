import { useOutletContext, useParams } from "react-router";
import { orgPath } from "../../lib/api";
import { QueryState, useResource } from "../../lib/useResource";
import type { ShellContext } from "../shell/Shell";

type Source = { id: string; title: string; content: string; enabled: boolean; revision: number };

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
      <div className="knowledge-content">{source.data.content}</div>
    </section>}
  </>;
}
