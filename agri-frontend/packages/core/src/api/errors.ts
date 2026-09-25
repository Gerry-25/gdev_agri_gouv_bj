/** Transforme une erreur de l'API en message affichable (les messages du backend sont déjà en français). */
export function apiErrorMessage(error: unknown, fallback = "Une erreur est survenue. Réessayez."): string {
  if (!error) return fallback;
  if (typeof error === "string") return error;
  if (error instanceof TypeError) return "Pas de connexion au serveur. Vérifiez votre réseau.";
  const detail = (error as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (detail && typeof detail === "object" && !Array.isArray(detail)) {
    const d = detail as { message?: string; reasons?: string[] };
    return [d.message, ...(d.reasons ?? [])].filter(Boolean).join(" ");
  }
  if (Array.isArray(detail) && detail.length) {
    // Erreurs de validation : on garde le premier message, sans le jargon technique
    const first = detail[0] as { msg?: string; loc?: (string | number)[] };
    const field = first.loc?.filter((p) => p !== "body").join(".");
    const msg = (first.msg ?? "").replace(/^Value error, /, "");
    return field ? `${msg} (${field})` : msg || fallback;
  }
  return fallback;
}

/** Statut HTTP qui ne changera pas en réessayant (données refusées par le serveur). */
export function isPermanentStatus(status: number): boolean {
  return status >= 400 && status < 500 && ![401, 408, 429].includes(status);
}
