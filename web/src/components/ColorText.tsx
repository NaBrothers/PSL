import React from 'react'

const COLOR_MAP: Record<string, string> = {
  w: 'text-slate-300',
  g: 'text-green-400',
  b: 'text-blue-400',
  p: 'text-purple-400',
  o: 'text-orange-400',
  r: 'text-red-400',
  f: 'text-pink-400',
  x: 'text-amber-600',
  '$': 'text-transparent bg-clip-text bg-[linear-gradient(90deg,#ef4444,#f97316,#eab308,#22c55e,#06b6d4,#3b82f6,#a855f7,#ec4899)]',
}

export function ColorText({ text }: { text: string }) {
  const parts: React.ReactNode[] = []
  let remaining = text
  let key = 0

  while (remaining.length > 0) {
    const idx = remaining.indexOf('/~')
    if (idx === -1) {
      parts.push(<span key={key++}>{remaining}</span>)
      break
    }

    if (idx > 0) {
      parts.push(<span key={key++}>{remaining.slice(0, idx)}</span>)
    }

    remaining = remaining.slice(idx + 2)
    const colorCode = remaining[0]
    remaining = remaining.slice(1)
    const endIdx = remaining.indexOf('/')
    if (endIdx === -1) {
      parts.push(<span key={key++}>{remaining}</span>)
      break
    }

    const content = remaining.slice(0, endIdx)
    remaining = remaining.slice(endIdx + 1)
    const className = COLOR_MAP[colorCode] || 'text-slate-300'
    parts.push(<span key={key++} className={className}>{content}</span>)
  }

  return <>{parts}</>
}

export function stripColorMarkup(text: string): string {
  return text.replace(/\/~[a-z$]([^/]*)\/|\/~([^/]*)\//g, '$1$2')
}
