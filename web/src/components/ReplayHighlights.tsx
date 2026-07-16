import { useState, useEffect, useRef, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Play, Pause, SkipForward, SkipBack, Maximize2 } from 'lucide-react'

interface ReplayFrame {
  type: string
  t: number
  half: number
  home: [number, number][]
  away: [number, number][]
  home_player_goals?: (string | null)[]
  away_player_goals?: (string | null)[]
  ball_holder: number | null
  ball?: [number, number] | null
  ball_team: string | null
  score: [number, number]
  ball_flight?: {
    id?: number
    from: [number, number]
    to: [number, number]
    end?: [number, number]
    path?: [number, number][]
    type: string
    on_target?: boolean
    elapsed_ticks?: number
    total_ticks?: number
    complete?: boolean
    end_reason?: string | null
  }
  event_text?: string
  pause_ms?: number
  cut?: boolean
}

interface ReplayHeader {
  type: 'header'
  home: { name: string; players: ReplayPlayer[] }
  away: { name: string; players: ReplayPlayer[] }
  field: { width: number; length: number }
}

interface ReplayPlayer {
  name: string
  player_id?: number | string | null
  pos: string
  color: string
  colored_name?: string
}

type ReplayLine = ReplayHeader | ReplayFrame

interface Clip { label: string; startIdx: number; endIdx: number; icon: string; minute: number; playerName: string }
interface Props { replayUrl: string }
type SelectedPlayer = { team: 'home' | 'away'; idx: number } | null

const PITCH_W = 68, PITCH_H = 105
const CANVAS_W = 300, CANVAS_H = Math.round(CANVAS_W * (PITCH_H / PITCH_W))
const SCALE_X = CANVAS_W / PITCH_W, SCALE_Y = CANVAS_H / PITCH_H
const PLAYER_R = 7, BALL_R = 4

const COLOR_MAP: Record<string, string> = { w:'#b8b8b8', g:'#4caf50', b:'#4fc3f7', p:'#b45cff', o:'#ff9800', r:'#ef5350', f:'#ff69b4', x:'#a52a2a', '$':'#fbbf24' }

