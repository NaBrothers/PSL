import { useState, useEffect, useRef, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Play, Pause, SkipForward, SkipBack, Maximize2 } from 'lucide-react'

interface ReplayFrame {
  type: string
  t: number
  half: number
  home: [number, number][]
  away: [number, number][]
  ball_holder: number | null
  ball_team: string | null
  score: [number, number]
  ball_flight?: { from: [number, number]; to: [number, number]; path?: [number, number][]; type: string; on_target?: boolean }
  event_text?: string
  pause_ms?: number
  cut?: boolean
}

interface ReplayHeader {
  type: 'header'
  home: { name: string; players: { name: string; pos: string; color: string }[] }
  away: { name: string; players: { name: string; pos: string; color: string }[] }
  field: { width: number; length: number }
}

type ReplayLine = ReplayHeader | ReplayFrame

interface Clip { label: string; startIdx: number; endIdx: number }
interface Props { replayUrl: string }

const PITCH_W = 68, PITCH_H = 105
const CANVAS_W = 300, CANVAS_H = Math.round(CANVAS_W * (PITCH_H / PITCH_W))
const SCALE_X = CANVAS_W / PITCH_W, SCALE_Y = CANVAS_H / PITCH_H
const PLAYER_R = 7, BALL_R = 4

const COLOR_MAP: Record<string, string> = { w:'#b8b8b8', g:'#4caf50', b:'#4fc3f7', p:'#b45cff', o:'#ff9800', r:'#ef5350', f:'#ff69b4', x:'#a52a2a', '$':'#fbbf24' }

function lerp(a: number, b: number, t: number) { return a + (b - a) * t }

function extractHighlights(frames: ReplayFrame[]): Clip[] {
  const clips: Clip[] = []
  for (let i = 0; i < frames.length; i++) {
    const f = frames[i]
    if (f.event_text === 'GOAL' || f.event_text === 'SAVE') {
      const startIdx = Math.max(0, i - 10), endIdx = i
      const minute = Math.floor(f.t / 60)
      const label = f.event_text === 'GOAL' ? `⚽ ${minute}' 进球 [${f.score[0]}-${f.score[1]}]` : `🧤 ${minute}' 扑救`
      if (clips.length > 0 && clips[clips.length - 1].endIdx >= startIdx - 2) { clips[clips.length - 1].endIdx = endIdx }
      else { clips.push({ label, startIdx, endIdx }) }
    }
  }
  return clips
}

function resolveReplayFileUrl(url: string): string {
  try { const u = new URL(url, window.location.origin); const path = u.searchParams.get("path"); if (path) return `/replays/${path}` } catch {}
  return url
}

