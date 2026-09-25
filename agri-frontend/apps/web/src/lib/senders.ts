import { api, ensureSent, registerSender } from "@agri/core";

/** Envois différés (file hors ligne) : un par type de saisie faite sur le terrain. */
export function registerSenders() {
  registerSender("land", async (item) => {
    ensureSent(await api.POST("/api/v1/lands/", { body: item.payload as never }));
  });
}
