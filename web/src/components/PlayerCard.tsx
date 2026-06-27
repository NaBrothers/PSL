import { overallColor, STYLE_NAMES } from '@/lib/card-display'

interface PlayerCardProps {
  playerId: number
  name: string
  position: string
  overall: number
  star: number
  style?: string
  size?: 'sm' | 'md' | 'lg'
  onClick?: () => void
  selected?: boolean
  badge?: string
  className?: string
}

const FRAME_COLORS: Record<string, { border: string; bg: string; glow: string }> = {
  rainbow: { border: 'border-yellow-300', bg: 'from-yellow-900/40 via-red-900/30 to-purple-900/40', glow: 'shadow-[0_0_15px_rgba(234,179,8,0.3)]' },
  pink: { border: 'border-pink-400/70', bg: 'from-pink-950/40 via-slate-900/60 to-pink-950/30', glow: 'shadow-[0_0_12px_rgba(236,72,153,0.2)]' },
  red: { border: 'border-red-400/70', bg: 'from-red-950/40 via-slate-900/60 to-red-950/30', glow: 'shadow-[0_0_10px_rgba(239,68,68,0.2)]' },
  orange: { border: 'border-orange-400/60', bg: 'from-orange-950/30 via-slate-900/60 to-orange-950/20', glow: '' },
  purple: { border: 'border-purple-400/60', bg: 'from-purple-950/30 via-slate-900/60 to-purple-950/20', glow: '' },
  blue: { border: 'border-blue-400/60', bg: 'from-blue-950/30 via-slate-900/60 to-blue-950/20', glow: '' },
  green: { border: 'border-green-400/50', bg: 'from-green-950/20 via-slate-900/60 to-green-950/20', glow: '' },
  white: { border: 'border-slate-600/50', bg: 'from-slate-800/40 via-slate-900/60 to-slate-800/40', glow: '' },
}

const STAR_ABILITY: Record<number, number> = {
  1: 0, 2: 1, 3: 2, 4: 4, 5: 6, 6: 8, 7: 11, 8: 14, 9: 17, 10: 21,
}

function getFrameKey(overall: number, star: number): string {
  const bonus = STAR_ABILITY[star] ?? 0
  const v = overall - bonus + star - 1
  if (v >= 97) return 'rainbow'
  if (v >= 94) return 'pink'
  if (v >= 92) return 'red'
  if (v >= 89) return 'orange'
  if (v >= 87) return 'purple'
  if (v >= 84) return 'blue'
  if (v >= 82) return 'green'
  return 'white'
}

function StarDisplay({ star }: { star: number }) {
  if (star <= 5) {
    return (
      <div className="flex gap-0.5 justify-center">
        {Array.from({ length: star }).map((_, i) => (
          <div key={i} className="w-2 h-2 bg-cyan-400 rotate-45 opacity-90" />
        ))}
      </div>
    )
  }
  return (
    <div className="flex items-center gap-0.5 justify-center">
      <div className="w-2 h-2 bg-cyan-400 rotate-45 opacity-90" />
      <span className="text-[9px] text-cyan-400 font-bold">×{star}</span>
    </div>
  )
}

export default function PlayerCard({
  playerId, name, position, overall, star, style,
  size = 'md', onClick, selected, badge, className = ''
}: PlayerCardProps) {
  const frameKey = getFrameKey(overall, star)
  const frame = FRAME_COLORS[frameKey]
  const avatarUrl = `/game-assets/avatars/${playerId}.png`

  const sizeClasses = {
    sm: 'w-[90px]',
    md: 'w-[110px]',
    lg: 'w-[140px]',
  }

  const avatarSizes = {
    sm: 'w-10 h-10',
    md: 'w-14 h-14',
    lg: 'w-20 h-20',
  }

  return (
    <div
      className={`
        ${sizeClasses[size]} relative flex flex-col items-center rounded-lg border-2 overflow-hidden
        cursor-pointer transition-all hover:scale-105
        ${frame.border} ${frame.glow}
        bg-gradient-to-b ${frame.bg}
        ${selected ? 'ring-2 ring-gold scale-95' : ''}
        ${className}
      `}
      onClick={onClick}
    >
      {/* Star row */}
      <div className="pt-1.5 pb-0.5">
        <StarDisplay star={star} />
      </div>

      {/* Overall + Position */}
      <div className="flex items-baseline gap-1 mb-0.5">
        <span className={`text-lg font-black leading-none ${overallColor(overall, star)}`}>{overall}</span>
        <span className="text-[8px] text-slate-400 uppercase">{position}</span>
      </div>

      {/* Avatar */}
      <div className={`${avatarSizes[size]} rounded-full overflow-hidden border border-white/20 bg-slate-800 mb-1`}>
        <img
          src={avatarUrl}
          alt={name}
          className="w-full h-full object-cover"
          onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
        />
      </div>

      {/* Name */}
      <div className="text-[9px] text-slate-200 font-medium truncate w-full text-center px-1">{name}</div>

      {/* Style */}
      {style && (
        <div className="text-[7px] text-emerald-400/80 truncate w-full text-center px-1 mb-1">
          {STYLE_NAMES[style] || style}
        </div>
      )}

      {/* Badge overlay */}
      {badge && (
        <div className="absolute top-1 right-1 text-[7px] font-bold text-gold bg-black/60 px-1 rounded">
          {badge}
        </div>
      )}
    </div>
  )
}
