import { createContext, useContext, useEffect, useState } from 'react'
import { createPortal } from 'react-dom'

interface ToastCtx {
  showToast: (message: string) => void
}

const ToastContext = createContext<ToastCtx>({ showToast: () => {} })

export function useToast() {
  return useContext(ToastContext)
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [message, setMessage] = useState('')
  const [visible, setVisible] = useState(false)

  const showToast = (nextMessage: string) => {
    setMessage(nextMessage)
    setVisible(true)
  }

  useEffect(() => {
    if (!message) {
      setVisible(false)
      return
    }
    setVisible(true)
    const hideTimer = window.setTimeout(() => setVisible(false), 4500)
    const clearTimer = window.setTimeout(() => setMessage(''), 5000)
    return () => {
      window.clearTimeout(hideTimer)
      window.clearTimeout(clearTimer)
    }
  }, [message])

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      {message && createPortal(
        <div
          className={`fixed top-4 left-1/2 -translate-x-1/2 bg-slate-800/95 border border-slate-600 rounded-lg px-4 py-2 text-sm text-slate-200 z-[9999] shadow-2xl backdrop-blur transition-all duration-500 ${
            visible ? 'translate-y-0 opacity-100' : '-translate-y-6 opacity-0'
          }`}
        >
          {message}
        </div>,
        document.body
      )}
    </ToastContext.Provider>
  )
}
