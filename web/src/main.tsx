import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import App from './App.tsx'
import FeedApp from './FeedApp.tsx'

// 메인은 인스타그램형 화면. 예전 단계형 화면은 #classic 으로 연다 (비교·시연용)
const Root = window.location.hash.startsWith('#classic') ? App : FeedApp

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
