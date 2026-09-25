/**
 * Réduit une photo dans le téléphone avant l'envoi : une photo de 4 Mo passe à environ 300 Ko,
 * ce qui compte en 3G. 1600 px suffisent au diagnostic (le serveur réduit ensuite à 1536 px).
 */
export async function compressImage(file: File, maxSide = 1600, quality = 0.82): Promise<Blob> {
  if (!file.type.startsWith("image/")) throw new Error("Le fichier choisi n'est pas une photo.");
  const bitmap = await createImageBitmap(file).catch(() => null);
  if (!bitmap) return file; // format non décodable ici : on envoie l'original, le serveur tranchera
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/jpeg", quality));
  return blob && blob.size < file.size ? blob : file;
}
