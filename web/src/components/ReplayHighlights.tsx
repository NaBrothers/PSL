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
  ball_team: TeamSide | null
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
    terminal_speed_ratio?: number
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
type TeamSide = 'home' | 'away'

interface Clip { label: string; startIdx: number; endIdx: number; icon: string; minute: number; playerName: string }
interface Props { replayUrl: string }
type SelectedPlayer = { team: 'home' | 'away'; idx: number } | null

const PITCH_W = 68, PITCH_H = 105
const CANVAS_W = 300, CANVAS_H = Math.round(CANVAS_W * (PITCH_H / PITCH_W))
const SCALE_X = CANVAS_W / PITCH_W, SCALE_Y = CANVAS_H / PITCH_H
const PLAYER_R = 7, BALL_R = 4
const PLAYER_BODY_SEPARATION_M = 0.9
const OPEN_PLAY_TIME_COMPRESSION = 2
const REPLAY_CUT_INTERVAL_MS = 300
const MIN_FRAME_INTERVAL_MS = 40

const COLOR_MAP: Record<string, string> = { w:'#b8b8b8', g:'#4caf50', b:'#4fc3f7', p:'#b45cff', o:'#ff9800', r:'#ef5350', f:'#ff69b4', x:'#a52a2a', '$':'#fbbf24' }

function lerp(a: number, b: number, t: number) { return a + (b - a) * t }
function pointDist(a: [number, number], b: [number, number]) {
  return Math.hypot(a[0] - b[0], a[1] - b[1])
}
function interpolatePoint(
  left: [number, number],
  right: [number, number],
  leftTime: number,
  rightTime: number,
  time: number,
): [number, number] {
  const span = rightTime - leftTime
  const progress = span > 1e-9 ? (time - leftTime) / span : 0
  return [
    lerp(left[0], right[0], progress),
    lerp(left[1], right[1], progress),
  ]
}
function centripetalCatmullRom(
  p0: [number, number],
  p1: [number, number],
  p2: [number, number],
  p3: [number, number],
  progress: number,
): [number, number] {
  const knotStep = (left: [number, number], right: [number, number]) =>
    Math.max(Math.sqrt(pointDist(left, right)), 1e-4)
  const t0 = 0
  const t1 = t0 + knotStep(p0, p1)
  const t2 = t1 + knotStep(p1, p2)
  const t3 = t2 + knotStep(p2, p3)
  const time = lerp(t1, t2, progress)
  const a1 = interpolatePoint(p0, p1, t0, t1, time)
  const a2 = interpolatePoint(p1, p2, t1, t2, time)
  const a3 = interpolatePoint(p2, p3, t2, t3, time)
  const b1 = interpolatePoint(a1, a2, t0, t2, time)
  const b2 = interpolatePoint(a2, a3, t1, t3, time)
  const curved = interpolatePoint(b1, b2, t1, t2, time)
  const linear: [number, number] = [
    lerp(p1[0], p2[0], progress),
    lerp(p1[1], p2[1], progress),
  ]
  const deviation = pointDist(curved, linear)
  const maxDeviation = Math.min(1.5, pointDist(p1, p2) * 0.25)
  const deviationScale = deviation > maxDeviation && deviation > 1e-9
    ? maxDeviation / deviation
    : 1
  return [
    Math.min(Math.max(lerp(linear[0], curved[0], deviationScale), 0), PITCH_W),
    Math.min(Math.max(lerp(linear[1], curved[1], deviationScale), 0), PITCH_H),
  ]
}

function isContinuousFlightEnd(flight: ReplayFrame['ball_flight']) {
  return flight?.complete === true
    && ['received', 'cleared', 'intercepted', 'loose', 'first_touch_error'].includes(flight.end_reason || '')
}

function oppositeTeam(team: TeamSide | null): TeamSide | null {
  if (team === 'home') return 'away'
  if (team === 'away') return 'home'
  return null
}

function nearestPlayerToBall(
  frame: ReplayFrame,
  team: TeamSide | null,
): { team: TeamSide; idx: number; distance: number } | null {
  if (!frame.ball) return null
  const candidates: { team: TeamSide; idx: number; distance: number }[] = []
  const collect = (side: TeamSide, players: [number, number][]) => {
    if (team && side !== team) return
    players.forEach((position, idx) => {
      candidates.push({ team: side, idx, distance: pointDist(position, frame.ball!) })
    })
  }
  collect('home', frame.home)
  collect('away', frame.away)
  return candidates.reduce<typeof candidates[number] | null>(
    (nearest, candidate) => !nearest || candidate.distance < nearest.distance ? candidate : nearest,
    null,
  )
}

