import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import ErrorBoundary from './components/ErrorBoundary'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary fallback={<div className="p-6 text-gray-600">应用加载失败，请重启。</div>}>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
)
