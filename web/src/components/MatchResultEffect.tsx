import { useEffect, useState } from 'react'

interface Props {
  result: 'win' | 'lose' | 'tie'
}

export default function MatchResultEffect({ result }: Props) {
  const [particles, setParticles] = useState<{id: number; x: number; delay: number; color: string; size: number}[]>([])

  useEffect(() => {
    if (result === 'win') {
      const p = Array.from({length: 40}, (_, i) => ({
        id: i,
        x: Math.random() * 100,
        delay: Math.random() * 1.5,
        color: ['#fbbf24', '#4ade80', '#60a5fa', '#f472b6', '#a78bfa'][Math.floor(Math.random() * 5)],
        size: Math.random() * 8 + 4,
      }))
      setParticles(p)
    }
  }, [result])

  if (result === 'win') {
    return (
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-10">
        {particles.map(p => (
          <div
            key={p.id}
            className="absolute top-0 animate-confettiFall"
            style={{
              left: `${p.x}%`,
              width: p.size,
              height: p.size * 1.5,
              background: p.color,
              animationDelay: `${p.delay}s`,
              borderRadius: '2px',
              transform: `rotate(${Math.random() * 360}deg)`,
            }}
          />
        ))}
      </div>
    )
  }

  if (result === 'lose') {
    return (
      <div className="absolute inset-0 bg-gradient-to-b from-red-950/20 to-transparent pointer-events-none z-10 animate-fadeIn" />
    )
  }

  return null
}
