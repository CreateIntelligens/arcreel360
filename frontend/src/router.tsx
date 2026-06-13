// router.tsx — Route definitions for the studio layout

import { useEffect } from "react";
import { Route, Switch, Redirect, useLocation, useParams } from "wouter";
import { StudioLayout } from "@/components/layout";
import { StudioCanvasRouter } from "@/components/canvas/StudioCanvasRouter";
import { ProjectsPage } from "@/components/pages/ProjectsPage";
import { SystemConfigPage } from "@/components/pages/SystemConfigPage";
import { ProjectSettingsPage } from "@/components/pages/ProjectSettingsPage";
import { LoginPage } from "@/components/pages/LoginPage";
import { NotFoundPage } from "@/components/pages/NotFoundPage";
import { ToastOverlay } from "@/components/layout/ToastOverlay";
import { ConfirmProvider } from "@/components/ui/ConfirmProvider";
import { API } from "@/api";
import { useProjectsStore } from "@/stores/projects-store";
import { useAssistantStore } from "@/stores/assistant-store";
import { useAuthStore } from "@/stores/auth-store";

// ---------------------------------------------------------------------------
// AuthGuard — redirects to /login when not authenticated
// ---------------------------------------------------------------------------

function AuthGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuthStore();

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-gray-950 text-gray-500">
        載入中...
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Redirect to="/login" />;
  }

  return <>{children}</>;
}

// ---------------------------------------------------------------------------
// StudioWorkspace — loads project data and renders three-column layout
// ---------------------------------------------------------------------------

function StudioWorkspace() {
  const params = useParams<{ projectName: string }>();
  const projectName = params.projectName ?? null;
  const [, navigate] = useLocation();
  const { setCurrentProject, setProjectDetailLoading } = useProjectsStore();

  useEffect(() => {
    if (!projectName) return;
    let cancelled = false;

    // 清空上一個專案的 assistant 狀態，確保會話隔離
    const assistantState = useAssistantStore.getState();
    assistantState.setSessions([]);
    assistantState.setCurrentSessionId(null);
    assistantState.setTurns([]);
    assistantState.setDraftTurn(null);
    assistantState.setSessionStatus(null);
    assistantState.setIsDraftSession(false);

    setProjectDetailLoading(true);
    API.getProject(projectName)
      .then((res) => {
        if (!cancelled) {
          setCurrentProject(projectName, res.project, res.scripts ?? {}, res.asset_fingerprints);
        }
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        if ((err as { status?: number }).status === 404) {
          setCurrentProject(null, null);
          setProjectDetailLoading(false);
          navigate("~/app/projects", { replace: true });
          return;
        }

        // Still set the project name so the UI shows something for transient failures.
        setCurrentProject(projectName, null);
      })
      .finally(() => {
        if (!cancelled) setProjectDetailLoading(false);
      });

    return () => {
      cancelled = true;
      setCurrentProject(null, null);
    };
  }, [navigate, projectName, setCurrentProject, setProjectDetailLoading]);

  return (
    <StudioLayout>
      <StudioCanvasRouter />
    </StudioLayout>
  );
}

// ---------------------------------------------------------------------------
// Top-level route tree
// ---------------------------------------------------------------------------

export function AppRoutes() {
  return (
    <ConfirmProvider>
      <Switch>
        {/* Login page */}
        <Route path="/login" component={LoginPage} />

        {/* Root redirects to projects list */}
        <Route path="/">
          <Redirect to="/app/projects" />
        </Route>

        {/* /app and /app/ also redirect to projects list */}
        <Route path="/app">
          <Redirect to="/app/projects" />
        </Route>

        {/* Projects list */}
        <Route path="/app/projects">
          <AuthGuard>
            <ProjectsPage />
          </AuthGuard>
        </Route>

        {/* System settings */}
        <Route path="/app/settings">
          <AuthGuard>
            <SystemConfigPage />
          </AuthGuard>
        </Route>

        {/* Project settings — full-screen, must be before the nested workspace route */}
        <Route path="/app/projects/:projectName/settings">
          <AuthGuard>
            <ProjectSettingsPage />
          </AuthGuard>
        </Route>

        {/* Studio workspace (three-column layout) */}
        <Route path="/app/projects/:projectName" nest>
          <AuthGuard>
            <StudioWorkspace />
          </AuthGuard>
        </Route>

        {/* 404 */}
        <Route>
          <NotFoundPage />
        </Route>
      </Switch>
      <ToastOverlay />
    </ConfirmProvider>
  );
}
