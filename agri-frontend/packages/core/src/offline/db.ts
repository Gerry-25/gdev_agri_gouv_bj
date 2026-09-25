import Dexie, { type Table } from "dexie";

export type OutboxStatus = "pending" | "failed";

/** Envoi en attente (saisi hors ligne ou pendant une coupure réseau). */
export interface OutboxItem {
  id?: number;
  clientRef: string;
  kind: string;
  /** Libellé affiché à l'utilisateur, ex. « Parcelle de manioc ». */
  label: string;
  payload: unknown;
  file?: Blob;
  createdAt: number;
  attempts: number;
  status: OutboxStatus;
  lastError?: string;
}

class AgriDatabase extends Dexie {
  outbox!: Table<OutboxItem, number>;

  constructor() {
    super("agrismart");
    this.version(1).stores({ outbox: "++id, clientRef, status, kind, createdAt" });
  }
}

export const db = new AgriDatabase();
