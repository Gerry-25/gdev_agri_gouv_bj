const LOCALE = "fr-FR";

export const formatNumber = (n: number, digits = 0) =>
  new Intl.NumberFormat(LOCALE, { maximumFractionDigits: digits }).format(n);

export const formatFcfa = (n: number) => `${formatNumber(n)} FCFA`;

/** 40 182 200 → « 40,2 M FCFA » (pour les indicateurs ; afficher la valeur exacte en infobulle). */
export const formatFcfaCompact = (n: number) => {
  if (Math.abs(n) >= 1e9) return `${formatNumber(n / 1e9, 1)} Md FCFA`;
  if (Math.abs(n) >= 1e6) return `${formatNumber(n / 1e6, 1)} M FCFA`;
  return formatFcfa(n);
};

export const formatHectares = (n: number) => `${formatNumber(n, n < 10 ? 2 : 1)} ha`;

export const formatDate = (iso: string | Date) =>
  new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "long", year: "numeric" }).format(new Date(iso));

export const formatRelative = (iso: string | Date) => {
  const minutes = Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.round(hours / 24);
  return days < 7 ? `il y a ${days} j` : formatDate(iso);
};

/** +2290161000000 → 01 61 00 00 00 */
export const formatPhone = (e164: string) => {
  const local = e164.replace(/^\+229/, "");
  return local.replace(/(\d{2})(?=\d)/g, "$1 ").trim();
};
