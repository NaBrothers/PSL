import { useState, useEffect } from 'react'

interface Props {
  value: number
  className?: string
  duration?: number
}

export default function FlipNumber({ value, className = '', duration = 1000 }: Props) {
  const [display, setDisplay] = useState(0)

  useEffect(() => {

    const startTime = Date.now()
    const animate = () => {
      const elapsed = Date.now() - startTime
      const progress = Math.min(elapsed / duration, 1)
      const eased = 1 - Math.pow(1 - progress, 3)
      setDisplay(Math.round(eased * value))
      if (progress < 1) requestAnimationFrame(animate)
    }
    requestAnimationFrame(animate)
  }, [value, duration])

  return <span className={className}>{display}</span>
}
