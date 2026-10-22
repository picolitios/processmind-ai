import { useOutletContext } from "react-router";
import type { ShellContext } from "../shell/Shell";
import { canWrite } from "../shell/Shell";
import { CopilotPanel } from "./CopilotPanel";

// The organization route reuses the same chat policy and isolated worker flow.
export function OrganizationAgentPage() {
  const { organizationId, role } = useOutletContext<ShellContext>();
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">ANÁLISE ASSISTIDA</p>
          <h1>Agente da empresa</h1>
          <p className="muted">Converse sobre auditorias, achados e evidências desta organização.</p>
        </div>
      </div>
      {canWrite(role) ? <CopilotPanel organizationId={organizationId} scope="organization" /> :
        <p className="notice">Seu papel permite consultar os dados, mas não iniciar chats.</p>}
    </>
  );
}
