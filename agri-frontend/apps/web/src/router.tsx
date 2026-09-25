import { useSession } from "@agri/core";
import { createBrowserRouter, redirect } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { RequireAuth } from "./components/Guards";
import { Card } from "./components/ui";
import { AgentHome } from "./pages/AgentHome";
import { FarmerDashboard } from "./pages/FarmerDashboard";
import { LoginPage } from "./pages/LoginPage";
import { MorePage, OutboxPage, Planned } from "./pages/misc";

function Home() {
  const { user } = useSession();
  if (user?.role === "farmer") return <FarmerDashboard />;
  if (user?.role === "buyer") return <Planned title="Portail acheteur" step={4} />;
  return <AgentHome />;
}

export const router = createBrowserRouter([
  { path: "/connexion", element: <LoginPage /> },
  // Ancienne adresse de l'espace agents : tout est désormais dans la même application
  { path: "/agents/*", loader: () => redirect("/") },
  {
    element: (
      <RequireAuth>
        <AppShell />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <Home /> },
      { path: "cadastre/*", element: <Planned title="Cadastre et fiche parcelle" step={2} /> },
      { path: "diagnostic", element: <Planned title="Diagnostic phytosanitaire" step={3} /> },
      { path: "stockage", element: <Planned title="Conseiller de stockage" step={3} /> },
      { path: "marche", element: <Planned title="Marché agricole" step={4} /> },
      { path: "supervision", element: <Planned title="Supervision nationale" step={4} /> },
      { path: "concessions", element: <Planned title="Terres de l'État" step={5} /> },
      { path: "reglementation", element: <Planned title="Conseils et réglementation" step={5} /> },
      { path: "plus", element: <MorePage /> },
      { path: "envois", element: <OutboxPage /> },
      { path: "*", element: <Card><p className="text-sm">Cette page n'existe pas.</p></Card> },
    ],
  },
]);