function nextKnownController(
  frames: ReplayFrame[],
  startIdx: number,
  expectedTeam: TeamSide | null,
): { team: TeamSide; idx: number } | null {
  for (let idx = startIdx + 1; idx < Math.min(frames.length, startIdx + 5); idx++) {
    const frame = frames[idx]
    if (frame.ball_flight && frame.ball_flight.id !== frames[startIdx].ball_flight?.id) break
    if (!frame.ball_team || frame.ball_holder == null) continue
    if (expectedTeam && frame.ball_team !== expectedTeam) return null
    return { team: frame.ball_team, idx: frame.ball_holder }
  }
  return null
}

function repairReplayControl(frames: ReplayFrame[]): ReplayFrame[] {
  let possessionTeam: ReplayFrame['ball_team'] = null
  return frames.map((frame, frameIdx) => {
    if (frame.ball_team && frame.ball_holder != null) {
      possessionTeam = frame.ball_team
      return frame
    }
    const reason = frame.ball_flight?.complete ? frame.ball_flight.end_reason : null
    if (reason !== 'received' && reason !== 'intercepted') return frame

    const expectedTeam = reason === 'received' ? possessionTeam : oppositeTeam(possessionTeam)
    const nearest = nearestPlayerToBall(frame, expectedTeam)
      || nearestPlayerToBall(frame, null)
    const controller = nearest && nearest.distance <= 3.0
      ? nearest
      : nextKnownController(frames, frameIdx, expectedTeam)
    if (!controller) return frame

    possessionTeam = controller.team
    return {
      ...frame,
      ball_holder: controller.idx,
      ball_team: controller.team,
    }
  })
}

function replayEventLabel(frame: ReplayFrame): string | null {
  if (frame.event_text === 'GOAL') return '⚽ GOAL'
  if (frame.event_text === 'SAVE') return '🧤 SAVE'
  if (frame.event_text) return frame.event_text
  if (frame.ball_flight?.complete !== true) return null
  switch (frame.ball_flight.end_reason) {
    case 'intercepted': return '拦截'
    case 'first_touch_error': return '停球失误'
    case 'loose': return null
    case 'offside': return '越位'
    case 'out_of_play': return '出界'
    default: return null
  }
}

function hasHardReplayCut(frame: ReplayFrame) {
  return frame.cut === true && !isContinuousFlightEnd(frame.ball_flight)
}

function blocksReplayExit(frame: ReplayFrame) {
  return hasHardReplayCut(frame)
}

function blocksReplayEntry(frame: ReplayFrame) {
  return frame.cut === true && frame.ball_flight?.complete !== true
}

function blocksReplayTransition(frame: ReplayFrame, nextFrame?: ReplayFrame) {
  return blocksReplayExit(frame) || (nextFrame ? blocksReplayEntry(nextFrame) : false)
}

function replayFrameInterval(frame: ReplayFrame, nextFrame: ReplayFrame, speed: number) {
  if (frame.pause_ms && (frame.ball_flight || frame.event_text)) {
    return frame.pause_ms / speed
  }
  if (blocksReplayTransition(frame, nextFrame)) {
    return REPLAY_CUT_INTERVAL_MS / speed
  }
  const matchTimeMs = (nextFrame.t - frame.t) * 1000
  if (matchTimeMs <= 0) {
    return 0
  }
  return Math.max(
    MIN_FRAME_INTERVAL_MS,
    matchTimeMs / OPEN_PLAY_TIME_COMPRESSION / speed,
  )
}

function flightProgress(flight: NonNullable<ReplayFrame['ball_flight']>) {
  const totalTicks = flight.total_ticks || 0
  return totalTicks > 0
    ? Math.min(Math.max((flight.elapsed_ticks || 0) / totalTicks, 0), 1)
    : 0
}

