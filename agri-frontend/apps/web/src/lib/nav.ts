import {
  BookOpen, Gauge, HeartPulse, Landmark, type LucideIcon, Map, ScanLine, ShieldCheck, ShoppingBasket, Sparkles, Sprout, Warehouse,
} from "lucide-react";

export type Role = "farmer" | "buyer" | "state_agent" | "state_supervisor";

export interface Tab {
  to: string;
  label: string;
  short: string; // libellé de la barre mobile
  icon: LucideIcon;
  roles: Role[];
}

const FIELD: Role[] = ["farmer"];
const AGENTS: Role[] = ["state_agent", "state_supervisor"];
const ALL: Role[] = ["farmer", "buyer", "state_agent", "state_supervisor"];

/** Onglets affichés selon le rôle réel de l'utilisateur (plus de sélecteur de rôle). */
export const TABS: Tab[] = [
  { to: "/", label: "Mon exploitation", short: "Accueil", icon: Sprout, roles: FIELD },
  { to: "/", label: "Portail acheteur", short: "Accueil", icon: ShoppingBasket, roles: ["buyer"] },
  { to: "/", label: "Guichet agent", short: "Accueil", icon: Gauge, roles: ["state_agent"] },
  { to: "/", label: "Cockpit État", short: "Accueil", icon: Gauge, roles: ["state_supervisor"] },
  { to: "/cadastre", label: "Cadastre", short: "Cadastre", icon: Map, roles: [...FIELD, ...AGENTS] },
  { to: "/diagnostic", label: "Diagnostic", short: "Diagnostic", icon: ScanLine, roles: [...FIELD, ...AGENTS] },
  { to: "/chat", label: "Assistant IA", short: "Assistant", icon: Sparkles, roles: ALL },
  { to: "/stockage", label: "Stockage", short: "Stocks", icon: Warehouse, roles: FIELD },
  { to: "/marche", label: "Marché", short: "Marché", icon: ShoppingBasket, roles: ALL },
  { to: "/supervision", label: "Supervision", short: "Supervision", icon: ShieldCheck, roles: AGENTS },
  { to: "/concessions", label: "Terres de l'État", short: "Terres", icon: Landmark, roles: [...FIELD, ...AGENTS] },
  { to: "/sante", label: "Santé exploitants", short: "Santé", icon: HeartPulse, roles: [...FIELD, ...AGENTS] },
  { to: "/reglementation", label: "Conseils", short: "Conseils", icon: BookOpen, roles: ALL },
];

export const tabsFor = (role?: string | null) => TABS.filter((t) => role && t.roles.includes(role as Role));

export const ROLE_LABELS: Record<Role, string> = {
  farmer: "Exploitant agricole",
  buyer: "Acheteur",
  state_agent: "Agent de l'État",
  state_supervisor: "Superviseur",
};
