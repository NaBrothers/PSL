import Phaser from 'phaser'
import type { ClubBuilding, ClubTownSceneData } from './types'

const WORLD_WIDTH = 1280
const WORLD_HEIGHT = 720
const TILE = 16

const KIT_COLORS = {
  GK: 0xeab308,
  DEF: 0x2563eb,
  MID: 0x16a34a,
  FWD: 0xdc2626,
  STAFF: 0x7c3aed,
}

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
    this.makeTileTexture('grass-a', 0x8ed46a, 0x75bd52)
    this.makeTileTexture('grass-b', 0x98dc75, 0x82c960)
    this.makeTileTexture('grass-c', 0x84c85e, 0x6eb04d)
    this.makeTileTexture('road', 0xe9d88f, 0xc6aa66)
    this.makeTileTexture('road-edge', 0xd2bd79, 0xb79a56)
    this.makeTileTexture('plaza', 0xdcd9bf, 0xbfc2aa)
    this.makeTreeTexture()
    this.makeConeTexture()
    this.makeDecorationTextures()
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

  private makeDecorationTextures() {
    const lamp = this.add.graphics()
    lamp.fillStyle(0x475569, 1).fillRect(7, 4, 2, 12)
    lamp.fillStyle(0xfde68a, 1).fillRect(4, 2, 8, 4)
    lamp.fillStyle(0xfffbeb, 1).fillRect(6, 3, 4, 2)
    lamp.generateTexture('lamp', 16, 18)
    lamp.destroy()

    const bench = this.add.graphics()
    bench.fillStyle(0x7c4a2d, 1).fillRect(2, 6, 12, 3)
    bench.fillRect(2, 11, 12, 3)
    bench.fillStyle(0x334155, 1).fillRect(4, 9, 2, 7)
    bench.fillRect(10, 9, 2, 7)
    bench.generateTexture('bench', 16, 18)
    bench.destroy()

    const flag = this.add.graphics()
    flag.fillStyle(0x475569, 1).fillRect(4, 2, 2, 18)
    flag.fillStyle(0xef4444, 1).fillRect(6, 3, 10, 7)
    flag.fillStyle(0xfacc15, 1).fillRect(6, 8, 7, 2)
    flag.generateTexture('flag', 18, 22)
    flag.destroy()

    const ball = this.add.graphics()
    ball.fillStyle(0xffffff, 1).fillCircle(8, 8, 5)
    ball.fillStyle(0x111827, 1).fillRect(7, 5, 2, 2).fillRect(4, 9, 2, 2).fillRect(10, 9, 2, 2)
    ball.generateTexture('ball', 16, 16)
    ball.destroy()

    const sign = this.add.graphics()
    sign.fillStyle(0x78350f, 1).fillRect(7, 9, 2, 9)
    sign.fillStyle(0xfef3c7, 1).fillRect(1, 1, 14, 9)
    sign.fillStyle(0x92400e, 1).strokeRect(1, 1, 14, 9)
    sign.generateTexture('sign', 16, 18)
    sign.destroy()

    const flower = this.add.graphics()
    flower.fillStyle(0x2f8f42, 1).fillRect(0, 7, 16, 7)
    flower.fillStyle(0xf9a8d4, 1).fillRect(2, 3, 3, 3)
    flower.fillStyle(0xfef08a, 1).fillRect(7, 2, 3, 3)
    flower.fillStyle(0x93c5fd, 1).fillRect(12, 4, 3, 3)
    flower.generateTexture('flower-bed', 16, 16)
    flower.destroy()

    const hedge = this.add.graphics()
    hedge.fillStyle(0x276749, 1).fillRect(0, 5, 16, 9)
    hedge.fillStyle(0x38a169, 1).fillRect(1, 3, 14, 5)
    hedge.fillStyle(0x68d391, 1).fillRect(3, 4, 3, 2).fillRect(10, 4, 3, 2)
    hedge.generateTexture('hedge', 16, 16)
    hedge.destroy()

    const bus = this.add.graphics()
    bus.fillStyle(0xfacc15, 1).fillRect(1, 5, 30, 13)
    bus.fillStyle(0x111827, 1).fillRect(5, 8, 6, 5).fillRect(13, 8, 6, 5).fillRect(21, 8, 6, 5)
    bus.fillStyle(0x1f2937, 1).fillCircle(8, 19, 3).fillCircle(24, 19, 3)
    bus.generateTexture('team-bus', 32, 24)
    bus.destroy()

    const wall = this.add.graphics()
    wall.fillStyle(0xe5e7eb, 1).fillRect(1, 3, 14, 20)
    wall.fillStyle(0x94a3b8, 1).fillRect(3, 5, 10, 3).fillRect(3, 11, 10, 3).fillRect(3, 17, 10, 3)
    wall.generateTexture('training-wall', 16, 24)
    wall.destroy()

    const fountain = this.add.graphics()
    fountain.fillStyle(0x94a3b8, 1).fillRect(2, 12, 28, 12)
    fountain.fillStyle(0x60a5fa, 1).fillRect(5, 14, 22, 7)
    fountain.fillStyle(0xdbeafe, 1).fillRect(14, 5, 4, 12)
    fountain.fillRect(10, 8, 12, 3)
    fountain.generateTexture('fountain', 32, 28)
    fountain.destroy()
  }

  private makeAgentTextures() {
    Object.entries(KIT_COLORS).forEach(([role, color]) => {
      for (let frame = 0; frame < 2; frame++) {
        const g = this.add.graphics()
        g.fillStyle(0xf2c29b, 1).fillRect(5, 1, 6, 5)
        g.fillStyle(0x3b2517, 1).fillRect(4, 0, 8, 2)
        g.fillStyle(color, 1).fillRect(4, 7, 8, 8)
        g.fillStyle(0xffffff, 1).fillRect(5, 9, 6, 1)
        g.fillStyle(0xf2c29b, 1).fillRect(frame === 0 ? 2 : 3, 8, 2, 5)
        g.fillRect(frame === 0 ? 12 : 11, 8, 2, 5)
        g.fillStyle(0x1f2937, 1).fillRect(frame === 0 ? 3 : 5, 15, 3, 5)
        g.fillRect(frame === 0 ? 10 : 8, 15, 3, 5)
        g.fillStyle(0x111827, 1).fillRect(frame === 0 ? 2 : 5, 20, 4, 2)
        g.fillRect(frame === 0 ? 10 : 8, 20, 4, 2)
        g.generateTexture(`agent-${role}-${frame}`, 16, 22)
        g.destroy()
      }
    })
  }

  private drawMap() {
    for (let y = 0; y < WORLD_HEIGHT; y += TILE) {
      for (let x = 0; x < WORLD_WIDTH; x += TILE) {
        const roll = (x / TILE * 7 + y / TILE * 11) % 9
        const key = roll === 0 ? 'grass-c' : roll <= 3 ? 'grass-b' : 'grass-a'
        this.add.image(x, y, key).setOrigin(0)
      }
    }

    this.drawRoadNetwork()
    this.drawGrandPlaza()
    this.drawFacilityGrounds()
    this.drawDecorations()
  }

  private drawRoadNetwork() {
    const paths: RoutePoint[][] = [
      [{ x: 690, y: 368 }, { x: 690, y: 214 }],
      [{ x: 690, y: 368 }, { x: 456, y: 368 }, { x: 456, y: 352 }],
      [{ x: 690, y: 368 }, { x: 880, y: 368 }],
      [{ x: 880, y: 208 }, { x: 880, y: 476 }],
      [{ x: 880, y: 208 }, { x: 920, y: 208 }],
      [{ x: 880, y: 424 }, { x: 964, y: 424 }],
      [{ x: 880, y: 476 }, { x: 888, y: 476 }],
      [{ x: 690, y: 368 }, { x: 690, y: 474 }],
      [{ x: 690, y: 474 }, { x: 258, y: 474 }, { x: 258, y: 482 }],
      [{ x: 690, y: 474 }, { x: 1012, y: 474 }, { x: 1012, y: 482 }],
    ]
    const tiles = new Set<string>()
    paths.forEach(path => {
      for (let i = 0; i < path.length - 1; i++) {
        this.collectRoadTiles(path[i], path[i + 1], tiles)
      }
    })
    tiles.forEach(key => {
      const [tx, ty] = key.split(',').map(Number)
      this.drawRoadTile(tx, ty, tiles)
    })
  }

  private collectRoadTiles(start: RoutePoint, end: RoutePoint, tiles: Set<string>) {
    const x1 = Math.round(start.x / TILE)
    const y1 = Math.round(start.y / TILE)
    const x2 = Math.round(end.x / TILE)
    const y2 = Math.round(end.y / TILE)
    if (x1 === x2) {
      const [from, to] = y1 < y2 ? [y1, y2] : [y2, y1]
      for (let y = from; y <= to; y++) this.addRoadBrush(x1, y, tiles)
      return
    }
    if (y1 === y2) {
      const [from, to] = x1 < x2 ? [x1, x2] : [x2, x1]
      for (let x = from; x <= to; x++) this.addRoadBrush(x, y1, tiles)
      return
    }
    this.collectRoadTiles(start, { x: end.x, y: start.y }, tiles)
    this.collectRoadTiles({ x: end.x, y: start.y }, end, tiles)
  }

  private addRoadBrush(cx: number, cy: number, tiles: Set<string>) {
    tiles.add(`${cx},${cy}`)
    tiles.add(`${cx + 1},${cy}`)
    tiles.add(`${cx},${cy + 1}`)
    tiles.add(`${cx + 1},${cy + 1}`)
  }

  private drawRoadTile(tx: number, ty: number, tiles: Set<string>) {
    const neighbors = [
      tiles.has(`${tx - 1},${ty}`),
      tiles.has(`${tx + 1},${ty}`),
      tiles.has(`${tx},${ty - 1}`),
      tiles.has(`${tx},${ty + 1}`),
    ]
    const edge = neighbors.some(v => !v)
    this.add.image(tx * TILE, ty * TILE, edge ? 'road-edge' : 'road').setOrigin(0).setDepth(1)
  }

  private drawPlaza(x: number, y: number, w: number, h: number) {
    for (let yy = y; yy < y + h; yy += TILE) {
      for (let xx = x; xx < x + w; xx += TILE) {
        this.add.image(xx, yy, 'plaza').setOrigin(0).setDepth(1)
      }
    }
  }

  private drawGrandPlaza() {
    this.drawPlaza(520, 276, 340, 180)
    const g = this.add.graphics().setDepth(2)
    g.lineStyle(3, 0xa8a29e, 0.9)
    g.strokeRect(528, 284, 324, 164)
    g.lineStyle(2, 0xfef3c7, 0.8)
    g.lineBetween(690, 284, 690, 448)
    g.lineBetween(528, 368, 852, 368)
    g.fillStyle(0xfef3c7, 0.9)
    g.fillRect(548, 298, 48, 10)
    g.fillRect(784, 298, 48, 10)
    g.fillRect(548, 428, 48, 10)
    g.fillRect(784, 428, 48, 10)

    this.add.image(690, 368, 'fountain').setScale(1.45).setDepth(388)
    this.add.image(610, 296, 'flag').setScale(1.25).setDepth(318)
    this.add.image(770, 296, 'flag').setScale(1.25).setDepth(318)

    this.drawFlowerBlock(548, 312, 3, 2)
    this.drawFlowerBlock(794, 312, 3, 2)
    this.drawFlowerBlock(548, 406, 3, 2)
    this.drawFlowerBlock(794, 406, 3, 2)
    this.drawHedgeLine(548, 288, 6, 'horizontal')
    this.drawHedgeLine(748, 288, 6, 'horizontal')
    this.drawHedgeLine(548, 442, 6, 'horizontal')
    this.drawHedgeLine(748, 442, 6, 'horizontal')
    this.drawHedgeLine(532, 304, 3, 'vertical')
    this.drawHedgeLine(532, 396, 3, 'vertical')
    this.drawHedgeLine(840, 304, 3, 'vertical')
    this.drawHedgeLine(840, 396, 3, 'vertical')
  }

  private drawFlowerBlock(x: number, y: number, cols: number, rows: number) {
    for (let yy = 0; yy < rows; yy++) {
      for (let xx = 0; xx < cols; xx++) {
        this.add.image(x + xx * 16, y + yy * 16, 'flower-bed').setOrigin(0).setDepth(y + yy * 16 + 8)
      }
    }
  }

  private drawHedgeLine(x: number, y: number, count: number, direction: 'horizontal' | 'vertical') {
    for (let i = 0; i < count; i++) {
      const xx = direction === 'horizontal' ? x + i * 16 : x
      const yy = direction === 'vertical' ? y + i * 16 : y
      this.add.image(xx, yy, 'hedge').setOrigin(0).setDepth(yy + 12)
    }
  }

  private drawFacilityGrounds() {
    this.drawPitch(66, 48, 420, 248)
    this.drawTrainingPitch(928, 30, 268, 156)
    this.drawMiniPitch(946, 544, 154, 58)
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

  private drawMiniPitch(x: number, y: number, w: number, h: number) {
    const g = this.add.graphics().setDepth(2)
    g.fillStyle(0x5fcf70, 1).fillRect(x, y, w, h)
    g.lineStyle(2, 0xffffff, 0.7).strokeRect(x + 6, y + 6, w - 12, h - 12)
    g.lineBetween(x + w / 2, y + 6, x + w / 2, y + h - 6)
  }

  private drawDecorations() {
    const trees = [
      [26, 24], [68, 28], [1200, 28], [1152, 36], [28, 582], [76, 614],
      [1190, 584], [1136, 610], [386, 590], [820, 26], [168, 388], [908, 226],
      [560, 158], [374, 226], [760, 584], [946, 624], [238, 594],
      [366, 32], [478, 36], [614, 60], [1218, 316], [1160, 426], [54, 374],
      [1024, 28], [1232, 122], [1126, 456], [462, 582],
    ]
    trees.forEach(([x, y]) => this.add.image(x, y, 'tree').setScale(1.45).setDepth(y))

    const lamps = [[604, 288], [776, 288], [604, 430], [776, 430], [856, 368], [480, 368], [856, 488], [342, 504], [900, 208], [936, 424]]
    lamps.forEach(([x, y]) => this.add.image(x, y, 'lamp').setDepth(y))

    const benches = [[574, 430], [798, 430], [594, 290], [786, 290], [918, 456], [326, 508]]
    benches.forEach(([x, y]) => this.add.image(x, y, 'bench').setDepth(y))

    const flags = [[430, 42], [1184, 28], [914, 512]]
    flags.forEach(([x, y]) => this.add.image(x, y, 'flag').setDepth(y + 20))

    for (let i = 0; i < 12; i++) this.add.image(934 + i * 18, 166, 'cone').setDepth(180)
    for (let i = 0; i < 6; i++) this.add.image(974 + i * 18, 140, 'ball').setDepth(142)
    for (let i = 0; i < 5; i++) this.add.image(1010 + i * 18, 94, 'training-wall').setDepth(118)

    this.drawFlowerBlock(72, 334, 6, 2)
    this.drawFlowerBlock(300, 528, 5, 2)
    this.drawFlowerBlock(1114, 486, 5, 2)
    this.drawFlowerBlock(904, 620, 6, 1)
    this.drawFlowerBlock(456, 492, 4, 2)
    this.drawHedgeLine(40, 320, 24, 'horizontal')
    this.drawHedgeLine(900, 632, 16, 'horizontal')
    this.drawHedgeLine(1192, 260, 9, 'vertical')

    this.add.image(126, 524, 'team-bus').setScale(1.4).setDepth(544)
    const parking = this.add.graphics().setDepth(3)
    parking.fillStyle(0xcbd5e1, 1).fillRect(54, 504, 150, 62)
    parking.lineStyle(2, 0xffffff, 0.8)
    for (let i = 0; i < 5; i++) parking.lineBetween(66 + i * 28, 512, 66 + i * 28, 558)

    this.add.image(408, 616, 'bench').setDepth(628)
    this.add.image(444, 616, 'bench').setDepth(628)
    this.add.image(1186, 510, 'sign').setScale(1.2).setDepth(534)

    const blinking = this.add.image(1148, 294, 'sign').setDepth(354)
    this.tweens.add({ targets: blinking, alpha: 0.45, duration: 900, yoyo: true, repeat: -1 })
    const medicalLamp = this.add.rectangle(628, 532, 10, 10, 0xef4444, 1).setDepth(556)
    this.tweens.add({ targets: medicalLamp, alpha: 0.25, duration: 650, yoyo: true, repeat: -1 })
  }

  private drawBuildings() {
    this.dataConfig.buildings.forEach(building => {
      switch (building.kind) {
        case 'stadium':
          this.drawStadiumBuilding(building)
          break
        case 'training':
          this.drawTrainingBuilding(building)
          break
        case 'academy':
          this.drawAcademyBuilding(building)
          break
        case 'scout':
          this.drawScoutBuilding(building)
          break
        case 'commerce':
          this.drawCommerceBuilding(building)
          break
        case 'medical':
          this.drawMedicalBuilding(building)
          break
        default:
          this.drawClubhouseBuilding(building)
      }
    })
  }

  private drawBaseBuilding(b: ClubBuilding, labelOffset = 8) {
    const footprint = b.building
    const depth = footprint.y + footprint.height
    const g = this.add.graphics().setDepth(depth)
    const colors = this.buildingColors(b.kind)
    g.fillStyle(0x000000, 0.22).fillRect(footprint.x + 8, footprint.y + footprint.height - 6, footprint.width, 14)
    g.fillStyle(colors.wall, 1).fillRect(footprint.x, footprint.y + 24, footprint.width, footprint.height - 24)
    g.fillStyle(colors.roof, 1).fillRect(footprint.x - 8, footprint.y + 8, footprint.width + 16, 26)
    g.fillStyle(colors.roofDark, 1).fillRect(footprint.x - 2, footprint.y, footprint.width + 4, 12)
    g.fillStyle(0x3f2d20, 1).fillRect(footprint.x + footprint.width / 2 - 10, footprint.y + footprint.height - 28, 20, 28)
    for (let i = 0; i < Math.max(2, Math.floor(footprint.width / 42)); i++) {
      g.fillStyle(0xbfe8ff, 1).fillRect(footprint.x + 16 + i * 42, footprint.y + 42, 18, 18)
      g.fillStyle(0x7aa5bd, 1).fillRect(footprint.x + 19 + i * 42, footprint.y + 45, 12, 12)
    }

    const label = this.add.text(footprint.x + footprint.width / 2, footprint.y + footprint.height + labelOffset, b.name, {
      fontFamily: 'monospace',
      fontSize: '14px',
      color: '#1f2937',
      backgroundColor: 'rgba(255,255,255,0.78)',
      padding: { x: 5, y: 2 },
    }).setOrigin(0.5, 0).setDepth(depth + 1)
    label.setResolution(2)

  }

  private addBuildingHitArea(b: ClubBuilding) {
    this.add.zone(b.plot.x, b.plot.y, b.plot.width, b.plot.height)
      .setOrigin(0)
      .setInteractive({ useHandCursor: true })
      .on('pointerup', (pointer: Phaser.Input.Pointer) => {
        if (this.isTap(pointer)) this.dataConfig.onBuildingClick(b.id)
      })
      .setDepth(3)
  }

  private drawStadiumBuilding(b: ClubBuilding) {
    const p = b.plot
    this.addBuildingHitArea(b)
    const g = this.add.graphics().setDepth(2)
    g.fillStyle(0x25633a, 1).fillRect(p.x + 4, p.y + 4, p.width - 8, p.height - 8)
    g.lineStyle(4, 0xffffff, 0.9).strokeRect(p.x + 16, p.y + 16, p.width - 32, p.height - 32)
    g.lineBetween(p.x + p.width / 2, p.y + 16, p.x + p.width / 2, p.y + p.height - 16)
    g.strokeCircle(p.x + p.width / 2, p.y + p.height / 2, 34)
    const stand = this.add.graphics().setDepth(p.y + p.height + 1)
    stand.fillStyle(0x64748b, 1).fillRect(p.x + 10, p.y - 18, p.width - 20, 20)
    stand.fillStyle(0x334155, 1).fillRect(p.x + 24, p.y - 10, p.width - 48, 8)
    stand.fillStyle(0xfacc15, 1).fillRect(p.x + p.width - 92, p.y - 42, 58, 28)
    this.add.text(p.x + p.width - 63, p.y - 35, 'PSL', { fontFamily: 'monospace', fontSize: '14px', color: '#111827' }).setOrigin(0.5, 0).setDepth(p.y + p.height + 1)
    this.add.text(p.x + p.width / 2, p.y + p.height + 8, b.name, { fontFamily: 'monospace', fontSize: '14px', color: '#1f2937', backgroundColor: 'rgba(255,255,255,0.82)', padding: { x: 5, y: 2 } }).setOrigin(0.5, 0).setDepth(p.y + p.height + 1)
  }

  private drawTrainingBuilding(b: ClubBuilding) {
    this.addBuildingHitArea(b)
    const p = b.plot
    this.drawBaseBuilding(b, 6)
    const g = this.add.graphics().setDepth(p.y + p.height + 4)
    g.fillStyle(0x475569, 1).fillRect(p.x + 24, p.y + 36, 80, 12)
    g.fillStyle(0xf97316, 1).fillRect(p.x + 118, p.y + 36, 10, 24)
    g.fillRect(p.x + 144, p.y + 36, 10, 24)
    g.fillStyle(0x334155, 1).fillRect(p.x + 28, p.y + 128, 78, 18)
    g.fillStyle(0xe5e7eb, 1).fillRect(p.x + 32, p.y + 132, 70, 4)
  }

  private drawAcademyBuilding(b: ClubBuilding) {
    this.addBuildingHitArea(b)
    const p = b.plot
    this.drawBaseBuilding(b)
    this.add.image(p.x + 26, p.y + 10, 'flag').setDepth(p.y + p.height + 3)
    this.add.image(p.x + p.width - 30, p.y + 84, 'ball').setDepth(p.y + p.height + 3)
  }

  private drawScoutBuilding(b: ClubBuilding) {
    this.addBuildingHitArea(b)
    const p = b.plot
    this.drawBaseBuilding(b)
    const g = this.add.graphics().setDepth(p.y + p.height + 3)
    g.fillStyle(0xfef3c7, 1).fillRect(p.x + p.width - 60, p.y + 34, 34, 24)
    g.lineStyle(2, 0x7c3aed, 1).strokeRect(p.x + p.width - 60, p.y + 34, 34, 24)
    g.lineBetween(p.x + p.width - 54, p.y + 48, p.x + p.width - 30, p.y + 40)
  }

  private drawCommerceBuilding(b: ClubBuilding) {
    this.addBuildingHitArea(b)
    const p = b.plot
    this.drawBaseBuilding(b)
    const g = this.add.graphics().setDepth(p.y + p.height + 3)
    g.fillStyle(0xfacc15, 1).fillRect(p.x + 54, p.y + 46, 106, 18)
    g.fillStyle(0x111827, 1).fillRect(p.x + 66, p.y + 51, 82, 3)
  }

  private drawMedicalBuilding(b: ClubBuilding) {
    this.addBuildingHitArea(b)
    const f = b.building
    const depth = f.y + f.height
    const g = this.add.graphics().setDepth(depth)
    g.fillStyle(0x000000, 0.2).fillRect(f.x + 8, f.y + f.height - 6, f.width, 14)
    g.fillStyle(0xecfeff, 1).fillRect(f.x, f.y + 22, f.width, f.height - 22)
    g.fillStyle(0x14b8a6, 1).fillRect(f.x - 8, f.y + 8, f.width + 16, 24)
    g.fillStyle(0x0f766e, 1).fillRect(f.x - 2, f.y, f.width + 4, 12)

    g.fillStyle(0xbfe8ff, 1).fillRect(f.x + 18, f.y + 42, 20, 18)
    g.fillStyle(0x7aa5bd, 1).fillRect(f.x + 22, f.y + 46, 12, 10)
    g.fillStyle(0xbfe8ff, 1).fillRect(f.x + f.width - 38, f.y + 42, 20, 18)
    g.fillStyle(0x7aa5bd, 1).fillRect(f.x + f.width - 34, f.y + 46, 12, 10)

    g.fillStyle(0xef4444, 1).fillRect(f.x + f.width / 2 - 5, f.y + 30, 10, 30)
    g.fillRect(f.x + f.width / 2 - 16, f.y + 41, 32, 8)

    g.fillStyle(0x3f2d20, 1).fillRect(f.x + f.width / 2 - 10, f.y + f.height - 28, 20, 28)

    const label = this.add.text(f.x + f.width / 2, f.y + f.height + 6, b.name, {
      fontFamily: 'monospace',
      fontSize: '14px',
      color: '#1f2937',
      backgroundColor: 'rgba(255,255,255,0.78)',
      padding: { x: 5, y: 2 },
    }).setOrigin(0.5, 0).setDepth(depth + 1)
    label.setResolution(2)
  }

  private drawClubhouseBuilding(b: ClubBuilding) {
    this.addBuildingHitArea(b)
    const p = b.plot
    this.drawBaseBuilding(b)
    const g = this.add.graphics().setDepth(p.y + p.height + 4)
    g.fillStyle(0xfacc15, 1).fillRect(p.x + p.width / 2 - 14, p.y + 38, 28, 22)
    g.fillStyle(0x111827, 1).fillRect(p.x + p.width / 2 - 8, p.y + 44, 16, 10)
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
      const role = this.roleForAgent(agent.position)
      const activity = this.activityForAgent(idx)
      const start = this.startPointForActivity(activity, idx)
      const { container, sprite } = this.createAgent(agent, role, start)
      this.animateAgentSprite(sprite, role, activity === 'idle' ? 620 : 320)
      this.runAgentActivity(container, activity, idx)
    })
  }

  private createAgent(agent: ClubTownSceneData['agents'][number], role: string, start: RoutePoint) {
    const container = this.add.container(start.x, start.y).setDepth(start.y + 20)
    const sprite = this.add.image(0, 0, `agent-${role}-0`).setOrigin(0.5, 1)
    sprite.setScale(1.15)
    const label = this.createNameplate(this.shortName(agent.name), agent.nameColor)
    container.add([sprite, label])
    const hitWidth = Math.max(42, label.width + 12)
    container.setSize(hitWidth, 62)
    container.setInteractive(new Phaser.Geom.Rectangle(-hitWidth / 2, -58, hitWidth, 64), Phaser.Geom.Rectangle.Contains)
    container.on('pointerup', (pointer: Phaser.Input.Pointer) => {
      if (this.isTap(pointer)) this.dataConfig.onAgentClick(agent.cardId)
    })
    return { container, sprite }
  }

  private createNameplate(name: string, color: string) {
    if (color !== 'rainbow') {
      const label = this.add.text(0, -30, name, {
        fontFamily: 'monospace',
        fontSize: '11px',
        color,
        stroke: '#0f172a',
        strokeThickness: 3,
        padding: { x: 2, y: 1 },
      }).setOrigin(0.5, 1)
      label.setResolution(2)
      return label
    }

    const colors = ['#ef4444', '#f97316', '#eab308', '#22c55e', '#06b6d4', '#3b82f6', '#a855f7', '#ec4899']
    const chars = [...name]
    const charWidth = 7
    const width = chars.length * charWidth + 8
    const container = this.add.container(0, -30)
    chars.forEach((char, index) => {
      const text = this.add.text(
        -((chars.length - 1) * charWidth) / 2 + index * charWidth,
        -7,
        char,
        {
          fontFamily: 'monospace',
          fontSize: '11px',
          color: colors[index % colors.length],
          stroke: '#0f172a',
          strokeThickness: 3,
        },
      ).setOrigin(0.5, 0.5)
      text.setResolution(2)
      container.add(text)
    })
    container.setSize(width, 18)
    return container
  }

  private animateAgentSprite(sprite: Phaser.GameObjects.Image, role: string, delay: number) {
    this.time.addEvent({
      delay,
      loop: true,
      callback: () => sprite.setTexture(`agent-${role}-${sprite.texture.key.endsWith('-0') ? 1 : 0}`),
    })
  }

  private activityForAgent(idx: number): 'pass' | 'dribble' | 'training' | 'chat' | 'medical' | 'walk' | 'idle' {
    if (idx === 0 || idx === 1) return 'pass'
    if (idx === 2) return 'dribble'
    if (idx === 3) return 'training'
    if (idx === 6 || idx === 7) return 'chat'
    if (idx === 8) return 'medical'
    if (idx === 9) return 'idle'
    return 'walk'
  }

  private startPointForActivity(activity: string, idx: number): RoutePoint {
    const points: Record<string, RoutePoint[]> = {
      pass: [{ x: 206, y: 150 }, { x: 330, y: 214 }],
      dribble: [{ x: 384, y: 126 }],
      training: [{ x: 990, y: 118 }, { x: 1040, y: 150 }, { x: 1100, y: 116 }],
      chat: [{ x: 640, y: 402 }, { x: 735, y: 402 }],
      medical: [{ x: 718, y: 548 }],
      idle: [{ x: 1148, y: 548 }],
      walk: [this.routeForAgent(idx)[0]],
    }
    const list = points[activity] || points.walk
    return list[idx % list.length]
  }

  private runAgentActivity(container: Phaser.GameObjects.Container, activity: string, idx: number) {
    if (activity === 'walk') {
      this.walkRoute(container, this.routeForAgent(idx), idx * 450)
      return
    }
    if (activity === 'pass') {
      this.runPassingPair(container, idx)
      return
    }
    if (activity === 'dribble') {
      this.runDribble(container)
      return
    }
    if (activity === 'training') {
      this.runTrainingDrill(container, idx)
      return
    }
    if (activity === 'chat') {
      this.runChat(container, idx)
      return
    }
    if (activity === 'medical') {
      this.runIdle(container, '恢复', idx)
      return
    }
    this.runIdle(container, '休息', idx)
  }

  private runPassingPair(container: Phaser.GameObjects.Container, idx: number) {
    const passA = { x: 206, y: 150 }
    const passB = { x: 330, y: 214 }
    const home = idx === 0 ? passA : passB
    const jitter = idx === 0 ? { x: 8, y: -4 } : { x: -8, y: 4 }
    this.tweens.add({
      targets: container,
      x: home.x + jitter.x,
      y: home.y + jitter.y,
      duration: 900,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.inOut',
      onUpdate: () => container.setDepth(container.y + 20),
    })
    if (idx !== 0) return
    const ball = this.add.image(passA.x + 18, passA.y - 2, 'ball').setScale(0.75).setDepth(passA.y + 18)
    this.tweens.add({
      targets: ball,
      x: passB.x - 18,
      y: passB.y - 2,
      duration: 780,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.inOut',
      onUpdate: () => ball.setDepth(ball.y + 6),
    })
  }

  private runDribble(container: Phaser.GameObjects.Container) {
    const route = [
      { x: 384, y: 126 },
      { x: 384, y: 250 },
      { x: 250, y: 250 },
      { x: 250, y: 126 },
    ]
    const ball = this.add.image(container.x + 12, container.y - 2, 'ball').setScale(0.72).setDepth(container.y + 18)
    let index = 0
    const moveNext = () => {
      index = (index + 1) % route.length
      const point = route[index]
      this.tweens.add({
        targets: container,
        x: point.x,
        y: point.y,
        duration: Phaser.Math.Distance.Between(container.x, container.y, point.x, point.y) * 11,
        ease: 'Sine.inOut',
        onUpdate: () => {
          container.setDepth(container.y + 20)
          ball.setPosition(container.x + 12, container.y - 2)
          ball.setDepth(container.y + 18)
        },
        onComplete: () => this.time.delayedCall(250, moveNext),
      })
    }
    moveNext()
  }

  private runTrainingDrill(container: Phaser.GameObjects.Container, idx: number) {
    const distance = 34 + (idx % 3) * 16
    this.tweens.add({
      targets: container,
      x: container.x + distance,
      duration: 900,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.inOut',
      onUpdate: () => container.setDepth(container.y + 20),
    })
  }

  private runChat(container: Phaser.GameObjects.Container, idx: number) {
    const bubble = this.add.text(container.x + (idx % 2 === 0 ? 20 : -20), container.y - 54, '...', {
      fontFamily: 'monospace',
      fontSize: '12px',
      color: '#111827',
      backgroundColor: 'rgba(255,255,255,0.9)',
      padding: { x: 5, y: 2 },
    }).setOrigin(0.5, 1).setDepth(container.y + 40)
    this.tweens.add({ targets: bubble, alpha: 0.25, duration: 900, yoyo: true, repeat: -1 })
    this.tweens.add({
      targets: container,
      y: container.y - 3,
      duration: 900,
      yoyo: true,
      repeat: -1,
      ease: 'Sine.inOut',
    })
  }

  private runIdle(container: Phaser.GameObjects.Container, text: string, idx: number) {
    const label = this.add.text(container.x, container.y - 54, text, {
      fontFamily: 'monospace',
      fontSize: '12px',
      color: '#111827',
      backgroundColor: 'rgba(255,255,255,0.9)',
      padding: { x: 5, y: 2 },
    }).setOrigin(0.5, 1).setDepth(container.y + 40)
    this.tweens.add({ targets: label, alpha: 0.35, duration: 1200 + idx * 80, yoyo: true, repeat: -1 })
    this.tweens.add({ targets: container, y: container.y + 4, duration: 1100, yoyo: true, repeat: -1 })
  }

  private roleForAgent(position?: string) {
    const first = (position || '').split(',')[0].trim()
    if (first === 'GK') return 'GK'
    if (['CB', 'LB', 'RB', 'LCB', 'RCB', 'LWB', 'RWB'].includes(first)) return 'DEF'
    if (['ST', 'CF', 'LW', 'RW', 'LS', 'RS', 'LF', 'RF'].includes(first)) return 'FWD'
    return 'MID'
  }

  private routeForAgent(idx: number): RoutePoint[] {
    const byId = new Map(this.dataConfig.buildings.map(building => [building.id, building.entry]))
    const stadium = byId.get('stadium') || { x: 488, y: 384 }
    const training = byId.get('training') || { x: 1040, y: 248 }
    const academy = byId.get('academy') || { x: 1012, y: 560 }
    const scout = byId.get('scout') || { x: 258, y: 560 }
    const commerce = byId.get('commerce') || { x: 1040, y: 476 }
    const medical = byId.get('medical') || { x: 690, y: 560 }
    const clubhouse = byId.get('clubhouse') || { x: 690, y: 330 }
    const plaza = { x: 690, y: 424 }
    const routes: RoutePoint[][] = [
      [stadium, plaza, training, plaza],
      [stadium, plaza, academy, plaza],
      [clubhouse, plaza, scout, plaza],
      [commerce, plaza, medical, plaza],
      [clubhouse, training, plaza, scout],
      [clubhouse, academy, plaza, stadium],
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
    camera.centerOn(690, 334)

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

  private isTap(pointer: Phaser.Input.Pointer) {
    return Phaser.Math.Distance.Between(pointer.downX, pointer.downY, pointer.x, pointer.y) <= 8
  }
}
