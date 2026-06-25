import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import api from '../api/client'
import { abilityColor, normalizePositionRating, overallColor, rarityBg, rarityBorder, ratingDiffClass, ratingDiffText, STYLE_NAMES } from '@/lib/card-display'

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
                  <div className="text-yellow-400 text-xs mt-1">{'★'.repeat(r.star)}</div>
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
          {detail && (
            <div className="space-y-3">
              <div className="flex items-center gap-3 text-sm">
                <span className="text-yellow-400">{'★'.repeat(detail.star)}</span>
                <span className="text-green-400">◆+{detail.breach}</span>
                <span className="text-slate-300">{detail.style_name || detail.style}</span>
              </div>

              {detail.position_ratings && (
                <div className="flex gap-3 text-sm flex-wrap">
                  {detail.position_ratings.map((item: any) => {
                    const pos = normalizePositionRating(item, detail.overall)
                    return (
                      <span key={pos.position} className="text-slate-200">
                        {pos.position}: <span className={`font-bold ${abilityColor(pos.rating)}`}>{pos.rating}</span>
                        {pos.diff !== 0 && <span className={`ml-0.5 text-xs ${ratingDiffClass(pos.diff)}`}>{ratingDiffText(pos.diff)}</span>}
                      </span>
                    )
                  })}
                </div>
              )}

              <div className="text-xs text-slate-500">
                {detail.age}岁 {detail.height}cm {detail.weight}kg 身价 ${detail.price?.toLocaleString()}
              </div>

              {detail.all_position_ratings && (() => {
                const rMap: Record<string, ReturnType<typeof normalizePositionRating>> = Object.fromEntries(
                  detail.all_position_ratings.map((item: any) => {
                    const pos = normalizePositionRating(item, detail.overall)
                    return [pos.position, pos]
                  })
                )
                const layout = [
                  [null, null, 'ST', null, null],
                  ['LRW', null, 'CF', null, 'LRW'],
                  [null, null, 'AM', null, null],
                  ['LRM', null, 'CM', null, 'LRM'],
                  [null, null, 'DM', null, null],
                  ['LRB', null, 'CB', null, 'LRB'],
                  [null, null, 'GK', null, null],
                ]
                return (
                  <div className="border-t border-slate-700 pt-2">
                    <div className="grid grid-cols-5 gap-y-0.5 text-xs text-center">
                      {layout.map((row, ri) => row.map((cell, ci) => (
                        <div key={`${ri}-${ci}`} className="h-5">
                          {cell && rMap[cell] !== undefined && (
                            <>
                              <span className="text-slate-500">{cell} </span>
                              <span className={`font-bold ${abilityColor(rMap[cell].rating)}`}>{rMap[cell].rating}</span>
                              {rMap[cell].diff !== 0 && <span className={`ml-0.5 text-[10px] ${ratingDiffClass(rMap[cell].diff)}`}>{ratingDiffText(rMap[cell].diff)}</span>}
                            </>
                          )}
                        </div>
                      )))}
                    </div>
                  </div>
                )
              })()}

              {detail.abilities && (
                <div className="border-t border-slate-700 pt-2">
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                    {Object.entries(detail.abilities as Record<string, {value: number; name: string; ext: number}>).map(([key, ab]) => (
                      <div key={key} className="flex justify-between">
                        <span className="text-slate-400">{ab.name}</span>
                        <span><span className={`font-bold ${abilityColor(ab.value)}`}>{ab.value}</span>{ab.ext > 0 && <span className="text-green-400 text-xs ml-0.5">(+{ab.ext})</span>}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="border-t border-slate-700 pt-2">
                <p className="text-xs text-slate-500 mb-1">赛季</p>
                <div className="grid grid-cols-5 gap-1 text-center text-xs">
                  <div><div className="text-slate-400">出场</div><div className="text-slate-200">{detail.season.appearance}</div></div>
                  <div><div className="text-slate-400">进球</div><div className="text-slate-200">{detail.season.goal}</div></div>
                  <div><div className="text-slate-400">助攻</div><div className="text-slate-200">{detail.season.assist}</div></div>
                  <div><div className="text-slate-400">抢断</div><div className="text-slate-200">{detail.season.tackle}</div></div>
                  <div><div className="text-slate-400">扑救</div><div className="text-slate-200">{detail.season.save}</div></div>
                </div>
              </div>

              <div className="border-t border-slate-700 pt-2">
                <p className="text-xs text-slate-500 mb-1">生涯</p>
                <div className="grid grid-cols-5 gap-1 text-center text-xs">
                  <div><div className="text-slate-400">出场</div><div className="text-slate-200">{detail.career.appearance}</div></div>
                  <div><div className="text-slate-400">进球</div><div className="text-slate-200">{detail.career.goal}</div></div>
                  <div><div className="text-slate-400">助攻</div><div className="text-slate-200">{detail.career.assist}</div></div>
                  <div><div className="text-slate-400">抢断</div><div className="text-slate-200">{detail.career.tackle}</div></div>
                  <div><div className="text-slate-400">扑救</div><div className="text-slate-200">{detail.career.save}</div></div>
                </div>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
