import createClient from "openapi-fetch";
import { authStore } from "../auth/store";
import type { paths } from "./schema";

type FetchLike = (input: Request) => Promise<Response>;

/** Origine de l'API : vide = même origine (proxy Vite en développement, nginx en production). */
export const API_ORIGIN: string = (import.meta.env?.VITE_API_ORIGIN as string | undefined) ?? "";

let refreshing: Promise<boolean> | null = null;

const absolute = (origin: string, path: string) => `${origin || globalThis.location?.origin || ""}${path}`;

/**
 * Renouvelle la session une seule fois même si plusieurs requêtes échouent en même temps.
 * - 401 : session expirée, l'utilisateur est déconnecté ;
 * - erreur réseau : la session est conservée (mode hors ligne).
 */
export function refreshSession(origin: string, fetchImpl: FetchLike = (r) => fetch(r)): Promise<boolean> {
  if (!refreshing) {
    refreshing = (async () => {
      const refreshToken = authStore.get().refreshToken;
      if (!refreshToken) return false;
      try {
        const res = await fetchImpl(
          new Request(absolute(origin, "/api/v1/auth/refresh"), {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: refreshToken }),
          }),
        );
        if (res.status === 401) {
          authStore.clear();
          return false;
        }
        if (!res.ok) return false;
        authStore.setSession(await res.json());
        return true;
      } catch {
        return false;
      }
    })().finally(() => {
      refreshing = null;
    });
  }
  return refreshing;
}

export function createAuthFetch(origin: string, fetchImpl: FetchLike = (r) => fetch(r)): FetchLike {
  const withToken = (req: Request) => {
    const token = authStore.get().accessToken;
    if (token) req.headers.set("Authorization", `Bearer ${token}`);
    return req;
  };
  return async (request: Request) => {
    const retry = request.clone(); // le corps d'une requête ne peut être lu qu'une fois
    const isAuthRoute = new URL(request.url).pathname.startsWith("/api/v1/auth/otp");
    const { accessToken, refreshToken } = authStore.get();
    if (!accessToken && refreshToken && !isAuthRoute) {
      await refreshSession(origin, fetchImpl); // application rouverte : pas encore de jeton d'accès
    }
    const res = await fetchImpl(withToken(request));
    if (res.status === 401 && !isAuthRoute && authStore.get().refreshToken) {
      if (await refreshSession(origin, fetchImpl)) return fetchImpl(withToken(retry));
    }
    return res;
  };
}

export function createApi(origin: string = API_ORIGIN, fetchImpl?: FetchLike) {
  return createClient<paths>({ baseUrl: absolute(origin, ""), fetch: createAuthFetch(origin, fetchImpl) });
}

export const api = createApi();
export type Api = ReturnType<typeof createApi>;