function lerp(a: number, b: number, t: number) { return a + (b - a) * t }
function catmullRom(p0: number, p1: number, p2: number, p3: number, t: number) {
  const t2 = t * t
  const t3 = t2 * t
  return 0.5 * (
    2 * p1 +
    (-p0 + p2) * t +
    (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 +
    (-p0 + 3 * p1 - 3 * p2 + p3) * t3
  )
}
function pointDist(a: [number, number], b: [number, number]) {
  return Math.hypot(a[0] - b[0], a[1] - b[1])
}

function isContinuousFlightEnd(flight: ReplayFrame['ball_flight']) {
  return flight?.complete === true
    && ['received', 'cleared', 'intercepted', 'loose', 'first_touch_error'].includes(flight.end_reason || '')
}

function hasHardReplayCut(frame: ReplayFrame) {
  return frame.cut === true && !isContinuousFlightEnd(frame.ball_flight)
}

function blocksReplayExit(frame: ReplayFrame) {
  return hasHardReplayCut(frame)
}

function flightProgress(flight: NonNullable<ReplayFrame['ball_flight']>) {
  const totalTicks = flight.total_ticks || 0
  return totalTicks > 0
    ? Math.min(Math.max((flight.elapsed_ticks || 0) / totalTicks, 0), 1)
    : 0
}

function terminalFlightFrame(
  frames: ReplayFrame[],
  idx: number,
  flightId: number | undefined,
) {
  if (flightId === undefined) return undefined
  for (let frameIdx = idx; frameIdx < frames.length; frameIdx++) {
    const candidate = frames[frameIdx]
    const candidateFlight = candidate.ball_flight
    if (!candidateFlight) continue
    if (candidateFlight.id !== flightId) return undefined
    if (candidateFlight.complete === true) return candidate
  }
  return undefined
}

function flightPath(
  frames: ReplayFrame[],
  idx: number,
  flight: NonNullable<ReplayFrame['ball_flight']>,
) {
  if (flight.path) return flight.path
  const terminalFrame = terminalFlightFrame(frames, idx, flight.id)
  const terminalBall = terminalFrame
    ? terminalFrame.ball || terminalFrame.ball_flight?.end
    : undefined
  const end = terminalBall || (flight.complete ? flight.end || frames[idx].ball : undefined) || flight.end || flight.to
  return [flight.from, end]
}

function pointAlongFlightPath(path: [number, number][], progress: number): [number, number] {
  const segmentCount = path.length - 1
  if (segmentCount <= 0) return path[0]
  const scaled = Math.min(Math.max(progress, 0) * segmentCount, segmentCount - 0.0001)
  const segment = Math.floor(scaled)
  const local = scaled - segment
  return [
    lerp(path[segment][0], path[segment + 1][0], local),
    lerp(path[segment][1], path[segment + 1][1], local),
  ]
}

function ballFlightPosition(
  frames: ReplayFrame[],
  idx: number,
  interpT: number,
): [number, number] | null {
  const frame = frames[idx]
  const nextFrame = frames[idx + 1]
  const flight = frame.ball_flight
  const nextFlight = nextFrame?.ball_flight
  const interpolation = Math.min(Math.max(interpT, 0), 1)

  if (flight && (!flight.complete || !isContinuousFlightEnd(flight))) {
    const startProgress = flightProgress(flight)
    const continuesSameFlight = flight.id !== undefined
      && nextFlight?.id === flight.id
      && nextFlight.total_ticks === flight.total_ticks
    const endProgress = continuesSameFlight
      ? Math.max(startProgress, flightProgress(nextFlight))
      : 1
    return pointAlongFlightPath(
      flightPath(frames, idx, flight),
      startProgress + (endProgress - startProgress) * interpolation,
    )
  }

  if (
    frame.ball
    && nextFlight
    && !hasHardReplayCut(frame)
  ) {
    const target = pointAlongFlightPath(
      flightPath(frames, idx + 1, nextFlight),
      flightProgress(nextFlight),
    )
    return [
      lerp(frame.ball[0], target[0], interpolation),
      lerp(frame.ball[1], target[1], interpolation),
    ]
  }

  return null
}

function smoothPoint(
  frames: ReplayFrame[],
  idx: number,
  side: 'home' | 'away',
  playerIdx: number,
  t: number,
): [number, number] {
  const frame = frames[idx]
  const next = frames[idx + 1]
  const current = side === 'home' ? frame.home[playerIdx] : frame.away[playerIdx]
  const target = next ? (side === 'home' ? next.home[playerIdx] : next.away[playerIdx]) : current
  if (!next || blocksReplayExit(frame)) return current

  const prev = idx > 0 && !hasHardReplayCut(frames[idx - 1])
    ? (side === 'home' ? frames[idx - 1].home[playerIdx] : frames[idx - 1].away[playerIdx])
    : current
  const after = !hasHardReplayCut(next)
    && idx + 2 < frames.length
    && !hasHardReplayCut(frames[idx + 2])
    ? (side === 'home' ? frames[idx + 2].home[playerIdx] : frames[idx + 2].away[playerIdx])
    : target
  const segment = pointDist(current, target)
  const prevSegment = pointDist(prev, current)
  const nextSegment = pointDist(target, after)
  const abnormalJump = segment > Math.max(10, prevSegment * 2.6 + 2, nextSegment * 2.6 + 2)
  if (abnormalJump) return [lerp(current[0], target[0], t), lerp(current[1], target[1], t)]
  return [
    catmullRom(prev[0], current[0], target[0], after[0], t),
    catmullRom(prev[1], current[1], target[1], after[1], t),
  ]
}
function extractHighlights(frames: ReplayFrame[], header: ReplayHeader | null): Clip[] {
  const clips: Clip[] = []
  for (let i = 0; i < frames.length; i++) {
    const f = frames[i]
    if (f.event_text === 'GOAL' || f.event_text === 'SAVE') {
      const startIdx = Math.max(0, i - 10), endIdx = i
      const minute = Math.floor(f.t / 60)
      const icon = f.event_text === 'GOAL' ? '⚽' : '🧤'
      let playerName = ''
      if (header && f.ball_holder != null && f.ball_team) {
        if (f.event_text === 'GOAL') {
          const team = f.ball_team === 'home' ? header.home : header.away
          playerName = team.players[f.ball_holder]?.name.split(' ').pop() || ''
        } else {
          const keeperTeam = f.ball_team === 'home' ? header.home : header.away
          playerName = keeperTeam.players[f.ball_holder]?.name.split(' ').pop() || ''
        }
      }
      const label = f.event_text === 'GOAL' ? `${minute}' 进球 [${f.score[0]}-${f.score[1]}]` : `${minute}' 扑救`
      clips.push({ label, startIdx, endIdx, icon, minute, playerName })
    }
  }
  return clips
}

function resolveReplayFileUrl(url: string): string {
  try { const u = new URL(url, window.location.origin); const path = u.searchParams.get("path"); if (path) return `/replays/${path}` } catch {}
  return url
}

function goalLabel(goal?: string | null): string {
  if (!goal) return '无'
  const labels: Record<string, string> = {
    hold_for_opportunity: '控球找机会',
    cut_inside_to_shoot: '内切寻找射门',
    release_pressure_with_layoff: '受压回做',
    release_to_arriving_support: '传给到位支援',
    wide_hold_for_overlap: '等待套边',
    arc_arrival_for_cutback: '弧顶接应',
    attack_far_post: '后点包抄',
    attack_box: '冲击禁区',
    support_second_line: '二线接应',
    drop_between_lines: '线间接应',
    support_carrier: '支援持球人',
    hold_width: '拉开宽度',
    run_behind: '前插身后',
    recycle_support: '回收接应',
    create_shot: '制造射门',
    progress_carry: '带球推进',
    protect_ball: '护球观察',
    recycle: '回传组织',
    switch_play: '转移弱侧',
    through_ball: '直塞身后',
    through_ball_behind: '直塞身后',
    wide_byline_attack: '下底进攻',
    clear_danger: '解围化险',
    defend_press: '上抢压迫',
    defend_cover_lane: '封堵线路',
    defend_mark_runner: '盯防跑位',
    defend_protect_box: '保护禁区',
    defend_recover_shape: '回收阵型',
  }
  return labels[goal] || goal
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
  const [selectedPlayer, setSelectedPlayer] = useState<SelectedPlayer>(null)

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
  const selectedPlayerRef = useRef<SelectedPlayer>(null)

  useEffect(() => { playingRef.current = playing }, [playing])
  useEffect(() => { frameIdxRef.current = frameIdx }, [frameIdx])
  useEffect(() => { headerRef.current = header }, [header])
  useEffect(() => { framesRef.current = frames }, [frames])
  useEffect(() => { speedRef.current = speed }, [speed])
  useEffect(() => { currentClipRef.current = currentClip }, [currentClip])
  useEffect(() => { clipsRef.current = clips }, [clips])
  useEffect(() => { fullReplayRef.current = fullReplay }, [fullReplay])
  useEffect(() => { singleClipRef.current = singleClip }, [singleClip])
  useEffect(() => { selectedPlayerRef.current = selectedPlayer }, [selectedPlayer])

  useEffect(() => {
    fetch(resolveReplayFileUrl(replayUrl)).then(r => r.text()).then(text => {
      const parsed = text.trim().split('\n').map(l => JSON.parse(l)) as ReplayLine[]
      const h = parsed.find(l => l.type === 'header') as ReplayHeader
      const f = parsed.filter(l => l.type === 'frame') as ReplayFrame[]
      setHeader(h); setFrames(f)
      const hl = extractHighlights(f, h); setClips(hl); setLoading(false)
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

    let home = frame.home.map(p => [...p] as [number, number]), away = frame.away.map(p => [...p] as [number, number])
    if (idx < f.length - 1 && interpT > 0 && !blocksReplayExit(frame)) {
      home = frame.home.map((_, i) => smoothPoint(f, idx, 'home', i, interpT))
      away = frame.away.map((_, i) => smoothPoint(f, idx, 'away', i, interpT))
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
    const selected = selectedPlayerRef.current
    for (let i = 0; i < home.length; i++) {
      const sx = home[i][0]*SCALE_X, sy = home[i][1]*SCALE_Y
      const hl = frame.ball_team === 'home' && frame.ball_holder === i
      const selectedDot = selected?.team === 'home' && selected.idx === i
      ctx.beginPath(); ctx.arc(sx, sy, PLAYER_R, 0, Math.PI*2)
      ctx.fillStyle = hl ? '#fbbf24' : '#4fc3f7'; ctx.fill()
      ctx.strokeStyle = selectedDot ? '#fff' : hl ? '#fff' : 'rgba(255,255,255,0.4)'; ctx.lineWidth = selectedDot ? 3 : hl ? 2 : 1; ctx.stroke()
      ctx.font = '8px sans-serif'; ctx.textAlign = 'center'
      ctx.fillStyle = COLOR_MAP[h.home.players[i]?.color||'b']||'#4fc3f7'
      ctx.fillText(h.home.players[i]?.name.split(' ').pop()||'', sx, sy-PLAYER_R-2)
    }
    for (let i = 0; i < away.length; i++) {
      const sx = away[i][0]*SCALE_X, sy = away[i][1]*SCALE_Y
      const hl = frame.ball_team === 'away' && frame.ball_holder === i
      const selectedDot = selected?.team === 'away' && selected.idx === i
      ctx.beginPath(); ctx.arc(sx, sy, PLAYER_R, 0, Math.PI*2)
      ctx.fillStyle = hl ? '#fbbf24' : '#ef5350'; ctx.fill()
      ctx.strokeStyle = selectedDot ? '#fff' : hl ? '#fff' : 'rgba(255,255,255,0.4)'; ctx.lineWidth = selectedDot ? 3 : hl ? 2 : 1; ctx.stroke()
      ctx.font = '8px sans-serif'; ctx.textAlign = 'center'
      ctx.fillStyle = COLOR_MAP[h.away.players[i]?.color||'r']||'#ef5350'
      ctx.fillText(h.away.players[i]?.name.split(' ').pop()||'', sx, sy-PLAYER_R-2)
    }

    // Ball
    let ballX: number, ballY: number
    const nextBallFrame = f[idx + 1]
    const flightPosition = ballFlightPosition(f, idx, interpT)
    if (flightPosition) {
      [ballX, ballY] = flightPosition
    } else if (
      frame.ball
      && nextBallFrame?.ball
      && !hasHardReplayCut(frame)
      && !hasHardReplayCut(nextBallFrame)
      && !nextBallFrame.ball_flight
    ) {
      // Only interpolate stable ball states; a new flight starts a distinct physical segment.
      ballX = lerp(frame.ball[0], nextBallFrame.ball![0], interpT)
      ballY = lerp(frame.ball[1], nextBallFrame.ball![1], interpT)
    } else if (frame.ball) {
      ballX = frame.ball[0]; ballY = frame.ball[1]
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
  const currentFrame = frames[frameIdx]
  const selectedMeta = selectedPlayer && header
    ? selectedPlayer.team === 'home'
      ? header.home.players[selectedPlayer.idx]
      : header.away.players[selectedPlayer.idx]
    : null
  const selectedGoal = selectedPlayer && currentFrame
    ? selectedPlayer.team === 'home'
      ? currentFrame.home_player_goals?.[selectedPlayer.idx]
      : currentFrame.away_player_goals?.[selectedPlayer.idx]
    : null
  const handleCanvasClick = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (!currentFrame) return
    const rect = event.currentTarget.getBoundingClientRect()
    const scaleX = CANVAS_W / rect.width
    const scaleY = CANVAS_H / rect.height
    const x = (event.clientX - rect.left) * scaleX
    const y = (event.clientY - rect.top) * scaleY
    type HitPlayer = { team: 'home' | 'away'; idx: number; dist: number }
    const hits: HitPlayer[] = []
    const scan = (team: 'home' | 'away', points: [number, number][]) => {
      points.forEach((p, idx) => {
        const sx = p[0] * SCALE_X
        const sy = p[1] * SCALE_Y
        const dist = Math.hypot(x - sx, y - sy)
        if (dist <= PLAYER_R + 8) hits.push({ team, idx, dist })
      })
    }
    scan('home', currentFrame.home)
    scan('away', currentFrame.away)
    const best = hits.sort((a, b) => a.dist - b.dist)[0]
    if (best) {
      setSelectedPlayer({ team: best.team, idx: best.idx })
      setPlaying(false)
    }
  }

  if (loading) return <div className="text-center text-slate-500 text-sm py-8">加载回放数据...</div>
  if (clips.length === 0 && !fullReplay) return (
    <div className="text-center py-8">
      <p className="text-slate-500 text-sm mb-3">本场没有精彩集锦</p>
      <Button variant="ghost" size="sm" className="text-xs text-slate-500" onClick={() => { setFullReplay(true); setFrameIdx(0) }}><Maximize2 size={12} className="mr-1" />查看完整回放</Button>
    </div>
  )

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="w-full max-w-[300px] rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-xs text-slate-300">
        {selectedMeta ? (
          <div className="flex items-center justify-between gap-2">
            <span className="font-semibold text-slate-100 truncate">{selectedMeta.pos} {selectedMeta.name}</span>
            <span className="shrink-0 text-accent">{goalLabel(selectedGoal)}</span>
          </div>
        ) : (
          <div className="text-slate-500">点击球员圆点查看当前 goal</div>
        )}
      </div>
      <canvas ref={canvasRef} width={CANVAS_W} height={CANVAS_H} onClick={handleCanvasClick} className="rounded-lg border border-slate-700 shadow-lg cursor-pointer" style={{ width: '100%', maxWidth: 300 }} />
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
        <div className="w-full">
          <div className="flex gap-2 overflow-x-auto scrollbar-hide pb-1 px-1">
            {clips.map((clip, i) => (
              <div key={i} onClick={() => goToClip(i)} className={`flex-shrink-0 w-16 flex flex-col items-center gap-0.5 py-2 px-1 rounded-lg cursor-pointer transition-colors ${i===currentClip ? 'bg-accent/20 border border-accent/30' : 'bg-slate-800/50 hover:bg-slate-700/50'}`}>
                <span className="text-lg">{clip.icon}</span>
                <span className={`text-[9px] font-bold ${i===currentClip ? 'text-accent' : 'text-slate-300'}`}>{clip.minute}'</span>
                <span className="text-[8px] text-slate-400 truncate w-full text-center">{clip.playerName}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <Button variant="ghost" size="sm" className="text-xs text-slate-500" onClick={() => { setFullReplay(!fullReplay); if (!fullReplay) setFrameIdx(0); else if (clips.length > 0) { setFrameIdx(clips[0].startIdx); setCurrentClip(0) } }}>
        <Maximize2 size={12} className="mr-1" />{fullReplay ? '返回集锦' : '完整回放'}
      </Button>
    </div>
  )
}
