import { useSession } from "@agri/core";
import type React from "react";
import { createBrowserRouter, redirect } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { RequireAuth } from "./components/Guards";
import { Card } from "./components/ui";
import { AgentHome } from "./pages/AgentHome";
import { BuyerHome } from "./pages/BuyerHome";
import { FarmerDashboard } from "./pages/FarmerDashboard";
import { LoginPage } from "./pages/LoginPage";
import { MorePage, OutboxPage } from "./pages/misc";

// Écrans avec carte chargés à la demande : MapLibre n'alourdit pas l'accueil (réseau 3G)
const cadastre = (name: "CadastrePage" | "NewParcelPage" | "ParcelDetailPage") => async () => {
  const mod = await (name === "CadastrePage" ? import("./pages/cadastre/CadastrePage") : name === "NewParcelPage" ? import("./pages/cadastre/NewParcelPage") : import("./pages/cadastre/ParcelDetailPage"));
  return { Component: (mod as Record<string, React.ComponentType>)[name] };
};

function Home() {
  const { user } = useSession();
  if (user?.role === "farmer") return <FarmerDashboard />;
  if (user?.role === "buyer") return <BuyerHome />;
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
      { path: "cadastre", lazy: cadastre("CadastrePage") },
      { path: "cadastre/nouvelle", lazy: cadastre("NewParcelPage") },
      { path: "cadastre/:id", lazy: cadastre("ParcelDetailPage") },
      { path: "cadastre/:id/contour", lazy: cadastre("NewParcelPage") },
      { path: "diagnostic", lazy: async () => ({ Component: (await import("./pages/diagnostic/DiagnosticPage")).DiagnosticPage }) },
      { path: "chat", lazy: async () => ({ Component: (await import("./pages/ChatPage")).ChatPage }) },
      { path: "stockage", lazy: async () => ({ Component: (await import("./pages/storage/StoragePage")).StoragePage }) },
      { path: "marche", lazy: async () => ({ Component: (await import("./pages/market/MarketPage")).MarketPage }) },
      { path: "supervision", lazy: async () => ({ Component: (await import("./pages/supervision/SupervisionPage")).SupervisionPage }) },
      { path: "concessions", lazy: async () => ({ Component: (await import("./pages/lands/LandsPage")).LandsPage }) },
      { path: "concessions/terres/nouvelle", lazy: async () => ({ Component: (await import("./pages/lands/NewDomainPage")).NewDomainPage }) },
      { path: "concessions/terres/:id", lazy: async () => ({ Component: (await import("./pages/lands/DomainDetail")).DomainDetail }) },
      { path: "concessions/terres/:id/appel", lazy: async () => ({ Component: (await import("./pages/lands/NewCallPage")).NewCallPage }) },
      { path: "sante", lazy: async () => ({ Component: (await import("./pages/health/HealthPage")).HealthPage }) },
      { path: "reglementation", lazy: async () => ({ Component: (await import("./pages/advice/AdvicePage")).AdvicePage }) },
      { path: "plus", element: <MorePage /> },
      { path: "envois", element: <OutboxPage /> },
      { path: "*", element: <Card><p className="text-sm">Cette page n'existe pas.</p></Card> },
    ],
  },
]);
