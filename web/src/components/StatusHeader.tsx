import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import api from '../api/client'

interface UserStatus {
  name: string
  money: number
  level: number
}

export default function StatusHeader() {
  const [status, setStatus] = useState<UserStatus | null>(null)
  const location = useLocation()

  useEffect(() => {
    api.get('/me').then(res => setStatus(res.data)).catch(() => {})
  }, [location.pathname])

  if (!status || location.pathname === '/login') return null

  return (
    <div className="sticky top-0 z-40 h-11 bg-[#0c1222]/95 backdrop-blur-md border-b border-slate-800/50 flex items-center justify-between px-4">
      <div className="flex items-center gap-2">
        <div className="w-7 h-7 rounded-full bg-gradient-to-br from-accent/30 to-blue-600/20 border border-accent/40 flex items-center justify-center">
          <span className="text-accent text-xs font-bold">{status.name[0]}</span>
        </div>
        <span className="text-sm text-slate-200 font-medium">{status.name}</span>
      </div>
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-1">
          <span className="text-yellow-400 text-xs">$</span>
          <span className="text-xs text-slate-200 font-medium">{status.money.toLocaleString()}</span>
        </div>
      </div>
    </div>
  )
}