function flightPositionProgress(
  flight: NonNullable<ReplayFrame['ball_flight']>,
  timeProgress: number,
) {
  const progress = Math.min(Math.max(timeProgress, 0), 1)
  const terminalRatio = flight.terminal_speed_ratio
  if (terminalRatio === undefined) return progress
  const ratio = Math.min(Math.max(terminalRatio, 0), 1)
  return (2 - ratio) * progress - (1 - ratio) * progress * progress
}

function flightTimeProgressAtPosition(
  flight: NonNullable<ReplayFrame['ball_flight']>,
  position: [number, number],
): number | null {
  const terminalRatio = flight.terminal_speed_ratio
  if (terminalRatio === undefined) return null
  const dx = flight.to[0] - flight.from[0]
  const dy = flight.to[1] - flight.from[1]
  const lengthSquared = dx * dx + dy * dy
  if (lengthSquared <= 1e-9) return null
  const positionProgress = Math.min(Math.max(
    ((position[0] - flight.from[0]) * dx + (position[1] - flight.from[1]) * dy)
      / lengthSquared,
    0,
  ), 1)
  const ratio = Math.min(Math.max(terminalRatio, 0), 1)
  if (ratio >= 1 - 1e-9) return positionProgress
  const initialSpeedRatio = 2 - ratio
  const deceleration = 1 - ratio
  const discriminant = Math.max(
    initialSpeedRatio * initialSpeedRatio - 4 * deceleration * positionProgress,
    0,
  )
  return Math.min(Math.max(
    (initialSpeedRatio - Math.sqrt(discriminant)) / (2 * deceleration),
    0,
  ), 1)
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
    const continuesSameFlight = flight.id !== undefined
      && nextFlight?.id === flight.id
      && nextFlight.total_ticks === flight.total_ticks
    if (continuesSameFlight && frame.ball && nextFrame.ball) {
      const startTimeProgress = flightTimeProgressAtPosition(flight, frame.ball)
      const endTimeProgress = flightTimeProgressAtPosition(flight, nextFrame.ball)
      const segmentProgress = startTimeProgress !== null
        && endTimeProgress !== null
        && endTimeProgress > startTimeProgress + 1e-9
        ? (() => {
            const positionStart = flightPositionProgress(flight, startTimeProgress)
            const positionEnd = flightPositionProgress(flight, endTimeProgress)
            const positionNow = flightPositionProgress(
              flight,
              lerp(startTimeProgress, endTimeProgress, interpolation),
            )
            return (positionNow - positionStart) / (positionEnd - positionStart)
          })()
        : interpolation
      return [
        lerp(frame.ball[0], nextFrame.ball[0], segmentProgress),
        lerp(frame.ball[1], nextFrame.ball[1], segmentProgress),
      ]
    }
    const startProgress = flightProgress(flight)
    const endProgress = continuesSameFlight
      ? Math.max(startProgress, flightProgress(nextFlight))
      : 1
    return pointAlongFlightPath(
      flightPath(frames, idx, flight),
      flightPositionProgress(
        flight,
        startProgress + (endProgress - startProgress) * interpolation,
      ),
    )
  }

  if (
    frame.ball
    && nextFlight
    && !blocksReplayTransition(frame, nextFrame)
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
  if (!next || blocksReplayTransition(frame, next)) return current

  const previousFrame = frames[idx - 1]
  const followingFrame = frames[idx + 2]
  const previous = previousFrame && !blocksReplayTransition(previousFrame, frame)
    ? (side === 'home' ? previousFrame.home[playerIdx] : previousFrame.away[playerIdx])
    : current
  const following = followingFrame && !blocksReplayTransition(next, followingFrame)
    ? (side === 'home' ? followingFrame.home[playerIdx] : followingFrame.away[playerIdx])
    : target
  const segmentDistance = pointDist(current, target)
  const previousDistance = pointDist(previous, current)
  const followingDistance = pointDist(target, following)
  const abnormalJump = segmentDistance > Math.max(
    10,
    previousDistance * 2.6 + 2,
    followingDistance * 2.6 + 2,
  )
  if (abnormalJump) {
    return [
      lerp(current[0], target[0], t),
      lerp(current[1], target[1], t),
    ]
  }

  return centripetalCatmullRom(previous, current, target, following, t)
}

