import { useState, useEffect } from 'react'

interface TeamAbilities {
  total: number
  forward: number
  midfield: number
  guard: number
}

interface Props {
  homeName: string
  awayName: string
  homeAbilities?: TeamAbilities
  awayAbilities?: TeamAbilities
  onComplete: () => void
}

export default function KickoffAnimation({ homeName, awayName, homeAbilities, awayAbilities, onComplete }: Props) {
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
          <div className="animate-slideInLeft text-center">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-accent/30 to-blue-600/20 border-2 border-accent/50 flex items-center justify-center shadow-[0_0_20px_rgba(79,195,247,0.4)] mx-auto">
              <span className="text-accent font-bold text-lg">{homeName[0]}</span>
            </div>
            <p className="text-xs text-slate-300 mt-2 font-medium">{homeName}</p>
            {homeAbilities && (
              <div className="mt-3 text-[10px] space-y-1 w-20">
                <div className="text-yellow-400 font-bold text-sm">{homeAbilities.total}</div>
                <div className="flex justify-between"><span className="text-slate-500">前场</span><span className="text-red-400 font-medium">{homeAbilities.forward}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">中场</span><span className="text-green-400 font-medium">{homeAbilities.midfield}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">后场</span><span className="text-blue-400 font-medium">{homeAbilities.guard}</span></div>
              </div>
            )}
          </div>
          <div className="animate-vsPopIn">
            <span className="text-4xl font-black text-gold drop-shadow-[0_0_12px_rgba(251,191,36,0.5)]">VS</span>
          </div>
          <div className="animate-slideInRight text-center">
            <div className="w-16 h-16 rounded-full bg-gradient-to-br from-red-500/30 to-red-800/20 border-2 border-red-400/50 flex items-center justify-center shadow-[0_0_20px_rgba(239,68,68,0.4)] mx-auto">
              <span className="text-red-400 font-bold text-lg">{awayName[0]}</span>
            </div>
            <p className="text-xs text-slate-300 mt-2 font-medium">{awayName}</p>
            {awayAbilities && (
              <div className="mt-3 text-[10px] space-y-1 w-20">
                <div className="text-yellow-400 font-bold text-sm">{awayAbilities.total}</div>
                <div className="flex justify-between"><span className="text-slate-500">前场</span><span className="text-red-400 font-medium">{awayAbilities.forward}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">中场</span><span className="text-green-400 font-medium">{awayAbilities.midfield}</span></div>
                <div className="flex justify-between"><span className="text-slate-500">后场</span><span className="text-blue-400 font-medium">{awayAbilities.guard}</span></div>
              </div>
            )}
          </div>
        </div>
      )}
      {phase === 'flash' && (
        <div className="w-full h-full bg-white animate-flashOut" />
      )}
    </div>
  )
}
