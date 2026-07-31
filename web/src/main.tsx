import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import App from '@/App.tsx'
import '@/index.css'

const root = document.getElementById('root')
if (!root) {
  // Fail loudly. A blank page on draft night is indistinguishable from a hung app.
  throw new Error('Root element #root not found in index.html')
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
