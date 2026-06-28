import { useState, useEffect } from 'react'
import { overallColor, cardBorderColor } from '@/lib/card-display'

interface PackCard {
  id: number
  player_id: number
  name: string
  position: string
  overall: number
  star: number
  style_name: string
  nationality: string
  club: string
}

interface Props {
  card: PackCard
  onComplete: () => void
}

type Phase = 'nationality' | 'club' | 'position' | 'reveal' | 'done'

export default function PackOpenAnimation({ card, onComplete }: Props) {
  const [phase, setPhase] = useState<Phase>('nationality')
  const [animClass, setAnimClass] = useState('animate-doorOpen')
  const [particles] = useState(() => Array.from({length: 30}, (_, i) => ({
    id: i,
    x: Math.random() * 100,
    y: Math.random() * 100,
    size: Math.random() * 3 + 1,
    duration: Math.random() * 3 + 2,
    delay: Math.random() * 2,
  })))

  useEffect(() => {
    const timers = [
      setTimeout(() => { setAnimClass('animate-fadeOut'); }, 900),
      setTimeout(() => { setPhase('club'); setAnimClass('animate-doorOpen'); }, 1200),
      setTimeout(() => { setAnimClass('animate-fadeOut'); }, 2100),
      setTimeout(() => { setPhase('position'); setAnimClass('animate-doorOpen'); }, 2400),
      setTimeout(() => { setAnimClass('animate-fadeOut'); }, 3300),
      setTimeout(() => { setPhase('reveal'); setAnimClass('animate-cardReveal'); }, 3600),
      
    ]
    return () => timers.forEach(clearTimeout)
  }, [])

  useEffect(() => {
    if (phase === 'done') onComplete()
  }, [phase, onComplete])

  const glowColor = card.star >= 5 ? 'rgba(168,85,247,0.4)' : card.star >= 4 ? 'rgba(239,68,68,0.3)' : 'rgba(251,191,36,0.3)'

  if (phase === 'done') return null

  return (
    <div className="fixed inset-0 z-[100] bg-black flex items-center justify-center" onClick={() => { if (phase === "reveal") onComplete() }}>
      {/* Particles background */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {particles.map(p => (
          <div key={p.id} className="absolute rounded-full" style={{
            left: `${p.x}%`, top: `${p.y}%`,
            width: p.size, height: p.size,
            background: glowColor,
            opacity: 0.6,
            animation: `particleFloat ${p.duration}s ease-in-out ${p.delay}s infinite alternate`,
          }} />
        ))}
      </div>

      {/* Speed streaks (warp tunnel) */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {Array.from({length: 12}).map((_, i) => (
          <div key={i} className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2" style={{
            width: 2, height: `${40 + Math.random() * 60}%`,
            background: `linear-gradient(to bottom, transparent, ${glowColor}, transparent)`,
            opacity: 0.15 + Math.random() * 0.2,
            transform: `rotate(${i * 30}deg)`,
            animation: `streakPulse ${1.5 + Math.random()}s ease-in-out ${Math.random()}s infinite`,
          }} />
        ))}
      </div>

      {/* Central glow */}
      <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
        <div className="w-48 h-48 rounded-full blur-3xl animate-pulse" style={{ background: glowColor, opacity: 0.25 }} />
      </div>

      {/* Door light seam */}
      {(phase === 'nationality' || phase === 'club' || phase === 'position') && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-[2px] h-48 bg-gradient-to-b from-transparent via-white/90 to-transparent" style={{ animation: 'doorSeam 0.6s ease-out' }} />
        </div>
      )}

      {/* Phase content */}
      {phase === 'nationality' && (
        <div className={`flex flex-col items-center gap-3 ${animClass}`}>
          <span className="text-slate-500 text-xs tracking-widest uppercase">国籍</span>
          <span className="text-3xl font-bold text-white">{card.nationality}</span>
        </div>
      )}

      {phase === 'club' && (
        <div className={`flex flex-col items-center gap-3 ${animClass}`}>
          <span className="text-slate-500 text-xs tracking-widest uppercase">俱乐部</span>
          <span className="text-2xl font-bold text-white text-center px-4">{card.club}</span>
        </div>
      )}

      {phase === 'position' && (
        <div className={`flex flex-col items-center gap-3 ${animClass}`}>
          <span className="text-slate-500 text-xs tracking-widest uppercase">位置</span>
          <span className="text-4xl font-black text-accent">{card.position.split(',')[0]}</span>
        </div>
      )}

      {phase === 'reveal' && (
        <div className={`flex flex-col items-center gap-4 ${animClass}`}>
          {/* Card */}
          <div className={`w-32 h-40 rounded-xl border-2 overflow-hidden shadow-2xl ${cardBorderColor(card.overall, card.star)} bg-[#20293a]`}
            style={{ boxShadow: `0 0 40px ${glowColor}` }}>
            <img
              src={`/game-assets/avatars/${card.player_id}.png`}
              alt={card.name}
              className="w-full h-full object-cover"
              onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
            />
          </div>
          <div className="text-center">
            <div className="text-yellow-400 text-sm mb-1">{'★'.repeat(Math.min(card.star, 5))}{card.star > 5 ? `×${card.star}` : ''}</div>
            <div className={`text-2xl font-black ${overallColor(card.overall, card.star)}`}>{card.overall}</div>
            <div className="text-white text-lg font-bold mt-1">{card.name}</div>
            <div className="text-slate-400 text-sm">{card.position.split(',')[0]} · {card.style_name}</div>
          </div>
        </div>
      )}

      {phase === "reveal" && <div className="absolute bottom-8 text-slate-400 text-xs animate-pulse">点击继续</div>}
    </div>
  )
}
