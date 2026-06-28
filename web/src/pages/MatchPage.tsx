import { useState, useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ColorText } from '@/components/ColorText'
import SquadView from '@/components/SquadView'
import type { SquadData } from '@/components/SquadView'
import api from '../api/client'
import { useToast } from '@/components/AppToast'

interface Opponent {
  id: number
  qq: number
  name: string
}

interface GoalInfo {
  minute: number
  team_side: string
  scorer: string
  assister: string | null
  scorer_color?: string
  assister_color?: string | null
}

interface PlayerRating {
  name: string
  colored_name?: string
  position: string
  rating: number
}

interface MatchRatings {
  home_ratings: PlayerRating[]
  away_ratings: PlayerRating[]
  motm: { name: string; colored_name?: string; team_side: string; rating: number }
}

interface MatchResult {
  home_name: string
  away_name: string
  home_score: number
  away_score: number
  home_stats: Record<string, number>
  away_stats: Record<string, number>
  goals: GoalInfo[]
  report: string
  stats_text: string
  replay_url: string | null
  ratings: MatchRatings | null
}

type Mode = 'quick' | 'watch' | 'ten' | 'odds'
type Phase = 'select' | 'squad' | 'live' | 'result'

const NAME_COLORS: Record<string, string> = {
  w: 'text-slate-300',
  g: 'text-green-400',
  b: 'text-blue-400',
  p: 'text-purple-400',
  o: 'text-orange-400',
  r: 'text-red-400',
  f: 'text-pink-400',
  '$': 'text-transparent bg-clip-text bg-[linear-gradient(90deg,#ef4444,#f97316,#eab308,#22c55e,#06b6d4,#3b82f6,#a855f7,#ec4899)]',
}

function ratingColor(rating: number): string {
  if (rating >= 8.0) return 'text-green-400'
  if (rating >= 7.0) return 'text-lime-400'
  if (rating >= 6.5) return 'text-yellow-400'
  if (rating >= 6.0) return 'text-orange-400'
  return 'text-red-400'
}

function ratingBg(rating: number): string {
  if (rating >= 8.0) return 'bg-green-500/20 border-green-500/30'
  if (rating >= 7.0) return 'bg-lime-500/20 border-lime-500/30'
  if (rating >= 6.5) return 'bg-yellow-500/20 border-yellow-500/30'
  if (rating >= 6.0) return 'bg-orange-500/20 border-orange-500/30'
  return 'bg-red-500/20 border-red-500/30'
}

function GoalName({ goal, align = 'left' }: { goal: GoalInfo; align?: 'left' | 'right' }) {
  return (
    <div className={`min-w-0 ${align === 'right' ? 'text-right' : 'text-left'}`}>
      <div className={`truncate ${NAME_COLORS[goal.scorer_color || 'w'] || 'text-slate-200'}`}>
        <span className="mr-1">⚽</span>
        {goal.scorer}
      </div>
      {goal.assister && (
        <div className={`truncate text-xs ${NAME_COLORS[goal.assister_color || 'w'] || 'text-slate-500'}`}>
          ({goal.assister})
        </div>
      )}
    </div>
  )
}

