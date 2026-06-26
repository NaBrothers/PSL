export const STYLE_NAMES: Record<string, string> = {
  sniper: '狙击手',
  finisher: '终结者',
  deadeye: '恶魔眼',
  marksman: '神枪手',
  hawk: '凤头鹰',
  artist: '艺术家',
  architect: '建筑师',
  powerhous: '抢球机器',
  maestro: '大师',
  engine: '发动机',
  sentinal: '哨兵',
  guardian: '护卫',
  gladiator: '斗士',
  backbone: '骨干',
  anchor: '铁锚',
  hunter: '狩猎者',
  catalyst: '催化剂',
  shadow: '暗影',
  speedster: '疾速魔',
  slugger: '重炮手',
  bronzewall: '铜墙',
  ironwall: '铁壁',
  agilecat: '灵猫',
  gloves: '手套',
}

const STAR_ABILITY: Record<number, number> = {
  1: 0, 2: 1, 3: 2, 4: 4, 5: 6, 6: 8, 7: 11, 8: 14, 9: 17, 10: 21,
}

function colorValue(overall: number, star: number): number {
  const bonus = STAR_ABILITY[star] ?? 0
  const base = overall - bonus
  return base + star - 1
}

export function overallColor(ov: number, star?: number): string {
  const v = star != null ? colorValue(ov, star) : ov
  if (v >= 97) return 'text-transparent bg-clip-text bg-[linear-gradient(90deg,#ef4444,#f97316,#eab308,#22c55e,#06b6d4,#3b82f6,#a855f7,#ec4899)]'
  if (v >= 94) return 'text-pink-400'
  if (v >= 92) return 'text-red-400'
  if (v >= 89) return 'text-orange-400'
  if (v >= 87) return 'text-purple-400'
  if (v >= 84) return 'text-blue-400'
  if (v >= 82) return 'text-green-400'
  return 'text-slate-300'
}

export function abilityColor(val: number): string {
  if (val >= 110) return 'text-transparent bg-clip-text bg-gradient-to-r from-red-400 via-green-400 to-blue-400'
  if (val >= 100) return 'text-pink-400'
  if (val >= 95) return 'text-red-400'
  if (val >= 90) return 'text-orange-400'
  if (val >= 88) return 'text-purple-400'
  if (val >= 85) return 'text-blue-400'
  if (val >= 82) return 'text-green-400'
  return 'text-slate-300'
}

export function rarityBorder(overall: number, star?: number): string {
  const v = star != null ? colorValue(overall, star) : overall
  if (v >= 97) return 'border-yellow-300/90 shadow-[0_0_20px_rgba(59,130,246,0.35)]'
  if (v >= 94) return 'border-pink-300/60'
  if (v >= 92) return 'border-red-400/60'
  if (v >= 89) return 'border-orange-400/60'
  if (v >= 87) return 'border-purple-400/60'
  if (v >= 84) return 'border-blue-400/60'
  if (v >= 82) return 'border-green-400/60'
  return 'border-slate-700'
}

export function rarityBg(overall: number, star?: number): string {
  const v = star != null ? colorValue(overall, star) : overall
  if (v >= 97) return 'bg-[linear-gradient(135deg,rgba(127,29,29,0.45),rgba(15,23,42,0.95),rgba(30,64,175,0.45),rgba(134,25,143,0.35))]'
  if (v >= 94) return 'bg-gradient-to-b from-pink-950/30 to-slate-900'
  if (v >= 92) return 'bg-gradient-to-b from-red-950/30 to-slate-900'
  if (v >= 87) return 'bg-gradient-to-b from-purple-950/30 to-slate-900'
  if (v >= 84) return 'bg-gradient-to-b from-blue-950/30 to-slate-900'
  return 'bg-slate-900'
}

export function rarityGlow(overall: number, star?: number): string {
  const v = star != null ? colorValue(overall, star) : overall
  if (v >= 97) return 'shadow-blue-400/40 shadow-xl border-yellow-300/90'
  if (v >= 94) return 'shadow-pink-400/30 shadow-lg border-pink-400/60'
  if (v >= 92) return 'shadow-red-500/30 shadow-lg border-red-400/60'
  if (v >= 89) return 'shadow-orange-500/30 shadow-lg border-orange-400/60'
  if (v >= 87) return 'shadow-purple-500/30 shadow-lg border-purple-400/60'
  if (v >= 84) return 'shadow-blue-500/20 shadow-md border-blue-400/60'
  return 'border-slate-700'
}

export function cardTone(ov: number, star?: number): string {
  const v = star != null ? colorValue(ov, star) : ov
  if (v >= 97) return 'bg-[linear-gradient(135deg,#ef4444,#f97316,#eab308,#22c55e,#06b6d4,#3b82f6,#a855f7,#ec4899)]'
  if (v >= 94) return 'bg-pink-400'
  if (v >= 92) return 'bg-red-500'
  if (v >= 89) return 'bg-orange-500'
  if (v >= 87) return 'bg-purple-500'
  if (v >= 84) return 'bg-blue-500'
  if (v >= 82) return 'bg-green-500'
  return 'bg-slate-500'
}

export type PositionRating = { position: string; rating: number; diff: number } | [string, number]

export function normalizePositionRating(item: PositionRating, baseOverall: number) {
  if (Array.isArray(item)) {
    return { position: item[0], rating: item[1], diff: item[1] - baseOverall }
  }
  return item
}

export function ratingDiffClass(diff: number): string {
  if (diff > 0) return 'text-red-400'
  if (diff < 0) return 'text-green-400'
  return 'text-slate-500'
}

export function ratingDiffText(diff: number): string {
  if (diff > 0) return `▲${diff}`
  if (diff < 0) return `▼${Math.abs(diff)}`
  return ''
}
