// Icone disegnate a mano (24x24, tratto tondo), così non serve una libreria di icone.
import type { ReactNode } from "react";

export type NomeIcona =
  | "sole"
  | "calendario"
  | "andamento"
  | "documento"
  | "pillola"
  | "bicchiere"
  | "telecamera"
  | "campanella"
  | "cursori"
  | "altro"
  | "goccia"
  | "pasto"
  | "luna"
  | "avviso"
  | "porta"
  | "casa"
  | "piu"
  | "cestino"
  | "freccia"
  | "indietro"
  | "spunta"
  | "chiudi"
  | "orologio"
  | "pausa"
  | "foto"
  | "scintilla"
  | "famiglia"
  | "cuore"
  | "scudo";

const DISEGNI: Record<NomeIcona, ReactNode> = {
  sole: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2" />
      <path d="M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </>
  ),
  calendario: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="3" />
      <path d="M3 10h18M8 3v4M16 3v4" />
    </>
  ),
  andamento: <path d="M3 17l5-5 4 4 8-8M15 8h5v5" />,
  documento: (
    <>
      <path d="M7 3h7l5 5v11a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z" />
      <path d="M14 3v5h5M9 13h6M9 17h4" />
    </>
  ),
  pillola: (
    <g transform="rotate(-45 12 12)">
      <rect x="3" y="8.5" width="18" height="7" rx="3.5" />
      <path d="M12 8.5v7" />
    </g>
  ),
  bicchiere: (
    <>
      <path d="M6 4h12l-1.5 15a2 2 0 0 1-2 1.8h-5a2 2 0 0 1-2-1.8z" />
      <path d="M6.7 10.5h10.6" />
    </>
  ),
  telecamera: (
    <>
      <rect x="2.5" y="7" width="13" height="10" rx="3" />
      <path d="M15.5 10.5l5-3v9l-5-3" />
    </>
  ),
  campanella: (
    <>
      <path d="M6 16v-5a6 6 0 0 1 12 0v5l1.5 2h-15z" />
      <path d="M10 20.5a2 2 0 0 0 4 0" />
    </>
  ),
  cursori: (
    <>
      <path d="M4 7h10M18 7h2M4 17h4M12 17h8" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="10" cy="17" r="2" />
    </>
  ),
  altro: (
    <>
      <circle cx="5.5" cy="12" r="1.6" fill="currentColor" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" />
      <circle cx="18.5" cy="12" r="1.6" fill="currentColor" />
    </>
  ),
  goccia: <path d="M12 3.5c-3.5 4.5-6 7.8-6 10.8a6 6 0 0 0 12 0c0-3-2.5-6.3-6-10.8z" />,
  pasto: (
    <>
      <path d="M3.5 12h17a8.5 7.5 0 0 1-17 0z" />
      <path d="M9 8.5c0-1.5 1-1.5 1-3M14 8.5c0-1.5 1-1.5 1-3" />
    </>
  ),
  luna: <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />,
  avviso: (
    <>
      <path d="M10.3 4.6a2 2 0 0 1 3.4 0l7.4 12.9a2 2 0 0 1-1.7 3H4.6a2 2 0 0 1-1.7-3z" />
      <path d="M12 10v4M12 17.3v.01" />
    </>
  ),
  porta: (
    <>
      <path d="M14 4H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h7" />
      <path d="M11 12h10M17 8l4 4-4 4" />
    </>
  ),
  casa: (
    <>
      <path d="M4 11l8-7 8 7v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" />
      <path d="M10 21v-6h4v6" />
    </>
  ),
  piu: <path d="M12 5v14M5 12h14" />,
  cestino: <path d="M4 7h16M10 4h4M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12" />,
  freccia: <path d="M5 12h14M13 6l6 6-6 6" />,
  indietro: <path d="M19 12H5M11 6l-6 6 6 6" />,
  spunta: <path d="M5 12.5l4.5 4.5L19 7.5" />,
  chiudi: <path d="M6 6l12 12M18 6L6 18" />,
  orologio: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  pausa: <path d="M9 6v12M15 6v12" />,
  foto: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="3" />
      <circle cx="9" cy="10" r="1.8" />
      <path d="M21 16l-5-5-8 8" />
    </>
  ),
  scintilla: (
    <>
      <path d="M12 3c.8 4.5 2.5 6.2 7 7-4.5.8-6.2 2.5-7 7-.8-4.5-2.5-6.2-7-7 4.5-.8 6.2-2.5 7-7z" />
      <path d="M19 16.5c.3 1.6.9 2.2 2.5 2.5-1.6.3-2.2.9-2.5 2.5-.3-1.6-.9-2.2-2.5-2.5 1.6-.3 2.2-.9 2.5-2.5z" />
    </>
  ),
  famiglia: (
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
      <circle cx="17" cy="9" r="2.5" />
      <path d="M15.5 14.2a4.5 4.5 0 0 1 5 4.8" />
    </>
  ),
  cuore: <path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z" />,
  scudo: <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z" />,
};

type Proprieta = {
  nome: NomeIcona;
  dimensione?: number;
};

export default function Icona({ nome, dimensione = 24 }: Proprieta) {
  return (
    <svg
      width={dimensione}
      height={dimensione}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {DISEGNI[nome]}
    </svg>
  );
}
