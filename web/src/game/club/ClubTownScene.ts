import Phaser from 'phaser'
import type { ClubBuilding, ClubTownSceneData } from './types'

const WORLD_WIDTH = 960
const WORLD_HEIGHT = 640
const TILE = 16

const KIT_COLORS = [0x2563eb, 0xdc2626, 0x16a34a, 0xca8a04, 0x7c3aed, 0x0f766e, 0xbe123c, 0x4f46e5, 0x0891b2, 0x65a30d, 0xc2410c]

interface RoutePoint {
  x: number
  y: number
}

export class ClubTownScene extends Phaser.Scene {
  private dataConfig!: ClubTownSceneData
  private dragStart?: { pointerX: number; pointerY: number; scrollX: number; scrollY: number }

  constructor() {
    super('ClubTownScene')
  }

  init(data: ClubTownSceneData) {
    this.dataConfig = data
  }

  create() {
    this.cameras.main.setBounds(0, 0, WORLD_WIDTH, WORLD_HEIGHT)
    this.physics.world.setBounds(0, 0, WORLD_WIDTH, WORLD_HEIGHT)
    this.createTextures()
    this.drawMap()
    this.drawBuildings()
    this.drawAgents()
    this.setupCamera()
  }

  private createTextures() {
    this.makeTileTexture('grass-a', 0x8bd26a, 0x79bf58)
    this.makeTileTexture('grass-b', 0x92d872, 0x7fca5f)
    this.makeTileTexture('road', 0xe8d68f, 0xd1b873)
    this.makeTileTexture('plaza', 0xd7d6c3, 0xbec0ad)
    this.makeTreeTexture()
    this.makeConeTexture()
    this.makeAgentTextures()
  }

  private makeTileTexture(key: string, base: number, accent: number) {
    const g = this.add.graphics()
    g.fillStyle(base, 1).fillRect(0, 0, TILE, TILE)
    g.fillStyle(accent, 1)
    g.fillRect(2, 3, 2, 2)
    g.fillRect(10, 11, 2, 2)
    g.generateTexture(key, TILE, TILE)
    g.destroy()
  }

  private makeTreeTexture() {
    const g = this.add.graphics()
    g.fillStyle(0x7a4a26, 1).fillRect(7, 10, 3, 5)
    g.fillStyle(0x2f8f42, 1).fillRect(4, 5, 9, 7)
    g.fillStyle(0x49b957, 1).fillRect(6, 2, 7, 7)
    g.fillStyle(0x1f6f34, 1).fillRect(2, 8, 7, 5)
    g.generateTexture('tree', 16, 16)
    g.destroy()
  }

  private makeConeTexture() {
    const g = this.add.graphics()
    g.fillStyle(0xf97316, 1).fillTriangle(8, 2, 13, 13, 3, 13)
    g.fillStyle(0xffedd5, 1).fillRect(5, 10, 6, 2)
    g.generateTexture('cone', 16, 16)
    g.destroy()
  }

  private makeAgentTextures() {
    KIT_COLORS.forEach((color, idx) => {
      const g = this.add.graphics()
      g.fillStyle(0xf2c29b, 1).fillRect(5, 1, 6, 5)
      g.fillStyle(0x3b2517, 1).fillRect(4, 0, 8, 2)
      g.fillStyle(color, 1).fillRect(4, 7, 8, 8)
      g.fillStyle(0xffffff, 1).fillRect(5, 9, 6, 1)
      g.fillStyle(0x1f2937, 1).fillRect(4, 15, 3, 5)
      g.fillRect(9, 15, 3, 5)
      g.fillStyle(0x111827, 1).fillRect(3, 20, 4, 2)
      g.fillRect(9, 20, 4, 2)
      g.generateTexture(`agent-${idx}`, 16, 22)
      g.destroy()
    })
  }

  private drawMap() {
    for (let y = 0; y < WORLD_HEIGHT; y += TILE) {
      for (let x = 0; x < WORLD_WIDTH; x += TILE) {
        const key = ((x / TILE + y / TILE) % 3 === 0) ? 'grass-b' : 'grass-a'
        this.add.image(x, y, key).setOrigin(0)
      }
    }

    this.drawRoad(470, 86, 470, 552, 3)
    this.drawRoad(144, 348, 812, 348, 3)
    this.drawRoad(238, 482, 470, 348, 2)
    this.drawRoad(470, 348, 718, 226, 2)
    this.drawRoad(470, 348, 724, 482, 2)
    this.drawRoad(470, 348, 284, 188, 2)

    this.drawPitch(72, 104, 330, 210)
    this.drawTrainingPitch(626, 82, 220, 132)

    const trees = [
      [36, 58], [76, 64], [896, 68], [842, 64], [48, 536], [82, 574],
      [884, 552], [832, 568], [378, 548], [562, 76], [164, 428], [760, 320],
    ]
    trees.forEach(([x, y]) => this.add.image(x, y, 'tree').setScale(1.5).setDepth(2))

    for (let i = 0; i < 9; i++) {
      this.add.image(640 + i * 18, 214, 'cone').setDepth(3)
    }
  }

