import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Portas exclusivas deste projeto. Nesta máquina, 5173 (Vite padrão), 8000 e 5432/5433
    // já estão ocupadas por outros projetos.
    // strictPort: se a porta estiver ocupada, FALHE — em vez de subir em outra porta em
    // silêncio e servir o app errado (foi exatamente o que aconteceu uma vez).
    port: 5273,
    strictPort: true,
    proxy: {
      // Proxy para a API (porta 8010). Evita CORS em dev.
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