export default function MatchPage() {
  const [opponents, setOpponents] = useState<Opponent[]>([])
  const [selected, setSelected] = useState<Opponent | null>(null)
  const [mode, setMode] = useState<Mode>('quick')
  const [result, setResult] = useState<MatchResult | null>(null)
  const [tenResult, setTenResult] = useState<any>(null)
  const [oddsResult, setOddsResult] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [phase, setPhase] = useState<Phase>('select')
  const [broadcasts, setBroadcasts] = useState<string[][]>([])
  const [opponentSquad, setOpponentSquad] = useState<SquadData | null>(null)
  const liveRef = useRef<HTMLDivElement>(null)
  const { showToast } = useToast()

  useEffect(() => {
    api.get('/matches/opponents').then(res => setOpponents(res.data))
  }, [])

  const viewOpponentSquad = async (opponent: Opponent) => {
    setSelected(opponent)
    try {
      const res = await api.get(`/squad/${opponent.id}`)
      setOpponentSquad(res.data)
      setPhase('squad')
    } catch {
      showToast('无法加载对手阵容')
    }
  }

  const startMatchWith = (opponent: Opponent) => {
    setSelected(opponent)
    selectedRef.current = opponent
    startMatch()
  }

  const selectedRef = useRef<Opponent | null>(null)
  selectedRef.current = selected

  useEffect(() => {
    if (liveRef.current) {
      liveRef.current.scrollTop = liveRef.current.scrollHeight
    }
  }, [broadcasts])

  const startMatch = async () => {
    const target = selectedRef.current
    if (!target) return
    setLoading(true)
    setResult(null)
    setTenResult(null)
    setOddsResult(null)
    setBroadcasts([])

    if (mode === 'watch') {
      setPhase('live')
      const token = localStorage.getItem('psl_token')
      const es = new EventSource(`/api/matches/watch?opponent_id=${target.id}&authorization=Bearer ${token}`)

      es.onmessage = (event) => {
        const msg = JSON.parse(event.data)
        if (msg.type === 'result') {
          es.close()
          setResult(msg.data)
          setPhase('result')
          setLoading(false)
        } else if (msg.type === 'error') {
          es.close()
          showToast(msg.text)
          setPhase('select')
          setLoading(false)
        } else {
          if (msg.type === "broadcast" && msg.lines) { setBroadcasts(prev => [...prev, msg.lines]) } else if (msg.text) { setBroadcasts(prev => [...prev, [msg.text]]) }
        }
      }

      es.onerror = () => {
        es.close()
        setPhase('select')
        setLoading(false)
      }
      return
    }

    try {
      const res = await api.post('/matches', { opponent_id: target.id, mode })
      if (mode === 'ten') {
        setTenResult(res.data)
      } else if (mode === 'odds') {
        setOddsResult(res.data)
      } else {
        setResult(res.data)
      }
      setPhase('result')
    } catch (e: any) {
      showToast(e.response?.data?.detail || '比赛失败')
    }
    setLoading(false)
  }

  const reset = () => {
    setPhase('select')
    setResult(null)
    setTenResult(null)
    setOddsResult(null)
    setBroadcasts([])
    setSelected(null)
    setOpponentSquad(null)
  }

  const STAT_LABELS: Record<string, string> = {
    possession: '控球率', shots: '射门', shots_on_target: '射正',
    shots_in_box: '禁区射门', passes: '传球', pass_success_rate: '传球成功率',
    final_third_entries: '进攻三区', box_entries: '禁区进入',
    progressive_passes: '推进传球', crosses: '传中', corners: '角球',
    dribbles: '过人', carries: '带球推进', tackles: '抢断',
    pressures: '逼抢', interceptions: '拦截', blocks: '封堵',
    turnovers: '丢失球权', saves: '扑救', xg: 'xG',
    post_shot_xg: 'PSxG', key_passes: '关键传球',
    box_touches: '禁区触球', big_chances: '绝对机会', offsides: '越位',
  }

  // Live broadcast phase
  if (phase === 'live') {
    return (
      <div className="p-4 flex flex-col">
        <h2 className="text-sm text-slate-400 text-center mb-2">比赛进行中...</h2>
        <div ref={liveRef} className="flex-1 overflow-y-auto scrollbar-hide space-y-3 pb-4 scrollbar-hide" style={{ maxHeight: 'calc(100vh - 100px)' }}>
          {broadcasts.map((group, i) => (
            <div key={i} className="bg-slate-900 border border-slate-800 rounded-lg p-3 text-sm leading-relaxed space-y-1">
              {group.map((line, j) => (
                <div key={j}><ColorText text={line} /></div>
              ))}
            </div>
          ))}
        </div>
      </div>
    )
  }

  // Squad preview phase
  if (phase === 'squad' && selected && opponentSquad) {
    return (
      <div className="p-4">
        <SquadView squad={opponentSquad} title={`${selected.name} 的阵容`} />
        <Button variant="outline" className="w-full mt-4" onClick={() => setPhase('select')}>返回</Button>
      </div>
    )
  }

  // Select phase
  if (phase === 'select') {
    return (
      <div className="p-4">
        <h1 className="text-lg font-bold text-slate-100 mb-4">比赛</h1>

        <div className="flex gap-2 mb-4">
          {([['quick', '快速'], ['watch', '播报'], ['ten', '十连'], ['odds', '赔率']] as [Mode, string][]).map(([m, label]) => (
            <Button key={m} variant={mode === m ? 'default' : 'outline'} size="sm" className="flex-1" onClick={() => setMode(m)}>
              {label}
            </Button>
          ))}
        </div>

        <p className="text-slate-500 text-sm mb-2">选择对手</p>
        <div className="space-y-2 mb-4">
          {opponents.map(o => (
            <Card key={o.id} className="transition-colors hover:border-slate-600">
              <CardContent className="p-3 flex items-center">
                <div className="w-8 h-8 rounded-full bg-slate-800 flex items-center justify-center text-accent font-bold text-sm mr-3">
                  {o.name[0]}
                </div>
                <span className="text-slate-200 text-sm font-medium flex-1">{o.name}</span>
                <Button variant="outline" size="sm" className="text-xs" onClick={() => viewOpponentSquad(o)}>阵容</Button>
                <Button size="sm" className="text-xs" disabled={loading} onClick={() => startMatchWith(o)}>
                  开赛
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    )
  }

  // Result phase - ten
  if (tenResult) {
    return (
      <div className="p-4">
        <h2 className="text-lg font-bold text-slate-100 mb-3">十连结果</h2>
        <div className="grid grid-cols-3 gap-3 text-center mb-4">
          <div className="bg-green-900/30 rounded-lg p-3"><div className="text-green-400 text-xl font-bold">{tenResult.wins}</div><div className="text-xs text-slate-500">胜</div></div>
          <div className="bg-yellow-900/30 rounded-lg p-3"><div className="text-yellow-400 text-xl font-bold">{tenResult.draws}</div><div className="text-xs text-slate-500">平</div></div>
          <div className="bg-red-900/30 rounded-lg p-3"><div className="text-red-400 text-xl font-bold">{tenResult.losses}</div><div className="text-xs text-slate-500">负</div></div>
        </div>
        <Card className="mb-4"><CardContent className="p-3">
          <p className="text-sm text-slate-300">总比分: {tenResult.total_home_goals} : {tenResult.total_away_goals}</p>
          <div className="mt-2 space-y-1">{tenResult.results.map((r: any, i: number) => (
            <div key={i} className="flex justify-between text-xs text-slate-400"><span>第{i+1}场</span><span className="font-mono">{r.home_score} : {r.away_score}</span></div>
          ))}</div>
        </CardContent></Card>
        <Button variant="outline" className="w-full" onClick={reset}>返回</Button>
      </div>
    )
  }

  // Result phase - odds
  if (oddsResult) {
    return (
      <div className="p-4">
        <h2 className="text-lg font-bold text-slate-100 mb-4">赔率</h2>
        <div className="grid grid-cols-3 gap-3 text-center mb-4">
          <div className="bg-slate-800 rounded-lg p-4"><div className="text-accent text-2xl font-bold">{oddsResult.home_win_odds}</div><div className="text-xs text-slate-500">主胜</div></div>
          <div className="bg-slate-800 rounded-lg p-4"><div className="text-yellow-400 text-2xl font-bold">{oddsResult.draw_odds}</div><div className="text-xs text-slate-500">平局</div></div>
          <div className="bg-slate-800 rounded-lg p-4"><div className="text-red-400 text-2xl font-bold">{oddsResult.away_win_odds}</div><div className="text-xs text-slate-500">客胜</div></div>
        </div>
        <p className="text-center text-xs text-slate-500 mb-4">样本: {oddsResult.samples}场</p>
        <Button variant="outline" className="w-full" onClick={reset}>返回</Button>
      </div>
    )
  }

  // Result phase - normal match
  if (!result) return null

  return (
    <div className="p-4">
      <div className="text-center py-6 mb-4 rounded-xl border border-dark-border bg-gradient-to-b from-dark-card/80 to-transparent relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(212,168,67,0.05),transparent_60%)]" />
        <div className="relative">
          <div className="text-5xl font-black mb-2">
            <span className="text-accent">{result.home_score}</span>
            <span className="text-gold mx-3">:</span>
            <span className="text-red-400">{result.away_score}</span>
          </div>
          <p className="text-sm text-slate-400">{result.home_name} vs {result.away_name}</p>
        </div>
      </div>

      <Tabs defaultValue="report" className="w-full">
        <TabsList className="w-full">
          <TabsTrigger value="report" className="flex-1">战报</TabsTrigger>
          <TabsTrigger value="goals" className="flex-1">进球</TabsTrigger>
          <TabsTrigger value="stats" className="flex-1">数据</TabsTrigger>
          {result.ratings && <TabsTrigger value="ratings" className="flex-1">评分</TabsTrigger>}
            {broadcasts.length > 0 && <TabsTrigger value="live" className="flex-1">播报</TabsTrigger>}
        </TabsList>

        <TabsContent value="report">
          <Card><CardContent className="p-4">
            <div className="text-sm text-slate-300 whitespace-pre-wrap leading-relaxed"><ColorText text={result.report} /></div>
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="goals">
          <Card><CardContent className="p-4 space-y-2">
            {result.goals.length === 0 ? (
              <p className="text-slate-500 text-sm text-center">无进球</p>
            ) : result.goals.map((g, i) => (
              <div key={i} className="grid grid-cols-[1fr_44px_1fr] items-center gap-2 text-sm min-h-8">
                <div className="min-w-0 text-left">
                  {g.team_side === 'home' && (
                    <GoalName goal={g} />
                  )}
                </div>
                <div className="text-center text-slate-600 text-xs">{g.minute}'</div>
                <div className="min-w-0 text-right">
                  {g.team_side === 'away' && (
                    <GoalName goal={g} align="right" />
                  )}
                </div>
              </div>
            ))}
          </CardContent></Card>
        </TabsContent>

        <TabsContent value="stats">
          <Card><CardContent className="p-4 space-y-2">
            {Object.entries(result.home_stats).map(([key, val]) => {
              const awayVal = (result.away_stats as any)[key]
              const label = STAT_LABELS[key] || key
              const homeNum = typeof val === 'number' ? val : 0
              const awayNum = typeof awayVal === 'number' ? awayVal : 0
              const total = homeNum + awayNum || 1
              let homeDisplay = String(val)
              let awayDisplay = String(awayVal)
              let suffix = ''
              if (key === 'possession') {
                homeDisplay = String(Math.round(homeNum * 1000 / total) / 10)
                awayDisplay = String(Math.round(awayNum * 1000 / total) / 10)
                suffix = '%'
              } else if (key === 'pass_success_rate') {
                suffix = '%'
              }
              return (
                <div key={key}>
                  <div className="flex justify-between text-xs text-slate-400 mb-1">
                    <span className="text-accent">{homeDisplay}{suffix}</span>
                    <span>{label}</span>
                    <span className="text-red-400">{awayDisplay}{suffix}</span>
                  </div>
                  <div className="flex h-1.5 rounded overflow-hidden bg-slate-800">
                    <div className="bg-accent/70 transition-all" style={{ width: `${(homeNum / total) * 100}%` }} />
                    <div className="bg-red-400/70 transition-all" style={{ width: `${(awayNum / total) * 100}%` }} />
                  </div>
                </div>
              )
            })}
          </CardContent></Card>
        </TabsContent>

        {result.ratings && (
          <TabsContent value="ratings">
            <Card><CardContent className="p-4">
              {result.ratings.motm && (
                <div className="text-center mb-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                  <div className="text-xs text-yellow-500 mb-1">⭐ 全场最佳</div>
                  <div className="text-lg font-bold text-yellow-400"><ColorText text={result.ratings.motm.colored_name || result.ratings.motm.name} /></div>
                  <div className={`text-2xl font-bold ${ratingColor(result.ratings.motm.rating)}`}>{result.ratings.motm.rating}</div>
                </div>
              )}
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <div className="text-xs text-accent font-medium mb-2 text-center">{result.home_name}</div>
                  <div className="space-y-1.5">
                    {result.ratings.home_ratings.map((p, i) => (
                      <div key={i} className={`flex items-center justify-between px-2 py-1.5 rounded border ${ratingBg(p.rating)}`}>
                        <div className="min-w-0 flex-1">
                          <span className="text-xs text-slate-500 mr-1">{p.position}</span>
                          <span className="text-xs truncate"><ColorText text={p.colored_name || p.name} /></span>
                        </div>
                        <span className={`text-sm font-bold ml-1 ${ratingColor(p.rating)}`}>{p.rating}</span>
                      </div>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-red-400 font-medium mb-2 text-center">{result.away_name}</div>
                  <div className="space-y-1.5">
                    {result.ratings.away_ratings.map((p, i) => (
                      <div key={i} className={`flex items-center justify-between px-2 py-1.5 rounded border ${ratingBg(p.rating)}`}>
                        <div className="min-w-0 flex-1">
                          <span className="text-xs text-slate-500 mr-1">{p.position}</span>
                          <span className="text-xs truncate"><ColorText text={p.colored_name || p.name} /></span>
                        </div>
                        <span className={`text-sm font-bold ml-1 ${ratingColor(p.rating)}`}>{p.rating}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </CardContent></Card>
          </TabsContent>
        )}

        {broadcasts.length > 0 && (
          <TabsContent value="live">
            <Card><CardContent className="p-4 space-y-3 max-h-96 overflow-y-auto scrollbar-hide">
              {broadcasts.map((group, i) => (
                <div key={i} className="border-b border-slate-800/50 pb-2 space-y-1">
                  {group.map((line, j) => (
                    <div key={j} className="text-sm text-slate-300 leading-relaxed"><ColorText text={line} /></div>
                  ))}
                </div>
              ))}
            </CardContent></Card>
          </TabsContent>
        )}
      </Tabs>

      <div className="flex gap-2 mt-4">
        {result.replay_url && (
          <Button variant="outline" className="flex-1" onClick={() => window.open(result.replay_url!, '_blank')}>观看回放</Button>
        )}
        <Button variant="secondary" className="flex-1" onClick={reset}>再来一场</Button>
      </div>
    </div>
  )
}