  private drawRoad(x1: number, y1: number, x2: number, y2: number, widthTiles: number) {
    const g = this.add.graphics().setDepth(1)
    g.lineStyle(widthTiles * TILE, 0xe6d28a, 1)
    g.beginPath()
    g.moveTo(x1, y1)
    g.lineTo(x2, y2)
    g.strokePath()
    g.lineStyle(Math.max(2, widthTiles * TILE - 10), 0xf1e0a6, 1)
    g.beginPath()
    g.moveTo(x1, y1)
    g.lineTo(x2, y2)
    g.strokePath()
  }

  private drawPitch(x: number, y: number, w: number, h: number) {
    const g = this.add.graphics().setDepth(2)
    g.fillStyle(0x3a9a48, 1).fillRect(x, y, w, h)
    for (let i = 0; i < 6; i++) {
      g.fillStyle(i % 2 === 0 ? 0x2f8d3f : 0x43aa52, 1).fillRect(x + i * (w / 6), y, w / 6, h)
    }
    g.lineStyle(3, 0xffffff, 0.85).strokeRect(x + 10, y + 10, w - 20, h - 20)
    g.lineBetween(x + w / 2, y + 10, x + w / 2, y + h - 10)
    g.strokeCircle(x + w / 2, y + h / 2, 34)
    g.strokeRect(x + 10, y + h / 2 - 42, 56, 84)
    g.strokeRect(x + w - 66, y + h / 2 - 42, 56, 84)
    this.add.text(x + 14, y + h - 30, 'MAIN PITCH', { fontFamily: 'monospace', fontSize: '14px', color: '#ffffff' }).setDepth(3)
  }

  private drawTrainingPitch(x: number, y: number, w: number, h: number) {
    const g = this.add.graphics().setDepth(2)
    g.fillStyle(0x4bb25b, 1).fillRect(x, y, w, h)
    g.lineStyle(2, 0xffffff, 0.75).strokeRect(x + 8, y + 8, w - 16, h - 16)
    for (let i = 0; i < 4; i++) {
      g.lineStyle(2, 0xfacc15, 0.9).lineBetween(x + 32 + i * 34, y + 28, x + 48 + i * 34, y + 28)
    }
    this.add.text(x + 12, y + h - 26, 'TRAINING', { fontFamily: 'monospace', fontSize: '13px', color: '#ffffff' }).setDepth(3)
  }

  private drawBuildings() {
    this.dataConfig.buildings.forEach(building => {
      this.drawBuilding(building)
    })
  }

  private drawBuilding(b: ClubBuilding) {
    const depth = b.y + b.height
    const g = this.add.graphics().setDepth(depth)
    const colors = this.buildingColors(b.kind)
    g.fillStyle(0x000000, 0.22).fillRect(b.x + 8, b.y + b.height - 6, b.width, 14)
    g.fillStyle(colors.wall, 1).fillRect(b.x, b.y + 24, b.width, b.height - 24)
    g.fillStyle(colors.roof, 1).fillRect(b.x - 8, b.y + 8, b.width + 16, 26)
    g.fillStyle(colors.roofDark, 1).fillRect(b.x - 2, b.y, b.width + 4, 12)
    g.fillStyle(0x3f2d20, 1).fillRect(b.x + b.width / 2 - 10, b.y + b.height - 28, 20, 28)
    for (let i = 0; i < Math.max(2, Math.floor(b.width / 42)); i++) {
      g.fillStyle(0xbfe8ff, 1).fillRect(b.x + 16 + i * 42, b.y + 42, 18, 18)
      g.fillStyle(0x7aa5bd, 1).fillRect(b.x + 19 + i * 42, b.y + 45, 12, 12)
    }

    const label = this.add.text(b.x + b.width / 2, b.y + b.height + 8, b.name, {
      fontFamily: 'monospace',
      fontSize: '14px',
      color: '#1f2937',
      backgroundColor: 'rgba(255,255,255,0.78)',
      padding: { x: 5, y: 2 },
    }).setOrigin(0.5, 0).setDepth(depth + 1)
    label.setResolution(2)

    this.add.zone(b.x, b.y, b.width, b.height)
      .setOrigin(0)
      .setInteractive({ useHandCursor: true })
      .on('pointerup', () => this.dataConfig.onBuildingClick(b.id))
      .setDepth(depth + 2)
  }

