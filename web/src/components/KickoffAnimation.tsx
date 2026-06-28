import { useState, useEffect } from 'react'

interface Props {
  homeName: string
  awayName: string
  onComplete: () => void
}

export default function KickoffAnimation({ homeName, awayName, onComplete }: Props) {
  const [phase, setPhase] = useState<'clash' | 'flash' | 'done'>('clash')

  useEffect(() => {
    const t1 = setTimeout(() => setPhase('flash'), 1800)
    const t2 = setTimeout(() => { setPhase('done'); onComplete() }, 2400)
    return () => { clearTimeout(t1); clearTimeout(t2) }
  }, [onComplete])

  if (phase === 'done') return null

  return (
    <div className="fixed inset-0 z-[90] bg-black/90 flex items-center justify-center">
      {phase === 'clash' && (
        <div className="flex items-center gap-4">
          <div className="animate-slideInLeft">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-accent/30 to-blue-600/20 border-2 border-accent/50 flex items-center justify-center shadow-[0_0_20px_rgba(79,195,247,0.4)]">
              <span className="text-accent font-bold text-lg">{homeName[0]}</span>
            </div>
            <p className="text-xs text-slate-300 text-center mt-2 font-medium">{homeName}</p>
          </div>
          <div className="animate-vsPopIn">
            <span className="text-4xl font-black text-gold drop-shadow-[0_0_12px_rgba(251,191,36,0.5)]">VS</span>
          </div>
          <div className="animate-slideInRight">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-red-500/30 to-red-800/20 border-2 border-red-400/50 flex items-center justify-center shadow-[0_0_20px_rgba(239,68,68,0.4)]">
              <span className="text-red-400 font-bold text-lg">{awayName[0]}</span>
            </div>
            <p className="text-xs text-slate-300 text-center mt-2 font-medium">{awayName}</p>
          </div>
        </div>
      )}
      {phase === 'flash' && (
        <div className="w-full h-full bg-white animate-flashOut" />
      )}
    </div>
  )
}
