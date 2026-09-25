/**
 * Session utilisateur.
 *
 * - Le jeton d'accès (1 h) reste en mémoire uniquement.
 * - Le jeton de rafraîchissement et le profil sont conservés sur l'appareil pour rouvrir
 *   l'application sans connexion réseau. Compromis assumé pour une PWA hors ligne :
 *   la protection repose sur l'absence de XSS (pas de HTML injecté, CSP au déploiement).
 */
import { useSyncExternalStore } from "react";
import type { components } from "../api/schema";

export type UserProfile = components["schemas"]["UserProfile"];
export type TokenResponse = components["schemas"]["TokenResponse"];

export interface SessionState {
  accessToken: string | null;
  refreshToken: string | null;
  user: UserProfile | null;
}

const STORAGE_KEY = "agrismart.session";

interface KeyValueStorage {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

function memoryStorage(): KeyValueStorage {
  const data = new Map<string, string>();
  return {
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
  };
}

const storage: KeyValueStorage = typeof localStorage !== "undefined" ? localStorage : memoryStorage();

function load(): SessionState {
  try {
    const raw = storage.getItem(STORAGE_KEY);
    if (raw) {
      const saved = JSON.parse(raw) as { refreshToken: string; user: UserProfile };
      return { accessToken: null, refreshToken: saved.refreshToken, user: saved.user };
    }
  } catch {
    storage.removeItem(STORAGE_KEY);
  }
  return { accessToken: null, refreshToken: null, user: null };
}

let state: SessionState = load();
const listeners = new Set<() => void>();

function emit(next: SessionState) {
  state = next;
  if (next.refreshToken && next.user) {
    storage.setItem(STORAGE_KEY, JSON.stringify({ refreshToken: next.refreshToken, user: next.user }));
  } else {
    storage.removeItem(STORAGE_KEY);
  }
  listeners.forEach((l) => l());
}

export const authStore = {
  get: (): SessionState => state,
  subscribe(listener: () => void) {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
  setSession(tokens: TokenResponse) {
    emit({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token, user: tokens.user });
  },
  setUser(user: UserProfile) {
    emit({ ...state, user });
  },
  clear() {
    emit({ accessToken: null, refreshToken: null, user: null });
  },
};

export function useSession(): SessionState {
  return useSyncExternalStore(authStore.subscribe, authStore.get, authStore.get);
}
