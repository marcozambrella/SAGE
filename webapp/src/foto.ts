// Foto di scatola e blister dei farmaci (D15), salvate solo nel browser (localStorage), rimpicciolite per starci:
// il localStorage tiene circa 5 MB e una foto da 640 px in JPEG pesa circa 50-80 KB.

// Lato più lungo della foto salvata, in pixel, e qualità del JPEG (da 0 a 1).
const LATO_MASSIMO = 640;
const QUALITA_JPEG = 0.7;

// Legge il file scelto dal telefono o dal computer e lo restituisce rimpicciolito, come testo "data:image/jpeg;...".
export async function rimpicciolisciFoto(file: File): Promise<string> {
  const immagine = await createImageBitmap(file);
  let scala = 1;
  const latoLungo = Math.max(immagine.width, immagine.height);
  if (latoLungo > LATO_MASSIMO) {
    scala = LATO_MASSIMO / latoLungo;
  }
  const larghezza = Math.round(immagine.width * scala);
  const altezza = Math.round(immagine.height * scala);

  const tela = document.createElement("canvas");
  tela.width = larghezza;
  tela.height = altezza;
  const pennello = tela.getContext("2d");
  if (pennello === null) {
    throw new Error("This browser can't resize photos.");
  }
  pennello.drawImage(immagine, 0, 0, larghezza, altezza);
  immagine.close();
  return tela.toDataURL("image/jpeg", QUALITA_JPEG);
}
