import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { abilityColor, overallColor } from '@/lib/card-display'
import RadarChart, { computeRadarValues, RADAR_LABELS, RADAR_LABELS_GK } from '@/components/RadarChart'

interface CompareViewProps {
  data: any
  open: boolean
  onClose: () => void
}

export default function CompareView({ data, open, onClose }: CompareViewProps) {
  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent className="max-h-[85vh] overflow-y-auto scrollbar-hide">
        <DialogHeader><DialogTitle>能力对比</DialogTitle></DialogHeader>
        {data && (
          <div className="space-y-2">
            <div className="flex justify-between text-sm font-bold mb-2">
              <span className={overallColor(data.card1.overall)}>{data.card1.name} {data.card1.overall}</span>
              <span className={overallColor(data.card2.overall)}>{data.card2.name} {data.card2.overall}</span>
            </div>
            {data.card1.abilities && Object.entries(data.card1.abilities as Record<string, {value: number; name: string}>).map(([key, ab]) => {
              const v1 = ab.value
              const v2 = (data.card2.abilities as any)[key]?.value || 0
              const leftAdv = Math.max(0, v1 - v2)
              const rightAdv = Math.max(0, v2 - v1)
              return (
                <div key={key} className="grid grid-cols-[28px_24px_1fr_40px_1fr_24px_28px] items-center gap-1 text-xs">
                  <span className={`text-right font-bold ${abilityColor(v1)}`}>{v1}</span>
                  <span className="text-right text-green-400">{leftAdv > 0 ? `+${leftAdv}` : ""}</span>
                  <div className="flex-1 flex items-center gap-1">
                    <div className="flex-1 h-1.5 bg-slate-800 rounded overflow-hidden flex justify-end"><div className="bg-accent/70 h-full" style={{width: `${Math.min(v1, 120) / 1.2}%`}} /></div>
                  </div>
                  <span className="text-slate-500 text-center">{ab.name}</span>
                  <div className="flex-1 h-1.5 bg-slate-800 rounded overflow-hidden"><div className="bg-red-400/70 h-full" style={{width: `${Math.min(v2, 120) / 1.2}%`}} /></div>
                  <span className="text-green-400">{rightAdv > 0 ? `+${rightAdv}` : ""}</span>
                  <span className={`font-bold ${abilityColor(v2)}`}>{v2}</span>
                </div>
              )
            })}
            {data.card1.abilities && data.card2.abilities && (
              <div className="border-t border-slate-700 pt-3 mt-2">
                <div className="flex justify-center gap-4 text-xs mb-2">
                  <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-[#4fc3f7] inline-block" />{data.card1.name}</span>
                  <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-[#4ade80] inline-block" />{data.card2.name}</span>
                </div>
                <div className="flex justify-center">
                  <RadarChart
                    values={computeRadarValues(data.card1.abilities, data.card1.position === 'GK' && data.card2.position === 'GK')}
                    labels={data.card1.position === 'GK' && data.card2.position === 'GK' ? RADAR_LABELS_GK : RADAR_LABELS}
                    secondValues={computeRadarValues(data.card2.abilities, data.card1.position === 'GK' && data.card2.position === 'GK')}
                    size={220}
                  />
                </div>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
