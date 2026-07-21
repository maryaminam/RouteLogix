import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
// Self-hosted (no external CDN). Apple devices get real SF Pro via -apple-system
// in the stack; Inter is the closest match for everyone else.
import '@fontsource-variable/inter'
import App from './App.jsx'

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
