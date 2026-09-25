import { beforeEach, describe, expect, it } from "vitest";
import { db } from "./db";
import { enqueue, PermanentError, processOutbox, registerSender, retryItem } from "./outbox";

const flush = async () => {
  // enqueue déclenche un envoi en arrière-plan : on attend qu'il se termine
  await new Promise((r) => setTimeout(r, 0));
  return processOutbox();
};

describe("file d'attente hors ligne", () => {
  beforeEach(async () => {
    await db.outbox.clear();
  });

  it("envoie puis retire les saisies, dans l'ordre", async () => {
    const sent: string[] = [];
    registerSender("ordre", async (item) => void sent.push((item.payload as { n: string }).n));
    await enqueue("ordre", "A", { n: "a" });
    await enqueue("ordre", "B", { n: "b" });
    await flush();
    expect(sent).toEqual(["a", "b"]);
    expect(await db.outbox.count()).toBe(0);
  });

  it("garde les saisies en cas de coupure et s'arrête pour préserver l'ordre", async () => {
    let online = false;
    const sent: string[] = [];
    registerSender("reseau", async (item) => {
      if (!online) throw new TypeError("Failed to fetch");
      sent.push(item.label);
    });
    await enqueue("reseau", "premier", {});
    await enqueue("reseau", "second", {});
    await flush();
    const items = await db.outbox.toArray();
    expect(items).toHaveLength(2);
    expect(items[0].attempts).toBeGreaterThan(0);
    expect(items[1].attempts).toBe(0);

    online = true;
    await processOutbox();
    expect(sent).toEqual(["premier", "second"]);
  });

  it("met de côté une saisie refusée sans bloquer les suivantes", async () => {
    registerSender("refus", async (item) => {
      if (item.label === "invalide") throw new PermanentError("Surface trop petite.");
    });
    await enqueue("refus", "invalide", {});
    await enqueue("refus", "valide", {});
    const result = await flush();
    const left = await db.outbox.toArray();
    expect(left).toHaveLength(1);
    expect(left[0]).toMatchObject({ label: "invalide", status: "failed", lastError: "Surface trop petite." });
    expect(result.remaining).toBe(0);

    // L'utilisateur corrige puis relance
    registerSender("refus", async () => {});
    await retryItem(left[0].id!);
    await flush();
    expect(await db.outbox.count()).toBe(0);
  });

  it("réutilise le client_ref fourni pour que le serveur ignore les doublons", async () => {
    registerSender("ref", async () => {
      throw new TypeError("hors ligne");
    });
    const ref = await enqueue("ref", "Parcelle", { client_ref: "3f6c1d2e-demo-0001" });
    expect(ref).toBe("3f6c1d2e-demo-0001");
    expect((await db.outbox.toArray())[0].clientRef).toBe(ref);
  });

  it("conserve les photos (Blob) jusqu'à l'envoi", async () => {
    let size = 0;
    registerSender("photo", async (item) => void (size = item.file!.size));
    await enqueue("photo", "Diagnostic", {}, new Blob([new Uint8Array(2048)], { type: "image/jpeg" }));
    await flush();
    expect(size).toBe(2048);
  });
});
