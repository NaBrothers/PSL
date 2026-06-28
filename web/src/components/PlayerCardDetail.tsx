import { abilityColor, normalizePositionRating, ratingDiffClass, ratingDiffText } from '@/lib/card-display'
import RadarChart, { computeRadarValues, RADAR_LABELS, RADAR_LABELS_GK } from '@/components/RadarChart'

interface PlayerCardDetailProps {
  detail: any
}

export default function PlayerCardDetail({ detail }: PlayerCardDetailProps) {
  if (!detail) return <p className="text-slate-500 text-center py-4">加载中...</p>

  const rMap: Record<string, any> = detail.all_position_ratings
    ? Object.fromEntries(
        detail.all_position_ratings.map((item: any) => {
          const pos = normalizePositionRating(item, detail.overall)
          return [pos.position, pos]
        })
      )
    : {}

  const layout = [
    [null, null, "ST", null, null],
    ["LRW", null, "CF", null, "LRW"],
    [null, null, "AM", null, null],
    ["LRM", null, "CM", null, "LRM"],
    [null, null, "DM", null, null],
    ["LRB", null, "CB", null, "LRB"],
    [null, null, "GK", null, null],
  ]

  return (
    <div className="space-y-3 relative">
      {detail.player_id && (
        <div className="absolute -top-1 right-0 w-16 h-16 rounded-lg overflow-hidden border border-slate-600/50 bg-slate-800">
          <img
            src={`/game-assets/avatars/${detail.player_id}.png`}
            alt={detail.name}
            className="w-full h-full object-cover"
            onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
          />
        </div>
      )}
      <div className="flex items-center gap-3 text-sm pr-18">
        <span className="text-yellow-400">{'★'.repeat(Math.min(detail.star, 5))}{detail.star > 5 ? `×${detail.star}` : ''}</span>
        <span className="text-green-400">◆+{detail.breach}</span>
        <span className="text-slate-300">{detail.style_name || detail.style}</span>
      </div>

      {detail.position_ratings && (
        <div className="flex gap-3 text-sm flex-wrap">
          {detail.position_ratings.map((item: any) => {
            const pos = normalizePositionRating(item, detail.overall)
            return (
              <span key={pos.position} className="text-slate-200">
                {pos.position}: <span className={`font-bold ${abilityColor(pos.rating)}`}>{pos.rating}</span>
                {pos.diff !== 0 && <span className={`ml-0.5 text-xs ${ratingDiffClass(pos.diff)}`}>{ratingDiffText(pos.diff)}</span>}
              </span>
            )
          })}
        </div>
      )}

      <div className="text-xs text-slate-500">
        {detail.age}岁 {detail.height}cm {detail.weight}kg 身价 ${detail.price?.toLocaleString()}
      </div>

      {detail.all_position_ratings && (
        <div className="border-t border-slate-700 pt-2">
          <div className="flex gap-0 items-center">
            <div className="flex-1 min-w-0">
              <div className="grid grid-cols-5 gap-y-0 text-[10px] text-center">
                {layout.map((row, ri) => row.map((cell, ci) => (
                  <div key={`${ri}-${ci}`} className="h-[22px] flex items-center justify-center">
                    {cell && rMap[cell] !== undefined && (
                      <span className="whitespace-nowrap">
                        <span className="text-slate-500">{cell} </span>
                        <span className={`font-bold ${abilityColor(rMap[cell].rating)}`}>{rMap[cell].rating}</span>
                        {rMap[cell].diff !== 0 && <span className={`ml-0.5 text-[8px] ${ratingDiffClass(rMap[cell].diff)}`}>{ratingDiffText(rMap[cell].diff)}</span>}
                      </span>
                    )}
                  </div>
                )))}
              </div>
            </div>
            {detail.abilities && (
              <div className="w-[160px] flex-shrink-0 flex items-center justify-center">
                <RadarChart values={computeRadarValues(detail.abilities, detail.position === 'GK')} labels={detail.position === 'GK' ? RADAR_LABELS_GK : RADAR_LABELS} size={155} />
              </div>
            )}
          </div>
        </div>
      )}

      {detail.abilities && (
        <div className="border-t border-slate-700 pt-2">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
            {Object.entries(detail.abilities as Record<string, {value: number; name: string; ext: number; style_boosted?: boolean}>).map(([key, ab]) => (
              <div key={key} className="flex justify-between">
                <span className={ab.style_boosted ? "text-amber-400" : "text-slate-400"}>{ab.name}</span>
                <span><span className={`font-bold ${abilityColor(ab.value)}`}>{ab.value}</span>{ab.ext > 0 && <span className="text-green-400 text-xs ml-0.5">(+{ab.ext})</span>}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {detail.season && (
        <div className="border-t border-slate-700 pt-2">
          <p className="text-xs text-slate-500 mb-1">赛季</p>
          <div className="grid grid-cols-5 gap-1 text-center text-xs">
            <div><div className="text-slate-400">出场</div><div className="text-slate-200">{detail.season.appearance}</div></div>
            <div><div className="text-slate-400">进球</div><div className="text-slate-200">{detail.season.goal}</div></div>
            <div><div className="text-slate-400">助攻</div><div className="text-slate-200">{detail.season.assist}</div></div>
            <div><div className="text-slate-400">抢断</div><div className="text-slate-200">{detail.season.tackle}</div></div>
            <div><div className="text-slate-400">扑救</div><div className="text-slate-200">{detail.season.save}</div></div>
          </div>
        </div>
      )}

      {detail.career && (
        <div className="border-t border-slate-700 pt-2">
          <p className="text-xs text-slate-500 mb-1">生涯</p>
          <div className="grid grid-cols-5 gap-1 text-center text-xs">
            <div><div className="text-slate-400">出场</div><div className="text-slate-200">{detail.career.appearance}</div></div>
            <div><div className="text-slate-400">进球</div><div className="text-slate-200">{detail.career.goal}</div></div>
            <div><div className="text-slate-400">助攻</div><div className="text-slate-200">{detail.career.assist}</div></div>
            <div><div className="text-slate-400">抢断</div><div className="text-slate-200">{detail.career.tackle}</div></div>
            <div><div className="text-slate-400">扑救</div><div className="text-slate-200">{detail.career.save}</div></div>
          </div>
        </div>
      )}
    </div>
  )
}
