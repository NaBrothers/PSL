import { useState, useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import api from '../api/client'
import { useNavigate } from 'react-router-dom'

interface UserStatus {
  name: string
  money: number
  level: number
}


export default function StatusHeader() {
  const [status, setStatus] = useState<UserStatus | null>(null)
  const [unread, setUnread] = useState(0)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    const token = localStorage.getItem('psl_token')
    if (!token) { setStatus(null); return }
    const fetchStatus = () => {
      api.get('/me').then(res => setStatus(res.data)).catch(() => setStatus(null))
      api.get('/inbox/unread').then(res => setUnread(res.data.count)).catch(() => {})
    }
    fetchStatus()
    window.addEventListener('psl-status-update', fetchStatus)
    return () => window.removeEventListener('psl-status-update', fetchStatus)
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
        <div className="relative cursor-pointer" onClick={() => navigate('/inbox')}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-slate-400">
            <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" /><path d="M13.73 21a2 2 0 0 1-3.46 0" />
          </svg>
          {unread > 0 && <span className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-red-500 text-[8px] text-white flex items-center justify-center">{unread > 9 ? '9+' : unread}</span>}
        </div>
      </div>
    </div>
  )
}
