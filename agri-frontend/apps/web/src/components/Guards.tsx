import { useSession } from "@agri/core";
import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import type { Role } from "../lib/nav";
import { Alert } from "./ui";

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useSession();
  return user ? <>{children}</> : <Navigate to="/connexion" replace />;
}

export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { user } = useSession();
  if (!user || !roles.includes(user.role as Role)) return <Alert tone="warning">Cette rubrique n'est pas accessible avec votre compte.</Alert>;
  return <>{children}</>;
}