function closestRelativeSegmentDistance(
  start: [number, number],
  end: [number, number],
) {
  const dx = end[0] - start[0]
  const dy = end[1] - start[1]
  const lengthSquared = dx * dx + dy * dy
  const progress = lengthSquared > 1e-9
    ? Math.min(Math.max(-(start[0] * dx + start[1] * dy) / lengthSquared, 0), 1)
    : 0
  return Math.hypot(start[0] + dx * progress, start[1] + dy * progress)
}

function smoothRelativePathMinimumDistance(
  frames: ReplayFrame[],
  frameIndex: number,
  holderSide: TeamSide,
  holderIndex: number,
  opponentSide: TeamSide,
  opponentIndex: number,
) {
  let minimumDistance = Number.POSITIVE_INFINITY
  for (let sample = 0; sample <= 8; sample++) {
    const progress = sample / 8
    const holder = smoothPoint(frames, frameIndex, holderSide, holderIndex, progress)
    const opponent = smoothPoint(frames, frameIndex, opponentSide, opponentIndex, progress)
    minimumDistance = Math.min(minimumDistance, pointDist(holder, opponent))
  }
  return minimumDistance
}

function collisionAvoidingOpponentPoint(
  holder: [number, number],
  holderStart: [number, number],
  holderEnd: [number, number],
  opponentStart: [number, number],
  opponentEnd: [number, number],
  progress: number,
  minimumSeparation: number,
  directionSeed: number,
  curvedPathIntersects: boolean,
): [number, number] | null {
  const relativeStart: [number, number] = [
    opponentStart[0] - holderStart[0],
    opponentStart[1] - holderStart[1],
  ]
  const relativeEnd: [number, number] = [
    opponentEnd[0] - holderEnd[0],
    opponentEnd[1] - holderEnd[1],
  ]
  if (
    !curvedPathIntersects
    && closestRelativeSegmentDistance(relativeStart, relativeEnd) >= minimumSeparation
  ) return null

  const startAngle = Math.atan2(relativeStart[1], relativeStart[0])
  const endAngle = Math.atan2(relativeEnd[1], relativeEnd[0])
  let angleDelta = Math.atan2(
    Math.sin(endAngle - startAngle),
    Math.cos(endAngle - startAngle),
  )
  if (Math.abs(Math.abs(angleDelta) - Math.PI) < 1e-6) {
    angleDelta = directionSeed % 2 === 0 ? Math.PI : -Math.PI
  }
  const startRadius = Math.hypot(relativeStart[0], relativeStart[1])
  const endRadius = Math.hypot(relativeEnd[0], relativeEnd[1])
  const radius = Math.max(minimumSeparation, lerp(startRadius, endRadius, progress))
  const angle = startAngle + angleDelta * progress
  return [
    holder[0] + Math.cos(angle) * radius,
    holder[1] + Math.sin(angle) * radius,
  ]
}

