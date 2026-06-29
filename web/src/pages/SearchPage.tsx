import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Search } from 'lucide-react'
import PlayerCard from '@/components/PlayerCard'
import api from '../api/client'

interface SearchResult {
  card_id: number
  player_id: number
  star: number
  style: string
  style_name?: string
  breach: number
  name: string
  position: string
  overall: number
  owner: string
  top_abilities?: { name: string; value: number }[]
}

export default function SearchPage() {
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [searched, setSearched] = useState(false)

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
    <div className="p-4 h-full flex flex-col">
      <h1 className="text-lg font-bold text-slate-100 mb-1 flex items-center gap-2">
        <Search size={18} className="text-gold" />
        全局查询
      </h1>
      <p className="text-xs text-slate-500 mb-3">默认展示全服卡牌能力前 100</p>

      <div className="flex gap-2 mb-3">
        <Input
          placeholder="输入球员名..."
          value={query}
          onChange={e => setQuery(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && doSearch()}
          className="flex-1"
        />
        <Button onClick={doSearch} size="sm" className="bg-gold/80 text-black hover:bg-gold">搜索</Button>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-hide">
        {searched && results.length === 0 && (
          <p className="text-slate-500 text-center py-8">没有找到匹配的球员</p>
        )}
        {results.length > 0 && (
          <div className="grid grid-cols-3 gap-2 justify-items-center">
            {results.map((r, i) => (
              <PlayerCard
                key={i}
                playerId={r.player_id}
                name={r.name}
                position={r.position}
                overall={r.overall}
                star={r.star}
                style={r.style}
                breach={r.breach}
                topAbilities={r.top_abilities}
                size="sm"
                badge={r.owner}
                onClick={() => navigate(`/cards/${r.card_id}`)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
