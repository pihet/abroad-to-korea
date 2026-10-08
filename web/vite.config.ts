import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// 개발 중에는 API·사진 요청을 FastAPI로 넘긴다. 주소는 web/.env 의 VITE_API_TARGET (없으면 http://localhost:8000).
// 배포는 `npm run build` 결과(web/dist)를 FastAPI가 직접 제공하므로 이 설정을 쓰지 않는다.
export default defineConfig(({ mode }) => {
  const target = loadEnv(mode, process.cwd(), 'VITE_').VITE_API_TARGET || 'http://localhost:8000'
  return {
    plugins: [react()],
    server: { proxy: { '/api': target, '/images': target } },
  }
})
