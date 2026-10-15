import { NavLink, Outlet, useNavigate, useParams } from "react-router";
import { useAuth } from "../auth/AuthProvider";
import { useResource } from "../../lib/useResource";
import type { Organization, Role } from "../../lib/api";

const nav = [
  ["dashboard", "Visão geral", "◫"],
  ["imports", "Importações", "⇧"],
  ["audits", "Auditorias", "◎"],
  ["findings", "Alertas", "◇"],
  ["cases", "Casos", "▣"],
  ["settings", "Configurações", "⚙"],
];
export function Shell() {
  const { organizationId } = useParams();
  const navigate = useNavigate();
  const { session, logout } = useAuth();
  const orgs = useResource<Organization[]>(["organizations"], "/organizations");
  const current = orgs.data?.find((org) => org.id === organizationId);
  const role = session?.memberships.find(
    (member) => member.organization_id === organizationId,
  )?.role;
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
            nav.map(([path, label, icon]) => (
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
            <strong>{session?.user.email}</strong>
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
          <span className="topbar-right">{roleLabel(role)}</span>
        </header>
        <main className="page">
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
      analyst: "Analista",
      viewer: "Visualizador",
    } as Record<Role, string>
  )[role || "viewer"];
}
