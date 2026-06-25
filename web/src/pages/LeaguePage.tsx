import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import api from '../api/client'
import { useToast } from '@/components/AppToast'

interface Standing {
  name: string
  played: number
  points: number
  wins: number
  draws: number
  losses: number
  goals_for: number
  goals_against: number
  goal_diff: number
}

interface ScheduleEntry {
  id: number
  round: number
  home_name: string
  away_name: string
  finished: boolean
  home_goal: number
  away_goal: number
}

export default function LeaguePage() {
  const [standings, setStandings] = useState<Standing[]>([])
  const [schedule, setSchedule] = useState<ScheduleEntry[]>([])
  const [stats, setStats] = useState<any>(null)
  const { showToast } = useToast()

  useEffect(() => {
    api.get('/league').then(res => setStandings(res.data.standings))
    api.get('/league/schedule').then(res => setSchedule(res.data.schedule)).catch(() => {})
    api.get('/league/stats').then(res => setStats(res.data)).catch(() => {})
  }, [])

  const register = async () => {
    try {
      await api.post('/league/register')
      showToast('报名成功！')
      api.get('/league').then(res => setStandings(res.data.standings))
    } catch (e: any) {
      showToast(e.response?.data?.detail || '报名失败')
    }
  }

  return (
    <div className="bg-dark p-4">
      <div className="max-w-md mx-auto">
        <div className="flex items-center justify-between mb-4">
          <h1 className="text-lg font-bold text-slate-100">联赛</h1>
          <Button size="sm" onClick={register}>报名</Button>
        </div>

        <Tabs defaultValue="standings" className="w-full">
          <TabsList className="w-full">
            <TabsTrigger value="standings" className="flex-1">积分榜</TabsTrigger>
            <TabsTrigger value="schedule" className="flex-1">赛程</TabsTrigger>
            <TabsTrigger value="stats" className="flex-1">数据榜</TabsTrigger>
          </TabsList>

          <TabsContent value="standings">
            {standings.length === 0 ? (
              <div className="text-center py-8 text-slate-500">暂无联赛数据</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-500 border-b border-slate-800">
                      <th className="text-left py-2 w-6">#</th>
                      <th className="text-left">球队</th>
                      <th className="text-center w-6">场</th>
                      <th className="text-center w-6">胜</th>
                      <th className="text-center w-6">平</th>
                      <th className="text-center w-6">负</th>
                      <th className="text-center w-8">净胜</th>
                      <th className="text-center w-8">积分</th>
                    </tr>
                  </thead>
                  <tbody>
                    {standings.map((s, i) => (
                      <tr key={i} className="border-b border-slate-800/50 text-slate-300">
                        <td className="py-2 text-slate-500">{i + 1}</td>
                        <td className="text-slate-100 font-medium">{s.name}</td>
                        <td className="text-center">{s.played}</td>
                        <td className="text-center text-green-400">{s.wins}</td>
                        <td className="text-center text-yellow-400">{s.draws}</td>
                        <td className="text-center text-red-400">{s.losses}</td>
                        <td className="text-center">{s.goal_diff > 0 ? '+' : ''}{s.goal_diff}</td>
                        <td className="text-center text-accent font-bold">{s.points}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </TabsContent>

          <TabsContent value="schedule">
            {schedule.length === 0 ? (
              <div className="text-center py-8 text-slate-500">暂无赛程</div>
            ) : (
              <div className="space-y-2">
                {schedule.map(s => (
                  <Card key={s.id}>
                    <CardContent className="p-3 flex items-center justify-between">
                      <div className="text-xs text-slate-500">R{s.round}</div>
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-slate-200">{s.home_name}</span>
                        {s.finished ? (
                          <span className="text-accent font-bold">{s.home_goal} - {s.away_goal}</span>
                        ) : (
                          <span className="text-slate-600">vs</span>
                        )}
                        <span className="text-slate-200">{s.away_name}</span>
                      </div>
                      <div className="text-xs">{s.finished ? <span className="text-slate-500">已结束</span> : <span className="text-green-400">待踢</span>}</div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          <TabsContent value="stats">
            {!stats ? (
              <div className="text-center py-8 text-slate-500">暂无数据</div>
            ) : (
              <div className="space-y-4">
                <div>
                  <h3 className="text-sm text-slate-400 mb-2">射手榜</h3>
                  {stats.top_scorers.map((s: any, i: number) => (
                    <div key={i} className="flex items-center justify-between py-1 text-sm">
                      <span className="text-slate-500 w-5">{i+1}</span>
                      <span className="text-slate-200 flex-1">{s.player}</span>
                      <span className="text-slate-500 text-xs mr-2">{s.owner}</span>
                      <span className="text-accent font-bold">{s.goals}</span>
                    </div>
                  ))}
                </div>
                <div>
                  <h3 className="text-sm text-slate-400 mb-2">助攻榜</h3>
                  {stats.top_assists.map((s: any, i: number) => (
                    <div key={i} className="flex items-center justify-between py-1 text-sm">
                      <span className="text-slate-500 w-5">{i+1}</span>
                      <span className="text-slate-200 flex-1">{s.player}</span>
                      <span className="text-slate-500 text-xs mr-2">{s.owner}</span>
                      <span className="text-accent font-bold">{s.assists}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </TabsContent>
        </Tabs>
      </div>
    </div>
  )
}
