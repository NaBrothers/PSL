import { useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import api from '../api/client'
import { cardBorderColor, overallColor } from '@/lib/card-display'

import CompareView from '@/components/CompareView'

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
  bench?: (CardInfo | null)[]
}

interface BagCard {
  id: number
  name: string
  position: string
  overall: number
  real_overall?: number | null
  star: number
  status: number
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

const FORMATIONS = ["442","433","343","4231","352","532","4141","451","3421","424"]

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

export default function SquadPage() {
  const navigate = useNavigate()
  const [squad, setSquad] = useState<SquadData | null>(null)
  const [selectedSlot, setSelectedSlot] = useState<number | null>(null)
  const [replaceCandidates, setReplaceCandidates] = useState<BagCard[]>([])
  const [showFormation, setShowFormation] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [compareData, setCompareData] = useState<any>(null)
  const [popupSlot, setPopupSlot] = useState<number | null>(null)
  const [benchOpen, setBenchOpen] = useState(false)

  const loadSquad = () => {
    api.get('/squad').then(res => setSquad(res.data))
  }

  useEffect(() => { loadSquad() }, [])

  const handleSlotClick = (idx: number) => {
    const card = idx < 11 ? squad?.cards[idx] : squad?.bench?.[idx - 11]
    if (!card) {
      openReplaceDialog(idx)
    } else {
      setPopupSlot(idx)
    }
  }

  const openReplaceDialog = (idx: number) => {
    setPopupSlot(null)
    setSelectedSlot(idx)
    setSearchQuery("")
    const pos = idx < 11 ? (squad?.positions[idx] || "CM") : ""
    const inSquadIds = new Set([
      ...(squad?.cards || []).filter(Boolean).map((c: any) => c.id),
      ...(squad?.bench || []).filter(Boolean).map((c: any) => c.id),
    ])
    api.get("/bag", { params: { page: 1, page_size: 500, query: "", for_position: pos } }).then(res => {
      setReplaceCandidates(res.data.cards.filter((c: BagCard) => c.status === 0 && !inSquadIds.has(c.id)))
    })
  }

  const openDetail = (idx: number) => {
    setPopupSlot(null)
    const card = idx < 11 ? squad?.cards[idx] : squad?.bench?.[idx - 11]
    if (!card) return
    navigate(`/cards/${card.id}`)
  }







  const handleReplace = async (candidateId: number) => {
    if (selectedSlot === null || !squad) return
    const currentCard = squad.cards[selectedSlot]
    if (!currentCard) {
      await api.post('/squad/assign', { slot: selectedSlot, card_id: candidateId })
    } else {
      await api.post('/squad/swap', { card_id_1: currentCard.id, card_id_2: candidateId })
    }
    setSelectedSlot(null)
    loadSquad()
  }









  const handleCompare = async (candidateId: number) => {
    if (selectedSlot === null || !squad) return
    const currentCard = squad.cards[selectedSlot]
    if (!currentCard) return
    const res = await api.get(`/cards/${currentCard.id}/compare/${candidateId}`)
    setCompareData(res.data)
  }

  const handleAutoSquad = async () => {
    const res = await api.post('/squad/auto')
    setSquad(res.data)
  }

  const handleFormationChange = async (f: string) => {
    await api.post('/squad/formation', { formation: f })
    setShowFormation(false)
    loadSquad()
  }

  if (!squad) {
    return <div className="flex items-center justify-center text-slate-500">加载中...</div>
  }

  const coords = FORMATION_COORDS[squad.formation] || FORMATION_COORDS["442"]
  const filteredCandidates = replaceCandidates.filter(c =>
    c.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <div className="p-4">
      <div className="max-w-md mx-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <h1 className="text-lg font-bold text-slate-100">阵容</h1>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setShowFormation(true)}>
              {squad.formation}
            </Button>
            <Button size="sm" onClick={handleAutoSquad}>自动排阵</Button>
          </div>
        </div>

        {/* Ability bar */}
        <div className="flex gap-3 text-xs mb-3">
          <span className="text-red-400">前场 {squad.forward_ability}</span>
          <span className="text-green-400">中场 {squad.midfield_ability}</span>
          <span className="text-blue-400">后场 {squad.guard_ability}</span>
          <span className="text-yellow-400 ml-auto">总 {squad.total_ability}</span>
        </div>

        {/* Pitch */}
        <div className="relative w-full aspect-[68/105] bg-gradient-to-b from-green-900 to-green-800 rounded-xl border border-green-700/50 overflow-hidden shadow-lg" onClick={() => setPopupSlot(null)}>
          {/* Field markings */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-20 h-20 border border-white/15 rounded-full" />
          </div>
          {/* Penalty boxes */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[60%] h-[16%] border-b border-l border-r border-white/15" />
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[60%] h-[16%] border-t border-l border-r border-white/15" />
          {/* 6-yard boxes */}
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[28%] h-[5.5%] border-b border-l border-r border-white/15" />
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[28%] h-[5.5%] border-t border-l border-r border-white/15" />
          <div className="absolute top-1/2 left-0 right-0 border-t border-white/15" />

          {/* Players */}
          {squad.cards.map((card, idx) => {
            const [x, y] = coords[idx] || [50, 50]
            const showPopup = popupSlot === idx
            return (
              <div
                key={idx}
                className="absolute flex flex-col items-center -translate-x-1/2 -translate-y-1/2 cursor-pointer group"
                style={{ left: `${x}%`, top: `${y}%`, zIndex: showPopup ? 50 : 1 }}
                onClick={(e) => { e.stopPropagation(); handleSlotClick(idx) }}
              >
                {/* Inline popup bubble */}
                {showPopup && card && (
                  <div className="absolute bottom-full mb-1 flex gap-1 bg-slate-900/95 border border-gold/30 rounded-lg px-2 py-1.5 shadow-lg whitespace-nowrap z-50" onClick={e => e.stopPropagation()}>
                    <button className="text-[10px] text-accent font-medium px-2 py-0.5 rounded hover:bg-slate-700/50" onClick={() => openDetail(idx)}>详情</button>
                    <button className="text-[10px] text-gold font-medium px-2 py-0.5 rounded hover:bg-slate-700/50" onClick={() => openReplaceDialog(idx)}>替换</button>
                  </div>
                )}
                {card ? (
                  <div className="flex flex-col items-center group-hover:scale-105 transition-transform">
                    <div className={`relative w-12 h-12 rounded-md overflow-hidden border-2 shadow-md ${cardBorderColor(card.overall, card.star)} ${cardBgColor(card.overall, card.star)}`}>
                      <img
                        src={`/game-assets/avatars/${card.player_id}.png`}
                        alt={card.name}
                        className="w-full h-full object-cover"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                      />
                      <span className="absolute top-0 left-0 text-[7px] text-yellow-400 leading-none bg-black/60 px-0.5 rounded-br">{card.star <= 5 ? '★'.repeat(card.star) : `★${card.star}`}</span>
                    </div>
                    <div className="flex items-center gap-0.5 mt-0.5">
                      <span className={`text-[9px] font-bold px-1 rounded ${positionColor(squad.positions[idx])}`}>{squad.positions[idx]}</span>
                      <span className={`text-[10px] font-bold ${overallColor(card.overall, card.star)}`}>{card.real_overall}</span>
                      {(() => { const diff = card.real_overall - card.overall; return diff !== 0 ? (
                        <span className={`text-[8px] font-bold ${diff > 0 ? "text-red-400" : "text-green-400"}`}>{diff > 0 ? "+" : ""}{diff}</span>
                      ) : null })()}
                    </div>
                    <span className="text-[8px] text-white/90 text-center font-medium leading-tight max-w-[60px] truncate">{card.name}</span>
                  </div>
                ) : (
                  <>
                    <div className="w-11 h-11 rounded-full bg-slate-700/60 border-2 border-dashed border-slate-500/60 flex items-center justify-center text-slate-400 text-sm group-hover:border-gold/60 transition-colors">
                      +
                    </div>
                    <span className="text-[9px] text-slate-500 mt-0.5">{squad.positions[idx]}</span>
                  </>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Bench - collapsible */}
      {squad?.bench && (
        <div className="max-w-md mx-auto border-t border-slate-700/50 mt-2">
          <button className="w-full flex items-center justify-between py-2 px-1" onClick={() => setBenchOpen(!benchOpen)}>
            <span className="text-xs text-slate-500 font-medium">替补席 ({squad.bench.filter(Boolean).length}/7)</span>
            <span className="text-xs text-slate-600">{benchOpen ? '收起 ▲' : '展开 ▼'}</span>
          </button>
          {benchOpen && (
          <div className="flex gap-2 overflow-x-auto scrollbar-hide pb-2">
            {squad.bench.map((card, idx) => (
              <div key={idx} className="flex-shrink-0 w-16 flex flex-col items-center cursor-pointer relative" onClick={() => handleSlotClick(11 + idx)}>
                {popupSlot === 11 + idx && card && (
                  <div className="absolute -top-8 left-1/2 -translate-x-1/2 flex gap-1 bg-slate-900/95 border border-gold/30 rounded-lg px-2 py-1.5 shadow-lg whitespace-nowrap z-[100]">
                    <button className="text-[10px] text-accent font-medium px-2 py-0.5 rounded hover:bg-slate-700/50" onClick={(e) => { e.stopPropagation(); openDetail(11 + idx) }}>详情</button>
                    <button className="text-[10px] text-gold font-medium px-2 py-0.5 rounded hover:bg-slate-700/50" onClick={(e) => { e.stopPropagation(); openReplaceDialog(11 + idx) }}>替换</button>
                  </div>
                )}
                {card ? (
                  <>
                    <div className={`relative w-12 h-12 rounded-md overflow-hidden border-2 shadow-md ${cardBorderColor(card.overall, card.star)} bg-[#20293a]`}>
                      <img src={`/game-assets/avatars/${card.player_id}.png`} alt={card.name} className="w-full h-full object-cover" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
                      <span className="absolute top-0 left-0 text-[7px] text-yellow-400 leading-none bg-black/60 px-0.5 rounded-br">{card.star <= 5 ? '\u2605'.repeat(card.star) : `\u2605${card.star}`}</span>
                    </div>
                    <span className={`text-[9px] font-bold mt-0.5 ${overallColor(card.overall, card.star)}`}>{card.real_overall}</span>
                    <span className="text-[8px] text-white/80 text-center truncate w-full">{card.name.split(' ').pop()}</span>
                  </>
                ) : (
                  <div className="w-12 h-12 rounded-md bg-slate-700/40 border-2 border-dashed border-slate-600/50 flex items-center justify-center text-slate-500 text-xs" onClick={() => openReplaceDialog(11 + idx)}>+</div>
                )}
              </div>
            ))}
          </div>
          )}
        </div>
      )}

            {/* Replace Dialog */}
      {/* Replace Dialog */}
      <Dialog open={selectedSlot !== null} onOpenChange={(open) => { if (!open) setSelectedSlot(null) }}>
        <DialogContent className="max-h-[70vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>选择替换球员</DialogTitle>
          </DialogHeader>
          <Input
            placeholder="搜索球员..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="mb-2"
          />
          <div className="overflow-y-auto scrollbar-hide flex-1 space-y-1">
            {filteredCandidates.map(c => (
              <div
                key={c.id}
                onClick={() => { const cur = squad?.cards[selectedSlot!]; cur ? handleCompare(c.id) : handleReplace(c.id) }}
                className="flex items-center gap-2 p-2 rounded-md hover:bg-slate-800 transition-colors cursor-pointer"
              >
                <span className="text-slate-500 w-8 text-xs">{c.position}</span>
                <span className="text-slate-100 flex-1 text-sm">{c.name}</span>
                <span className="text-yellow-400 text-xs">{c.star <= 5 ? '★'.repeat(c.star) : `★${c.star}`}</span>
                <div className="flex items-center gap-1">
                  <span className={`text-sm font-bold ${overallColor(c.overall, c.star)}`}>{c.real_overall ?? c.overall}</span>
                  {((c.real_overall ?? c.overall) !== c.overall) && (
                    <span className={`text-[10px] font-bold ${(c.real_overall ?? c.overall) > c.overall ? 'text-red-400' : 'text-green-400'}`}>
                      {(c.real_overall ?? c.overall) > c.overall ? '▲' : '▼'}{Math.abs((c.real_overall ?? c.overall) - c.overall)}
                    </span>
                  )}
                </div>
                <Button
                  size="sm"
                  className="h-7 px-2 text-xs"
                  onClick={(e) => {
                    e.stopPropagation()
                    handleReplace(c.id)
                  }}
                >
                  替换
                </Button>
              </div>
            ))}
            {filteredCandidates.length === 0 && (
              <p className="text-slate-500 text-center text-sm py-4">没有可用球员</p>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* Formation Dialog */}
      <Dialog open={showFormation} onOpenChange={setShowFormation}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>选择阵型</DialogTitle>
          </DialogHeader>
          <div className="grid grid-cols-2 gap-2">
            {FORMATIONS.map(f => (
              <Button
                key={f}
                variant={f === squad.formation ? "default" : "outline"}
                onClick={() => handleFormationChange(f)}
              >
                {f}
              </Button>
            ))}
          </div>
        </DialogContent>
      </Dialog>




      <CompareView data={compareData} open={compareData !== null} onClose={() => setCompareData(null)} />
    </div>
  )
}