function separateReplayDefendersFromHolder(
  home: [number, number][],
  away: [number, number][],
  frames: ReplayFrame[],
  frameIndex: number,
  progress: number,
  field: ReplayHeader['field'],
) {
  const frame = frames[frameIndex]
  if (frame.ball_team !== 'home' && frame.ball_team !== 'away') return
  if (frame.ball_holder == null) return
  const holderTeam = frame.ball_team === 'home' ? home : away
  const opponents = frame.ball_team === 'home' ? away : home
  const holder = holderTeam[frame.ball_holder]
  if (!holder) return
  const minimumDisplaySeparation = PLAYER_BODY_SEPARATION_M
  const nextFrame = frames[frameIndex + 1]
  const continuousHolder = nextFrame
    && nextFrame.ball_team === frame.ball_team
    && nextFrame.ball_holder === frame.ball_holder
    && !blocksReplayTransition(frame, nextFrame)
  if (continuousHolder) {
    const holderStart = frame.ball_team === 'home'
      ? frame.home[frame.ball_holder]
      : frame.away[frame.ball_holder]
    const holderEnd = frame.ball_team === 'home'
      ? nextFrame.home[frame.ball_holder]
      : nextFrame.away[frame.ball_holder]
    const opponentStart = frame.ball_team === 'home' ? frame.away : frame.home
    const opponentEnd = frame.ball_team === 'home' ? nextFrame.away : nextFrame.home
    opponents.forEach((opponent, index) => {
      const opponentSide = frame.ball_team === 'home' ? 'away' : 'home'
      const curvedPathIntersects = smoothRelativePathMinimumDistance(
        frames,
        frameIndex,
        frame.ball_team!,
        frame.ball_holder!,
        opponentSide,
        index,
      ) < minimumDisplaySeparation
      const adjusted = collisionAvoidingOpponentPoint(
        holder,
        holderStart,
        holderEnd,
        opponentStart[index],
        opponentEnd[index],
        progress,
        minimumDisplaySeparation,
        index,
        curvedPathIntersects,
      )
      if (adjusted) {
        opponent[0] = Math.min(Math.max(adjusted[0], 0.5), field.width - 0.5)
        opponent[1] = Math.min(Math.max(adjusted[1], 0.5), field.length - 0.5)
      }
    })
  }
  opponents.forEach((opponent, index) => {
    const dx = opponent[0] - holder[0]
    const dy = opponent[1] - holder[1]
    const separation = Math.hypot(dx, dy)
    if (separation >= minimumDisplaySeparation) return
    const fallbackAngle = index * 2.399963229728653
    const nx = separation > 1e-9 ? dx / separation : Math.cos(fallbackAngle)
    const ny = separation > 1e-9 ? dy / separation : Math.sin(fallbackAngle)
    opponent[0] = Math.min(
      Math.max(holder[0] + nx * minimumDisplaySeparation, 0.5),
      field.width - 0.5,
    )
    opponent[1] = Math.min(
      Math.max(holder[1] + ny * minimumDisplaySeparation, 0.5),
      field.length - 0.5,
    )
  })
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
  const segmentProgressRef = useRef(0)
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
      const f = repairReplayControl(parsed.filter(l => l.type === 'frame') as ReplayFrame[])
      setHeader(h); setFrames(f)
      const hl = extractHighlights(f, h); setClips(hl); setLoading(false)
      if (hl.length > 0) {
        frameIdxRef.current = hl[0].startIdx
        segmentProgressRef.current = 0
        setFrameIdx(hl[0].startIdx)
        setPlaying(true)
      }
    })
  }, [replayUrl])

  const currentFrames = fullReplay ? { start: 0, end: frames.length - 1 } : clips[currentClip] ? { start: clips[currentClip].startIdx, end: clips[currentClip].endIdx } : { start: 0, end: 0 }
  useEffect(() => { currentFramesRef.current = currentFrames })

  const getInterval = useCallback((idx: number): number => {
    const f = framesRef.current
    if (idx >= f.length - 1) return 500
    return replayFrameInterval(f[idx], f[idx + 1], speedRef.current)
  }, [])

  const drawFrame = useCallback((idx: number, interpT: number = 0) => {
    const canvas = canvasRef.current, h = headerRef.current, f = framesRef.current
    if (!canvas || !h || f.length === 0) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const frame = f[idx]
    if (!frame) return

    let home = frame.home.map(p => [...p] as [number, number]), away = frame.away.map(p => [...p] as [number, number])
    if (
      idx < f.length - 1
      && interpT > 0
      && !blocksReplayTransition(frame, f[idx + 1])
    ) {
      home = frame.home.map((_, i) => smoothPoint(f, idx, 'home', i, interpT))
      away = frame.away.map((_, i) => smoothPoint(f, idx, 'away', i, interpT))
    }
    separateReplayDefendersFromHolder(home, away, f, idx, interpT, h.field)

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
    const eventLabel = replayEventLabel(frame)
    if (frame.event_text === 'GOAL') {
      ctx.fillStyle = 'rgba(0,0,0,0.6)'; ctx.fillRect(0, CANVAS_H/2-18, CANVAS_W, 36)
      ctx.fillStyle = '#4ade80'; ctx.font = 'bold 16px sans-serif'; ctx.textAlign = 'center'
      ctx.fillText(eventLabel!, CANVAS_W/2, CANVAS_H/2+5)
    } else if (frame.event_text === 'SAVE') {
      ctx.fillStyle = 'rgba(0,0,0,0.5)'; ctx.fillRect(0, CANVAS_H/2-14, CANVAS_W, 28)
      ctx.fillStyle = '#facc15'; ctx.font = 'bold 13px sans-serif'; ctx.textAlign = 'center'
      ctx.fillText(eventLabel!, CANVAS_W/2, CANVAS_H/2+4)
    } else if (eventLabel) {
      ctx.fillStyle = 'rgba(0,0,0,0.55)'; ctx.fillRect(CANVAS_W/2-38, CANVAS_H/2-11, 76, 22)
      ctx.fillStyle = '#fff'; ctx.font = 'bold 11px sans-serif'; ctx.textAlign = 'center'
      ctx.fillText(eventLabel, CANVAS_W/2, CANVAS_H/2+4)
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
      let elapsed = ts - lastRenderTimeRef.current
      lastRenderTimeRef.current = ts
      let idx = frameIdxRef.current
      let progress = segmentProgressRef.current

      while (elapsed > 0) {
        const interval = getInterval(idx)
        const remaining = (1 - progress) * interval
        if (elapsed < remaining) {
          progress += elapsed / interval
          elapsed = 0
          break
        }
        elapsed -= remaining
        progress = 0
        const nextIdx = idx + 1
        if (nextIdx > currentFramesRef.current.end) {
          if (!fullReplayRef.current && !singleClipRef.current && currentClipRef.current < clipsRef.current.length-1) {
            const next = currentClipRef.current + 1
            const nextStart = clipsRef.current[next].startIdx
            currentClipRef.current = next
            frameIdxRef.current = nextStart
            segmentProgressRef.current = 0
            setCurrentClip(next)
            setFrameIdx(nextStart)
          } else { setPlaying(false); setSingleClip(false) }
          return
        }
        idx = nextIdx
        frameIdxRef.current = idx
        setFrameIdx(idx)
      }
      segmentProgressRef.current = progress
      drawFrame(idx, progress)
      animRef.current = requestAnimationFrame(loop)
    }
    animRef.current = requestAnimationFrame(loop)
    return () => cancelAnimationFrame(animRef.current)
  }, [playing, getInterval, drawFrame])

  useEffect(() => { if (!playing) drawFrame(frameIdx, 0) }, [frameIdx, playing, drawFrame])

  const goToClip = (idx: number) => {
    setPlaying(false)
    setTimeout(() => {
      const startIdx = clips[idx].startIdx
      currentClipRef.current = idx
      frameIdxRef.current = startIdx
      segmentProgressRef.current = 0
      setCurrentClip(idx)
      setFrameIdx(startIdx)
      setSingleClip(true)
      setPlaying(true)
    }, 0)
  }
  const seekToFrame = (idx: number) => {
    frameIdxRef.current = idx
    segmentProgressRef.current = 0
    lastRenderTimeRef.current = 0
    setFrameIdx(idx)
  }
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
      <Button variant="ghost" size="sm" className="text-xs text-slate-500" onClick={() => { setFullReplay(true); seekToFrame(0) }}><Maximize2 size={12} className="mr-1" />查看完整回放</Button>
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
        <Button variant="ghost" size="sm" onClick={() => seekToFrame(Math.max(currentFrames.start, frameIdx-5))}><SkipBack size={14} /></Button>
        <Button variant="outline" size="sm" onClick={() => setPlaying(!playing)}>{playing ? <Pause size={14} /> : <Play size={14} />}</Button>
        <Button variant="ghost" size="sm" onClick={() => { if (!fullReplay && currentClip < clips.length-1) goToClip(currentClip+1); else seekToFrame(Math.min(currentFrames.end, frameIdx+5)) }}><SkipForward size={14} /></Button>
        <div className="flex gap-1 ml-2">
          {[1,2,4].map(s => <Button key={s} variant={speed===s?'default':'ghost'} size="sm" className="text-[10px] px-2 h-6" onClick={() => setSpeed(s)}>{s}x</Button>)}
        </div>
      </div>
      {fullReplay && frames.length > 0 && (
        <input type="range" min={0} max={frames.length - 1} value={frameIdx} className="w-full max-w-[300px] h-1 cursor-pointer accent-accent"
          onChange={e => { seekToFrame(parseInt(e.target.value)); setPlaying(false) }} />
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
      <Button variant="ghost" size="sm" className="text-xs text-slate-500" onClick={() => {
        setFullReplay(!fullReplay)
        if (!fullReplay) {
          seekToFrame(0)
        } else if (clips.length > 0) {
          currentClipRef.current = 0
          setCurrentClip(0)
          seekToFrame(clips[0].startIdx)
        }
      }}>
        <Maximize2 size={12} className="mr-1" />{fullReplay ? '返回集锦' : '完整回放'}
      </Button>
    </div>
  )
}
