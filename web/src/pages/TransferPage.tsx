import { useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import api from '../api/client'
import { useToast } from '@/components/AppToast'

interface TransferItem {
  card_id: number
  seller_qq: number
  player_name: string
  position: string
  overall: number
  star: number
  seller_name: string
  cost: number
}

export default function TransferPage() {
  const [items, setItems] = useState<TransferItem[]>([])
  const [me, setMe] = useState<{ qq: number } | null>(null)
  const [page, setPage] = useState(1)
  const [totalPages, setTotalPages] = useState(1)
  const [loadingMore, setLoadingMore] = useState(false)
  const [showSell, setShowSell] = useState(false)
  const [sellCards, setSellCards] = useState<any[]>([])
  const [sellTarget, setSellTarget] = useState<any>(null)
  const [sellPrice, setSellPrice] = useState('')
  const [confirmTarget, setConfirmTarget] = useState<{ cardId: number; cost: number; isMine: boolean; name: string } | null>(null)
  const listRef = useRef<HTMLDivElement | null>(null)
  const { showToast } = useToast()

  const loadMarket = async (p: number = 1, append: boolean = false) => {
    const res = await api.get('/transfer', { params: { page: p } })
    setItems(prev => (append ? [...prev, ...res.data.items] : res.data.items))
    setPage(res.data.page)
    setTotalPages(res.data.total_pages)
  }

  useEffect(() => {
    loadMarket()
    api.get('/me').then(res => setMe({ qq: res.data.qq }))
  }, [])

  useEffect(() => {
    const node = listRef.current
    if (!node) return

    const onScroll = () => {
      if (loadingMore || page >= totalPages) return
      const nearBottom = node.scrollTop + node.clientHeight >= node.scrollHeight - 80
      if (!nearBottom) return
      setLoadingMore(true)
      loadMarket(page + 1, true).finally(() => setLoadingMore(false))
    }

    node.addEventListener('scroll', onScroll)
    return () => node.removeEventListener('scroll', onScroll)
  }, [loadingMore, page, totalPages])

  const buy = async (cardId: number, isMine: boolean) => {
    try {
      if (isMine) {
        await api.post('/transfer/cancel', { card_id: cardId })
      } else {
        await api.post('/transfer/buy', { card_id: cardId })
      }
      setConfirmTarget(null)
      loadMarket(page)
    } catch (e: any) {
      showToast(e.response?.data?.detail || (isMine ? '下架失败' : '购买失败'))
    }
  }

  const openSellDialog = () => {
    api.get('/bag', { params: { page: 1, query: '' } }).then(res => {
      setSellCards(res.data.cards.filter((c: any) => c.status === 0 && !c.locked))
      setShowSell(true)
    })
  }

  const confirmSell = async () => {
    if (!sellTarget || !sellPrice) return
    try {
      await api.post('/transfer/list', { card_id: sellTarget.id, price: parseInt(sellPrice) })
      setShowSell(false)
      setSellTarget(null)
      setSellPrice('')
      loadMarket()
    } catch (e: any) {
      showToast(e.response?.data?.detail || '上架失败')
    }
  }

  return (
    <div className="bg-dark p-4">
      <div className="max-w-md mx-auto">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-lg font-bold text-slate-100">转会市场</h1>
          <Button size="sm" onClick={openSellDialog}>上架球员</Button>
        </div>

        {items.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-slate-500">暂无球员在售</p>
          </div>
        ) : (
          <div ref={listRef} className="space-y-2 mb-3 overflow-y-auto scrollbar-hide flex-1">
            {items.map(item => (
              <Card key={item.card_id} className="hover:border-slate-600 transition-colors">
                <CardContent className="p-3 flex items-center gap-3">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-slate-200 font-medium text-sm">{item.player_name}</span>
                      <span className="text-yellow-400 text-xs">{'★'.repeat(item.star)}</span>
                    </div>
                    <div className="text-xs text-slate-500">{item.position} · {item.overall} · 卖家: {item.seller_name}</div>
                  </div>
                  <div className="text-right">
                    <div className="text-yellow-400 font-bold text-sm">${item.cost}</div>
                    <Button
                      size="sm"
                      className="mt-1 h-7 text-xs"
                      variant={me?.qq === item.seller_qq ? 'outline' : 'default'}
                      onClick={() => setConfirmTarget({
                        cardId: item.card_id,
                        cost: item.cost,
                        isMine: me?.qq === item.seller_qq,
                        name: item.player_name,
                      })}
                    >
                      {me?.qq === item.seller_qq ? '下架' : '购买'}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}

        <div className="py-2" />
      </div>

      {/* Sell Dialog */}
      <Dialog open={showSell} onOpenChange={setShowSell}>
        <DialogContent className="max-h-[70vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>{sellTarget ? '设置价格' : '选择要上架的球员'}</DialogTitle>
          </DialogHeader>
          {!sellTarget ? (
            <div className="overflow-y-auto flex-1 space-y-1">
              {sellCards.map((c: any) => (
                <div key={c.id} onClick={() => setSellTarget(c)}
                  className="flex items-center gap-2 p-2 rounded-md hover:bg-slate-800 cursor-pointer">
                  <span className="text-slate-500 text-xs w-8">{c.position}</span>
                  <span className="text-slate-200 text-sm flex-1">{c.name}</span>
                  <span className="text-yellow-400 text-xs">{'★'.repeat(c.star)}</span>
                  <span className="text-sm text-slate-300">{c.overall}</span>
                </div>
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-slate-300">{sellTarget.name} · {sellTarget.position} · {sellTarget.overall}</p>
              <Input placeholder="输入价格" value={sellPrice} onChange={e => setSellPrice(e.target.value.replace(/\D/g, ''))} />
              <div className="flex gap-2">
                <Button variant="outline" className="flex-1" onClick={() => setSellTarget(null)}>返回</Button>
                <Button className="flex-1" onClick={confirmSell} disabled={!sellPrice}>确认上架</Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={confirmTarget !== null} onOpenChange={(open) => { if (!open) setConfirmTarget(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{confirmTarget?.isMine ? '确认下架' : '确认购买'}</DialogTitle>
          </DialogHeader>
          {confirmTarget && (
            <div className="space-y-4">
              <p className="text-sm text-slate-300">
                {confirmTarget.isMine
                  ? `确定下架 ${confirmTarget.name}？`
                  : `确定花费 $${confirmTarget.cost} 购买 ${confirmTarget.name}？`}
              </p>
              <div className="flex gap-2">
                <Button variant="outline" className="flex-1" onClick={() => setConfirmTarget(null)}>取消</Button>
                <Button className="flex-1" onClick={() => buy(confirmTarget.cardId, confirmTarget.isMine)}>
                  确认
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
