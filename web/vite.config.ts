import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// 개발 중에는 API·사진 요청을 FastAPI(8000)로 넘긴다. 배포는 `npm run build` 결과(web/dist)를 FastAPI가 직접 제공한다.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000',
      '/images': 'http://localhost:8000',
    },
  },
})
