import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import api from '../api/client'
import { useToast } from '@/components/AppToast'
import { overallColor } from '@/lib/card-display'
import PlayerCardDetail from '@/components/PlayerCardDetail'

interface TransferItem {
  card_id: number
  seller_qq: number
  player_name: string
  position: string
  overall: number
  star: number
  style: string
  style_name: string
  breach: number
  seller_name: string
  cost: number
}

const POSITION_FILTERS = [
  { key: '', label: '全部' },
  { key: 'FWD', label: '前锋' },
  { key: 'MID', label: '中场' },
  { key: 'DEF', label: '后卫' },
  { key: 'GK', label: '门将' },
]

const SORT_OPTIONS = [
  { key: 'overall', label: '能力值' },
  { key: 'price_asc', label: '价格↑' },
  { key: 'price_desc', label: '价格↓' },
  { key: 'star', label: '星级' },
  { key: 'Speed', label: '速度' },
  { key: 'Finishing', label: '终结' },
  { key: 'Dribbling', label: '盘带' },
  { key: 'Defence', label: '防守' },
  { key: 'Tackling', label: '抢断' },
  { key: 'Short_Passing', label: '短传' },
]

const STYLE_OPTIONS = [
  { key: '', label: '全部特性' },
  { key: 'hunter', label: '狩猎者' }, { key: 'shadow', label: '暗影' },
  { key: 'catalyst', label: '催化剂' }, { key: 'engine', label: '发动机' },
  { key: 'sniper', label: '狙击手' }, { key: 'finisher', label: '终结者' },
  { key: 'deadeye', label: '恶魔眼' }, { key: 'hawk', label: '凤头鹰' },
  { key: 'artist', label: '艺术家' }, { key: 'maestro', label: '大师' },
  { key: 'powerhous', label: '抢球机器' }, { key: 'sentinal', label: '哨兵' },
  { key: 'anchor', label: '铁锚' }, { key: 'guardian', label: '护卫' },
  { key: 'gladiator', label: '斗士' }, { key: 'backbone', label: '骨干' },
  { key: 'marksman', label: '神枪手' }, { key: 'architect', label: '建筑师' },
  { key: 'speedster', label: '疾速魔' }, { key: 'slugger', label: '重炮手' },
]

