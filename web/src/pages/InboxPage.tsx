import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Mail, DollarSign, Trophy, Megaphone, Gift, Check } from 'lucide-react'
import api from '../api/client'

interface Message {
  id: number
  type: string
  title: string
  content: string
  data: any
  read: boolean
  created_at: string
}

const TYPE_ICONS: Record<string, any> = {
  transfer_sold: DollarSign,
  transfer_expired: Mail,
  league_result: Trophy,
  system: Megaphone,
  reward: Gift,
}

const TYPE_COLORS: Record<string, string> = {
  transfer_sold: 'text-green-400 bg-green-400/10',
  transfer_expired: 'text-orange-400 bg-orange-400/10',
  league_result: 'text-blue-400 bg-blue-400/10',
  system: 'text-slate-400 bg-slate-400/10',
  reward: 'text-yellow-400 bg-yellow-400/10',
}

export default function InboxPage() {
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/inbox').then(res => { setMessages(res.data.messages); setLoading(false) })
  }, [])

  const markAllRead = async () => {
    await api.post('/inbox/read', {})
    setMessages(prev => prev.map(m => ({ ...m, read: true })))
  }

  const markRead = async (id: number) => {
    await api.post('/inbox/read', { message_id: id })
    setMessages(prev => prev.map(m => m.id === id ? { ...m, read: true } : m))
  }

  const formatTime = (iso: string) => {
    const d = new Date(iso)
    const now = new Date()
    const diff = now.getTime() - d.getTime()
    if (diff < 60000) return '刚刚'
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
    return `${Math.floor(diff / 86400000)}天前`
  }

  if (loading) return <div className="flex items-center justify-center h-32 text-slate-500 text-sm">加载中...</div>

  return (
    <div className="p-4">
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-lg font-bold text-slate-100">消息中心</h1>
        <div className="flex gap-2">
          {messages.some(m => !m.read) && (
            <Button variant="ghost" size="sm" className="text-xs text-slate-400" onClick={markAllRead}>
              <Check size={12} className="mr-1" />全部已读
            </Button>
          )}
          {messages.some(m => m.read) && (
            <Button variant="ghost" size="sm" className="text-xs text-red-400" onClick={async () => { await api.post('/inbox/delete-read', {}); setMessages(prev => prev.filter(m => !m.read)) }}>
              删除已读
            </Button>
          )}
        </div>
      </div>

      {messages.length === 0 ? (
        <div className="text-center py-12">
          <Mail size={40} className="text-slate-700 mx-auto mb-3" />
          <p className="text-slate-500 text-sm">暂无消息</p>
        </div>
      ) : (
        <div className="space-y-2">
          {messages.map(msg => {
            const Icon = TYPE_ICONS[msg.type] || Mail
            const colorClass = TYPE_COLORS[msg.type] || 'text-slate-400 bg-slate-400/10'
            return (
              <Card
                key={msg.id}
                className={`transition-colors ${!msg.read ? 'border-slate-600' : 'border-slate-800 opacity-60'}`}
                onClick={() => !msg.read && markRead(msg.id)}
              >
                <CardContent className="p-3 flex items-start gap-3">
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${colorClass}`}>
                    <Icon size={16} />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-medium ${!msg.read ? 'text-slate-100' : 'text-slate-400'}`}>{msg.title}</span>
                      {!msg.read && <div className="w-2 h-2 rounded-full bg-accent flex-shrink-0" />}
                    </div>
                    {msg.content && <p className="text-xs text-slate-500 mt-0.5 truncate">{msg.content}</p>}
                    <p className="text-[10px] text-slate-600 mt-1">{formatTime(msg.created_at)}</p>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}
    </div>
  )
}
