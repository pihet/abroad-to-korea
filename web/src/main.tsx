import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import App from './App.tsx'
import FeedApp from './FeedApp.tsx'

// #feed 로 열면 인스타그램형 디자인 시안 (기존 화면은 그대로)
const Root = window.location.hash.startsWith('#feed') ? FeedApp : App

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Root />
  </StrictMode>,
)