  private buildingColors(kind: ClubBuilding['kind']) {
    const map = {
      stadium: { wall: 0xd7f3dc, roof: 0x2d8f43, roofDark: 0x1d6b31 },
      training: { wall: 0xd7ecff, roof: 0x3b82f6, roofDark: 0x1d4ed8 },
      academy: { wall: 0xfff0bd, roof: 0xf59e0b, roofDark: 0xb45309 },
      scout: { wall: 0xe9ddff, roof: 0x7c3aed, roofDark: 0x4c1d95 },
      commerce: { wall: 0xffdfdf, roof: 0xef4444, roofDark: 0x991b1b },
      medical: { wall: 0xecfeff, roof: 0x14b8a6, roofDark: 0x0f766e },
      clubhouse: { wall: 0xe7e5e4, roof: 0x64748b, roofDark: 0x334155 },
    }
    return map[kind]
  }

  private drawAgents() {
    this.dataConfig.agents.forEach((agent, idx) => {
      const route = this.routeForAgent(idx)
      const start = route[0]
      const container = this.add.container(start.x, start.y).setDepth(start.y + 20)
      const sprite = this.add.image(0, 0, `agent-${idx % KIT_COLORS.length}`).setOrigin(0.5, 1)
      sprite.setScale(1.15)
      const name = this.shortName(agent.name)
      const label = this.add.text(0, -30, name, {
        fontFamily: 'monospace',
        fontSize: '11px',
        color: '#111827',
        backgroundColor: 'rgba(255,255,255,0.86)',
        padding: { x: 4, y: 1 },
      }).setOrigin(0.5, 1)
      label.setResolution(2)
      container.add([sprite, label])
      container.setSize(36, 44)
      container.setInteractive(new Phaser.Geom.Rectangle(-18, -42, 36, 44), Phaser.Geom.Rectangle.Contains)
      container.on('pointerup', () => this.dataConfig.onAgentClick(agent.cardId))
      this.walkRoute(container, route, idx * 450)
    })
  }

  private routeForAgent(idx: number): RoutePoint[] {
    const routes: RoutePoint[][] = [
      [{ x: 190, y: 334 }, { x: 470, y: 348 }, { x: 682, y: 150 }, { x: 470, y: 348 }],
      [{ x: 260, y: 278 }, { x: 470, y: 348 }, { x: 712, y: 470 }, { x: 470, y: 348 }],
      [{ x: 336, y: 390 }, { x: 470, y: 348 }, { x: 300, y: 520 }, { x: 470, y: 348 }],
      [{ x: 690, y: 335 }, { x: 470, y: 348 }, { x: 512, y: 548 }, { x: 470, y: 348 }],
      [{ x: 540, y: 292 }, { x: 718, y: 226 }, { x: 470, y: 348 }, { x: 238, y: 482 }],
      [{ x: 520, y: 410 }, { x: 724, y: 482 }, { x: 470, y: 348 }, { x: 284, y: 188 }],
    ]
    return routes[idx % routes.length]
  }

  private walkRoute(target: Phaser.GameObjects.Container, route: RoutePoint[], delay: number) {
    let index = 0
    const moveNext = () => {
      index = (index + 1) % route.length
      const point = route[index]
      this.tweens.add({
        targets: target,
        x: point.x,
        y: point.y,
        duration: Phaser.Math.Distance.Between(target.x, target.y, point.x, point.y) * 12,
        ease: 'Linear',
        onUpdate: () => target.setDepth(target.y + 20),
        onComplete: () => this.time.delayedCall(700, moveNext),
      })
    }
    this.time.delayedCall(delay, moveNext)
  }

  private shortName(name: string) {
    return name.length > 12 ? `${name.slice(0, 11)}...` : name
  }

  private setupCamera() {
    const camera = this.cameras.main
    const centerX = Math.max(0, (WORLD_WIDTH - camera.width) / 2)
    const centerY = Math.max(0, (WORLD_HEIGHT - camera.height) / 2)
    camera.scrollX = centerX
    camera.scrollY = centerY

    this.input.on('pointerdown', (pointer: Phaser.Input.Pointer) => {
      this.dragStart = { pointerX: pointer.x, pointerY: pointer.y, scrollX: camera.scrollX, scrollY: camera.scrollY }
    })
    this.input.on('pointermove', (pointer: Phaser.Input.Pointer) => {
      if (!this.dragStart || !pointer.isDown) return
      camera.scrollX = this.dragStart.scrollX + (this.dragStart.pointerX - pointer.x)
      camera.scrollY = this.dragStart.scrollY + (this.dragStart.pointerY - pointer.y)
    })
    this.input.on('pointerup', () => {
      this.dragStart = undefined
    })
  }
}
