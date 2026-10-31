import { AppShell } from "../layout/AppShell";
import { ForbiddenPage } from "../pages/ForbiddenPage";
import { LoginPage } from "../pages/LoginPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { useAuth } from "../state/auth";
import { ROUTES } from "./routes";
import { useRouter } from "./router";

export function App() {
  const { isAuthenticated, can } = useAuth();
  const { path } = useRouter();

  if (!isAuthenticated) return <LoginPage />;

  const route = ROUTES.find((r) => r.path === path);
  const Page = !route ? NotFoundPage : can(route.minRole) ? route.component : ForbiddenPage;
  return (
    <AppShell>
      <Page />
    </AppShell>
  );
}
