import { describe, expect, it } from "vitest";
import { apiErrorMessage, isPermanentStatus } from "./errors";

describe("messages d'erreur", () => {
  it("reprend le message du serveur", () => {
    expect(apiErrorMessage({ detail: "Code incorrect. Il vous reste 4 essai(s)." })).toBe("Code incorrect. Il vous reste 4 essai(s).");
  });
  it("assemble message et motifs", () => {
    expect(apiErrorMessage({ detail: { message: "Candidature impossible.", reasons: ["Score trop bas."] } })).toBe("Candidature impossible. Score trop bas.");
  });
  it("nettoie les erreurs de validation", () => {
    const err = { detail: [{ loc: ["body", "npi"], msg: "Value error, NPI invalide" }] };
    expect(apiErrorMessage(err)).toBe("NPI invalide (npi)");
  });
  it("explique une coupure réseau", () => {
    expect(apiErrorMessage(new TypeError("Failed to fetch"))).toMatch(/réseau/);
  });
  it("distingue les erreurs définitives des erreurs temporaires", () => {
    expect(isPermanentStatus(422)).toBe(true);
    expect(isPermanentStatus(409)).toBe(true);
    expect(isPermanentStatus(401)).toBe(false);
    expect(isPermanentStatus(429)).toBe(false);
    expect(isPermanentStatus(503)).toBe(false);
  });
});
