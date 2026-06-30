import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import api from '../api/client'
import { useToast } from '@/components/AppToast'
import { overallColor, STYLE_NAMES } from '@/lib/card-display'

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

interface BidItem {
  bid_id: number
  buyer_qq: number
  buyer_name: string
  player_name: string
  star: number
  position: string
  style: string
  max_price: number
  created_at: string
  is_mine: boolean
  quantity: number
  filled: number
}

interface SupplyCandidate {
  card_id: number
  player_name: string
  position: string
  star: number
  style: string
  style_name: string
  overall: number
  breach: number
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

function formatTimeAgo(isoStr: string): string {
  const d = new Date(isoStr)
  const now = new Date()
  const diff = Math.floor((now.getTime() - d.getTime()) / 1000)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return `${Math.floor(diff / 60)}分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)}小时前`
  return `${Math.floor(diff / 86400)}天前`
}

function positionLabel(key: string): string {
  const map: Record<string, string> = { FWD: '前锋', MID: '中场', DEF: '后卫', GK: '门将' }
  return map[key] || '不限'
}

export default function TransferPage() {
  const [activeTab, setActiveTab] = useState('market')

  return (
    <div className="flex flex-col h-full">
      <Tabs value={activeTab} onValueChange={setActiveTab} className="flex flex-col h-full">
        <div className="px-3 pt-3 flex-shrink-0">
          <TabsList className="w-full">
            <TabsTrigger value="market" className="flex-1">在售市场</TabsTrigger>
            <TabsTrigger value="bids" className="flex-1">求购大厅</TabsTrigger>
          </TabsList>
        </div>
        <TabsContent value="market" className="flex-1 flex flex-col overflow-hidden mt-0 min-h-0 data-[state=inactive]:hidden">
          <MarketTab />
        </TabsContent>
        <TabsContent value="bids" className="flex-1 flex flex-col overflow-hidden mt-0 min-h-0 data-[state=inactive]:hidden">
          <BidHallTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function MarketTab() {
  const navigate = useNavigate()
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
  const [marketPlayers, setMarketPlayers] = useState<any[]>([])
  const [selectedPlayer, setSelectedPlayer] = useState<any>(null)
  const [playerStar, setPlayerStar] = useState(0)

  const listRef = useRef<HTMLDivElement | null>(null)
  const { showToast } = useToast()

  const loadMarketPlayers = async () => {
    const res = await api.get('/transfer/players', { params: { query, position } })
    setMarketPlayers(res.data.players || [])
  }

  const loadMarket = async (p: number = 1, append: boolean = false, pid?: number, st?: number) => {
    const res = await api.get('/transfer', {
      params: { page: p, page_size: 20, query, position, min_star: minStar, style, sort_by: sortBy, player_id: pid ?? (selectedPlayer?.player_id || 0), star: st ?? playerStar }
    })
    setItems(prev => (append ? [...prev, ...res.data.items] : res.data.items))
    setPage(res.data.page)
    setTotalPages(res.data.total_pages)
  }

  useEffect(() => {
    loadMarketPlayers()
    api.get('/me').then(res => setMe({ qq: res.data.qq }))
  }, [])

  useEffect(() => {
    if (selectedPlayer) loadMarket(1, false)
    else loadMarketPlayers()
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
        const feeMsg = res.data.fee > 0 ? `（含税 $${res.data.fee}）` : ''
        showToast(`购买成功，花费 $${res.data.cost}${feeMsg}`)
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

  const openDetail = (cardId: number) => {
    if (selectMode) { toggleSelect(cardId); return }
    navigate(`/cards/${cardId}`)
  }

  const activeFilters = [
    position && POSITION_FILTERS.find(p => p.key === position)?.label,
    minStar > 0 && `≥${minStar}星`,
    style && STYLE_OPTIONS.find(s => s.key === style)?.label,
  ].filter(Boolean)

  const totalCost = items.filter(i => selected.has(i.card_id)).reduce((s, i) => s + i.cost, 0)

  return (
    <>
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
      {/* Player detail header */}
      {selectedPlayer && (
        <div className="px-3 pb-2">
          <button className="text-xs text-accent mb-2" onClick={() => { setSelectedPlayer(null); setItems([]); loadMarketPlayers() }}>← 返回球员列表</button>
          <div className="flex items-center gap-3 mb-2">
            <img src={`/game-assets/avatars/${selectedPlayer.player_id}.png`} className="w-10 h-10 rounded-lg bg-[#20293a] object-cover" onError={(e: any) => { e.target.style.display='none' }} />
            <div>
              <div className="text-sm font-bold text-slate-100">{selectedPlayer.name}</div>
              <div className="text-[10px] text-slate-500">{selectedPlayer.position} · OVR {selectedPlayer.overall} · {selectedPlayer.listing_count}件在售</div>
            </div>
          </div>
          <div className="flex gap-1 overflow-x-auto scrollbar-hide">
            {[0,1,2,3,4,5,6,7,8,9,10].map(s => (
              <button key={s} onClick={() => { setPlayerStar(s); loadMarket(1, false, selectedPlayer.player_id, s) }}
                className={`px-2 py-1 rounded text-xs whitespace-nowrap ${playerStar === s ? 'bg-gold/80 text-black' : 'bg-slate-800 text-slate-400'}`}>
                {s === 0 ? '全部' : `${s}★`}
              </button>
            ))}
          </div>
        </div>
      )}

      <div ref={listRef} className="flex-1 overflow-y-auto scrollbar-hide px-3 space-y-2 pb-20">
        {!selectedPlayer ? (
          <div className="space-y-1.5">
            {marketPlayers.map(p => (
              <div key={p.player_id} className="flex items-center gap-3 p-3 bg-slate-800/50 border border-slate-700/50 rounded-lg cursor-pointer hover:border-slate-600 transition-colors" onClick={() => { setSelectedPlayer(p); setPlayerStar(0); loadMarket(1, false, p.player_id, 0) }}>
                <img src={`/game-assets/avatars/${p.player_id}.png`} className="w-10 h-10 rounded-lg bg-[#20293a] object-cover" onError={(e: any) => { e.target.style.display='none' }} />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-slate-200 font-medium">{p.name}</div>
                  <div className="text-[10px] text-slate-500">{p.position} · OVR {p.overall}</div>
                </div>
                <div className="text-right">
                  <div className="text-xs text-gold font-bold">${p.min_price?.toLocaleString()}</div>
                  <div className="text-[10px] text-slate-500">{p.listing_count}件在售</div>
                </div>
              </div>
            ))}
            {marketPlayers.length === 0 && <p className="text-center text-slate-500 text-sm py-8">暂无在售球员</p>}
          </div>
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
                    <span className={`font-medium text-sm truncate ${overallColor(item.overall, item.star)}`}>{item.player_name}</span>
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
          <div className="space-y-4 overflow-y-auto scrollbar-hide flex-1">
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
              <p className="text-xs text-slate-500 mb-2">指定星级</p>
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
    </>
  )
}

function BidHallTab() {
  const [bids, setBids] = useState<BidItem[]>([])
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [loadingMore, setLoadingMore] = useState(false)
  const [showCreateBid, setShowCreateBid] = useState(false)

  // Create bid form
  const [bidPlayerName, setBidPlayerName] = useState('')
  const [bidStar, setBidStar] = useState(1)
  const [bidPosition, setBidPosition] = useState('')
  const [bidStyle, setBidStyle] = useState('')
  const [bidMaxPrice, setBidMaxPrice] = useState('')
  const [bidQuantity, setBidQuantity] = useState('1')
  const [playerSuggestions, setPlayerSuggestions] = useState<string[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)

  // Supply dialog
  const [supplyBidId, setSupplyBidId] = useState<number | null>(null)
  const [candidates, setCandidates] = useState<SupplyCandidate[]>([])
  const [loadingCandidates, setLoadingCandidates] = useState(false)

  const listRef = useRef<HTMLDivElement | null>(null)
  const { showToast } = useToast()

  const loadBids = async (p: number = 1, append: boolean = false) => {
    const res = await api.get('/bids', { params: { page: p, page_size: 20 } })
    setBids(prev => (append ? [...prev, ...res.data.items] : res.data.items))
    setPage(res.data.page)
    setTotalPages(res.data.total_pages)
  }

  useEffect(() => { loadBids() }, [])

  useEffect(() => {
    const node = listRef.current
    if (!node) return
    const onScroll = () => {
      if (loadingMore || page >= totalPages) return
      if (node.scrollTop + node.clientHeight >= node.scrollHeight - 80) {
        setLoadingMore(true)
        loadBids(page + 1, true).finally(() => setLoadingMore(false))
      }
    }
    node.addEventListener('scroll', onScroll)
    return () => node.removeEventListener('scroll', onScroll)
  }, [loadingMore, page, totalPages])

  const handleCreateBid = async () => {
    const price = parseInt(bidMaxPrice)
    if (!price || price <= 0) { showToast('请输入有效出价'); return }
    try {
      const res = await api.post('/bids/create', {
        player_name: bidPlayerName || null,
        star: bidStar,
        position: bidPosition || null,
        style: bidStyle || null,
        max_price: price, quantity: parseInt(bidQuantity) || 1,
      })
      if (res.data.matched) {
        showToast(`求购已自动成交：${res.data.match_detail.card_name}，花费 $${res.data.match_detail.price}`)
      } else {
        showToast('求购单已发布')
      }
      setShowCreateBid(false)
      resetBidForm()
      loadBids(1, false)
    } catch (e: any) {
      showToast(e.response?.data?.detail || '发布失败')
    }
  }

  const handleCancelBid = async (bidId: number) => {
    try {
      await api.post('/bids/cancel', { bid_id: bidId })
      showToast('已取消求购')
      loadBids(1, false)
    } catch (e: any) {
      showToast(e.response?.data?.detail || '取消失败')
    }
  }

  const openSupply = async (bidId: number) => {
    setSupplyBidId(bidId)
    setLoadingCandidates(true)
    try {
      const res = await api.get(`/bids/${bidId}/candidates`)
      setCandidates(res.data.items)
    } catch {
      setCandidates([])
    } finally {
      setLoadingCandidates(false)
    }
  }

  const handleSupply = async (cardId: number) => {
    if (!supplyBidId) return
    try {
      const res = await api.post('/bids/supply', { bid_id: supplyBidId, card_id: cardId })
      showToast(`供货成功！收入 $${res.data.price}${res.data.fee > 0 ? `（税 $${res.data.fee}）` : ''}`)
      setSupplyBidId(null)
      setCandidates([])
      loadBids(1, false)
    } catch (e: any) {
      showToast(e.response?.data?.detail || '供货失败')
    }
  }

  const resetBidForm = () => {
    setBidPlayerName('')
    setBidStar(1)
    setBidPosition('')
    setBidStyle('')
    setBidMaxPrice(''); setBidQuantity('1')
    setPlayerSuggestions([])
    setShowSuggestions(false)
  }

  const searchPlayerName = async (q: string) => {
    setBidPlayerName(q)
    if (q.length < 1) { setPlayerSuggestions([]); setShowSuggestions(false); return }
    try {
      const res = await api.get('/players/search', { params: { q } })
      setPlayerSuggestions(res.data)
      setShowSuggestions(res.data.length > 0)
    } catch { setPlayerSuggestions([]); setShowSuggestions(false) }
  }

  const selectPlayer = (name: string) => {
    setBidPlayerName(name)
    setShowSuggestions(false)
    setPlayerSuggestions([])
  }

  return (
    <>
      {/* Header */}
      <div className="p-3">
        <Button className="w-full" onClick={() => setShowCreateBid(true)}>
          发布求购
        </Button>
      </div>

      {/* Bid list */}
      <div ref={listRef} className="flex-1 overflow-y-auto scrollbar-hide px-3 space-y-2 pb-20">
        {bids.length === 0 ? (
          <div className="text-center py-12"><p className="text-slate-500">暂无求购单</p></div>
        ) : bids.map(bid => (
          <Card key={bid.bid_id} className="hover:border-slate-600">
            <CardContent className="p-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-slate-200">{bid.buyer_name}</span>
                    <span className="text-xs text-slate-500">求购</span>
                  </div>
                  <div className="flex flex-wrap gap-1 mb-1">
                    {bid.player_name && (
                      <span className="bg-blue-900/50 text-blue-300 text-xs px-2 py-0.5 rounded-full">{bid.player_name}</span>
                    )}
                    {bid.star > 1 && (
                      <span className="bg-yellow-900/50 text-yellow-300 text-xs px-2 py-0.5 rounded-full">≥{bid.star}★</span>
                    )}
                    {bid.position && (
                      <span className="bg-green-900/50 text-green-300 text-xs px-2 py-0.5 rounded-full">{positionLabel(bid.position)}</span>
                    )}
                    {bid.style && (
                      <span className="bg-purple-900/50 text-purple-300 text-xs px-2 py-0.5 rounded-full">{STYLE_NAMES[bid.style] || bid.style}</span>
                    )}
                    {!bid.player_name && !bid.position && bid.star <= 1 && !bid.style && (
                      <span className="bg-slate-700 text-slate-400 text-xs px-2 py-0.5 rounded-full">不限</span>
                    )}
                  </div>
                  <div className="text-xs text-slate-500">{formatTimeAgo(bid.created_at)}</div>
                </div>
                <div className="text-right flex-shrink-0">
                  <div className="text-yellow-400 font-bold text-sm mb-1">${bid.max_price.toLocaleString()} {bid.quantity > 1 && <span className="text-slate-400 text-xs font-normal">×{bid.quantity}{bid.filled > 0 && ` (已成交${bid.filled})`}</span>}</div>
                  {bid.is_mine ? (
                    <Button size="sm" variant="outline" className="h-6 text-xs px-2"
                      onClick={() => handleCancelBid(bid.bid_id)}>
                      取消
                    </Button>
                  ) : (
                    <Button size="sm" className="h-6 text-xs px-2"
                      onClick={() => openSupply(bid.bid_id)}>
                      供货
                    </Button>
                  )}
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Create bid dialog */}
      <Dialog open={showCreateBid} onOpenChange={setShowCreateBid}>
        <DialogContent className="max-h-[70vh] flex flex-col">
          <DialogHeader><DialogTitle>发布求购</DialogTitle></DialogHeader>
          <div className="space-y-4 overflow-y-auto scrollbar-hide flex-1">
            <div>
              <p className="text-xs text-slate-500 mb-1">球员名（留空=不限）</p>
              <div className="relative">
                <Input
                  placeholder="搜索球员名..."
                  value={bidPlayerName}
                  onChange={e => searchPlayerName(e.target.value)}
                  onFocus={() => { if (playerSuggestions.length > 0) setShowSuggestions(true) }}
                  onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
                />
                {showSuggestions && playerSuggestions.length > 0 && (
                  <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-slate-800 border border-slate-700 rounded-md max-h-40 overflow-y-auto scrollbar-hide shadow-lg">
                    {playerSuggestions.map(name => (
                      <button
                        key={name}
                        className="w-full text-left px-3 py-1.5 text-sm text-slate-200 hover:bg-slate-700 transition-colors"
                        onMouseDown={() => selectPlayer(name)}
                      >
                        {name}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>
            <div>
              <p className="text-xs text-slate-500 mb-1">指定星级</p>
              <div className="flex flex-wrap gap-2">
                {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(s => (
                  <button key={s}
                    className={`px-3 py-1 rounded-full text-xs ${bidStar === s ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}
                    onClick={() => setBidStar(s)}
                  >{s === 0 ? '不限' : `${s}★`}</button>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs text-slate-500 mb-1">位置（不选=不限）</p>
              <div className="flex flex-wrap gap-2">
                {POSITION_FILTERS.map(p => (
                  <button key={p.key}
                    className={`px-3 py-1 rounded-full text-xs ${bidPosition === p.key ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-300'}`}
                    onClick={() => setBidPosition(p.key)}
                  >{p.label}</button>
                ))}
              </div>
            </div>
            <div>
              <p className="text-xs text-slate-500 mb-1">特性（不选=不限）</p>
              <select value={bidStyle} onChange={e => setBidStyle(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded px-3 py-2 text-sm text-slate-200">
                {STYLE_OPTIONS.map(s => <option key={s.key} value={s.key}>{s.label}</option>)}
              </select>
            </div>
            <div>
              <p className="text-xs text-slate-500 mb-1">出价上限</p>
              <Input
                type="number"
                placeholder="最多愿意出多少钱"
                value={bidMaxPrice}
                onChange={e => setBidMaxPrice(e.target.value)}
              />
            </div>
            <div>
              <p className="text-xs text-slate-500 mb-1">求购数量</p>
              <Input
                type="number"
                placeholder="想买几张"
                value={bidQuantity}
                onChange={e => setBidQuantity(e.target.value)}
                min="1"
              />
            </div>
          </div>
          <Button className="mt-3" onClick={handleCreateBid}>发布求购</Button>
        </DialogContent>
      </Dialog>

      {/* Supply candidates dialog */}
      <Dialog open={supplyBidId !== null} onOpenChange={(open) => { if (!open) { setSupplyBidId(null); setCandidates([]) } }}>
        <DialogContent className="max-h-[70vh] flex flex-col">
          <DialogHeader><DialogTitle>选择供货球员</DialogTitle></DialogHeader>
          <div className="flex-1 overflow-y-auto scrollbar-hide space-y-2">
            {loadingCandidates ? (
              <div className="text-center py-8"><p className="text-slate-500">加载中...</p></div>
            ) : candidates.length === 0 ? (
              <div className="text-center py-8"><p className="text-slate-500">没有满足条件的球员</p></div>
            ) : candidates.map(c => (
              <Card key={c.card_id} className="hover:border-slate-600 cursor-pointer" onClick={() => handleSupply(c.card_id)}>
                <CardContent className="p-3 flex items-center gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`font-medium text-sm ${overallColor(c.overall, c.star)}`}>{c.player_name}</span>
                      <span className="text-yellow-400 text-xs">{'★'.repeat(Math.min(c.star, 5))}{c.star > 5 ? `×${c.star}` : ''}</span>
                    </div>
                    <div className="text-xs text-slate-500">
                      {c.position} · {c.overall} · {c.style_name}{c.breach > 0 ? ` · ◆+${c.breach}` : ''}
                    </div>
                  </div>
                  <Button size="sm" className="h-7 text-xs px-3 flex-shrink-0">选择</Button>
                </CardContent>
              </Card>
            ))}
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
