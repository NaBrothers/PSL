import { useEffect, useState } from 'react'
import api from '../api/client'
import { overallColor } from '@/lib/card-display'

interface MarketInfoProps {
  playerName: string
  playerId: number
  star: number
}

interface ListingItem {
  card_id: number
  cost: number
  seller_name: string
  star: number
  overall: number
}

interface BidItem {
  bid_id: number
  buyer_name: string
  max_price: number
  min_star: number
}

export default function MarketInfo({ playerName, playerId, star }: MarketInfoProps) {
  const [refPrice, setRefPrice] = useState<{ has_data: boolean; price: number; count: number } | null>(null)
  const [listings, setListings] = useState<ListingItem[]>([])
  const [bids, setBids] = useState<BidItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    Promise.all([
      api.get('/transfer/reference-price', { params: { player_id: playerId, star } }),
      api.get('/transfer', { params: { player_id: playerId, page_size: 10 } }),
      api.get('/bids', { params: { page_size: 50 } }),
    ]).then(([refRes, listRes, bidRes]) => {
      setRefPrice(refRes.data)
      setListings(listRes.data.items || [])
      const allBids = bidRes.data.items || []
      setBids(allBids.filter((b: any) =>
        !b.player_name || b.player_name.toLowerCase() === playerName.toLowerCase()
      ))
    }).catch(() => {}).finally(() => setLoading(false))
  }, [playerName, playerId, star])

  if (loading) return <p className="text-slate-500 text-center py-4">加载中...</p>

  return (
    <div className="space-y-4">
      {/* Reference price */}
      <div className="bg-slate-800/50 rounded-lg p-3">
        <p className="text-xs text-slate-500 mb-1">参考身价（★{star}）</p>
        {refPrice?.has_data ? (
          <p className="text-lg font-bold text-yellow-400">${refPrice.price.toLocaleString()}</p>
        ) : (
          <p className="text-sm text-slate-400">暂无成交记录</p>
        )}
        {refPrice?.has_data && <p className="text-[10px] text-slate-500">基于最近 {refPrice.count} 笔成交</p>}
      </div>

      {/* Current listings */}
      <div>
        <p className="text-xs text-slate-500 mb-2">在售（{listings.length}）</p>
        {listings.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-2">暂无在售</p>
        ) : (
          <div className="space-y-1">
            {listings.map(item => (
              <div key={item.card_id} className="flex items-center justify-between px-2 py-1.5 rounded bg-slate-800/30">
                <div className="flex items-center gap-2">
                  <span className="text-yellow-400 text-xs">★{item.star}</span>
                  <span className={`text-sm ${overallColor(item.overall, item.star)}`}>{item.overall}</span>
                  <span className="text-xs text-slate-500">{item.seller_name}</span>
                </div>
                <span className="text-yellow-400 font-medium text-sm">${item.cost.toLocaleString()}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Active bid orders */}
      <div>
        <p className="text-xs text-slate-500 mb-2">求购中（{bids.length}）</p>
        {bids.length === 0 ? (
          <p className="text-sm text-slate-400 text-center py-2">暂无求购</p>
        ) : (
          <div className="space-y-1">
            {bids.map(item => (
              <div key={item.bid_id} className="flex items-center justify-between px-2 py-1.5 rounded bg-slate-800/30">
                <div className="flex items-center gap-2">
                  {item.min_star > 1 && <span className="text-yellow-400 text-xs">≥★{item.min_star}</span>}
                  <span className="text-xs text-slate-500">{item.buyer_name}</span>
                </div>
                <span className="text-green-400 font-medium text-sm">出价 ${item.max_price.toLocaleString()}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
