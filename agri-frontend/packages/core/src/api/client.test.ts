import { beforeEach, describe, expect, it } from "vitest";
import { authStore } from "../auth/store";
import { createApi } from "./client";

const ORIGIN = "http://api.test";
const USER = { npi: "1111111111", phone: "+2290161000000", full_name: "Awa", role: "farmer" as const };
const tokens = (n: number) => ({ access_token: `access-${n}`, refresh_token: `refresh-${n}`, expires_in: 3600, refresh_expires_in: 1, user: USER });

/** Faux serveur : n'accepte que le jeton d'accès courant. */
function fakeServer(opts: { refreshStatus?: number } = {}) {
  let valid = "access-1";
  let issued = 1;
  const calls: string[] = [];
  const fetchImpl = async (req: Request) => {
    const path = new URL(req.url).pathname;
    calls.push(path);
    if (path === "/api/v1/auth/refresh") {
      if (opts.refreshStatus) return new Response("{}", { status: opts.refreshStatus });
      await new Promise((r) => setTimeout(r, 10)); // laisse les requêtes concurrentes attendre
      issued++;
      valid = `access-${issued}`;
      return Response.json(tokens(issued));
    }
    if (req.headers.get("Authorization") !== `Bearer ${valid}`) return Response.json({ detail: "Jeton expiré." }, { status: 401 });
    const body = req.method !== "GET" ? await req.json() : null;
    return Response.json({ ok: true, body });
  };
  return { fetchImpl, calls, expire: () => (valid = "nouveau-jeton-inconnu") };
}

describe("client API et session", () => {
  beforeEach(() => authStore.setSession(tokens(1)));

  it("ajoute le jeton d'accès", async () => {
    const server = fakeServer();
    const api = createApi(ORIGIN, server.fetchImpl);
    const { response } = await api.GET("/api/v1/auth/me");
    expect(response.status).toBe(200);
  });

  it("renouvelle la session une seule fois pour des requêtes simultanées, puis les rejoue", async () => {
    const server = fakeServer();
    const api = createApi(ORIGIN, server.fetchImpl);
    server.expire();
    authStore.setSession({ ...tokens(1), access_token: "périmé" });
    const results = await Promise.all([
      api.GET("/api/v1/auth/me"),
      api.GET("/api/v1/notifications/me/unread-count"),
      api.PATCH("/api/v1/auth/me", { body: { full_name: "Awa K." } }),
    ]);
    expect(results.map((r) => r.response.status)).toEqual([200, 200, 200]);
    expect(server.calls.filter((c) => c === "/api/v1/auth/refresh")).toHaveLength(1);
    expect(authStore.get().refreshToken).toBe("refresh-2");
    // le corps de la requête rejouée est intact
    expect((results[2].data as unknown as { body: { full_name: string } }).body.full_name).toBe("Awa K.");
  });

  it("à la réouverture de l'application, obtient un jeton avant la première requête", async () => {
    const server = fakeServer();
    authStore.setSession(tokens(1));
    authStore.setSession({ ...tokens(1), access_token: "" }); // jeton d'accès perdu (mémoire vidée)
    const api = createApi(ORIGIN, server.fetchImpl);
    const { response } = await api.GET("/api/v1/auth/me");
    expect(response.status).toBe(200);
    expect(server.calls[0]).toBe("/api/v1/auth/refresh");
  });

  it("déconnecte si le serveur refuse le renouvellement", async () => {
    const server = fakeServer({ refreshStatus: 401 });
    server.expire();
    const api = createApi(ORIGIN, server.fetchImpl);
    const { response } = await api.GET("/api/v1/auth/me");
    expect(response.status).toBe(401);
    expect(authStore.get().user).toBeNull();
  });

  it("garde la session si le réseau est coupé pendant le renouvellement", async () => {
    const api = createApi(ORIGIN, async (req) => {
      if (new URL(req.url).pathname === "/api/v1/auth/refresh") throw new TypeError("Failed to fetch");
      return Response.json({ detail: "Jeton expiré." }, { status: 401 });
    });
    await api.GET("/api/v1/auth/me");
    expect(authStore.get().user?.npi).toBe("1111111111");
  });

  it("n'essaie pas de renouveler pendant la connexion par code", async () => {
    const server = fakeServer();
    authStore.clear();
    const api = createApi(ORIGIN, server.fetchImpl);
    await api.POST("/api/v1/auth/otp/verify", { body: { npi: "1111111111", code: "123456" } });
    expect(server.calls).not.toContain("/api/v1/auth/refresh");
  });
});
