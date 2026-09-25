import { api, ensureSent, registerSender } from "@agri/core";

/** Envois différés (file hors ligne) : un par type de saisie faite sur le terrain. */
export function registerSenders() {
  registerSender("land", async (item) => {
    ensureSent(await api.POST("/api/v1/lands/", { body: item.payload as never }));
  });

  // Diagnostic photographié sans réseau : la photo est gardée dans le téléphone jusqu'à l'envoi
  registerSender("diagnosis", async (item) => {
    const form = new FormData();
    for (const [k, v] of Object.entries(item.payload as Record<string, string | number | undefined>)) {
      if (v !== undefined && v !== null && v !== "") form.append(k, String(v));
    }
    form.append("file", item.file!, "photo.jpg");
    ensureSent(await api.POST("/api/v1/monitoring/diagnose", { body: form as never }));
  });

  registerSender("stock", async (item) => {
    ensureSent(await api.POST("/api/v1/storage/lots", { body: item.payload as never }));
  });
}
