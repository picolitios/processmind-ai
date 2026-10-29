import { useEffect, useRef, useState } from "react";
import { orgPath } from "../../lib/api";
import { useResource } from "../../lib/useResource";
import { CopilotPanel } from "./CopilotPanel";

type Capabilities = { can_chat: boolean; agent_enabled: boolean };

// Mounted while closed so temporary chats survive closing and reopening during this page session.
export function FloatingAgent({ organizationId }: { organizationId: string }) {
  const [open, setOpen] = useState(false);
  const launcher = useRef<HTMLButtonElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const capabilities = useResource<Capabilities>(
    ["agent-capabilities", organizationId],
    `${orgPath(organizationId)}/agent/capabilities`, Boolean(organizationId), 15000,
  );
  useEffect(() => { setOpen(false); }, [organizationId]);
  useEffect(() => {
    if (open) closeButton.current?.focus();
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        launcher.current?.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);
  if (!capabilities.data?.can_chat) return null;
  return <div className="floating-agent">
    <button ref={launcher} className="floating-agent-launcher" type="button"
      aria-expanded={open} aria-controls="floating-agent-panel"
      onClick={() => setOpen((current) => !current)}>
      ✦ {open ? "Fechar agente" : "Abrir agente"}
    </button>
    <aside id="floating-agent-panel" className="floating-agent-panel"
      role="dialog" aria-label="Agente da empresa" aria-modal="false" hidden={!open}>
      <div className="floating-agent-heading">
        <strong>Agente da empresa</strong>
        <button ref={closeButton} className="icon-button" type="button" aria-label="Fechar agente"
          onClick={() => { setOpen(false); launcher.current?.focus(); }}>×</button>
      </div>
      <CopilotPanel organizationId={organizationId} scope="organization" />
    </aside>
  </div>;
}
