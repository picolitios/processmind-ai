// Liga a sessão às rotas e carrega cada tela apenas quando ela é aberta.
import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router";
import { AuthProvider, useAuth } from "./features/auth/AuthProvider";
import { AuthPage } from "./features/auth/AuthPage";
import { Shell } from "./features/shell/Shell";
import { InviteAcceptPage } from "./features/team/InviteAcceptPage";
import { ThemeProvider } from "./features/theme/ThemeProvider";

const OrganizationsPage = lazy(() =>
  import("./features/organizations/OrganizationsPage").then(
    ({ OrganizationsPage }) => ({ default: OrganizationsPage }),
  ),
);
const DashboardPage = lazy(() =>
  import("./features/dashboard/DashboardPage").then(({ DashboardPage }) => ({
    default: DashboardPage,
  })),
);
const ImportsPage = lazy(() =>
  import("./features/imports/ImportsPage").then(({ ImportsPage }) => ({
    default: ImportsPage,
  })),
);
const ImportDetailPage = lazy(() =>
  import("./features/imports/ImportDetailPage").then(
    ({ ImportDetailPage }) => ({ default: ImportDetailPage }),
  ),
);
const AuditsPage = lazy(() =>
  import("./features/audits/AuditsPage").then(({ AuditsPage }) => ({
    default: AuditsPage,
  })),
);
const AuditDetailPage = lazy(() =>
  import("./features/audits/AuditDetailPage").then(({ AuditDetailPage }) => ({
    default: AuditDetailPage,
  })),
);
const FindingsPage = lazy(() =>
  import("./features/findings/FindingsPage").then(({ FindingsPage }) => ({
    default: FindingsPage,
  })),
);
const FindingDetailPage = lazy(() =>
  import("./features/findings/FindingDetailPage").then(
    ({ FindingDetailPage }) => ({ default: FindingDetailPage }),
  ),
);
const CasesPage = lazy(() =>
  import("./features/cases/CasesPage").then(({ CasesPage }) => ({
    default: CasesPage,
  })),
);
const CaseDetailPage = lazy(() =>
  import("./features/cases/CaseDetailPage").then(({ CaseDetailPage }) => ({
    default: CaseDetailPage,
  })),
);
const SettingsPage = lazy(() =>
  import("./features/settings/SettingsPage").then(({ SettingsPage }) => ({
    default: SettingsPage,
  })),
);
const TeamPage = lazy(() =>
  import("./features/team/TeamPage").then(({ TeamPage }) => ({ default: TeamPage })),
);
const OrganizationAgentPage = lazy(() =>
  import("./features/copilot/OrganizationAgentPage").then(({ OrganizationAgentPage }) => ({
    default: OrganizationAgentPage,
  })),
);
const KnowledgeSourcePage = lazy(() =>
  import("./features/copilot/KnowledgeSourcePage").then(({ KnowledgeSourcePage }) => ({
    default: KnowledgeSourcePage,
  })),
);

function Router() {
  const { session, loading } = useAuth();
  if (loading)
    return (
      <div className="loading-screen" role="status">
        Carregando ProcessMind AI…
      </div>
    );
  if (!session)
    return (
      <Routes>
        <Route path="/login" element={<AuthPage />} />
        <Route path="/invite" element={<InviteAcceptPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  return (
    <Suspense
      fallback={
        <div className="loading-screen" role="status">
          Carregando tela…
        </div>
      }
    >
      <Routes>
        <Route path="/invite" element={<InviteAcceptPage />} />
        <Route path="/login" element={<Navigate to={sessionStorage.getItem("processmind-pending-invite") ? "/invite" : "/"} replace />} />
        <Route element={<Shell />}>
          <Route path="/" element={<OrganizationsPage />} />
          <Route
            path="/organizations/:organizationId/dashboard"
            element={<DashboardPage />}
          />
          <Route
            path="/organizations/:organizationId/imports"
            element={<ImportsPage />}
          />
          <Route
            path="/organizations/:organizationId/imports/:importId"
            element={<ImportDetailPage />}
          />
          <Route
            path="/organizations/:organizationId/audits"
            element={<AuditsPage />}
          />
          <Route
            path="/organizations/:organizationId/audits/:auditId"
            element={<AuditDetailPage />}
          />
          <Route
            path="/organizations/:organizationId/findings"
            element={<FindingsPage />}
          />
          <Route
            path="/organizations/:organizationId/findings/:findingId"
            element={<FindingDetailPage />}
          />
          <Route
            path="/organizations/:organizationId/cases"
            element={<CasesPage />}
          />
          <Route
            path="/organizations/:organizationId/cases/:caseId"
            element={<CaseDetailPage />}
          />
          <Route
            path="/organizations/:organizationId/settings"
            element={<SettingsPage />}
          />
          <Route path="/organizations/:organizationId/team" element={<TeamPage />} />
          <Route
            path="/organizations/:organizationId/agent"
            element={<OrganizationAgentPage />}
          />
          <Route path="/organizations/:organizationId/knowledge/:sourceId"
            element={<KnowledgeSourcePage />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <Router />
      </AuthProvider>
    </ThemeProvider>
  );
}
