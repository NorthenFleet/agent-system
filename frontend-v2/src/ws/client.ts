/**
 * WebSocket 客户端 — 断线重连 + 心跳保活
 *
 * 特性：
 * - 指数退避重连（1s → 2s → 4s → 8s → 16s → 30s 上限）
 * - 服务端 ping / 客户端 pong 心跳保活
 * - 连接状态事件
 * - 自动重连上限（可配置）
 *
 * @task task-P3-B-002
 * @author 🟥 拉斐尔 (后端) + 🟪 多纳泰罗 (前端适配)
 */

export type WsEventType =
  | 'connected'
  | 'heartbeat_update'
  | 'status_update'
  | 'agent_status_change'
  | 'task_status_change'
  | 'queue_update'
  | 'ping'
  | 'error'
  | 'disconnected'

export interface WsMessage {
  type: WsEventType
  data: Record<string, unknown>
  timestamp: string
}

export type WsState = 'connecting' | 'open' | 'closed' | 'reconnecting'

export interface WsClientOptions {
  /** 最大重连次数，0 = 无限 */
  maxRetries?: number
  /** 初始重连间隔 ms */
  baseDelay?: number
  /** 最大重连间隔 ms */
  maxDelay?: number
  /** pong 超时时间 ms */
  pongTimeout?: number
  /** 是否自动发送 pong */
  autoPong?: boolean
}

const DEFAULTS: Required<WsClientOptions> = {
  maxRetries: 0,
  baseDelay: 1000,
  maxDelay: 30000,
  pongTimeout: 30000,
  autoPong: true,
}

export class WsClient {
  private ws: WebSocket | null = null
  private token: string
  private opts: Required<WsClientOptions>
  private state: WsState = 'closed'
  private retryCount = 0
  private pongTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private manualClose = false
  private listeners = new Map<WsEventType, Set<(msg: WsMessage) => void>>()

  constructor(token: string, opts?: WsClientOptions) {
    this.token = token
    this.opts = { ...DEFAULTS, ...opts }
  }

  // ── 公共 API ──

  connect(): void {
    if (this.ws && this.ws.readyState <= WebSocket.OPEN) return
    this.manualClose = false
    this._doConnect()
  }

  close(): void {
    this.manualClose = true
    this._clearTimers()
    this.ws?.close()
    this.ws = null
    this._setState('closed')
  }

  on(event: WsEventType, cb: (msg: WsMessage) => void): () => void {
    if (!this.listeners.has(event)) this.listeners.set(event, new Set())
    this.listeners.get(event)!.add(cb)
    return () => this.listeners.get(event)?.delete(cb)
  }

  getState(): WsState {
    return this.state
  }

  // ── 内部 ──

  private _url(): string {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${window.location.host}/ws/status?token=${encodeURIComponent(this.token)}`
  }

  private _doConnect(): void {
    if (this.manualClose) return
    this._setState(this.retryCount > 0 ? 'reconnecting' : 'connecting')

    try {
      this.ws = new WebSocket(this._url())
    } catch (e) {
      this._onError('连接创建失败')
      this._scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      this.retryCount = 0
      this._setState('open')
      this._fire('connected', { conn_id: 0, message: 'WebSocket 已连接' })
      this._startPongTimer()
    }

    this.ws.onmessage = (evt: MessageEvent) => {
      try {
        const msg: WsMessage = JSON.parse(evt.data)
        if (msg.type === 'ping' && this.opts.autoPong) {
          // 自动响应 pong
          this.ws?.send(JSON.stringify({ type: 'pong' }))
          this._resetPongTimer()
          return
        }
        this._resetPongTimer()
        this._fire(msg.type, msg.data)
      } catch {
        console.warn('[WS] 解析消息失败', evt.data)
      }
    }

    this.ws.onclose = (evt: CloseEvent) => {
      this._clearTimers()
      if (!this.manualClose) {
        console.log(`[WS] 连接断开(code=${evt.code})，准备重连...`)
        this._scheduleReconnect()
      }
    }

    this.ws.onerror = () => {
      this._onError('连接错误')
    }
  }

  private _scheduleReconnect(): void {
    if (this.manualClose) return
    if (this.opts.maxRetries > 0 && this.retryCount >= this.opts.maxRetries) {
      console.warn('[WS] 达到最大重连次数，停止重连')
      this._setState('closed')
      this._fire('disconnected', { reason: 'max_retries' })
      return
    }

    const delay = Math.min(
      this.opts.baseDelay * Math.pow(2, this.retryCount),
      this.opts.maxDelay
    )
    // 加随机抖动避免雷击
    const jitter = delay * (0.5 + Math.random() * 0.5)

    console.log(`[WS] ${Math.round(jitter)}ms 后重连 (第 ${this.retryCount + 1} 次)`)
    this.reconnectTimer = setTimeout(() => {
      this.retryCount++
      this._doConnect()
    }, jitter)
  }

  private _startPongTimer(): void {
    this._resetPongTimer()
  }

  private _resetPongTimer(): void {
    if (this.pongTimer) clearTimeout(this.pongTimer)
    this.pongTimer = setTimeout(() => {
      console.warn('[WS] pong 超时，可能连接已死')
      this.ws?.close()
    }, this.opts.pongTimeout)
  }

  private _clearTimers(): void {
    if (this.pongTimer) { clearTimeout(this.pongTimer); this.pongTimer = null }
    if (this.reconnectTimer) { clearTimeout(this.reconnectTimer); this.reconnectTimer = null }
  }

  private _setState(s: WsState): void {
    this.state = s
  }

  private _fire(type: WsEventType, data: Record<string, unknown>): void {
    const cbs = this.listeners.get(type)
    if (cbs) cbs.forEach(cb => cb({ type, data, timestamp: new Date().toISOString() }))
  }

  private _onError(msg: string): void {
    console.error(`[WS] ${msg}`)
    this._fire('error', { message: msg })
  }
}

// ── 全局单例 ──

let _instance: WsClient | null = null

export function getWsClient(token: string, opts?: WsClientOptions): WsClient {
  if (!_instance) {
    _instance = new WsClient(token, opts)
  }
  return _instance
}

export function resetWsClient(): void {
  _instance?.close()
  _instance = null
}