export default function TransferPage() {
  const [items, setItems] = useState<TransferItem[]>([])
  const [me, setMe] = useState<{ qq: number } | null>(null)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [loadingMore, setLoadingMore] = useState(false)

  const [query, setQuery] = useState('')
  const [position, setPosition] = useState('')
  const [minStar, setMinStar] = useState(0)
  const [style, setStyle] = useState('')
  const [sortBy, setSortBy] = useState('overall')
  const [showFilter, setShowFilter] = useState(false)

  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<Set<number>>(new Set())

  const [detailId, setDetailId] = useState<number | null>(null)
  const [detail, setDetail] = useState<any>(null)

  const listRef = useRef<HTMLDivElement | null>(null)
  const { showToast } = useToast()

  const loadMarket = async (p: number = 1, append: boolean = false) => {
    const res = await api.get('/transfer', {
      params: { page: p, page_size: 20, query, position, min_star: minStar, style, sort_by: sortBy }
    })
    setItems(prev => (append ? [...prev, ...res.data.items] : res.data.items))
    setPage(res.data.page)
    setTotalPages(res.data.total_pages)
  }

  useEffect(() => {
    loadMarket()
    api.get('/me').then(res => setMe({ qq: res.data.qq }))
  }, [])

  useEffect(() => {
    loadMarket(1, false)
    setSelected(new Set())
  }, [query, position, minStar, style, sortBy])

  useEffect(() => {
    const node = listRef.current
    if (!node) return
    const onScroll = () => {
      if (loadingMore || page >= totalPages) return
      if (node.scrollTop + node.clientHeight >= node.scrollHeight - 80) {
        setLoadingMore(true)
        loadMarket(page + 1, true).finally(() => setLoadingMore(false))
      }
    }
    node.addEventListener('scroll', onScroll)
    return () => node.removeEventListener('scroll', onScroll)
  }, [loadingMore, page, totalPages])

  const handleBuy = async (cardId: number) => {
    try {
      const res = await api.post('/transfer/buy', { card_id: cardId })
      if (res.data.cancelled) {
        showToast('已下架')
      } else {
        showToast(`购买成功，花费 $${res.data.cost}`)
      }
      loadMarket(1, false)
    } catch (e: any) {
      showToast(e.response?.data?.detail || '操作失败')
    }
  }

  const handleBatchBuy = async () => {
    if (selected.size === 0) return
    const ids = Array.from(selected)
    const res = await api.post('/transfer/batch-buy', { card_ids: ids })
    const ok = res.data.results.filter((r: any) => r.ok).length
    const fail = res.data.results.filter((r: any) => !r.ok).length
    showToast(`批量购买：成功 ${ok} 张${fail > 0 ? `，失败 ${fail} 张` : ''}`)
    setSelected(new Set())
    setSelectMode(false)
    loadMarket(1, false)
  }

  const toggleSelect = (cardId: number) => {
    setSelected(prev => {
      const next = new Set(prev)
      if (next.has(cardId)) next.delete(cardId)
      else next.add(cardId)
      return next
    })
  }

  const openDetail = async (cardId: number) => {
    if (selectMode) { toggleSelect(cardId); return }
    setDetailId(cardId)
    try {
      const res = await api.get(`/cards/${cardId}`)
      setDetail(res.data)
    } catch { setDetail(null) }
  }

  const activeFilters = [
    position && POSITION_FILTERS.find(p => p.key === position)?.label,
    minStar > 0 && `≥${minStar}星`,
    style && STYLE_OPTIONS.find(s => s.key === style)?.label,
  ].filter(Boolean)

  const totalCost = items.filter(i => selected.has(i.card_id)).reduce((s, i) => s + i.cost, 0)

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="p-3 space-y-2">
        <div className="flex items-center gap-2">
          <Input
            placeholder="搜索球员名..."
            value={query}
            onChange={e => setQuery(e.target.value)}
            className="flex-1 h-9"
          />
          <Button size="sm" variant="outline" className="h-9 px-3" onClick={() => setShowFilter(!showFilter)}>
            筛选
          </Button>
          <Button
            size="sm"
            variant={selectMode ? 'default' : 'outline'}
            className="h-9 px-3"
            onClick={() => { setSelectMode(!selectMode); setSelected(new Set()) }}
          >
            多选
          </Button>
        </div>

        {activeFilters.length > 0 && (
          <div className="flex gap-1 flex-wrap">
            {activeFilters.map((f, i) => (
              <span key={i} className="bg-slate-700 text-slate-300 text-xs px-2 py-0.5 rounded-full">{f}</span>
            ))}
            <button className="text-xs text-slate-500 underline ml-1" onClick={() => { setPosition(''); setMinStar(0); setStyle('') }}>
              清除
            </button>
          </div>
        )}
      </div>

      {/* List */}
      <div ref={listRef} className="flex-1 overflow-y-auto scrollbar-hide px-3 space-y-2 pb-20">
        {items.length === 0 ? (
          <div className="text-center py-12"><p className="text-slate-500">暂无球员在售</p></div>
        ) : items.map(item => {
          const isMine = me?.qq === item.seller_qq
          const isSelected = selected.has(item.card_id)
          return (
            <Card
              key={item.card_id}
              className={`transition-colors cursor-pointer ${isSelected ? 'border-blue-500 bg-blue-950/20' : 'hover:border-slate-600'}`}
              onClick={() => openDetail(item.card_id)}
            >
              <CardContent className="p-3 flex items-center gap-3">
                {selectMode && !isMine && (
                  <div className={`w-5 h-5 rounded border-2 flex items-center justify-center flex-shrink-0 ${isSelected ? 'bg-blue-500 border-blue-500' : 'border-slate-600'}`}>
                    {isSelected && <span className="text-white text-xs">✓</span>}
                  </div>
                )}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`font-medium text-sm truncate ${overallColor(item.overall)}`}>{item.player_name}</span>
                    <span className="text-yellow-400 text-xs flex-shrink-0">{'★'.repeat(Math.min(item.star, 5))}{item.star > 5 ? `×${item.star}` : ''}</span>
                  </div>
                  <div className="text-xs text-slate-500 truncate">
                    {item.position} · {item.overall} · {item.style_name}{item.breach > 0 ? ` · ◆+${item.breach}` : ''} · {item.seller_name}
                  </div>
                </div>
                <div className="text-right flex-shrink-0">
                  <div className="text-yellow-400 font-bold text-sm">${item.cost.toLocaleString()}</div>
                  {!selectMode && (
                    <Button
                      size="sm"
                      className="mt-1 h-6 text-xs px-2"
                      variant={isMine ? 'outline' : 'default'}
                      onClick={(e) => { e.stopPropagation(); handleBuy(item.card_id) }}
                    >
                      {isMine ? '下架' : '购买'}
                    </Button>
                  )}
                </div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* Batch buy bar */}
      {selectMode && selected.size > 0 && (
        <div className="fixed bottom-16 left-0 right-0 mx-auto max-w-[430px] p-3 bg-slate-900/95 border-t border-slate-700">
          <Button className="w-full" onClick={handleBatchBuy}>
            购买 {selected.size} 张 · 总计 ${totalCost.toLocaleString()}
          </Button>
        </div>
      )}

      {/* Filter bottom sheet */}
      <Dialog open={showFilter} onOpenChange={setShowFilter}>
        <DialogContent className="max-h-[60vh] flex flex-col">
          <DialogHeader><DialogTitle>筛选与排序</DialogTitle></DialogHeader>
          <div className="space-y-4 overflow-y-auto flex-1">
            <div>
              <p className="text-xs text-slate-500 mb-2">位置</p>
              <div className="flex flex-wrap gap-2">
                {POSITION_FILTERS.map(p => (
                  <button key={p.key}
                    className={`px-3 py-1 rounded-full text-xs ${position === p.key ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}
                    onClick={() => setPosition(p.key)}
                  >{p.label}</button>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs text-slate-500 mb-2">最低星级</p>
              <div className="flex flex-wrap gap-2">
                {[0, 3, 5, 7, 9].map(s => (
                  <button key={s}
                    className={`px-3 py-1 rounded-full text-xs ${minStar === s ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}
                    onClick={() => setMinStar(s)}
                  >{s === 0 ? '不限' : `≥${s}★`}</button>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs text-slate-500 mb-2">特性</p>
              <select value={style} onChange={e => setStyle(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200">
                {STYLE_OPTIONS.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
            </div>
            <div>
              <p className="text-xs text-slate-500 mb-2">排序</p>
              <select value={sortBy} onChange={e => setSortBy(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200">
                {SORT_OPTIONS.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
            </div>
          </div>
          <Button className="mt-3" onClick={() => setShowFilter(false)}>确认</Button>
        </DialogContent>
      </Dialog>

      {/* Card detail dialog */}
      <Dialog open={detailId !== null} onOpenChange={(open) => { if (!open) { setDetailId(null); setDetail(null) } }}>
        <DialogContent className="max-h-[70vh] overflow-y-auto">
          <DialogHeader><DialogTitle>球员详情</DialogTitle></DialogHeader>
          <PlayerCardDetail detail={detail} />
        </DialogContent>
      </Dialog>
    </div>
  )
}
