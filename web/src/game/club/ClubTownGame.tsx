import { useEffect, useRef } from 'react'
import Phaser from 'phaser'
import { ClubTownScene } from './ClubTownScene'
import type { ClubAgent, ClubBuilding } from './types'

interface ClubTownGameProps {
  agents: ClubAgent[]
  buildings: ClubBuilding[]
  onBuildingClick: (id: string) => void
  onAgentClick: (cardId: number) => void
}

export default function ClubTownGame({ agents, buildings, onBuildingClick, onAgentClick }: ClubTownGameProps) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const gameRef = useRef<Phaser.Game | null>(null)
  const callbacksRef = useRef({ onBuildingClick, onAgentClick })

  callbacksRef.current = { onBuildingClick, onAgentClick }

  useEffect(() => {
    if (!hostRef.current || gameRef.current) return

    const scene = new ClubTownScene()
    const game = new Phaser.Game({
      type: Phaser.AUTO,
      parent: hostRef.current,
      backgroundColor: '#8bd26a',
      pixelArt: true,
      antialias: false,
      roundPixels: true,
      scale: {
        mode: Phaser.Scale.RESIZE,
        width: hostRef.current.clientWidth,
        height: hostRef.current.clientHeight,
      },
      physics: {
        default: 'arcade',
      },
      scene,
    })

    game.scene.start('ClubTownScene', {
      agents,
      buildings,
      onBuildingClick: (id: string) => callbacksRef.current.onBuildingClick(id),
      onAgentClick: (cardId: number) => callbacksRef.current.onAgentClick(cardId),
    })
    gameRef.current = game

    return () => {
      game.destroy(true)
      gameRef.current = null
    }
  }, [])

  useEffect(() => {
    const game = gameRef.current
    if (!game) return
    const scene = game.scene.getScene('ClubTownScene')
    if (!scene) return
    game.scene.stop('ClubTownScene')
    game.scene.start('ClubTownScene', {
      agents,
      buildings,
      onBuildingClick: (id: string) => callbacksRef.current.onBuildingClick(id),
      onAgentClick: (cardId: number) => callbacksRef.current.onAgentClick(cardId),
    })
  }, [agents, buildings])

  return <div ref={hostRef} className="h-full w-full touch-none" />
}
