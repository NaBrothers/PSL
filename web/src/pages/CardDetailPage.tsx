import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { ArrowLeft, TrendingUp, Lock, Unlock, Trash2, ArrowUpCircle, Zap, DollarSign, GitCompare } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import api from '../api/client'
import { useToast } from '@/components/AppToast'
import { overallColor, STYLE_NAMES } from '@/lib/card-display'
import PlayerCardDetail from '@/components/PlayerCardDetail'
import CompareView from '@/components/CompareView'
import MarketInfo from '@/components/MarketInfo'

interface BagCard {
  id: number
  name: string
  position: string
  overall: number
  star: number
  style: string
}

type DialogMode = 'upgrade' | 'breach' | 'sell' | 'recycle' | 'compare-select' | 'compare-view' | 'market' | null

export default function CardDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const { showToast } = useToast()

  const [detail, setDetail] = useState<any>(null)
  const [me, setMe] = useState<{ qq: number } | null>(null)
  const [hasMarketListings, setHasMarketListings] = useState(false)
  const [dialogMode, setDialogMode] = useState<DialogMode>(null)
  const [subCards, setSubCards] = useState<any[]>([])
  const [compareData, setCompareData] = useState<any>(null)
  const [sellPrice, setSellPrice] = useState('')

  const ids: number[] = JSON.parse(sessionStorage.getItem('card_nav_ids') || '[]')
  const currentIdx = ids.indexOf(Number(id))
  const hasPrev = currentIdx > 0
  const hasNext = currentIdx >= 0 && currentIdx < ids.length - 1
  const isOwner = me && detail && detail.owner_qq === me.qq

  const loadDetail = (cardId: string) => {
    api.get(`/cards/${cardId}`).then(res => { setDetail(res.data); api.get("/transfer/players", { params: { query: res.data.name } }).then(r => setHasMarketListings((r.data.players || []).length > 0)).catch(() => {}) }).catch(() => setDetail(null))
  }

  useEffect(() => {
    if (id) loadDetail(id)
    api.get('/me').then(res => setMe({ qq: res.data.qq }))
  }, [id])

  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft' && hasPrev) goTo(ids[currentIdx - 1])
      if (e.key === 'ArrowRight' && hasNext) goTo(ids[currentIdx + 1])
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [hasPrev, hasNext, currentIdx, ids])

  const goTo = (newId: number) => {
    navigate(`/cards/${newId}`, { replace: true })
  }

  const handleBack = () => navigate(-1)

  const openUpgrade = () => {
    if (!detail) return
    api.get('/bag', { params: { page: 1, query: detail.name, page_size: 100 } }).then(res => {
      setSubCards(res.data.cards.filter((c: BagCard) => c.id !== detail.id && c.name === detail.name))
      setDialogMode('upgrade')
    })
  }

  const openBreach = () => {
    if (!detail) return
    api.get('/bag', { params: { page: 1, query: detail.name, page_size: 100 } }).then(res => {
      setSubCards(res.data.cards.filter((c: BagCard) => c.id !== detail.id && c.name === detail.name))
      setDialogMode('breach')
    })
  }

  const doUpgrade = async (subId: number) => {
    try {
      const res = await api.post('/cards/upgrade', { main_id: detail.id, sub_id: subId })
      showToast(`强化成功！新星级: ${'★'.repeat(res.data.new_star)}`)
      setDialogMode(null)
      loadDetail(String(detail.id))
    } catch (e: any) {
      showToast(e.response?.data?.detail || '强化失败')
      setDialogMode(null)
    }
  }

  const doBreach = async (subId: number) => {
    try {
      const res = await api.post('/cards/breach', { main_id: detail.id, sub_id: subId })
      showToast(`突破成功！「${res.data.boosted_ability}」+${res.data.boost_amount}`)
      setDialogMode(null)
      loadDetail(String(detail.id))
    } catch (e: any) {
      showToast(e.response?.data?.detail || '突破失败')
      setDialogMode(null)
    }
  }

  const handleLock = async () => {
    if (!detail) return
    const res = await api.post(`/cards/${detail.id}/lock`)
    setDetail({ ...detail, locked: res.data.locked })
    showToast(res.data.locked ? '已锁定' : '已解锁')
  }

  const handleRecycle = async () => {
    if (!detail) return
    const res = await api.post('/cards/recycle', { ids: [detail.id] })
    showToast(`回收成功！获得 $${res.data.earned}`)
    setDialogMode(null)
    // Go to next card or go back
    if (hasNext) goTo(ids[currentIdx + 1])
    else if (hasPrev) goTo(ids[currentIdx - 1])
    else navigate(-1)
  }

  const handleSell = async () => {
    try {
      const price = parseInt(sellPrice) || 0
      const res = await api.post('/transfer/list', { card_id: detail.id, price })
      if (res.data.matched) {
        showToast(`已上架并自动成交！$${res.data.price}`)
      } else {
        showToast(`已上架，挂牌价 $${res.data.price}`)
      }
      setDialogMode(null)
      setSellPrice('')
      loadDetail(String(detail.id))
    } catch (e: any) {
      showToast(e.response?.data?.detail || '上架失败')
    }
  }

  const openCompare = () => {
    if (!detail) return
    api.get('/bag', { params: { page: 1, sort: 'overall', for_position: detail.position, page_size: 50 } }).then(r => {
      setSubCards(r.data.cards.filter((c: BagCard) => c.id !== detail.id))
      setDialogMode('compare-select')
    })
  }

  const doCompare = async (otherId: number) => {
    const res = await api.get(`/cards/${detail.id}/compare/${otherId}`)
    setCompareData(res.data)
    setDialogMode('compare-view')
  }

  if (!detail) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-slate-500">加载中...</p>
      </div>
    )
  }

  const toolbarItems = [
    { key: 'upgrade', label: '强化', icon: ArrowUpCircle, action: openUpgrade, badge: detail.can_upgrade, disabled: !isOwner },
    { key: 'breach', label: '突破', icon: Zap, action: openBreach, badge: detail.can_breach, disabled: !isOwner },
    { key: 'sell', label: '出售', icon: DollarSign, action: () => setDialogMode('sell'), disabled: !isOwner },
    { key: 'lock', label: detail.locked ? '解锁' : '锁定', icon: detail.locked ? Unlock : Lock, action: handleLock, disabled: !isOwner },
    { key: 'recycle', label: '回收', icon: Trash2, action: () => setDialogMode('recycle'), disabled: !isOwner },
    { key: 'compare', label: '比较', icon: GitCompare, action: openCompare, disabled: false },
    { key: 'market', label: '市场', icon: TrendingUp, action: () => setDialogMode('market'), disabled: false, badge: hasMarketListings },
  ]

  return (
    <div className="flex flex-col h-full bg-[#070b16]">
      {/* Top nav */}
      <div className="flex items-center px-3 py-2 flex-shrink-0">
        <button onClick={handleBack} className="p-1.5 rounded-full hover:bg-slate-800 transition-colors">
          <ArrowLeft size={20} className="text-slate-300" />
        </button>
        <div className="flex-1 flex items-center justify-center gap-2">
          <span className="text-slate-500 text-sm">[{detail.id}]</span>
          <span className="text-slate-400 text-sm">{detail.position}</span>
          <span className={`font-bold text-base ${overallColor(detail.overall, detail.star)}`}>{detail.name}</span>
          <span className={`font-bold text-base ${overallColor(detail.overall, detail.star)}`}>{detail.overall}</span>
        </div>
        <div className="w-8" />
      </div>

      {/* Main content with swipe + keyboard nav */}
      <div
        className="flex-1 overflow-y-auto scrollbar-hide relative px-3 pb-2"
        onTouchStart={e => { (e.currentTarget as any)._touchX = e.touches[0].clientX }}
        onTouchEnd={e => {
          const startX = (e.currentTarget as any)._touchX
          if (startX == null) return
          const diff = e.changedTouches[0].clientX - startX
          if (diff > 60 && hasPrev) goTo(ids[currentIdx - 1])
          else if (diff < -60 && hasNext) goTo(ids[currentIdx + 1])
        }}
      >
        <PlayerCardDetail detail={detail} />
      </div>

      {/* Bottom toolbar */}
      <div className="flex-shrink-0 border-t border-slate-700/50 bg-[#0c1222]/95 backdrop-blur-md px-1 py-2">
        <div className="flex justify-around">
          {toolbarItems.map(item => {
            const Icon = item.icon
            return (
              <button
                key={item.key}
                onClick={item.disabled ? undefined : item.action}
                className={`relative flex flex-col items-center gap-0.5 px-1.5 py-1 rounded-lg transition-colors min-w-[40px] ${item.disabled ? 'opacity-30 cursor-not-allowed' : 'hover:bg-slate-800/60'}`}
              >
                <Icon size={18} className="text-slate-300" />
                <span className="text-[10px] text-slate-400">{item.label}</span>
                {item.badge && !item.disabled && <span className="absolute top-0 right-0.5 w-2 h-2 rounded-full bg-red-500" />}
              </button>
            )
          })}
        </div>
      </div>

      {/* Upgrade dialog */}
      <Dialog open={dialogMode === 'upgrade'} onOpenChange={(open) => { if (!open) setDialogMode(null) }}>
        <DialogContent>
          <DialogHeader><DialogTitle>选择副卡（强化）</DialogTitle></DialogHeader>
          <p className="text-xs text-slate-500 mb-2">选择同球员副卡，星级+1</p>
          {subCards.length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-4">没有可用的同球员副卡</p>
          ) : (
            <div className="space-y-1 max-h-60 overflow-y-auto scrollbar-hide">
              {subCards.map((c: BagCard) => (
                <div key={c.id} onClick={() => doUpgrade(c.id)} className="flex items-center gap-2 p-2 rounded-md hover:bg-slate-800 cursor-pointer">
                  <span className="text-slate-200 text-sm flex-1">{c.name}</span>
                  {c.style && <span className="text-emerald-400 text-[10px]">{STYLE_NAMES[c.style] || c.style}</span>}
                  <span className="text-yellow-400 text-xs">{'★'.repeat(Math.min(c.star, 5))}{c.star > 5 ? `×${c.star}` : ''}</span>
                  <span className={`text-sm font-bold ${overallColor(c.overall, c.star)}`}>{c.overall}</span>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Breach dialog */}
      <Dialog open={dialogMode === 'breach'} onOpenChange={(open) => { if (!open) setDialogMode(null) }}>
        <DialogContent>
          <DialogHeader><DialogTitle>选择副卡（突破）</DialogTitle></DialogHeader>
          <p className="text-xs text-slate-500 mb-2">选择同球员副卡，随机提升一项能力</p>
          {subCards.length === 0 ? (
            <p className="text-slate-500 text-sm text-center py-4">没有可用的同球员副卡</p>
          ) : (
            <div className="space-y-1 max-h-60 overflow-y-auto scrollbar-hide">
              {subCards.map((c: BagCard) => (
                <div key={c.id} onClick={() => doBreach(c.id)} className="flex items-center gap-2 p-2 rounded-md hover:bg-slate-800 cursor-pointer">
                  <span className="text-slate-200 text-sm flex-1">{c.name}</span>
                  {c.style && <span className="text-emerald-400 text-[10px]">{STYLE_NAMES[c.style] || c.style}</span>}
                  <span className="text-yellow-400 text-xs">{'★'.repeat(Math.min(c.star, 5))}{c.star > 5 ? `×${c.star}` : ''}</span>
                  <span className={`text-sm font-bold ${overallColor(c.overall, c.star)}`}>{c.overall}</span>
                </div>
              ))}
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Sell dialog */}
      <Dialog open={dialogMode === 'sell'} onOpenChange={(open) => { if (!open) { setDialogMode(null); setSellPrice('') } }}>
        <DialogContent>
          <DialogHeader><DialogTitle>出售球员</DialogTitle></DialogHeader>
          <p className="text-xs text-slate-500 mb-2">设定价格（留空使用默认身价）</p>
          <Input
            type="number"
            placeholder="输入挂牌价..."
            value={sellPrice}
            onChange={e => setSellPrice(e.target.value.replace(/\D/g, ''))}
          />
          <div className="flex gap-2 mt-3">
            <Button variant="outline" className="flex-1" onClick={() => { setDialogMode(null); setSellPrice('') }}>取消</Button>
            <Button className="flex-1" onClick={handleSell}>确认上架</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Recycle confirm */}
      <Dialog open={dialogMode === 'recycle'} onOpenChange={(open) => { if (!open) setDialogMode(null) }}>
        <DialogContent>
          <DialogHeader><DialogTitle>确认回收</DialogTitle></DialogHeader>
          <p className="text-sm text-slate-300 mb-4">确定回收 {detail.name}？此操作不可撤销。</p>
          <div className="flex gap-2">
            <Button variant="outline" className="flex-1" onClick={() => setDialogMode(null)}>取消</Button>
            <Button variant="destructive" className="flex-1" onClick={handleRecycle}>确认回收</Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Compare select */}
      <Dialog open={dialogMode === 'compare-select'} onOpenChange={(open) => { if (!open) setDialogMode(null) }}>
        <DialogContent>
          <DialogHeader><DialogTitle>选择对比球员</DialogTitle></DialogHeader>
          <Input placeholder="搜索球员..." className="mb-2" onChange={e => {
            const q = e.target.value
            if (q.length > 0) {
              api.get('/bag', { params: { page: 1, query: q, page_size: 50 } }).then(r =>
                setSubCards(r.data.cards.filter((c: BagCard) => c.id !== detail?.id))
              )
            } else if (detail) {
              api.get('/bag', { params: { page: 1, sort: 'overall', for_position: detail.position, page_size: 50 } }).then(r =>
                setSubCards(r.data.cards.filter((c: BagCard) => c.id !== detail.id))
              )
            }
          }} />
          <div className="space-y-1 max-h-60 overflow-y-auto scrollbar-hide">
            {subCards.map((c: BagCard) => (
              <div key={c.id} onClick={() => doCompare(c.id)} className="flex items-center gap-2 p-2 rounded-md hover:bg-slate-800 cursor-pointer">
                <span className="text-slate-400 text-xs">{c.position}</span>
                <span className="text-slate-200 text-sm flex-1">{c.name}</span>
                <span className="text-yellow-400 text-xs">{'★'.repeat(Math.min(c.star, 5))}{c.star > 5 ? `×${c.star}` : ''}</span>
                <span className={`text-sm font-bold ${overallColor(c.overall, c.star)}`}>{c.overall}</span>
              </div>
            ))}
          </div>
        </DialogContent>
      </Dialog>

      {/* Compare view */}
      <CompareView data={compareData} open={dialogMode === 'compare-view'} onClose={() => { setDialogMode(null); setCompareData(null) }} />

      {/* Market info */}
      <Dialog open={dialogMode === 'market'} onOpenChange={(open) => { if (!open) setDialogMode(null) }}>
        <DialogContent className="max-h-[70vh] overflow-y-auto scrollbar-hide">
          <DialogHeader><DialogTitle>市场行情</DialogTitle></DialogHeader>
          <MarketInfo playerName={detail.name} playerId={detail.player_id} star={detail.star} />
          <Button className="w-full mt-3" variant="outline" onClick={() => { setDialogMode(null); navigate(`/transfer?player_id=${detail.player_id}&name=${encodeURIComponent(detail.name)}`) }}>
            在市场中查看该球员
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  )
}
