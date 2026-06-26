import { copyFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";
import { defineConfig, type Plugin } from "vite";

const currentDir = fileURLToPath(new URL(".", import.meta.url));

function copyManifest(): Plugin {
  return {
    name: "copy-extension-manifest",
    closeBundle() {
      mkdirSync(resolve(currentDir, "dist"), { recursive: true });
      copyFileSync(
        resolve(currentDir, "manifest.json"),
        resolve(currentDir, "dist", "manifest.json"),
      );
    },
  };
}

export default defineConfig({
  publicDir: "public",
  plugins: [copyManifest()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        popup: resolve(currentDir, "src/popup/popup.html"),
        upload: resolve(currentDir, "src/upload/upload.html"),
        sidepanel: resolve(currentDir, "src/sidepanel/sidepanel.html"),
        serviceWorker: resolve(currentDir, "src/background/serviceWorker.ts"),
        pageAssistant: resolve(currentDir, "src/content/pageAssistant.ts"),
      },
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name].[ext]",
      },
    },
  },
});
