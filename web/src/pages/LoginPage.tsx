import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import api from '../api/client'
import { useAuth } from '../main'

interface Player {
  id: number
  qq: number
  name: string
  has_pin: boolean
}

export default function LoginPage() {
  const [players, setPlayers] = useState<Player[]>([])
  const [selected, setSelected] = useState<Player | null>(null)
  const [pin, setPin] = useState(['', '', '', ''])
  const [error, setError] = useState('')
  const [isSetup, setIsSetup] = useState(false)
  const navigate = useNavigate()
  const { setToken } = useAuth()
  const inputRefs = useRef<(HTMLInputElement | null)[]>([])

  useEffect(() => {
    api.get('/players').then((res) => setPlayers(res.data))
  }, [])

  const handleSelect = (player: Player) => {
    setSelected(player)
    setIsSetup(!player.has_pin)
    setPin(['', '', '', ''])
    setError('')
    setTimeout(() => inputRefs.current[0]?.focus(), 50)
  }

  const handlePinChange = (index: number, value: string) => {
    if (!/^\d?$/.test(value)) return
    const next = [...pin]
    next[index] = value
    setPin(next)
    if (value && index < 3) {
      inputRefs.current[index + 1]?.focus()
    }
    if (next.every(d => d !== '')) {
      handleSubmit(next.join(''))
    }
  }

  const handleKeyDown = (index: number, e: React.KeyboardEvent) => {
    if (e.key === 'Backspace' && !pin[index] && index > 0) {
      inputRefs.current[index - 1]?.focus()
    }
  }

  const handleSubmit = async (pinStr?: string) => {
    const finalPin = pinStr || pin.join('')
    if (!selected || finalPin.length !== 4) return
    setError('')
    try {
      if (isSetup) {
        await api.post('/auth/setup-pin', { qq: selected.qq, pin: finalPin })
      }
      const res = await api.post('/auth/login', { qq: selected.qq, pin: finalPin })
      setToken(res.data.token)
      navigate('/home')
    } catch (e: any) {
      setError(e.response?.data?.detail || '登录失败')
      setPin(['', '', '', ''])
      inputRefs.current[0]?.focus()
    }
  }

  if (!selected) {
    return (
      <div className="bg-dark flex flex-col items-center justify-center p-6">
        <div className="mb-8 text-center">
          <h1 className="text-3xl font-bold text-accent tracking-wider">PSL</h1>
          <p className="text-slate-500 text-sm mt-2">选择你的账号</p>
        </div>
        <div className="w-full max-w-sm space-y-3">
          {players.map((p) => (
            <Card
              key={p.id}
              className="cursor-pointer hover:border-accent/60 transition-colors"
              onClick={() => handleSelect(p)}
            >
              <CardContent className="p-4 flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-slate-800 flex items-center justify-center text-accent font-bold text-lg">
                  {p.name[0]}
                </div>
                <div className="flex-1">
                  <p className="font-medium text-slate-100">{p.name}</p>
                  <p className="text-xs text-slate-500">ID: {p.id}</p>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="bg-dark flex flex-col items-center justify-center p-6">
      <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center text-accent font-bold text-xl mb-4">
        {selected.name[0]}
      </div>
      <h2 className="text-xl font-bold text-slate-100 mb-1">{selected.name}</h2>
      <p className="text-slate-500 text-sm mb-6">
        {isSetup ? '设置4位数字密码' : '输入密码'}
      </p>

      <div className="flex gap-3 mb-4">
        {pin.map((digit, i) => (
          <input
            key={i}
            ref={el => { inputRefs.current[i] = el }}
            type="password"
            inputMode="numeric"
            maxLength={1}
            value={digit}
            onChange={e => handlePinChange(i, e.target.value)}
            onKeyDown={e => handleKeyDown(i, e)}
            className="w-12 h-14 text-center text-xl font-bold bg-slate-800 border-2 border-slate-700 rounded-lg text-white focus:border-accent focus:outline-none transition-colors"
          />
        ))}
      </div>

      {error && <p className="text-red-400 text-sm mb-3">{error}</p>}

      <Button
        onClick={() => handleSubmit()}
        disabled={pin.some(d => d === '')}
        size="lg"
        className="w-48"
      >
        {isSetup ? '设置并登录' : '登录'}
      </Button>

      <button
        onClick={() => setSelected(null)}
        className="mt-4 text-slate-500 text-sm hover:text-slate-300 transition-colors"
      >
        ← 返回选择
      </button>
    </div>
  )
}
