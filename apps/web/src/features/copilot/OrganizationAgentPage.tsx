import { useOutletContext } from "react-router";
import type { ShellContext } from "../shell/Shell";
import { canWrite } from "../shell/Shell";
import { CopilotPanel } from "./CopilotPanel";
import { orgPath } from "../../lib/api";
import { QueryState, useResource } from "../../lib/useResource";

// The organization route reuses the same chat policy and isolated worker flow.
export function OrganizationAgentPage() {
  const { organizationId, role } = useOutletContext<ShellContext>();
  const capabilities = useResource<{ can_chat: boolean; agent_enabled: boolean }>(
    ["agent-capabilities", organizationId], `${orgPath(organizationId)}/agent/capabilities`,
  );
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ANÁLISE ASSISTIDA</p>
          <h1>Agente da empresa</h1>
          <p className="muted">Converse sobre processos documentados e análises de compras habilitadas nesta organização.</p>
        </div>
      </div>
      <QueryState loading={capabilities.isLoading} error={capabilities.error} />
      {capabilities.data?.can_chat && canWrite(role) ?
        <CopilotPanel organizationId={organizationId} scope="organization" /> :
        capabilities.data && <p className="notice">O agente não está habilitado para este acesso. Peça a um administrador para verificar as capacidades da empresa.</p>}
    </>
  );
}
