import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell } from 'lucide-react'
import api from '../api/client'

interface Message {
  id: number
  type: string
  title: string
  content: string
  read: boolean
}

export default function InboxBanner() {
  const [messages, setMessages] = useState<Message[]>([])
  const [currentIdx, setCurrentIdx] = useState(0)
  const navigate = useNavigate()

  useEffect(() => {
    api.get('/inbox?page_size=5').then(res => {
      const unread = res.data.messages.filter((m: Message) => !m.read)
      setMessages(unread)
    }).catch(() => {})
  }, [])

  useEffect(() => {
    if (messages.length <= 1) return
    const timer = setInterval(() => {
      setCurrentIdx(prev => (prev + 1) % messages.length)
    }, 3000)
    return () => clearInterval(timer)
  }, [messages.length])

  if (messages.length === 0) return null

  const msg = messages[currentIdx]

  return (
    <div
      className="flex items-center gap-2 bg-slate-800/50 border border-slate-700/50 rounded-lg px-3 py-2 cursor-pointer hover:bg-slate-700/50 transition-colors"
      onClick={() => navigate('/inbox')}
    >
      <Bell size={14} className="text-accent flex-shrink-0" />
      <span className="text-xs text-slate-300 truncate flex-1">{msg.title}</span>
      {messages.some(m => !m.read) && (
        <span className="w-4 h-4 rounded-full bg-red-500 text-[9px] text-white flex items-center justify-center flex-shrink-0">
          {messages.filter(m => !m.read).length}
        </span>
      )}
    </div>
  )
}
