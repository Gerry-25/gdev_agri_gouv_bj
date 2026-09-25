/**
 * File d'attente hors ligne.
 *
 * Chaque saisie reçoit un `clientRef` unique dès sa création. Le backend s'en sert pour ignorer
 * les doublons : un envoi rejoué après une coupure renvoie la ressource déjà créée.
 */
import { apiErrorMessage, isPermanentStatus } from "../api/errors";
import { db, type OutboxItem } from "./db";

/** Erreur définitive : le serveur refuse les données, réessayer ne servira à rien. */
export class PermanentError extends Error {}

export type Sender = (item: OutboxItem) => Promise<void>;

const senders = new Map<string, Sender>();
let running: Promise<SyncResult> | null = null;
/** Une saisie a été ajoutée pendant une synchronisation : il faudra refaire un passage. */
let dirty = false;

export interface SyncResult {
  sent: number;
  failed: number;
  remaining: number;
}

export function registerSender(kind: string, sender: Sender): void {
  senders.set(kind, sender);
}

export function newClientRef(): string {
  return crypto.randomUUID();
}

/** Interprète le résultat d'openapi-fetch : succès, erreur définitive ou erreur temporaire. */
export function ensureSent(result: { error?: unknown; response: Response }): void {
  if (!result.error) return;
  const message = apiErrorMessage(result.error);
  if (isPermanentStatus(result.response.status)) throw new PermanentError(message);
  throw new Error(message);
}

export async function enqueue(kind: string, label: string, payload: unknown, file?: Blob): Promise<string> {
  const clientRef = (payload as { client_ref?: string } | null)?.client_ref ?? newClientRef();
  await db.outbox.add({ clientRef, kind, label, payload, file, createdAt: Date.now(), attempts: 0, status: "pending" });
  dirty = true;
  void processOutbox();
  return clientRef;
}

const isOffline = () => typeof navigator !== "undefined" && navigator.onLine === false;

export function processOutbox(): Promise<SyncResult> {
  if (!running) {
    running = (async () => {
      let sent = 0;
      let failed = 0;
      let networkDown = false;
      do {
        dirty = false;
        const items = await db.outbox.where("status").equals("pending").sortBy("createdAt");
        for (const item of items) {
          const sender = senders.get(item.kind);
          if (!sender || isOffline()) continue;
          try {
            await sender(item);
            await db.outbox.delete(item.id!);
            sent++;
          } catch (e) {
            const message = e instanceof Error ? e.message : String(e);
            if (e instanceof PermanentError) {
              await db.outbox.update(item.id!, { status: "failed", lastError: message, attempts: item.attempts + 1 });
              failed++;
            } else {
              // Réseau indisponible : on réessaiera plus tard, dans l'ordre de saisie
              await db.outbox.update(item.id!, { lastError: message, attempts: item.attempts + 1 });
              networkDown = true;
              break;
            }
          }
        }
      } while (dirty && !networkDown);
      const remaining = await db.outbox.where("status").equals("pending").count();
      return { sent, failed, remaining };
    })().finally(() => {
      running = null;
    });
  }
  return running;
}

export async function retryItem(id: number): Promise<void> {
  await db.outbox.update(id, { status: "pending", lastError: undefined });
  void processOutbox();
}

export async function discardItem(id: number): Promise<void> {
  await db.outbox.delete(id);
}

/** Synchronise au démarrage, au retour du réseau et à intervalle régulier. */
export function startOutboxSync(intervalMs = 60_000): () => void {
  const run = () => void processOutbox();
  window.addEventListener("online", run);
  const timer = window.setInterval(run, intervalMs);
  run();
  return () => {
    window.removeEventListener("online", run);
    window.clearInterval(timer);
  };
}
