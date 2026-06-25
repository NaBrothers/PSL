import React, { useState, createContext, useContext } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom'
import './index.css'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
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
import { ToastProvider } from '@/components/AppToast'

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
    { path: '/home', label: '首页' },
    { path: '/squad', label: '球队' },
    { path: '/match', label: '比赛' },
    { path: '/bag', label: '背包' },
    { path: '/more', label: '更多' },
  ]

  if (location.pathname === '/login') return null

  return (
    <nav className="sticky bottom-0 h-16 bg-slate-900 border-t border-slate-800 flex z-50">
      {tabs.map(t => (
        <button
          key={t.path}
          onClick={() => navigate(t.path)}
          className={`flex-1 h-full text-sm font-medium transition-colors ${
            location.pathname === t.path ? 'text-accent' : 'text-slate-500'
          }`}
        >
          {t.label}
        </button>
      ))}
    </nav>
  )
}

function MorePage() {
  const navigate = useNavigate()
  const { setToken } = useAuth()
  const pages = [
    { path: '/lottery', label: '抽卡' },
    { path: '/transfer', label: '转会市场' },
    { path: '/league', label: '联赛' },
    { path: '/challenge', label: '每日挑战' },
    { path: '/search', label: '全局查询' },
  ]
  return (
    <div className="bg-dark p-4">
      <div className="max-w-md mx-auto">
        <h1 className="text-lg font-bold text-slate-100 mb-4">更多</h1>
        <div className="space-y-2">
          {pages.map(p => (
            <Card key={p.path} className="cursor-pointer hover:border-slate-600 transition-colors" onClick={() => navigate(p.path)}>
              <CardContent className="p-4 flex items-center justify-between">
                <span className="text-slate-200 font-medium text-sm">{p.label}</span>
                <span className="text-slate-600">→</span>
              </CardContent>
            </Card>
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
            <div className="flex-1 overflow-y-auto scrollbar-hide">
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
