import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // Indirizzi dei file relativi ("./assets/..."): la stessa build funziona pubblicata alla radice di un sito
  // (https://sito/) o in una sottocartella (https://utente.github.io/SAGE/app/). Le pagine usano gli indirizzi
  // con "#" (HashRouter in main.tsx), quindi il server non deve sapere nulla delle pagine della web app.
  base: "./",
});
