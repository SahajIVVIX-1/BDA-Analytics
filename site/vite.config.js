import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Served by GitHub Pages at https://<user>.github.io/BDA-Analytics/
export default defineConfig({
  base: '/BDA-Analytics/',
  plugins: [react()],
})
