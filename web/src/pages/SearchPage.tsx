import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import PlayerCardDetail from '@/components/PlayerCardDetail'
import api from '../api/client'
import { overallColor, rarityBg, rarityBorder, STYLE_NAMES } from '@/lib/card-display'

interface SearchResult {
  card_id: number
  star: number
  style: string
  style_name?: string
  breach: number
  name: string
  position: string
  overall: number
  owner: string
}

export default function SearchPage() {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [searched, setSearched] = useState(false)
  const [detail, setDetail] = useState<any>(null)

  useEffect(() => {
    api.get('/search').then(res => {
      setResults(res.data.results)
      setSearched(true)
    })
  }, [])

  const doSearch = () => {
    api.get('/search', { params: { query: query.trim() } }).then(res => {
      setResults(res.data.results)
      setSearched(true)
    })
  }

  return (
    <div className="bg-dark p-4 h-full flex flex-col">
      <h1 className="text-lg font-bold text-slate-100 mb-1">全局查询</h1>
      <p className="text-xs text-slate-500 mb-3">默认展示全服卡牌能力前 100</p>

      <div className="flex gap-2 mb-3">
        <Input
          placeholder="输入球员名..."
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && doSearch()}
          className="flex-1"
        />
        <Button onClick={doSearch} size="sm">搜索</Button>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-hide">
        {searched && results.length === 0 && (
          <p className="text-slate-500 text-center py-8">没有找到匹配的球员</p>
        )}
        {results.length > 0 && (
          <div className="grid grid-cols-2 gap-3">
            {results.map((r, i) => (
              <Card
                key={i}
                className={`${rarityBorder(r.overall)} ${rarityBg(r.overall)} cursor-pointer hover:scale-[1.02] transition-transform`}
                onClick={() => api.get(`/cards/${r.card_id}`).then(res => setDetail(res.data))}
              >
                <CardContent className="p-3 text-center">
                  <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1">
                    <span>{r.position}</span>
                    <span>{r.owner}</span>
                  </div>
                  <div className={`text-2xl font-bold ${overallColor(r.overall)}`}>{r.overall}</div>
                  <div className={`text-sm mt-1 truncate ${overallColor(r.overall)}`}>{r.name}</div>
                  <div className="text-yellow-400 text-xs mt-1">{r.star <= 5 ? '★'.repeat(r.star) : `★${r.star}`}</div>
                  <div className="text-[10px] text-slate-500 mt-1">{r.style_name || STYLE_NAMES[r.style] || r.style}</div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </div>

      <Dialog open={detail !== null} onOpenChange={(open) => { if (!open) setDetail(null) }}>
        <DialogContent className="max-h-[85vh] overflow-y-auto scrollbar-hide">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 flex-wrap">
              <span className="text-slate-500 text-sm">[{detail?.id}]</span>
              <span className="text-slate-400 text-sm">{detail?.position}</span>
              <span className={overallColor(detail?.overall || 0)}>{detail?.name}</span>
              <span className={`font-bold ${overallColor(detail?.overall || 0)}`}>{detail?.overall}</span>
            </DialogTitle>
          </DialogHeader>
          <PlayerCardDetail detail={detail} />
        </DialogContent>
      </Dialog>
    </div>
  )
}
