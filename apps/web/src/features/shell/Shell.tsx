// Layout comum: seleciona a empresa e oferece navegação conforme o acesso do membro.
import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { useResource } from "../../lib/useResource";
import type { Organization, Role } from "../../lib/api";
import { ThemeToggle } from "../theme/ThemeProvider";

const nav = [
  ["dashboard", "Visão geral", "◫"],
  ["imports", "Importações", "⇧"],
  ["audits", "Auditorias", "◎"],
  ["findings", "Alertas", "◇"],
  ["cases", "Casos", "▣"],
  ["team", "Equipe", "♙"],
  ["agent", "Agente da empresa", "✦"],
  ["settings", "Configurações", "⚙"],
];

// Direct links return to their section; in-app navigation uses the browser's prior entry.
function fallbackPath(organizationId: string, pathname: string) {
  if (!organizationId) return "/";
  const prefix = `/organizations/${organizationId}`;
  const parts = pathname.slice(prefix.length).split("/").filter(Boolean);
  if (parts.length === 2 && ["imports", "audits", "findings", "cases"].includes(parts[0])) {
    return `${prefix}/${parts[0]}`;
  }
  return parts[0] === "dashboard" ? "/" : `${prefix}/dashboard`;
}

export function Shell() {
  const { organizationId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const route = `${location.pathname}${location.search}${location.hash}`;
  const lastRoute = useRef(route);
  const [hasPreviousScreen, setHasPreviousScreen] = useState(false);
  const { session, logout } = useAuth();
  const orgs = useResource<Organization[]>(["organizations"], "/organizations");
  const current = orgs.data?.find((org) => org.id === organizationId);
  const role = session?.memberships.find(
    (member) => member.organization_id === organizationId,
  )?.role;
  useEffect(() => {
    if (lastRoute.current !== route) {
      lastRoute.current = route;
      setHasPreviousScreen(true);
    }
  }, [route]);

  function goBack() {
    const historyIndex = (window.history.state as { idx?: unknown } | null)?.idx;
    if (hasPreviousScreen && typeof historyIndex === "number" && historyIndex > 0) {
      navigate(-1);
    } else {
      navigate(fallbackPath(organizationId || "", location.pathname));
    }
  }

  async function signOut() {
    await logout();
    navigate("/login");
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink className="brand" to="/">
          <span className="brand-mark small">PM</span>
          <span>
            ProcessMind <strong>AI</strong>
          </span>
        </NavLink>
        <div className="workspace-label">WORKSPACE</div>
        <select
          aria-label="Organização"
          className="org-select"
          value={organizationId || ""}
          onChange={(e) =>
            navigate(`/organizations/${e.target.value}/dashboard`)
          }
        >
          <option value="" disabled>
            Selecione uma organização
          </option>
          {orgs.data?.map((org) => (
            <option key={org.id} value={org.id}>
              {org.name}
            </option>
          ))}
        </select>
        <nav aria-label="Principal">
          <p className="nav-heading">GERENCIAMENTO</p>
          {organizationId &&
            nav.filter(([path]) => path !== "agent" || canWrite(role)).map(([path, label, icon]) => (
              <NavLink
                key={path}
                to={`/organizations/${organizationId}/${path}`}
                className={({ isActive }) =>
                  `nav-link ${isActive ? "active" : ""}`
                }
              >
                <span aria-hidden="true">{icon}</span>
                {label}
              </NavLink>
            ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="avatar">
            {session?.user.email.slice(0, 1).toUpperCase()}
          </span>
          <span className="user-info">
            <strong>{session?.user.display_name || session?.user.email}</strong>
            <small>{roleLabel(role)}</small>
          </span>
          <button
            className="icon-button"
            onClick={() => void signOut()}
            aria-label="Sair"
          >
            ↪
          </button>
        </div>
      </aside>
      <div className="content">
        <header className="topbar">
          <span className="breadcrumb">
            Workspace <span>/</span> {current?.name || "Organizações"}
          </span>
          <div className="topbar-actions">
            <ThemeToggle />
            <span className="topbar-right">{roleLabel(role)}</span>
          </div>
        </header>
        <main className="page">
          {organizationId && (
            <button type="button" className="back-link" onClick={goBack}>
              ← Voltar à tela anterior
            </button>
          )}
          <Outlet
            context={{
              organizationId: organizationId || "",
              role,
              current,
              orgs,
            }}
          />
        </main>
      </div>
    </div>
  );
}
export type ShellContext = {
  organizationId: string;
  role?: Role;
  current?: Organization;
  orgs: ReturnType<typeof useResource<Organization[]>>;
};
export const canWrite = (role?: Role) =>
  role === "owner" || role === "admin" || role === "analyst";
export const canAdmin = (role?: Role) => role === "owner" || role === "admin";
export function roleLabel(role?: Role) {
  return (
    {
      owner: "Proprietário",
      admin: "Administrador",
      analyst: "Líder",
      viewer: "Funcionário",
    } as Record<Role, string>
  )[role || "viewer"];
}
