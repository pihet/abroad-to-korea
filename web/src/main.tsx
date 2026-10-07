import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './styles.css'
import FeedApp from './FeedApp.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <FeedApp />
  </StrictMode>,
)
