/**
 * Carte hors ligne : le fichier du fond de carte (benin.pmtiles, hébergé par nous) peut être gardé
 * dans le téléphone. C'est permis car ce fichier est le nôtre (données OpenStreetMap, licence ODbL).
 */
const CACHE = "carte-hors-ligne";
export const PMTILES_URL: string = (import.meta.env.VITE_BASEMAP_PMTILES as string | undefined) ?? "/tiles/benin.pmtiles";

export async function offlineMapFile(): Promise<File | null> {
  if (!("caches" in window)) return null;
  const res = await (await caches.open(CACHE)).match(PMTILES_URL);
  return res ? new File([await res.blob()], "benin.pmtiles") : null;
}

export async function offlineMapSize(): Promise<number | null> {
  const f = await offlineMapFile();
  return f ? f.size : null;
}

export async function downloadOfflineMap(onProgress: (ratio: number) => void): Promise<void> {
  const res = await fetch(PMTILES_URL);
  if (!res.ok || !res.body) throw new Error("Fond de carte introuvable sur le serveur.");
  const total = Number(res.headers.get("Content-Length")) || 0;
  const reader = res.body.getReader();
  const chunks: Uint8Array[] = [];
  let received = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    received += value.length;
    if (total) onProgress(received / total);
  }
  const blob = new Blob(chunks as BlobPart[], { type: "application/octet-stream" });
  await (await caches.open(CACHE)).put(PMTILES_URL, new Response(blob, { headers: { "Content-Length": String(blob.size) } }));
  onProgress(1);
}

export async function removeOfflineMap(): Promise<void> {
  if ("caches" in window) await caches.delete(CACHE);
}
