import { useState, useEffect } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import api from '../api/client'
import { useToast } from '@/components/AppToast'

interface ConfigItem { key: string; label: string; type: string; value: any; default: any }
interface ConfigGroup { name: string; items: ConfigItem[] }
interface PlayerInfo { id: number; qq: number; name: string; level: number; money: number; is_admin: boolean; card_count: number }

export default function AdminPage() {
  const [configGroups, setConfigGroups] = useState<ConfigGroup[]>([])
  const [players, setPlayers] = useState<PlayerInfo[]>([])
  const [stats, setStats] = useState<any>(null)
  const [broadcastTitle, setBroadcastTitle] = useState('')
  const [broadcastContent, setBroadcastContent] = useState('')
  const [packQQ, setPackQQ] = useState('')
  const [packPool, setPackPool] = useState('初级')
  const [packCount, setPackCount] = useState('1')
  const [moneyQQ, setMoneyQQ] = useState('')
  const [moneyAmount, setMoneyAmount] = useState('')
  const [moneyAction, setMoneyAction] = useState('add')
  const { showToast } = useToast()

  useEffect(() => {
    api.get('/admin/config').then(r => setConfigGroups(r.data.groups)).catch(() => showToast('无管理员权限'))
    api.get('/admin/players').then(r => setPlayers(r.data)).catch(() => {})
    api.get('/admin/stats').then(r => setStats(r.data)).catch(() => {})
  }, [])

  const updateConfig = async (key: string, value: any, type: string) => {
    const parsed = type === 'float' ? parseFloat(value) : parseInt(value)
    if (isNaN(parsed)) return
    await api.post('/admin/config', { key, value: parsed })
    showToast(`${key} 已更新`)
    api.get('/admin/config').then(r => setConfigGroups(r.data.groups))
  }

  const sendBroadcast = async () => {
    if (!broadcastTitle) return
    await api.post('/admin/broadcast', { title: broadcastTitle, content: broadcastContent })
    showToast('广播已发送')
    setBroadcastTitle(''); setBroadcastContent('')
  }

  const distributePacks = async () => {
    const qq = packQQ ? parseInt(packQQ) : undefined
    const res = await api.post('/admin/distribute-packs', { qq: qq || null, pool_key: packPool, count: parseInt(packCount) })
    showToast(`已发放给 ${res.data.total} 人`)
  }

  const modifyMoney = async () => {
    if (!moneyQQ || !moneyAmount) return
    await api.post('/admin/players/money', { qq: parseInt(moneyQQ), amount: parseInt(moneyAmount), action: moneyAction })
    showToast('金币已修改')
    api.get('/admin/players').then(r => setPlayers(r.data))
  }

  return (
    <div className="p-4">
      <h1 className="text-lg font-bold text-slate-100 mb-4">管理后台</h1>

      <Tabs defaultValue="stats" className="w-full">
        <TabsList className="w-full mb-3">
          <TabsTrigger value="stats" className="flex-1 text-xs">总览</TabsTrigger>
          <TabsTrigger value="config" className="flex-1 text-xs">配置</TabsTrigger>
          <TabsTrigger value="players" className="flex-1 text-xs">玩家</TabsTrigger>
          <TabsTrigger value="actions" className="flex-1 text-xs">操作</TabsTrigger>
        </TabsList>

        <TabsContent value="stats">
          {stats && (
            <div className="grid grid-cols-2 gap-3">
              <Card><CardContent className="p-3 text-center">
                <div className="text-2xl font-bold text-accent">{stats.players.total}</div>
                <div className="text-xs text-slate-500">玩家数</div>
              </CardContent></Card>
              <Card><CardContent className="p-3 text-center">
                <div className="text-2xl font-bold text-gold">${(stats.players.total_money / 10000).toFixed(1)}万</div>
                <div className="text-xs text-slate-500">全服总金币</div>
              </CardContent></Card>
              <Card><CardContent className="p-3 text-center">
                <div className="text-2xl font-bold text-green-400">{stats.cards.total}</div>
                <div className="text-xs text-slate-500">总卡片数</div>
              </CardContent></Card>
              <Card><CardContent className="p-3 text-center">
                <div className="text-2xl font-bold text-purple-400">{stats.cards.avg_star}★</div>
                <div className="text-xs text-slate-500">平均星级</div>
              </CardContent></Card>
              <Card><CardContent className="p-3 text-center">
                <div className="text-2xl font-bold text-orange-400">${stats.players.avg_money.toLocaleString()}</div>
                <div className="text-xs text-slate-500">人均金币</div>
              </CardContent></Card>
              <Card><CardContent className="p-3 text-center">
                <div className="text-2xl font-bold text-blue-400">{stats.market.listings}</div>
                <div className="text-xs text-slate-500">市场挂牌数</div>
              </CardContent></Card>
            </div>
          )}
        </TabsContent>

        <TabsContent value="config">
          <div className="space-y-4 max-h-[60vh] overflow-y-auto scrollbar-hide">
            {configGroups.map(group => (
              <div key={group.name}>
                <h3 className="text-sm font-bold text-slate-300 mb-2">{group.name}</h3>
                <div className="space-y-1.5">
                  {group.items.map(item => (
                    <div key={item.key} className="flex items-center gap-2">
                      <span className="text-xs text-slate-400 flex-1 min-w-0 truncate">{item.label}</span>
                      <Input
                        type="number"
                        defaultValue={item.value}
                        className="w-24 h-7 text-xs"
                        onBlur={e => {
                          if (e.target.value !== String(item.value)) updateConfig(item.key, e.target.value, item.type)
                        }}
                      />
                      {item.value !== item.default && <span className="text-[9px] text-orange-400">已改</span>}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="players">
          <div className="space-y-1.5 max-h-[60vh] overflow-y-auto scrollbar-hide">
            {players.map(p => (
              <Card key={p.id}>
                <CardContent className="p-2 flex items-center gap-2 text-xs">
                  <span className="text-slate-200 font-medium flex-1">{p.name}</span>
                  <span className="text-slate-500">QQ:{p.qq}</span>
                  <span className="text-gold">${p.money.toLocaleString()}</span>
                  <span className="text-slate-500">{p.card_count}卡</span>
                  {p.is_admin && <span className="text-red-400 text-[9px]">管理员</span>}
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="actions">
          <div className="space-y-4">
            {/* Money */}
            <Card><CardContent className="p-3">
              <h3 className="text-sm font-bold text-slate-300 mb-2">修改金币</h3>
              <div className="flex gap-2 items-end">
                <Input placeholder="QQ" value={moneyQQ} onChange={e => setMoneyQQ(e.target.value)} className="flex-1 h-8 text-xs" />
                <select value={moneyAction} onChange={e => setMoneyAction(e.target.value)} className="h-8 bg-slate-800 border border-slate-700 rounded text-xs px-2">
                  <option value="add">增加</option>
                  <option value="set">设为</option>
                </select>
                <Input placeholder="金额" value={moneyAmount} onChange={e => setMoneyAmount(e.target.value)} className="w-24 h-8 text-xs" />
                <Button size="sm" onClick={modifyMoney}>确认</Button>
              </div>
            </CardContent></Card>

            {/* Broadcast */}
            <Card><CardContent className="p-3">
              <h3 className="text-sm font-bold text-slate-300 mb-2">系统广播</h3>
              <Input placeholder="标题" value={broadcastTitle} onChange={e => setBroadcastTitle(e.target.value)} className="mb-2 h-8 text-xs" />
              <Input placeholder="内容（可选）" value={broadcastContent} onChange={e => setBroadcastContent(e.target.value)} className="mb-2 h-8 text-xs" />
              <Button size="sm" onClick={sendBroadcast}>发送广播</Button>
            </CardContent></Card>

            {/* Pack distribution */}
            <Card><CardContent className="p-3">
              <h3 className="text-sm font-bold text-slate-300 mb-2">发放卡包</h3>
              <div className="flex gap-2 items-end">
                <Input placeholder="QQ（空=全服）" value={packQQ} onChange={e => setPackQQ(e.target.value)} className="flex-1 h-8 text-xs" />
                <select value={packPool} onChange={e => setPackPool(e.target.value)} className="h-8 bg-slate-800 border border-slate-700 rounded text-xs px-2">
                  <option value="初级">初级</option>
                  <option value="中级">中级</option>
                  <option value="高级">高级</option>
                </select>
                <Input placeholder="数量" value={packCount} onChange={e => setPackCount(e.target.value)} className="w-16 h-8 text-xs" />
                <Button size="sm" onClick={distributePacks}>发放</Button>
              </div>
            </CardContent></Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
