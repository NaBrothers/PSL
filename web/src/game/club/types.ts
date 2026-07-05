export interface ClubAgent {
  id: number
  cardId: number
  playerId: number
  name: string
  overall: number
  star: number
  position?: string
}

export interface ClubBuilding {
  id: string
  name: string
  level: number
  status: string
  production: string
  actionLabel: string
  path: string
  x: number
  y: number
  width: number
  height: number
  kind: 'stadium' | 'training' | 'academy' | 'scout' | 'commerce' | 'medical' | 'clubhouse'
}

export interface ClubTownCallbacks {
  onBuildingClick: (id: string) => void
  onAgentClick: (cardId: number) => void
}

export interface ClubTownSceneData extends ClubTownCallbacks {
  agents: ClubAgent[]
  buildings: ClubBuilding[]
}
