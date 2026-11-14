import { defineConfig } from 'vite';

export default defineConfig({
  // Necesario para GitHub Pages: el sitio se sirve en /<nombre-del-repo>/
  base: '/martian-map/',
  server: {
    // Los COG se piden con HTTP range requests; Vite los sirve bien en local.
    fs: { strict: false },
  },
  build: {
    chunkSizeWarningLimit: 1200,
  },
});
