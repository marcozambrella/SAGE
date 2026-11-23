/// <reference types="vite/client" />

// Variabili d'ambiente lette dalla web app (file .env.local, mai nel repo).
interface ImportMetaEnv {
  // Indirizzo del backend, es. http://localhost:8000. Vuoto: si usano i dati finti di sviluppo.
  readonly VITE_API_URL?: string;
}
