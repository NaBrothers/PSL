import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Grid3X3, List } from 'lucide-react'
import api from '../api/client'
import { abilityColor, overallColor, rarityBg, rarityBorder } from '@/lib/card-display'
import PlayerCardDetail from '@/components/PlayerCardDetail'

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
}

type DialogMode = 'detail' | 'upgrade' | 'breach' | 'compare-select' | 'compare-view' | 'confirm-recycle' | 'confirm-batch-recycle' | 'confirm-batch-transfer' | null

export default function BagPage() {
  const [cards, setCards] = useState<BagCard[]>([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [total, setTotal] = useState(0)
  const [compareData, setCompareData] = useState<any>(null)
  const [query, setQuery] = useState("")
  const [sortBy, setSortBy] = useState("overall")
  const [filterPos, setFilterPos] = useState("")
  const [filterColor, setFilterColor] = useState("")
  const [viewMode, setViewMode] = useState<"grid" | "list">("grid")
  const [manageMode, setManageMode] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [detail, setDetail] = useState<any>(null)
  const [dialogMode, setDialogMode] = useState<DialogMode>(null)
  const [subCards, setSubCards] = useState<any[]>([])
  const [opResult, setOpResult] = useState<string>("")
  const [showToast, setShowToast] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const listRef = useRef<HTMLDivElement | null>(null)
  const [batchTransferPrices, setBatchTransferPrices] = useState<Record<number, string>>({})

  const loadBag = async (
    p: number = page,
    q: string = query,
    s: string = sortBy,
    pos: string = filterPos,
    col: string = filterColor,
    append: boolean = false,
  ) => {
    const res = await api.get("/bag", { params: { page: p, query: q, sort: s, position: pos, color: col } })
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
      api.get(`/cards/${card.id}`).then(res => {
        setDetail(res.data)
        setDialogMode('detail')
        setOpResult('')
      })
    }
  }

  const handleLock = async () => {
    if (!detail) return
    const res = await api.post(`/cards/${detail.id}/lock`)
    setDetail({ ...detail, locked: res.data.locked })
    loadBag()
  }

  const handleRecycleSingle = async () => {
    if (!detail) return
    const res = await api.post('/cards/recycle', { ids: [detail.id] })
    setOpResult(`回收成功！获得 $${res.data.earned}`)
    setDialogMode(null)
    setDetail(null)
    loadBag()
  }

  const handleBatchRecycle = async () => {
    const res = await api.post('/cards/recycle', { ids: Array.from(selected) })
    setOpResult(`回收 ${res.data.recycled.length} 张，获得 $${res.data.earned}`)
    setSelected(new Set())
    setManageMode(false)
    setDialogMode(null)
    loadBag()
  }

  const handleBatchTransfer = () => {
    const prices: Record<number, string> = {}
    for (const id of Array.from(selected)) { prices[id] = '' }
    setBatchTransferPrices(prices)
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
    loadBag()
  }

  const openUpgrade = () => {
    if (!detail) return
    api.get('/bag', { params: { page: 1, query: detail.name } }).then(res => {
      const subs = res.data.cards.filter((c: BagCard) => c.id !== detail.id && c.name === detail.name)
      setSubCards(subs)
      setDialogMode('upgrade')
    })
  }

  const openBreach = () => {
    if (!detail) return
    api.get('/bag', { params: { page: 1, query: detail.name } }).then(res => {
      const subs = res.data.cards.filter((c: BagCard) => c.id !== detail.id && c.name === detail.name)
      setSubCards(subs)
      setDialogMode('breach')
    })
  }

  const doUpgrade = async (subId: number) => {
    try {
      const res = await api.post("/cards/upgrade", { main_id: detail.id, sub_id: subId })
      setOpResult(`强化成功！新星级: ${"★".repeat(res.data.new_star)}`)
      loadBag()
      const newDetail = await api.get(`/cards/${detail.id}`)
      setDetail(newDetail.data)
      setDialogMode("detail")
    } catch (e: any) {
      setOpResult(e.response?.data?.detail || "强化失败")
      setDialogMode("detail")
    }
  }

  const doBreach = async (subId: number) => {
    try {
      const res = await api.post("/cards/breach", { main_id: detail.id, sub_id: subId })
      setOpResult(`突破成功！「${res.data.boosted_ability}」+${res.data.boost_amount}${res.data.style_bonus ? " (风格加成!)" : ""}`)
      loadBag()
      const newDetail = await api.get(`/cards/${detail.id}`)
      setDetail(newDetail.data)
      setDialogMode("detail")
    } catch (e: any) {
      setOpResult(e.response?.data?.detail || "突破失败")
      setDialogMode("detail")
    }
  }


  const openCompare = () => {
    if (!detail) return
    api.get("/bag", { params: { page: 1, query: "", sort: "overall", position: "", color: "", for_position: detail.position } }).then(r => {
      setSubCards(r.data.cards.filter((c: BagCard) => c.id !== detail.id))
    })
    setDialogMode("compare-select")
  }

  const doCompare = async (otherId: number) => {
    const res = await api.get(`/cards/${detail.id}/compare/${otherId}`)
    setCompareData(res.data)
    setDialogMode("compare-view")
  }
  return (
    <div className="bg-dark p-4 flex flex-col h-full">
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

      {/* Search + Filter */}
      <Input
        placeholder="搜索球员..."
        value={query}
        onChange={e => { setQuery(e.target.value); loadBag(1, e.target.value, sortBy, filterPos, filterColor, false) }}
        className="mb-2"
      />
      <div className="flex gap-1 mb-3 flex-wrap">
        {/* Sort */}
        <select
          value={sortBy}
          onChange={e => { setSortBy(e.target.value); loadBag(1, query, e.target.value, filterPos, filterColor, false) }}
          className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-300"
        >
          <option value="overall">能力排序</option>
          <option value="name">名字排序</option>
          <option value="star">星级排序</option>
        </select>
        {/* Position filter */}
        <select
          value={filterPos}
          onChange={e => { setFilterPos(e.target.value); loadBag(1, query, sortBy, e.target.value, filterColor, false) }}
          className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-300"
        >
          <option value="">全部位置</option>
          <option value="GK">门将</option>
          <option value="DEF">后卫</option>
          <option value="MID">中场</option>
          <option value="FWD">前锋</option>
        </select>
        {/* Color filter */}
        <select
          value={filterColor}
          onChange={e => { setFilterColor(e.target.value); loadBag(1, query, sortBy, filterPos, e.target.value, false) }}
          className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-300"
        >
          <option value="">全部颜色</option>
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
          <div className="grid grid-cols-3 gap-2 mb-3">
            {cards.map(card => (
              <div
                key={card.id}
                onClick={() => handleCardClick(card)}
                className={`relative rounded-lg border-2 p-2 text-center cursor-pointer transition-all ${rarityBorder(card.overall)} ${rarityBg(card.overall)} ${selected.has(card.id) ? 'ring-2 ring-accent scale-95' : 'hover:scale-105'}`}
              >
                {manageMode && (
                  <div className={`absolute top-1 left-1 w-4 h-4 rounded border ${selected.has(card.id) ? 'bg-accent border-accent' : 'border-slate-500'}`} />
                )}
                <div className="text-[10px] text-slate-500 absolute top-1 right-1">{card.position}</div>
                {card.locked && <div className="absolute bottom-1 right-1 text-[10px]">🔒</div>}
                {card.status === 2 && <div className="absolute bottom-1 left-1 text-[8px] text-accent font-bold">首发</div>}
                {card.status === 1 && <div className="absolute bottom-1 left-1 text-[8px] text-orange-400 font-bold">转会中</div>}
                <div className={`text-xl font-bold mt-3 ${overallColor(card.overall)}`}>{card.overall}</div>
                <div className="text-[10px] text-slate-300 truncate mt-0.5">{card.name}</div>
                <div className="text-[9px] text-yellow-400 mt-0.5">{'★'.repeat(Math.min(card.star, 5))}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-1 mb-3">
            {cards.map(card => (
              <div
                key={card.id}
                onClick={() => handleCardClick(card)}
                className={`flex items-center gap-2 p-2 rounded-lg border cursor-pointer transition-colors ${selected.has(card.id) ? 'border-accent bg-slate-800/50' : `${rarityBorder(card.overall)} bg-slate-900 hover:bg-slate-800/50`}`}
              >
                {manageMode && (
                  <div className={`w-4 h-4 rounded border flex-shrink-0 ${selected.has(card.id) ? 'bg-accent border-accent' : 'border-slate-500'}`} />
                )}
                <span className="text-slate-500 w-7 text-xs text-right">{card.id}</span>
                <span className="text-slate-400 w-8 text-xs">{card.position}</span>
                <span className="text-slate-100 flex-1 text-sm truncate">{card.name}</span>
                <span className="text-yellow-400 text-xs">{'★'.repeat(card.star)}</span>
                <span className={`text-sm font-bold ${overallColor(card.overall)}`}>{card.overall}</span>
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
      {manageMode && selected.size > 0 && (
        <div className="flex items-center justify-between py-2 border-t border-slate-700">
          <span className="text-sm text-slate-300">已选 {selected.size} 张</span>
          <div className="flex gap-2"><Button variant="destructive" size="sm" onClick={() => setDialogMode("confirm-batch-recycle")}>回收选中</Button><Button variant="secondary" size="sm" onClick={handleBatchTransfer}>批量上架</Button></div>
        </div>
      )}

      {/* Operation result toast */}
      {opResult && (
        <div
          className={`fixed top-4 left-1/2 -translate-x-1/2 bg-slate-800/95 border border-slate-600 rounded-lg px-4 py-2 text-sm text-slate-200 z-[120] shadow-2xl backdrop-blur transition-all duration-500 ${
            showToast ? 'translate-y-0 opacity-100' : '-translate-y-6 opacity-0'
          }`}
        >
          {opResult}
        </div>
      )}

      {/* Detail Dialog */}
      <Dialog open={dialogMode === 'detail'} onOpenChange={(open) => { if (!open) { setDialogMode(null); setDetail(null) } }}>
        <DialogContent className="max-h-[85vh] overflow-y-auto scrollbar-hide">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 flex-wrap">
              <span className="text-slate-500 text-sm">[{detail?.id}]</span>
              <span className="text-slate-400 text-sm">{detail?.position}</span>
              <span className={overallColor(detail?.overall || 0)}>{detail?.name}</span>
              <span className={`font-bold ${overallColor(detail?.overall || 0)}`}>{detail?.overall}</span>
            </DialogTitle>
          </DialogHeader>
          {detail && (
            <div className="space-y-3">
              <PlayerCardDetail detail={detail} />
              <div className="border-t border-slate-700 pt-3 grid grid-cols-5 gap-2">
                <Button variant="outline" size="sm" onClick={handleLock}>
                  {detail.locked ? '解锁' : '锁定'}
                </Button>
                <Button variant="secondary" size="sm" onClick={openUpgrade}>强化</Button>
                <Button variant="secondary" size="sm" onClick={openBreach}>突破</Button>
                <Button variant="destructive" size="sm" onClick={() => setDialogMode('confirm-recycle')}>回收</Button>
                <Button variant="outline" size="sm" onClick={openCompare}>比较</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Upgrade Dialog */}
      <Dialog open={dialogMode === 'upgrade'} onOpenChange={(open) => { if (!open) setDialogMode('detail') }}>
        <DialogContent>
          <DialogHeader><DialogTitle>选择副卡（强化）</DialogTitle></DialogHeader>
          <p className="text-xs text-slate-500 mb-2">选择同球员的副卡，星级+1</p>
          {subCards.length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-4">没有可用的同球员副卡</p>
          ) : (
            <div className="space-y-1 max-h-60 overflow-y-auto scrollbar-hide">
              {subCards.map((c: BagCard) => (
                <div key={c.id} onClick={() => doUpgrade(c.id)} className="flex items-center gap-2 p-2 rounded-md hover:bg-slate-800 cursor-pointer">
                  <span className="text-slate-500 text-xs">[{c.id}]</span>
                  <span className="text-slate-200 text-sm flex-1">{c.name}</span>
                  <span className="text-yellow-400 text-xs">{'★'.repeat(c.star)}</span>
                  <span className={`text-sm font-bold ${overallColor(c.overall)}`}>{c.overall}</span>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Breach Dialog */}
      <Dialog open={dialogMode === 'breach'} onOpenChange={(open) => { if (!open) setDialogMode('detail') }}>
        <DialogContent>
          <DialogHeader><DialogTitle>选择副卡（突破）</DialogTitle></DialogHeader>
          <p className="text-xs text-slate-500 mb-2">选择同球员的副卡，随机提升一项能力</p>
          {subCards.length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-4">没有可用的同球员副卡</p>
          ) : (
            <div className="space-y-1 max-h-60 overflow-y-auto scrollbar-hide">
              {subCards.map((c: BagCard) => (
                <div key={c.id} onClick={() => doBreach(c.id)} className="flex items-center gap-2 p-2 rounded-md hover:bg-slate-800 cursor-pointer">
                  <span className="text-slate-500 text-xs">[{c.id}]</span>
                  <span className="text-slate-200 text-sm flex-1">{c.name}</span>
                  <span className="text-yellow-400 text-xs">{'★'.repeat(c.star)}</span>
                  <span className={`text-sm font-bold ${overallColor(c.overall)}`}>{c.overall}</span>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Confirm single recycle */}
      <Dialog open={dialogMode === 'confirm-recycle'} onOpenChange={(open) => { if (!open) setDialogMode('detail') }}>
        <DialogContent>
          <DialogHeader><DialogTitle>确认回收</DialogTitle></DialogHeader>
          <p className="text-sm text-slate-300 mb-4">确定回收 [{detail?.id}] {detail?.name}？此操作不可撤销。</p>
          <div className="flex gap-2">
            <Button variant="outline" className="flex-1" onClick={() => setDialogMode('detail')}>取消</Button>
            <Button variant="destructive" className="flex-1" onClick={handleRecycleSingle}>确认回收</Button>
          </div>
        </DialogContent>
      </Dialog>

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
                <Input
                  className="w-24 h-7 text-xs"
                  placeholder="默认身价"
                  value={batchTransferPrices[c.id] || ""}
                  onChange={e => setBatchTransferPrices(p => ({ ...p, [c.id]: e.target.value.replace(/\D/g, "") }))}
                />
              </div>
            ))}
          </div>
          <div className="flex gap-2 mt-3">
            <Button variant="outline" className="flex-1" onClick={() => setDialogMode(null)}>取消</Button>
            <Button className="flex-1" onClick={confirmBatchTransfer}>确认上架 {selected.size} 张</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Compare select */}
      <Dialog open={dialogMode === "compare-select"} onOpenChange={(open) => { if (!open) setDialogMode("detail") }}>
        <DialogContent>
          <DialogHeader><DialogTitle>选择对比球员</DialogTitle></DialogHeader>
          <Input placeholder="搜索球员..." className="mb-2" onChange={e => {
            const q = e.target.value
            if (q.length > 0) {
              api.get("/bag", { params: { page: 1, query: q } }).then(r => setSubCards(r.data.cards.filter((c: BagCard) => c.id !== detail?.id)))
            } else if (detail) {
              api.get("/bag", { params: { page: 1, query: "", sort: "overall", position: "", color: "", for_position: detail.position } }).then(r => {
                setSubCards(r.data.cards.filter((c: BagCard) => c.id !== detail.id))
              })
            }
          }} />
          <div className="space-y-1 max-h-60 overflow-y-auto scrollbar-hide">
            {subCards.map((c: BagCard) => (
              <div key={c.id} onClick={() => doCompare(c.id)} className="flex items-center gap-2 p-2 rounded-md hover:bg-slate-800 cursor-pointer">
                <span className="text-slate-500 text-xs">[{c.id}]</span>
                <span className="text-slate-400 text-xs">{c.position}</span>
                <span className="text-slate-200 text-sm flex-1">{c.name}</span>
                <span className="text-yellow-400 text-xs">{"★".repeat(c.star)}</span>
                <span className={`text-sm font-bold ${overallColor(c.overall)}`}>{c.overall}</span>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* Compare view */}
      <Dialog open={dialogMode === "compare-view"} onOpenChange={(open) => { if (!open) { setDialogMode("detail"); setCompareData(null) } }}>
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
                    <span className={`text-right font-bold ${abilityColor(v1)}`}>{v1}</span>
                    <span className="text-right text-green-400">{leftAdv > 0 ? `+${leftAdv}` : ""}</span>
                    <div className="flex-1 flex items-center gap-1">
                      <div className="flex-1 h-1.5 bg-slate-800 rounded overflow-hidden flex justify-end"><div className="bg-accent/70 h-full" style={{width: `${Math.min(v1, 120) / 1.2}%`}} /></div>
                    </div>
                    <span className="text-slate-500 text-center">{ab.name}</span>
                    <div className="flex-1 h-1.5 bg-slate-800 rounded overflow-hidden"><div className="bg-red-400/70 h-full" style={{width: `${Math.min(v2, 120) / 1.2}%`}} /></div>
                    <span className="text-green-400">{rightAdv > 0 ? `+${rightAdv}` : ""}</span>
                    <span className={`font-bold ${abilityColor(v2)}`}>{v2}</span>
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
