export interface ClubAgent {
  id: number
  cardId: number
  playerId: number
  name: string
  overall: number
  star: number
  position?: string
  nameColor: string
}

export interface ClubBuilding {
  id: string
  name: string
  level: number
  status: string
  production: string
  actionLabel: string
  path: string
  plot: { x: number; y: number; width: number; height: number }
  building: { x: number; y: number; width: number; height: number }
  entry: { x: number; y: number }
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
