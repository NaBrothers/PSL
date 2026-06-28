import { overallColor, cardBorderColor } from '@/lib/card-display'

const FORWARD_POS = ["ST", "RW", "RS", "LW", "CF", "LS", "LF", "RF"]
const MID_POS = ["RM", "LM", "LCM", "CM", "CDM", "CAM", "RAM", "RCM", "LDM", "LAM", "RDM"]
const DEF_POS = ["RB", "CB", "LB", "RCB", "RWB", "LCB", "LWB"]

function positionColor(pos: string): string {
  if (FORWARD_POS.includes(pos)) return 'bg-red-500 text-white'
  if (MID_POS.includes(pos)) return 'bg-green-500 text-white'
  if (DEF_POS.includes(pos)) return 'bg-blue-500 text-white'
  if (pos === 'GK') return 'bg-yellow-500 text-black'
  return 'bg-slate-500 text-white'
}

function cardBgColor(_overall: number, _star?: number): string {
  return 'bg-[#20293a]'
}

interface CardInfo {
  id: number
  player_id: number
  name: string
  position: string
  overall: number
  real_overall: number
  star: number
  style: string
  breach: number
  locked: boolean
  status: number
}

interface SquadData {
  formation: string
  total_ability: number
  forward_ability: number
  midfield_ability: number
  guard_ability: number
  positions: string[]
  cards: (CardInfo | null)[]
}

interface SquadViewProps {
  squad: SquadData
  title?: string
}

const FORMATION_COORDS: Record<string, [number, number][]> = {
  "442": [[50,92],[20,72],[38,72],[62,72],[80,72],[20,48],[38,48],[62,48],[80,48],[38,22],[62,22]],
  "433": [[50,92],[20,72],[38,72],[62,72],[80,72],[30,48],[50,48],[70,48],[20,22],[50,22],[80,22]],
  "343": [[50,92],[30,72],[50,72],[70,72],[20,48],[38,48],[62,48],[80,48],[20,22],[50,22],[80,22]],
  "4231": [[50,92],[20,72],[38,72],[62,72],[80,72],[38,58],[62,58],[20,38],[80,38],[50,28],[50,12]],
  "352": [[50,92],[30,72],[50,72],[70,72],[30,52],[70,52],[15,38],[85,38],[50,32],[38,14],[62,14]],
  "532": [[50,92],[15,72],[30,72],[50,72],[70,72],[85,72],[50,52],[30,38],[70,38],[38,14],[62,14]],
  "4141": [[50,92],[20,72],[38,72],[62,72],[80,72],[50,58],[20,38],[38,38],[62,38],[80,38],[50,14]],
  "451": [[50,92],[20,72],[38,72],[62,72],[80,72],[20,44],[35,44],[50,44],[65,44],[80,44],[50,14]],
  "3421": [[50,92],[30,72],[50,72],[70,72],[20,48],[38,48],[62,48],[80,48],[35,26],[65,26],[50,10]],
  "424": [[50,92],[20,72],[38,72],[62,72],[80,72],[38,48],[62,48],[20,22],[40,22],[60,22],[80,22]],
}

export default function SquadView({ squad, title }: SquadViewProps) {
  const coords = FORMATION_COORDS[squad.formation] || FORMATION_COORDS["442"]

  return (
    <div className="max-w-md mx-auto">
      {title && (
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-sm font-bold text-slate-200">{title}</h2>
          <span className="text-xs text-slate-500">{squad.formation}</span>
        </div>
      )}

      <div className="flex gap-3 text-xs mb-2">
        <span className="text-red-400">前场 {squad.forward_ability}</span>
        <span className="text-green-400">中场 {squad.midfield_ability}</span>
        <span className="text-blue-400">后场 {squad.guard_ability}</span>
        <span className="text-yellow-400 ml-auto">总 {squad.total_ability}</span>
      </div>

      <div className="relative w-full aspect-[68/105] bg-gradient-to-b from-green-900 to-green-800 rounded-xl border border-green-700/50 overflow-hidden shadow-lg">
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-20 h-20 border border-white/15 rounded-full" />
        </div>
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-36 h-14 border-b border-l border-r border-white/15" />
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-36 h-14 border-t border-l border-r border-white/15" />
        <div className="absolute top-1/2 left-0 right-0 border-t border-white/15" />

        {squad.cards.map((card, idx) => {
          const [x, y] = coords[idx] || [50, 50]
          return (
            <div
              key={idx}
              className="absolute flex flex-col items-center -translate-x-1/2 -translate-y-1/2"
              style={{ left: `${x}%`, top: `${y}%` }}
            >
              {card ? (
                <div className="flex flex-col items-center">
                  <div className={`w-12 h-12 rounded-md overflow-hidden border-2 shadow-md ${cardBorderColor(card.overall, card.star)} ${cardBgColor(card.overall, card.star)}`}>
                    <img
                      src={`/game-assets/avatars/${card.player_id}.png`}
                      alt={card.name}
                      className="w-full h-full object-cover"
                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                    />
                  </div>
                  <div className="flex items-center gap-0.5 mt-0.5">
                    <span className={`text-[9px] font-bold px-1 rounded ${positionColor(squad.positions[idx])}`}>{squad.positions[idx]}</span>
                    <span className={`text-[10px] font-bold ${overallColor(card.overall, card.star)}`}>{card.real_overall}</span>
                  </div>
                  <span className="text-[8px] text-white/90 text-center font-medium leading-tight max-w-[60px] truncate">{card.name}</span>
                </div>
              ) : (
                <>
                  <div className="w-11 h-11 rounded-full bg-slate-700/60 border-2 border-dashed border-slate-500/60 flex items-center justify-center text-slate-400 text-sm">
                    ?
                  </div>
                  <span className="text-[9px] text-slate-500 mt-0.5">{squad.positions[idx]}</span>
                </>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

export type { SquadData, CardInfo }
