import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ColorText } from '@/components/ColorText'
import SquadView from '@/components/SquadView'
import ReplayHighlights from "@/components/ReplayHighlights"
import type { SquadData } from '@/components/SquadView'
import PlayerMatchDetail from "@/components/PlayerMatchDetail"
import type { PlayerStat } from "@/components/PlayerMatchDetail"
import { Dialog, DialogContent } from "@/components/ui/dialog"
import { Trophy, Zap } from 'lucide-react'
import api from '../api/client'
import { useToast } from '@/components/AppToast'

interface ChallengeInfo {
  npc_name: string
  times_left: number
  difficulties: { key: string; star: number }[]
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

interface ChallengeResult {
  home_name: string
  away_name: string
  home_score: number
  away_score: number
  result: string
  award: string
  report: string
  stats_text: string
  goals: GoalInfo[]
  home_stats: Record<string, number>
  away_stats: Record<string, number>
  ratings: MatchRatings | null
  replay_url: string | null
  times_left: number
  home_player_stats: PlayerStat[] | null
  away_player_stats: PlayerStat[] | null
}

const DIFF_COLORS: Record<string, string> = {
  '简单': 'from-green-500/20 to-green-900/10 border-green-500/30',
  '普通': 'from-blue-500/20 to-blue-900/10 border-blue-500/30',
  '困难': 'from-orange-500/20 to-orange-900/10 border-orange-500/30',
  '地狱': 'from-red-500/20 to-red-900/10 border-red-500/30',
  '噩梦': 'from-purple-500/20 to-purple-900/10 border-purple-500/30',
}

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

function ratingColor(rating: number): string {
  if (rating >= 8.0) return 'text-green-400'
  if (rating >= 7.0) return 'text-lime-400'
  if (rating >= 6.5) return 'text-yellow-400'
  if (rating >= 6.0) return 'text-orange-400'
  return 'text-red-400'
}

function ratingBg(_rating: number): string {
  return 'bg-slate-800/50 border-slate-700/50 hover:bg-slate-700/50'
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

export default function ChallengePage() {
  const [info, setInfo] = useState<ChallengeInfo | null>(null)
  const [result, setResult] = useState<ChallengeResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [npcSquad, setNpcSquad] = useState<SquadData | null>(null)
  const [selectedDifficulty, setSelectedDifficulty] = useState<string | null>(null)
  const [playerDetail, setPlayerDetail] = useState<{player: PlayerStat, side: "home"|"away"} | null>(null)
  const { showToast } = useToast()

  useEffect(() => {
    api.get('/challenge').then(res => setInfo(res.data))
  }, [])

  const viewNpcSquad = async (difficulty: string) => {
    setSelectedDifficulty(difficulty)
    try {
      const res = await api.get('/challenge/squad', { params: { difficulty } })
      setNpcSquad(res.data)
    } catch {
      showToast('无法加载 NPC 阵容')
    }
  }

  const play = async (difficulty: string) => {
    setLoading(true)
    try {
      const res = await api.post('/challenge/play', { difficulty, mode: 'quick' })
      setResult(res.data)
      setInfo(prev => prev ? { ...prev, times_left: res.data.times_left } : null)
    } catch (e: any) {
      showToast(e.response?.data?.detail || '挑战失败')
    }
    setLoading(false)
  }

  const resetSquadView = () => {
    setNpcSquad(null)
    setSelectedDifficulty(null)
  }

  if (!info) return <div className="flex items-center justify-center h-full text-slate-500">加载中...</div>

  // NPC Squad preview
  if (npcSquad && !result) {
    return (
      <div className="p-4">
        <SquadView squad={npcSquad} title={`${info.npc_name} 的阵容`} />
        <div className="flex gap-2 mt-4">
          <Button variant="outline" className="flex-1" onClick={resetSquadView}>返回</Button>
          <Button className="flex-1 bg-gold/80 text-black hover:bg-gold font-bold" disabled={loading || info.times_left <= 0} onClick={() => { if (selectedDifficulty) play(selectedDifficulty) }}>
            {loading ? '进行中...' : '开赛'}
          </Button>
        </div>
      </div>
    )
  }

  if (result) {
    return (
      <div className="p-4">
        {/* Score header */}
        <div className="text-center py-6 mb-4 rounded-xl border border-dark-border bg-gradient-to-b from-dark-card/80 to-transparent relative overflow-hidden">
          <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(212,168,67,0.05),transparent_60%)]" />
          <div className="relative">
            <div className="text-5xl font-black mb-2">
              <span className="text-accent">{result.home_score}</span>
              <span className="text-gold mx-3">:</span>
              <span className="text-red-400">{result.away_score}</span>
            </div>
            <p className="text-sm text-slate-400">{result.home_name} vs {result.away_name}</p>
            <p className={`text-lg font-bold mt-1 ${result.result === 'win' ? 'text-green-400' : result.result === 'lose' ? 'text-red-400' : 'text-yellow-400'}`}>
              {result.result === 'win' ? '胜利！' : result.result === 'lose' ? '失败' : '平局'}
            </p>
            {result.award && (
              <p className="text-gold text-sm mt-1 font-medium">奖励: {result.award}</p>
            )}
          </div>
        </div>

        {/* Tabs */}
        <Tabs defaultValue="report" className="w-full">
          <TabsList className="w-full">
            <TabsTrigger value="report" className="flex-1">战报</TabsTrigger>
            <TabsTrigger value="goals" className="flex-1">进球</TabsTrigger>
            <TabsTrigger value="stats" className="flex-1">数据</TabsTrigger>
            {result.ratings && <TabsTrigger value="ratings" className="flex-1">评分</TabsTrigger>}
            {result.replay_url && <TabsTrigger value="highlights" className="flex-1">集锦</TabsTrigger>}
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
                    {g.team_side === 'home' && <GoalName goal={g} />}
                  </div>
                  <div className="text-center text-slate-600 text-xs">{g.minute}'</div>
                  <div className="min-w-0 text-right">
                    {g.team_side === 'away' && <GoalName goal={g} align="right" />}
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
                <p className="text-center text-[10px] text-slate-500 mb-3">点击球员查看详细数据</p>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <div className="text-xs text-accent font-medium mb-2 text-center">{result.home_name}</div>
                    <div className="space-y-1.5">
                      {result.ratings.home_ratings.map((p, i) => (
                        <div key={i} className={`flex items-center justify-between px-2 py-1.5 rounded border cursor-pointer hover:opacity-80 ${ratingBg(p.rating)}`} onClick={() => { const ps = result.home_player_stats?.find(s => s.name === p.name); if (ps) setPlayerDetail({player: ps, side: "home"}) }}>
                          <div className="min-w-0 flex-1">
                            <span className="text-xs text-slate-500 mr-1">{p.position}</span>
                            <span className="text-xs truncate"><ColorText text={p.colored_name || p.name} /></span>
                          </div>
                          <span className={`text-sm font-bold ml-1 ${ratingColor(p.rating)}`}>{p.rating}</span>
                          <span className="text-slate-600 text-xs ml-1">›</span>
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-red-400 font-medium mb-2 text-center">{result.away_name}</div>
                    <div className="space-y-1.5">
                      {result.ratings.away_ratings.map((p, i) => (
                        <div key={i} className={`flex items-center justify-between px-2 py-1.5 rounded border cursor-pointer hover:opacity-80 ${ratingBg(p.rating)}`} onClick={() => { const ps = result.away_player_stats?.find(s => s.name === p.name); if (ps) setPlayerDetail({player: ps, side: "away"}) }}>
                          <div className="min-w-0 flex-1">
                            <span className="text-xs text-slate-500 mr-1">{p.position}</span>
                            <span className="text-xs truncate"><ColorText text={p.colored_name || p.name} /></span>
                          </div>
                          <span className={`text-sm font-bold ml-1 ${ratingColor(p.rating)}`}>{p.rating}</span>
                          <span className="text-slate-600 text-xs ml-1">›</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </CardContent></Card>
            </TabsContent>
          )}
          {result.replay_url && (
            <TabsContent value="highlights">
              <ReplayHighlights replayUrl={result.replay_url} />
            </TabsContent>
          )}
        </Tabs>

        <div className="flex gap-2 mt-4">
          <Button variant="secondary" className="flex-1" onClick={() => { setResult(null); resetSquadView() }}>返回</Button>
        </div>
      <Dialog open={playerDetail !== null} onOpenChange={(open) => { if (!open) setPlayerDetail(null) }}>
        <DialogContent className="max-h-[85vh] overflow-y-auto scrollbar-hide">
          {playerDetail && (
            <PlayerMatchDetail
              player={playerDetail.player}
              teamPlayers={(playerDetail.side === "home" ? result.home_player_stats : result.away_player_stats) || []}
              teamSide={playerDetail.side}
            />
          )}
        </DialogContent>
      </Dialog>
      </div>
    )
  }

  return (
    <div className="p-4">
      <h1 className="text-lg font-bold text-slate-100 mb-4 flex items-center gap-2">
        <Trophy size={20} className="text-gold" />
        每日挑战
      </h1>

      {/* NPC Info */}
      <div className="mb-5 text-center bg-gradient-to-b from-dark-card/80 to-transparent border border-dark-border rounded-xl p-5 relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_center,rgba(79,195,247,0.03),transparent_70%)]" />
        <div className="relative">
          <div className="w-16 h-16 rounded-full bg-gradient-to-br from-accent/20 to-blue-600/10 border-2 border-accent/40 flex items-center justify-center mx-auto mb-3">
            <span className="text-2xl">🏟️</span>
          </div>
          <h2 className="text-accent font-bold text-lg">{info.npc_name}</h2>
          <div className="flex items-center justify-center gap-1 mt-2">
            <Zap size={14} className="text-gold" />
            <span className="text-slate-400 text-sm">剩余次数:</span>
            <span className="text-gold font-bold">{info.times_left}</span>
          </div>
        </div>
      </div>

      {/* Difficulties */}
      <p className="text-slate-400 text-sm mb-2 font-medium">选择难度</p>
      <div className="space-y-2">
        {info.difficulties.map(d => {
          const colorClass = DIFF_COLORS[d.key] || 'from-slate-500/20 to-slate-900/10 border-slate-500/30'
          return (
            <div
              key={d.key}
              className={`rounded-xl border bg-gradient-to-r ${colorClass} p-4 flex items-center justify-between cursor-pointer hover:scale-[1.01] transition-transform`}
              onClick={() => viewNpcSquad(d.key)}
            >
              <div className="flex items-center gap-3">
                <span className="text-slate-100 font-bold">{d.key}</span>
                <div className="flex gap-0.5">
                  {Array.from({ length: Math.min(d.star, 5) }).map((_, i) => (
                    <div key={i} className="w-2 h-2 bg-gold rotate-45" />
                  ))}
                  {d.star > 5 && <span className="text-[9px] text-gold ml-0.5">×{d.star}</span>}
                </div>
              </div>
              <Button size="sm" disabled={loading || info.times_left <= 0} className="bg-gold/80 text-black hover:bg-gold font-bold text-xs" onClick={(e) => { e.stopPropagation(); play(d.key) }}>
                {loading ? '...' : '开赛'}
              </Button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
