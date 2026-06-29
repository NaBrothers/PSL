import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Grid3X3, List } from 'lucide-react'
import api from '../api/client'
import { overallColor, rarityBorder, STYLE_NAMES } from '@/lib/card-display'
import PlayerCard from '@/components/PlayerCard'

interface BagCard {
  id: number
  player_id: number
  name: string
  position: string
  overall: number
  star: number
  style: string
  breach: number
  locked: boolean
  status: number
  status_text: string
  top_abilities?: { name: string; value: number }[]
  can_upgrade?: boolean
  can_breach?: boolean
}

type DialogMode = 'confirm-batch-recycle' | 'confirm-batch-transfer' | null

export default function BagPage() {
  const navigate = useNavigate()
  const [cards, setCards] = useState<BagCard[]>([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [query, setQuery] = useState("")
  const [sortBy, setSortBy] = useState("overall")
  const [filterPos, setFilterPos] = useState("")
  const [filterColor, setFilterColor] = useState("")
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid")
  const [manageMode, setManageMode] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [filterUpgradable, setFilterUpgradable] = useState(false)

  const [dialogMode, setDialogMode] = useState<DialogMode>(null)
  const [opResult, setOpResult] = useState<string>("")
  const [showToast, setShowToast] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const listRef = useRef<HTMLDivElement | null>(null)
  const [batchTransferPrices, setBatchTransferPrices] = useState<Record<number, string>>({})
  const [refPrices, setRefPrices] = useState<Record<number, number>>({})

  const loadBag = async (
    p: number = page,
    q: string = query,
    s: string = sortBy,
    pos: string = filterPos,
    col: string = filterColor,
    append: boolean = false,
    upgradable: boolean = filterUpgradable,
  ) => {
    const params: any = { page: p, query: q, sort: s, position: pos, color: col, upgradable }
    const res = await api.get("/bag", { params })
    setCards(prev => (append ? [...prev, ...res.data.cards] : res.data.cards))
    setTotalPages(res.data.total_pages)
    setPage(res.data.page)
    setTotal(res.data.total)
  }

  useEffect(() => {
    loadBag(1)
  }, [])

  useEffect(() => {
    const node = listRef.current
    if (!node) return

    const onScroll = () => {
      if (loadingMore || page >= totalPages) return
      const nearBottom = node.scrollTop + node.clientHeight >= node.scrollHeight - 80
      if (!nearBottom) return
      setLoadingMore(true)
      loadBag(page + 1, query, sortBy, filterPos, filterColor, true).finally(() => {
        setLoadingMore(false)
      })
    }

    node.addEventListener("scroll", onScroll)
    return () => node.removeEventListener("scroll", onScroll)
  }, [loadingMore, page, totalPages, query, sortBy, filterPos, filterColor])

  useEffect(() => {
    if (!opResult) {
      setShowToast(false)
      return
    }
    setShowToast(true)
    const hideTimer = window.setTimeout(() => setShowToast(false), 4500)
    const clearTimer = window.setTimeout(() => setOpResult(''), 5000)
    return () => {
      window.clearTimeout(hideTimer)
      window.clearTimeout(clearTimer)
    }
  }, [opResult])

  const handleCardClick = (card: BagCard) => {
    if (manageMode) {
      const next = new Set(selected)
      next.has(card.id) ? next.delete(card.id) : next.add(card.id)
      setSelected(next)
    } else {
      sessionStorage.setItem('card_nav_ids', JSON.stringify(cards.map(c => c.id)))
      navigate(`/cards/${card.id}`)
    }
  }

  const handleBatchRecycle = async () => {
    const res = await api.post('/cards/recycle', { ids: Array.from(selected) })
    setOpResult(`回收 ${res.data.recycled.length} 张，获得 $${res.data.earned}`)
    setSelected(new Set())
    setManageMode(false)
    setDialogMode(null)
    loadBag(1)
  }

  const handleBatchTransfer = async () => {
    const prices: Record<number, string> = {}
    for (const id of Array.from(selected)) { prices[id] = '' }
    setBatchTransferPrices(prices)
    const refs: Record<number, number> = {}
    for (const id of Array.from(selected)) {
      const card = cards.find(c => c.id === id)
      if (card) {
        try {
          const res = await api.get('/transfer/reference-price', { params: { player_id: card.player_id, star: card.star } })
          if (res.data.has_data) refs[id] = res.data.price
        } catch { /* ignore */ }
      }
    }
    setRefPrices(refs)
    setDialogMode('confirm-batch-transfer')
  }

  const confirmBatchTransfer = async () => {
    const items = Object.entries(batchTransferPrices).map(([id, price]) => ({
      card_id: parseInt(id), price: parseInt(price) || 0
    }))
    const res = await api.post("/transfer/batch-list", { cards: items })
    const ok = res.data.results.filter((r: any) => r.ok).length
    const fail = res.data.results.filter((r: any) => !r.ok).length
    setOpResult(`已上架 ${ok} 张${fail > 0 ? `，${fail} 张失败` : ''}`)
    setSelected(new Set())
    setManageMode(false)
    setDialogMode(null)
    loadBag(1)
  }
  return (
    <div className="p-4 flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <h1 className="text-lg font-bold text-slate-100">背包 <span className="text-sm text-slate-500 font-normal">({total})</span></h1>
        <div className="flex gap-1">
          <Button
            variant={manageMode ? 'default' : 'outline'}
            size="sm"
            onClick={() => { setManageMode(!manageMode); setSelected(new Set()) }}
          >
            {manageMode ? '完成' : '管理'}
          </Button>
          <Button variant={viewMode === 'grid' ? 'default' : 'ghost'} size="icon" className="w-8 h-8" onClick={() => setViewMode('grid')}>
            <Grid3X3 className="w-4 h-4" />
          </Button>
          <Button variant={viewMode === 'list' ? 'default' : 'ghost'} size="icon" className="w-8 h-8" onClick={() => setViewMode('list')}>
            <List className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Search */}
      <Input
        placeholder="搜索球员..."
        value={query}
        onChange={e => { setQuery(e.target.value); loadBag(1, e.target.value, sortBy, filterPos, filterColor, false) }}
        className="mb-2"
      />
      {/* Position pill buttons + upgradable filter */}
      <div className="flex gap-1.5 mb-2 overflow-x-auto scrollbar-hide items-center">
        {[['', '全部'], ['FWD', '前锋'], ['MID', '中场'], ['DEF', '后卫'], ['GK', '门将']].map(([val, label]) => (
          <button
            key={val}
            onClick={() => { setFilterPos(val); loadBag(1, query, sortBy, val, filterColor, false) }}
            className={`px-3 py-1 rounded-full text-xs font-medium whitespace-nowrap transition-colors ${
              filterPos === val ? 'bg-gold/90 text-black' : 'bg-slate-800 text-slate-400 border border-slate-700'
            }`}
          >
            {label}
          </button>
        ))}
        <label className="flex items-center gap-1 ml-auto cursor-pointer whitespace-nowrap flex-shrink-0">
          <input type="checkbox" checked={filterUpgradable} onChange={e => { setFilterUpgradable(e.target.checked); loadBag(1, query, sortBy, filterPos, filterColor, false, e.target.checked) }}
            className="w-3.5 h-3.5 rounded border-slate-600 bg-slate-800 accent-gold" />
          <span className="text-xs text-slate-400">可强化</span>
        </label>
      </div>
      {/* Sort + Color filters */}
      <div className="flex gap-1.5 mb-3">
        <select
          value={sortBy}
          onChange={e => { setSortBy(e.target.value); loadBag(1, query, e.target.value, filterPos, filterColor, false) }}
          className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1 text-xs text-slate-300 flex-1"
        >
          <option value="overall">能力排序</option>
          <option value="name">名字排序</option>
          <option value="star">星级排序</option>
        </select>
        <select
          value={filterColor}
          onChange={e => { setFilterColor(e.target.value); loadBag(1, query, sortBy, filterPos, e.target.value, false) }}
          className="bg-slate-800 border border-slate-700 rounded-lg px-2 py-1 text-xs text-slate-300 flex-1"
        >
          <option value="">全部品质</option>
          <option value="pink">粉色 (94+)</option>
          <option value="red">红色 (92+)</option>
          <option value="orange">橙色 (89+)</option>
          <option value="purple">紫色 (87+)</option>
          <option value="blue">蓝色 (84+)</option>
          <option value="green">绿色 (82+)</option>
          <option value="white">白色</option>
        </select>
      </div>

      {/* Card list */}
      <div ref={listRef} className="flex-1 overflow-y-auto scrollbar-hide">
        {viewMode === 'grid' ? (
          <div className="grid grid-cols-3 gap-1.5 mb-3">
            {cards.map(card => (
              <div key={card.id} className="relative overflow-visible">
                {manageMode && (
                  <div className={`absolute -top-1 -left-1 z-10 w-4 h-4 rounded border ${selected.has(card.id) ? 'bg-accent border-accent' : 'border-slate-500 bg-dark-card'}`} />
                )}
                {!manageMode && card.can_upgrade && (
                  <div className="absolute -top-1 -right-1 z-10 w-3 h-3 rounded-full bg-red-500 border-2 border-[#070b16]" />
                )}
                <PlayerCard
                  playerId={card.player_id}
                  name={card.name}
                  position={card.position}
                  overall={card.overall}
                  star={card.star}
                  style={card.style}
                  breach={card.breach}
                  topAbilities={card.top_abilities}
                  size="sm"
                  selected={selected.has(card.id)}
                  badge={card.status === 2 ? '首发' : card.status === 1 ? '转会中' : card.locked ? '🔒' : undefined}
                  onClick={() => handleCardClick(card)}
                />
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-1 mb-3">
            {cards.map(card => (
              <div
                key={card.id}
                onClick={() => handleCardClick(card)}
                className={`flex items-center gap-2 p-2 rounded-lg border cursor-pointer transition-colors ${selected.has(card.id) ? 'border-accent bg-slate-800/50' : `${rarityBorder(card.overall, card.star)} bg-slate-900 hover:bg-slate-800/50`}`}
              >
                {manageMode && (
                  <div className={`w-4 h-4 rounded border flex-shrink-0 ${selected.has(card.id) ? 'bg-accent border-accent' : 'border-slate-500'}`} />
                )}
                <span className="text-slate-500 w-7 text-xs text-right">{card.id}</span>
                <span className="text-slate-400 w-8 text-xs">{card.position}</span>
                <span className="text-slate-100 flex-1 text-sm truncate">{card.name}</span>
                <span className="text-yellow-400 text-xs">{card.star <= 5 ? '★'.repeat(card.star) : `★${card.star}`}</span>
                <span className={`text-sm font-bold ${overallColor(card.overall, card.star)}`}>{card.overall}</span>
                {card.style && <span className="text-emerald-400 text-[10px]">{STYLE_NAMES[card.style] || card.style}</span>}
                {card.locked && <span className="text-xs">🔒</span>}
                {card.status === 2 && <span className="text-accent text-[10px]">首发</span>}
                {card.status === 1 && <span className="text-orange-400 text-[10px]">转会中</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      <div className="py-2" />

      {/* Batch recycle bar */}
      {manageMode && (
        <div className="flex items-center justify-between py-2 border-t border-slate-700">
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" className="text-xs" onClick={() => {
              if (selected.size === cards.length) { setSelected(new Set()) }
              else { setSelected(new Set(cards.filter(c => !c.locked && c.status === 0).map(c => c.id))) }
            }}>
              {selected.size > 0 && selected.size === cards.filter(c => !c.locked && c.status === 0).length ? '取消全选' : '全选'}
            </Button>
            <span className="text-sm text-slate-400">{selected.size > 0 ? `已选 ${selected.size} 张` : ''}</span>
          </div>
          {selected.size > 0 && (
            <div className="flex gap-2"><Button variant="destructive" size="sm" onClick={() => setDialogMode("confirm-batch-recycle")}>回收选中</Button><Button variant="secondary" size="sm" onClick={handleBatchTransfer}>批量上架</Button></div>
          )}
        </div>
      )}

      {/* Operation result toast */}
      {opResult && createPortal(
        <div
          className={`fixed top-4 left-1/2 -translate-x-1/2 bg-slate-800/95 border border-slate-600 rounded-lg px-4 py-2 text-sm text-slate-200 z-[9999] shadow-2xl backdrop-blur transition-all duration-500 ${
            showToast ? 'translate-y-0 opacity-100' : '-translate-y-6 opacity-0'
          }`}
        >
          {opResult}
        </div>,
        document.body
      )}

      {/* Confirm batch recycle */}
      <Dialog open={dialogMode === 'confirm-batch-recycle'} onOpenChange={(open) => { if (!open) setDialogMode(null) }}>
        <DialogContent>
          <DialogHeader><DialogTitle>批量回收</DialogTitle></DialogHeader>
          <p className="text-sm text-slate-300 mb-4">确定回收选中的 {selected.size} 张球员卡？此操作不可撤销。</p>
          <div className="flex gap-2">
            <Button variant="outline" className="flex-1" onClick={() => setDialogMode(null)}>取消</Button>
            <Button variant="destructive" className="flex-1" onClick={handleBatchRecycle}>确认回收</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Batch transfer confirm */}
      <Dialog open={dialogMode === "confirm-batch-transfer"} onOpenChange={(open) => { if (!open) setDialogMode(null) }}>
        <DialogContent className="max-h-[70vh] flex flex-col">
          <DialogHeader><DialogTitle>批量上架确认</DialogTitle></DialogHeader>
          <p className="text-xs text-slate-500 mb-2">留空价格将使用默认身价</p>
          <div className="overflow-y-auto scrollbar-hide flex-1 space-y-2">
            {cards.filter(c => selected.has(c.id)).map(c => (
              <div key={c.id} className="flex items-center gap-2">
                <span className="text-slate-200 text-sm flex-1 truncate">{c.name} ★{c.star} {c.overall}</span>
                <div className="flex flex-col items-end gap-0.5">
                  {refPrices[c.id] && <span className="text-[10px] text-slate-500">参考 ${refPrices[c.id].toLocaleString()}</span>}
                  <Input
                    className="w-24 h-7 text-xs"
                    placeholder={refPrices[c.id] ? `${refPrices[c.id]}` : "默认身价"}
                    value={batchTransferPrices[c.id] || ""}
                    onChange={e => setBatchTransferPrices(p => ({ ...p, [c.id]: e.target.value.replace(/\D/g, "") }))}
                  />
                </div>
              </div>
            ))}
          </div>
          <div className="flex gap-2 mt-3">
            <Button variant="outline" className="flex-1" onClick={() => setDialogMode(null)}>取消</Button>
            <Button className="flex-1" onClick={confirmBatchTransfer}>确认上架 {selected.size} 张</Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
