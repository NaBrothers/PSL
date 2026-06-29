import React, { useState, useEffect, createContext, useContext } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import './index.css'
import { Button } from '@/components/ui/button'
import { Home, Shield, Swords, Backpack, Menu } from 'lucide-react'
import LoginPage from './pages/LoginPage'
import HomePage from './pages/HomePage'
import SquadPage from './pages/SquadPage'
import MatchPage from './pages/MatchPage'
import BagPage from './pages/BagPage'
import LotteryPage from './pages/LotteryPage'
import TransferPage from './pages/TransferPage'
import LeaguePage from './pages/LeaguePage'
import ChallengePage from './pages/ChallengePage'
import SearchPage from './pages/SearchPage'
import InboxPage from './pages/InboxPage'
import AdminPage from './pages/AdminPage'
import { ToastProvider } from '@/components/AppToast'
import StatusHeader from '@/components/StatusHeader'
import api from './api/client'


interface AuthCtx {
  token: string | null
  setToken: (t: string | null) => void
}

const AuthContext = createContext<AuthCtx>({ token: null, setToken: () => {} })
export function useAuth() { return useContext(AuthContext) }

function TabBar() {
  const navigate = useNavigate()
  const location = useLocation()
  const tabs = [
    { path: '/home', label: '首页', icon: Home },
    { path: '/squad', label: '球队', icon: Shield },
    { path: '/match', label: '比赛', icon: Swords },
    { path: '/bag', label: '背包', icon: Backpack },
    { path: '/more', label: '更多', icon: Menu },
  ]

  if (location.pathname === '/login') return null

  return (
    <nav className="sticky bottom-0 h-16 bg-gradient-to-t from-[#070b16] via-[#0c1222]/98 to-[#0c1222]/90 backdrop-blur-md border-t border-gold/20 flex z-50">
      {tabs.map(t => {
        const active = location.pathname === t.path
        const Icon = t.icon
        return (
          <button
            key={t.path}
            onClick={() => navigate(t.path)}
            className={`flex-1 h-full flex flex-col items-center justify-center gap-0.5 relative transition-all ${
              active ? 'text-gold-light' : 'text-slate-500'
            }`}
          >
            {active && (
              <div className="absolute top-0 left-1/2 -translate-x-1/2 w-8 h-0.5 bg-gradient-to-r from-transparent via-gold-light to-transparent rounded-full transition-all duration-300" />
            )}
            <div className={`transition-transform duration-200 ${active ? 'scale-110 -translate-y-0.5' : 'scale-100'}`}>
              <Icon size={20} strokeWidth={active ? 2.5 : 1.5} />
            </div>
            <span className="text-[10px] font-medium">{t.label}</span>
          </button>
        )
      })}
    </nav>
  )
}

function MorePage() {
  const navigate = useNavigate()
  const { setToken } = useAuth()
  const [isAdmin, setIsAdmin] = useState(false)
  useEffect(() => { api.get('/admin/stats').then(() => setIsAdmin(true)).catch(() => {}) }, [])
  const pages = [
    { path: '/lottery', label: '抽卡', desc: '开启卡包获取球员' },
    { path: '/transfer', label: '转会市场', desc: '买卖球员卡' },
    { path: '/league', label: '联赛', desc: '查看积分榜和赛程' },
    { path: '/challenge', label: '每日挑战', desc: '挑战NPC赢取奖励' },
    { path: '/search', label: '全局查询', desc: '搜索全服球员卡' },
    ...(isAdmin ? [{ path: '/admin', label: '管理后台', desc: '系统配置与管理' }] : []),
  ]
  return (
    <div className="p-4 relative z-10">
      <h1 className="text-lg font-bold text-slate-100 mb-4">更多</h1>
      <div className="space-y-2">
        {pages.map(p => (
          <div
            key={p.path}
            className="bg-dark-card/80 border border-dark-border rounded-xl p-4 flex items-center justify-between cursor-pointer hover:border-gold/30 transition-colors"
            onClick={() => navigate(p.path)}
          >
            <div>
              <span className="text-slate-200 font-medium text-sm">{p.label}</span>
              <p className="text-slate-500 text-xs mt-0.5">{p.desc}</p>
            </div>
            <span className="text-gold/60 text-lg">›</span>
          </div>
        ))}
      </div>
      <Button
        variant="outline"
        className="w-full mt-6 text-red-400 border-red-900/50 hover:bg-red-950/30"
        onClick={() => { setToken(null); navigate('/login') }}
      >
        退出登录
      </Button>
    </div>
  )
}

function App() {
  const [token, setToken] = useState<string | null>(localStorage.getItem('psl_token'))

  const handleSetToken = (t: string | null) => {
    if (t) {
      localStorage.setItem('psl_token', t)
    } else {
      localStorage.removeItem('psl_token')
    }
    setToken(t)
  }

  return (
    <AuthContext.Provider value={{ token, setToken: handleSetToken }}>
      <ToastProvider>
        <BrowserRouter>
          <div className="flex flex-col h-full overflow-hidden">
            <StatusHeader />
            <div className="flex-1 overflow-y-auto scrollbar-hide relative z-10">
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route path="/home" element={token ? <HomePage /> : <Navigate to="/login" />} />
                <Route path="/squad" element={token ? <SquadPage /> : <Navigate to="/login" />} />
                <Route path="/match" element={token ? <MatchPage /> : <Navigate to="/login" />} />
                <Route path="/bag" element={token ? <BagPage /> : <Navigate to="/login" />} />
                <Route path="/lottery" element={token ? <LotteryPage /> : <Navigate to="/login" />} />
                <Route path="/transfer" element={token ? <TransferPage /> : <Navigate to="/login" />} />
                <Route path="/league" element={token ? <LeaguePage /> : <Navigate to="/login" />} />
                <Route path="/challenge" element={token ? <ChallengePage /> : <Navigate to="/login" />} />
                <Route path="/search" element={token ? <SearchPage /> : <Navigate to="/login" />} />
                <Route path="/inbox" element={token ? <InboxPage /> : <Navigate to="/login" />} />
                <Route path="/admin" element={token ? <AdminPage /> : <Navigate to="/login" />} />
                <Route path="/more" element={token ? <MorePage /> : <Navigate to="/login" />} />
                <Route path="*" element={<Navigate to={token ? "/home" : "/login"} />} />
              </Routes>
            </div>
            <TabBar />
          </div>
        </BrowserRouter>
      </ToastProvider>
    </AuthContext.Provider>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