export default function ReplayHighlights({ replayUrl }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [header, setHeader] = useState<ReplayHeader | null>(null)
  const [frames, setFrames] = useState<ReplayFrame[]>([])
  const [clips, setClips] = useState<Clip[]>([])
  const [currentClip, setCurrentClip] = useState(0)
  const [frameIdx, setFrameIdx] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [loading, setLoading] = useState(true)
  const [fullReplay, setFullReplay] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [singleClip, setSingleClip] = useState(false)

  const playingRef = useRef(false)
  const frameIdxRef = useRef(0)
  const headerRef = useRef<ReplayHeader | null>(null)
  const framesRef = useRef<ReplayFrame[]>([])
  const speedRef = useRef(1)
  const animRef = useRef(0)
  const lastRenderTimeRef = useRef(0)
  const currentFramesRef = useRef({ start: 0, end: 0 })
  const currentClipRef = useRef(0)
  const clipsRef = useRef<Clip[]>([])
  const fullReplayRef = useRef(false)
  const singleClipRef = useRef(false)

  useEffect(() => { playingRef.current = playing }, [playing])
  useEffect(() => { frameIdxRef.current = frameIdx }, [frameIdx])
  useEffect(() => { headerRef.current = header }, [header])
  useEffect(() => { framesRef.current = frames }, [frames])
  useEffect(() => { speedRef.current = speed }, [speed])
  useEffect(() => { currentClipRef.current = currentClip }, [currentClip])
  useEffect(() => { clipsRef.current = clips }, [clips])
  useEffect(() => { fullReplayRef.current = fullReplay }, [fullReplay])
  useEffect(() => { singleClipRef.current = singleClip }, [singleClip])

  useEffect(() => {
    fetch(resolveReplayFileUrl(replayUrl)).then(r => r.text()).then(text => {
      const parsed = text.trim().split('\n').map(l => JSON.parse(l)) as ReplayLine[]
      const h = parsed.find(l => l.type === 'header') as ReplayHeader
      const f = parsed.filter(l => l.type === 'frame') as ReplayFrame[]
      setHeader(h); setFrames(f)
      const hl = extractHighlights(f); setClips(hl); setLoading(false)
      if (hl.length > 0) { setFrameIdx(hl[0].startIdx); setPlaying(true) }
    })
  }, [replayUrl])

  const currentFrames = fullReplay ? { start: 0, end: frames.length - 1 } : clips[currentClip] ? { start: clips[currentClip].startIdx, end: clips[currentClip].endIdx } : { start: 0, end: 0 }
  useEffect(() => { currentFramesRef.current = currentFrames })

  const getInterval = useCallback((idx: number): number => {
    const f = framesRef.current
    if (idx >= f.length - 1) return 500
    const frame = f[idx]
    if (frame.pause_ms && (frame.ball_flight || frame.event_text)) return frame.pause_ms / speedRef.current
    const nextFrame = f[idx + 1]
    const raw = (nextFrame.t - frame.t) * 1000
    const base = raw === 0 ? (nextFrame.pause_ms || 300) : Math.max(100, Math.min(2000, raw))
    return Math.max(40, base / speedRef.current)
  }, [])

  const drawFrame = useCallback((idx: number, interpT: number = 0) => {
    const canvas = canvasRef.current, h = headerRef.current, f = framesRef.current
    if (!canvas || !h || f.length === 0) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const frame = f[idx]
    if (!frame) return

    let home = frame.home, away = frame.away
    if (idx < f.length - 1 && interpT > 0 && !frame.cut && !f[idx + 1].cut) {
      const nxt = f[idx + 1]
      home = frame.home.map((p, i) => [lerp(p[0], nxt.home[i][0], interpT), lerp(p[1], nxt.home[i][1], interpT)] as [number, number])
      away = frame.away.map((p, i) => [lerp(p[0], nxt.away[i][0], interpT), lerp(p[1], nxt.away[i][1], interpT)] as [number, number])
    }

    // Field
    ctx.fillStyle = '#2d5a27'; ctx.fillRect(0, 0, CANVAS_W, CANVAS_H)
    ctx.strokeStyle = 'rgba(255,255,255,0.3)'; ctx.lineWidth = 1
    ctx.beginPath(); ctx.moveTo(0, CANVAS_H/2); ctx.lineTo(CANVAS_W, CANVAS_H/2); ctx.stroke()
    ctx.beginPath(); ctx.arc(CANVAS_W/2, CANVAS_H/2, 9.15*SCALE_X, 0, Math.PI*2); ctx.stroke()
    const boxW = 40.32*SCALE_X, boxH = 16.5*SCALE_Y
    ctx.strokeRect((CANVAS_W-boxW)/2, 0, boxW, boxH); ctx.strokeRect((CANVAS_W-boxW)/2, CANVAS_H-boxH, boxW, boxH)
    const sixW = 18.32*SCALE_X, sixH = 5.5*SCALE_Y
    ctx.strokeRect((CANVAS_W-sixW)/2, 0, sixW, sixH); ctx.strokeRect((CANVAS_W-sixW)/2, CANVAS_H-sixH, sixW, sixH)
    ctx.fillStyle = 'rgba(255,255,255,0.5)'; const goalW = 7.32*SCALE_X
    ctx.fillRect((CANVAS_W-goalW)/2, 0, goalW, 3); ctx.fillRect((CANVAS_W-goalW)/2, CANVAS_H-3, goalW, 3)

    // Players
    for (let i = 0; i < home.length; i++) {
      const sx = home[i][0]*SCALE_X, sy = home[i][1]*SCALE_Y
      const hl = frame.ball_team === 'home' && frame.ball_holder === i
      ctx.beginPath(); ctx.arc(sx, sy, PLAYER_R, 0, Math.PI*2)
      ctx.fillStyle = hl ? '#fbbf24' : '#4fc3f7'; ctx.fill()
      ctx.strokeStyle = hl ? '#fff' : 'rgba(255,255,255,0.4)'; ctx.lineWidth = hl ? 2 : 1; ctx.stroke()
      ctx.font = '8px sans-serif'; ctx.textAlign = 'center'
      ctx.fillStyle = COLOR_MAP[h.home.players[i]?.color||'b']||'#4fc3f7'
      ctx.fillText(h.home.players[i]?.name.split(' ').pop()||'', sx, sy-PLAYER_R-2)
    }
    for (let i = 0; i < away.length; i++) {
      const sx = away[i][0]*SCALE_X, sy = away[i][1]*SCALE_Y
      const hl = frame.ball_team === 'away' && frame.ball_holder === i
      ctx.beginPath(); ctx.arc(sx, sy, PLAYER_R, 0, Math.PI*2)
      ctx.fillStyle = hl ? '#fbbf24' : '#ef5350'; ctx.fill()
      ctx.strokeStyle = hl ? '#fff' : 'rgba(255,255,255,0.4)'; ctx.lineWidth = hl ? 2 : 1; ctx.stroke()
      ctx.font = '8px sans-serif'; ctx.textAlign = 'center'
      ctx.fillStyle = COLOR_MAP[h.away.players[i]?.color||'r']||'#ef5350'
      ctx.fillText(h.away.players[i]?.name.split(' ').pop()||'', sx, sy-PLAYER_R-2)
    }

    // Ball
    let ballX: number, ballY: number
    if (frame.ball_flight) {
      const bf = frame.ball_flight, path = bf.path || [bf.from, bf.to]
      const p = Math.min(interpT, 1), segCount = path.length-1
      const scaled = Math.min(p*segCount, segCount-0.0001), seg = Math.floor(scaled), local = scaled-seg
      ballX = lerp(path[seg][0], path[seg+1][0], local); ballY = lerp(path[seg][1], path[seg+1][1], local)
      let trailColor = 'rgba(255,255,255,0.3)'
      if (bf.type === 'shot') trailColor = bf.on_target ? '#ff7043' : '#888'
      ctx.beginPath(); ctx.moveTo(path[0][0]*SCALE_X, path[0][1]*SCALE_Y)
      for (let i = 1; i < path.length; i++) ctx.lineTo(path[i][0]*SCALE_X, path[i][1]*SCALE_Y)
      ctx.strokeStyle = trailColor; ctx.lineWidth = 1.5; ctx.setLineDash([3,3]); ctx.stroke(); ctx.setLineDash([])
    } else {
      const holder = frame.ball_team==='home' ? home[frame.ball_holder!] : frame.ball_team==='away' ? away[frame.ball_holder!] : null
      if (holder) { ballX = holder[0]; ballY = holder[1] } else { ballX = PITCH_W/2; ballY = PITCH_H/2 }
    }
    ctx.beginPath(); ctx.arc(ballX*SCALE_X, ballY*SCALE_Y, BALL_R, 0, Math.PI*2)
    ctx.fillStyle = '#fff'; ctx.fill(); ctx.strokeStyle = '#000'; ctx.lineWidth = 0.5; ctx.stroke()

    // Event overlay
    if (frame.event_text === 'GOAL') {
      ctx.fillStyle = 'rgba(0,0,0,0.6)'; ctx.fillRect(0, CANVAS_H/2-18, CANVAS_W, 36)
      ctx.fillStyle = '#4ade80'; ctx.font = 'bold 16px sans-serif'; ctx.textAlign = 'center'
      ctx.fillText('⚽ GOAL', CANVAS_W/2, CANVAS_H/2+5)
    } else if (frame.event_text === 'SAVE') {
      ctx.fillStyle = 'rgba(0,0,0,0.5)'; ctx.fillRect(0, CANVAS_H/2-14, CANVAS_W, 28)
      ctx.fillStyle = '#facc15'; ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'center'
      ctx.fillText('🧤 SAVE', CANVAS_W/2, CANVAS_H/2+4)
    }

    // HUD
    ctx.fillStyle = 'rgba(0,0,0,0.5)'; ctx.fillRect(0, 0, CANVAS_W, 20)
    ctx.fillStyle = '#fff'; ctx.font = '10px sans-serif'; ctx.textAlign = 'center'
    const mins = Math.floor(frame.t/60), halfLabel = frame.half===1 ? '' : '45+'
    ctx.fillText(`${h.home.name} ${frame.score[0]} - ${frame.score[1]} ${h.away.name}  ${halfLabel}${mins}'`, CANVAS_W/2, 14)
  }, [])

  // Animation loop
  useEffect(() => {
    if (!playing) { cancelAnimationFrame(animRef.current); return }
    lastRenderTimeRef.current = 0
    const loop = (ts: number) => {
      if (!playingRef.current) return
      if (!lastRenderTimeRef.current) lastRenderTimeRef.current = ts
      const elapsed = ts - lastRenderTimeRef.current
      const interval = getInterval(frameIdxRef.current)
      const interpT = Math.min(elapsed / interval, 1)
      drawFrame(frameIdxRef.current, interpT)
      if (elapsed >= interval) {
        lastRenderTimeRef.current = ts
        const nextIdx = frameIdxRef.current + 1
        if (nextIdx > currentFramesRef.current.end) {
          if (!fullReplayRef.current && !singleClipRef.current && currentClipRef.current < clipsRef.current.length-1) {
            const next = currentClipRef.current + 1; setCurrentClip(next); setFrameIdx(clipsRef.current[next].startIdx)
          } else { setPlaying(false); setSingleClip(false) }
          return
        }
        setFrameIdx(nextIdx)
      }
      animRef.current = requestAnimationFrame(loop)
    }
    animRef.current = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(animRef.current)
  }, [playing, getInterval, drawFrame])

  useEffect(() => { if (!playing) drawFrame(frameIdx, 0) }, [frameIdx, playing, drawFrame])

  const goToClip = (idx: number) => { setPlaying(false); setTimeout(() => { setCurrentClip(idx); setFrameIdx(clips[idx].startIdx); setSingleClip(true); setPlaying(true) }, 0) }

  if (loading) return <div className="text-center text-slate-500 text-sm py-8">加载回放数据...</div>
  if (clips.length === 0 && !fullReplay) return (
    <div className="text-center py-8">
      <p className="text-slate-500 text-sm mb-3">本场没有精彩集锦</p>
      <Button variant="ghost" size="sm" className="text-xs text-slate-500" onClick={() => { setFullReplay(true); setFrameIdx(0) }}><Maximize2 size={12} className="mr-1" />查看完整回放</Button>
    </div>
  )

  return (
    <div className="flex flex-col items-center gap-3">
      <canvas ref={canvasRef} width={CANVAS_W} height={CANVAS_H} className="rounded-lg border border-slate-700 shadow-lg" style={{ width: '100%', maxWidth: 300 }} />
      <div className="flex items-center gap-2">
        <Button variant="ghost" size="sm" onClick={() => setFrameIdx(Math.max(currentFrames.start, frameIdx-5))}><SkipBack size={14} /></Button>
        <Button variant="outline" size="sm" onClick={() => setPlaying(!playing)}>{playing ? <Pause size={14} /> : <Play size={14} />}</Button>
        <Button variant="ghost" size="sm" onClick={() => { if (!fullReplay && currentClip < clips.length-1) goToClip(currentClip+1); else setFrameIdx(Math.min(currentFrames.end, frameIdx+5)) }}><SkipForward size={14} /></Button>
        <div className="flex gap-1 ml-2">
          {[1,2,4].map(s => <Button key={s} variant={speed===s?'default':'ghost'} size="sm" className="text-[10px] px-2 h-6" onClick={() => setSpeed(s)}>{s}x</Button>)}
        </div>
      </div>
      {fullReplay && frames.length > 0 && (
        <input type="range" min={0} max={frames.length - 1} value={frameIdx} className="w-full max-w-[300px] h-1 cursor-pointer accent-accent"
          onChange={e => { setFrameIdx(parseInt(e.target.value)); setPlaying(false) }} />
      )}
      {!fullReplay && clips.length > 0 && (
        <div className="w-full space-y-1">
          <p className="text-[10px] text-slate-500 text-center">精彩集锦</p>
          {clips.map((clip, i) => (
            <div key={i} onClick={() => goToClip(i)} className={`text-xs px-3 py-1.5 rounded cursor-pointer transition-colors ${i===currentClip ? 'bg-accent/20 text-accent border border-accent/30' : 'bg-slate-800/50 text-slate-400 hover:bg-slate-700/50'}`}>{clip.label}</div>
          ))}
        </div>
      )}
      <Button variant="ghost" size="sm" className="text-xs text-slate-500" onClick={() => { setFullReplay(!fullReplay); if (!fullReplay) setFrameIdx(0); else if (clips.length > 0) { setFrameIdx(clips[0].startIdx); setCurrentClip(0) } }}>
        <Maximize2 size={12} className="mr-1" />{fullReplay ? '返回集锦' : '完整回放'}
      </Button>
    </div>
  )
}
