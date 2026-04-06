import type { WsMessage } from '../types'

export type WsListener = (msg: WsMessage) => void

export class SimulationWebSocket {
  private ws: WebSocket | null = null
  private listeners = new Set<WsListener>()
  private uid: string | null = null

  connect(uid: string): void {
    if (this.ws) this.disconnect()
    this.uid = uid
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const url = `${proto}://${location.host}/api/ws/simulations/${uid}`
    this.ws = new WebSocket(url)
    this.ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data) as WsMessage
        this.listeners.forEach((fn) => fn(msg))
      } catch { /* ignore parse errors */ }
    }
    this.ws.onclose = () => { if (this.uid === uid) this.ws = null }
  }

  disconnect(): void {
    this.ws?.close()
    this.ws = null
    this.uid = null
  }

  subscribe(fn: WsListener): () => void {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }
}

export const simulationWS = new SimulationWebSocket()
