import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import api from '../api/client'
import { cardTone, overallColor } from '@/lib/card-display'

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

export default function SquadPage() {
  const [squad, setSquad] = useState<SquadData | null>(null)
  const [selectedSlot, setSelectedSlot] = useState<number | null>(null)
  const [replaceCandidates, setReplaceCandidates] = useState<BagCard[]>([])
  const [showFormation, setShowFormation] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [compareData, setCompareData] = useState<any>(null)

  const loadSquad = () => {
    api.get('/squad').then(res => setSquad(res.data))
  }

  useEffect(() => { loadSquad() }, [])

  const handleSlotClick = (idx: number) => {
    setSelectedSlot(idx)
    setSearchQuery("")
    const pos = squad?.positions[idx] || "CM"
    api.get("/bag", { params: { page: 1, query: "", for_position: pos } }).then(res => {
      setReplaceCandidates(res.data.cards.filter((c: BagCard) => c.status === 0))
    })
  }

  const handleReplace = async (candidateId: number) => {
    if (selectedSlot === null || !squad) return
    const currentCard = squad.cards[selectedSlot]
    if (!currentCard) return
    await api.post('/squad/swap', { card_id_1: currentCard.id, card_id_2: candidateId })
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
    return <div className="bg-dark flex items-center justify-center text-slate-500">加载中...</div>
  }

  const coords = FORMATION_COORDS[squad.formation] || FORMATION_COORDS["442"]
  const filteredCandidates = replaceCandidates.filter(c =>
    c.name.toLowerCase().includes(searchQuery.toLowerCase())
  )

  return (
    <div className="bg-dark p-4">
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
        <div className="relative w-full aspect-[68/105] bg-gradient-to-b from-green-900 to-green-800 rounded-xl border border-green-700/50 overflow-hidden shadow-lg">
          {/* Field markings */}
          <div className="absolute inset-0 flex items-center justify-center">
            <div className="w-20 h-20 border border-white/15 rounded-full" />
          </div>
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-36 h-14 border-b border-l border-r border-white/15" />
          <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-36 h-14 border-t border-l border-r border-white/15" />
          <div className="absolute top-1/2 left-0 right-0 border-t border-white/15" />

          {/* Players */}
          {squad.cards.map((card, idx) => {
            const [x, y] = coords[idx] || [50, 50]
            return (
              <div
                key={idx}
                className="absolute flex flex-col items-center -translate-x-1/2 -translate-y-1/2 cursor-pointer group"
                style={{ left: `${x}%`, top: `${y}%` }}
                onClick={() => handleSlotClick(idx)}
              >
                {card ? (
                  <>
                    <div className="flex items-center gap-0.5">
                      <div className={`w-9 h-9 rounded-full border-2 border-white/80 flex items-center justify-center text-[11px] font-bold text-white shadow-md group-hover:scale-110 transition-transform ${cardTone(card.overall)}`}>
                        {card.real_overall}
                      </div>
                      {(() => { const diff = card.real_overall - card.overall; return diff !== 0 ? (
                        <span className={`text-[7px] font-bold leading-none ${diff > 0 ? "text-red-400" : "text-green-400"}`}>{diff > 0 ? "▲" : "▼"}{Math.abs(diff)}</span>
                      ) : null })()}
                    </div>
                    <span className={`text-[9px] mt-0.5 font-medium truncate max-w-[56px] text-center ${overallColor(card.overall)}`}>
                      {card.name}
                    </span>
                    <span className="text-[8px] text-yellow-400">{'★'.repeat(Math.min(card.star, 5))}{card.star > 5 ? `+${card.star-5}` : ''}</span>
                  </>
                ) : (
                  <>
                    <div className="w-9 h-9 rounded-full bg-slate-700/80 border-2 border-dashed border-slate-500 flex items-center justify-center text-slate-400 text-xs group-hover:border-accent transition-colors">
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
          <div className="overflow-y-auto flex-1 space-y-1">
            {filteredCandidates.map(c => (
              <div
                key={c.id}
                onClick={() => handleCompare(c.id)}
                className="flex items-center gap-2 p-2 rounded-md hover:bg-slate-800 transition-colors cursor-pointer"
              >
                <span className="text-slate-500 w-8 text-xs">{c.position}</span>
                <span className="text-slate-100 flex-1 text-sm">{c.name}</span>
                <span className="text-yellow-400 text-xs">{'★'.repeat(c.star)}</span>
                <div className="flex items-center gap-1">
                  <span className={`text-sm font-bold ${overallColor(c.overall)}`}>{c.real_overall ?? c.overall}</span>
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

      {/* Compare view */}
      <Dialog open={compareData !== null} onOpenChange={(open) => { if (!open) setCompareData(null) }}>
        <DialogContent className="max-h-[85vh] overflow-y-auto scrollbar-hide">
          <DialogHeader><DialogTitle>能力对比</DialogTitle></DialogHeader>
          {compareData && (
            <div className="space-y-2">
              <div className="flex justify-between text-sm font-bold mb-2">
                <span className={overallColor(compareData.card1.overall)}>{compareData.card1.name} {compareData.card1.overall}</span>
                <span className={overallColor(compareData.card2.overall)}>{compareData.card2.name} {compareData.card2.overall}</span>
              </div>
              {compareData.card1.abilities && Object.entries(compareData.card1.abilities as Record<string, {value: number; name: string}>).map(([key, ab]) => {
                const v1 = ab.value
                const v2 = (compareData.card2.abilities as any)[key]?.value || 0
                const leftAdv = Math.max(0, v1 - v2)
                const rightAdv = Math.max(0, v2 - v1)
                return (
                  <div key={key} className="grid grid-cols-[28px_24px_1fr_40px_1fr_24px_28px] items-center gap-1 text-xs">
                    <span className={`text-right font-bold ${overallColor(v1)}`}>{v1}</span>
                    <span className="text-right text-green-400">{leftAdv > 0 ? `+${leftAdv}` : ""}</span>
                    <div className="flex-1 flex items-center gap-1">
                      <div className="flex-1 h-1.5 bg-slate-800 rounded overflow-hidden flex justify-end"><div className="bg-accent/70 h-full" style={{width: `${Math.min(v1, 120) / 1.2}%`}} /></div>
                    </div>
                    <span className="text-slate-500 text-center">{ab.name}</span>
                    <div className="flex-1 h-1.5 bg-slate-800 rounded overflow-hidden"><div className="bg-red-400/70 h-full" style={{width: `${Math.min(v2, 120) / 1.2}%`}} /></div>
                    <span className="text-green-400">{rightAdv > 0 ? `+${rightAdv}` : ""}</span>
                    <span className={`font-bold ${overallColor(v2)}`}>{v2}</span>
                  </div>
                )
              })}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
