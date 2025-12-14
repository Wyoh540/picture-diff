import { createFileRoute } from '@tanstack/react-router'
import { useState, useEffect, useCallback, useRef } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import {
  Loader2,
  AlertCircle,
  Unplug,
  RefreshCw,
  Monitor,
  Camera,
  Download,
  Wifi,
  Play,
  Pause,
  Video,
  ScanSearch,
  Image,
  X,
} from 'lucide-react'
import {
  getStatusApiV1ScrcpyStatusGetOptions,
  adbConnectApiV1ScrcpyAdbConnectPostMutation,
  connectDeviceApiV1ScrcpyConnectPostMutation,
  disconnectDeviceApiV1ScrcpyDisconnectPostMutation,
  detectDifferencesApiV1DiffDetectPostMutation,
} from '../client/@tanstack/react-query.gen'
import {
  captureScreenshotApiV1ScrcpyScreenshotGet,
} from '../client/sdk.gen'
import type { DiffResponse } from '../client/types.gen'

export const Route = createFileRoute('/screen')({ component: ScreenPage })

// WebSocket 消息类型
interface WsFrameMessage {
  type: 'frame'
  image: string
  width: number
  height: number
  size: number
  fps: number
  source: 'scrcpy' | 'adb'  // 视频源：scrcpy 或 adb screencap
}

interface WsStatusMessage {
  type: 'status'
  streaming: boolean
  interval: number
  quality?: number
  scrcpy_mode?: boolean  // 是否使用 scrcpy 视频流模式
}

interface WsErrorMessage {
  type: 'error'
  message: string
}

type WsMessage = WsFrameMessage | WsStatusMessage | WsErrorMessage

function ScreenPage() {
  const [hostInput, setHostInput] = useState('')
  const [portInput, setPortInput] = useState('5555')

  const [screenData, setScreenData] = useState<string | null>(null)
  const [isCapturing, setIsCapturing] = useState(false)
  const [captureError, setCaptureError] = useState<string | null>(null)
  const [autoRefresh, setAutoRefresh] = useState(false)
  const autoRefreshRef = useRef(false)

  // 实时监看状态
  const [isLiveMode, setIsLiveMode] = useState(false)
  const [isLivePaused, setIsLivePaused] = useState(false)
  const [liveFps, setLiveFps] = useState(0)
  const [targetFps, setTargetFps] = useState<30 | 60>(60) // 目标帧率：30或60，scrcpy 模式支持更高帧率
  const [videoSource, setVideoSource] = useState<'scrcpy' | 'adb' | null>(null) // 当前视频源
  const [isScrcpyMode, setIsScrcpyMode] = useState(false) // 是否使用 scrcpy 视频流模式
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)

  // 差异识别相关状态
  const [diffResult, setDiffResult] = useState<DiffResponse | null>(null) // 差异识别结果
  const [isDiffDetecting, setIsDiffDetecting] = useState(false) // 是否正在检测
  const [diffError, setDiffError] = useState<string | null>(null) // 差异识别错误
  const [showDiffResult, setShowDiffResult] = useState(false) // 是否显示差异结果

  // 帧率对应的间隔时间
  const fpsToInterval = (fps: 30 | 60) => Math.round(1000 / fps)

  // 差异识别 mutation
  const diffMutation = useMutation({
    ...detectDifferencesApiV1DiffDetectPostMutation(),
    onSuccess: (data) => {
      setDiffResult(data)
      setIsDiffDetecting(false)
    },
    onError: (error) => {
      setDiffError(error.message || '差异识别失败')
      setIsDiffDetecting(false)
    },
  })

  // 使用生成的客户端获取 scrcpy 状态
  const {
    data: statusData,
    refetch: refetchStatus,
  } = useQuery({
    ...getStatusApiV1ScrcpyStatusGetOptions(),
    refetchInterval: false,
  })

  const isConnected = statusData?.connected ?? false
  const isStreaming = statusData?.streaming ?? false
  const deviceInfo = statusData?.device ?? null

  // ADB 连接 mutation（用于无线调试）
  const adbConnectMutation = useMutation({
    ...adbConnectApiV1ScrcpyAdbConnectPostMutation(),
    onSuccess: (data) => {
      if (data.success) {
        // ADB 连接成功后，启动 scrcpy 连接
        scrcpyConnectMutation.mutate({})
      }
    },
  })

  // Scrcpy 连接 mutation
  const scrcpyConnectMutation = useMutation({
    ...connectDeviceApiV1ScrcpyConnectPostMutation(),
    onSuccess: (data) => {
      if (data.success) {
        refetchStatus()
      }
    },
  })

  // 断开连接 mutation
  const disconnectMutation = useMutation({
    ...disconnectDeviceApiV1ScrcpyDisconnectPostMutation(),
    onSuccess: () => {
      refetchStatus()
      setScreenData(null)
      setAutoRefresh(false)
      // 停止实时监看
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      setIsLiveMode(false)
      setIsLivePaused(false)
      setLiveFps(0)
      setVideoSource(null)
      setIsScrcpyMode(false)
    },
  })

  const error = adbConnectMutation.error?.message || 
    scrcpyConnectMutation.error?.message || 
    (adbConnectMutation.data && !adbConnectMutation.data.success ? adbConnectMutation.data.message : null) ||
    (scrcpyConnectMutation.data && !scrcpyConnectMutation.data.success ? scrcpyConnectMutation.data.message : null)
  const isConnecting = adbConnectMutation.isPending || scrcpyConnectMutation.isPending

  // 连接设备
  const connect = async () => {
    if (!hostInput.trim()) {
      return
    }

    // 先通过 ADB 连接无线设备
    adbConnectMutation.mutate({
      body: {
        host: hostInput.trim(),
        port: parseInt(portInput) || 5555,
      },
    })
  }

  // 断开连接
  const disconnect = async () => {
    disconnectMutation.mutate({})
  }

  // 截取屏幕（使用 scrcpy）
  const captureScreen = useCallback(async () => {
    setIsCapturing(true)
    setCaptureError(null)

    try {
      const { data } = await captureScreenshotApiV1ScrcpyScreenshotGet()

      if (data?.success && data.image) {
        // scrcpy 返回的是 JPEG 格式
        setScreenData(`data:image/jpeg;base64,${data.image}`)
        console.log(`截图成功: ${data.size} 字节, ${data.width}x${data.height}`)
      } else {
        setCaptureError(data?.message || '截图失败')
        // 如果截图失败，可能是连接断开了
        if (data?.message?.includes('未连接')) {
          refetchStatus()
        }
      }
    } catch (err) {
      setCaptureError('截图请求失败，请检查后端服务')
    } finally {
      setIsCapturing(false)
    }
  }, [refetchStatus])

  // 自动刷新
  useEffect(() => {
    autoRefreshRef.current = autoRefresh

    if (autoRefresh && isConnected) {
      const refresh = async () => {
        if (autoRefreshRef.current && isConnected) {
          await captureScreen()
          setTimeout(refresh, 1000)
        }
      }
      refresh()
    }
  }, [autoRefresh, isConnected, captureScreen])

  // 断开连接时停止自动刷新和实时监看
  useEffect(() => {
    if (!isConnected) {
      setAutoRefresh(false)
      stopLiveMode()
    }
  }, [isConnected])

  // 获取 WebSocket URL（scrcpy 视频流）
  const getWsUrl = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.hostname
    const port = '8000' // 后端端口
    return `${protocol}//${host}:${port}/api/v1/scrcpy/stream`
  }, [])

  // 启动实时监看
  const startLiveMode = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(getWsUrl())
    wsRef.current = ws

    ws.onopen = () => {
      console.log('实时监看 WebSocket 已连接')
      setIsLiveMode(true)
      setIsLivePaused(false)
      setCaptureError(null)
      // 设置帧率
      ws.send(JSON.stringify({ action: 'set_interval', interval: fpsToInterval(targetFps) }))
    }

    ws.onmessage = (event) => {
      try {
        const data: WsMessage = JSON.parse(event.data)
        
        if (data.type === 'frame') {
          setScreenData(`data:image/jpeg;base64,${data.image}`)
          setLiveFps(data.fps)
          setVideoSource(data.source)
        } else if (data.type === 'status') {
          setIsLivePaused(!data.streaming)
          if (data.scrcpy_mode !== undefined) {
            setIsScrcpyMode(data.scrcpy_mode)
          }
        } else if (data.type === 'error') {
          setCaptureError(data.message)
        }
      } catch (err) {
        console.error('解析 WebSocket 消息失败:', err)
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket 错误:', error)
      setCaptureError('实时监看连接错误')
    }

    ws.onclose = () => {
      console.log('实时监看 WebSocket 已关闭')
      setIsLiveMode(false)
      setLiveFps(0)
      wsRef.current = null
    }
  }, [getWsUrl, targetFps, fpsToInterval])

  // 停止实时监看
  const stopLiveMode = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.send(JSON.stringify({ action: 'stop' }))
      wsRef.current.close()
      wsRef.current = null
    }
    setIsLiveMode(false)
    setIsLivePaused(false)
    setLiveFps(0)
    setVideoSource(null)
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
  }, [])

  // 暂停/恢复实时监看
  const toggleLivePause = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    
    if (isLivePaused) {
      wsRef.current.send(JSON.stringify({ action: 'resume' }))
    } else {
      wsRef.current.send(JSON.stringify({ action: 'pause' }))
    }
    setIsLivePaused(!isLivePaused)
  }, [isLivePaused])

  // 切换帧率
  const switchFps = useCallback((fps: 30 | 60) => {
    setTargetFps(fps)
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ action: 'set_interval', interval: fpsToInterval(fps) }))
    }
  }, [fpsToInterval])

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      stopLiveMode()
    }
  }, [stopLiveMode])

  // 下载截图
  const downloadScreenshot = () => {
    if (!screenData) return

    const link = document.createElement('a')
    link.href = screenData
    link.download = `screenshot_${new Date().toISOString().replace(/[:.]/g, '-')}.png`
    link.click()
  }

  // 截取当前画面并进行差异识别
  const captureAndDetectDiff = useCallback(async () => {
    setIsDiffDetecting(true)
    setDiffError(null)
    setDiffResult(null)
    setShowDiffResult(true)

    try {
      let imageData: string | null = screenData

      // 如果没有当前画面，先截图
      if (!imageData) {
        const result = await captureScreenshotApiV1ScrcpyScreenshotGet()
        if (result.data?.success && result.data.image) {
          imageData = `data:image/jpeg;base64,${result.data.image}`
        } else {
          setDiffError('截取图片失败')
          setIsDiffDetecting(false)
          return
        }
      }

      // 将 base64 转换为 Blob
      const response = await fetch(imageData)
      const blob = await response.blob()
      const file = new File([blob], 'screenshot.png', { type: 'image/png' })

      // 调用差异识别 API
      diffMutation.mutate({
        body: {
          file,
        },
      })
    } catch (err) {
      setDiffError('差异识别失败: ' + (err instanceof Error ? err.message : '未知错误'))
      setIsDiffDetecting(false)
    }
  }, [screenData, diffMutation])

  // 关闭差异识别结果
  const closeDiffResult = useCallback(() => {
    setShowDiffResult(false)
    setDiffResult(null)
    setDiffError(null)
  }, [])

  return (
    <div className="min-h-screen bg-gradient-to-b from-slate-900 via-slate-800 to-slate-900">
      {/* Hero 区域 */}
      <section className="relative py-12 px-6 text-center overflow-hidden">
        <div className="absolute inset-0 bg-gradient-to-r from-purple-500/10 via-pink-500/10 to-cyan-500/10"></div>
        <div className="relative max-w-4xl mx-auto">
          <div className="flex items-center justify-center gap-4 mb-4">
            <Monitor className="w-16 h-16 text-purple-400" />
            <h1 className="text-4xl md:text-5xl font-bold text-white">
              手机屏幕查看
            </h1>
          </div>
          <p className="text-lg text-gray-300 mb-2">
            通过无线调试连接 Android 手机，实时查看手机屏幕
          </p>
          <p className="text-sm text-gray-400">
            需要在手机上启用无线调试模式
          </p>
        </div>
      </section>

      {/* 连接控制区域 */}
      <section className="py-8 px-6 max-w-4xl mx-auto">
        <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700">
          {isConnected ? (
            <div className="flex flex-col md:flex-row items-center justify-between gap-4">
              <div className="flex items-center gap-4">
                <div className={`w-4 h-4 rounded-full ${isStreaming ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'}`} />
                <div>
                  <p className="text-white font-medium">
                    已连接: {deviceInfo?.serial || deviceInfo?.name || '设备'}
                  </p>
                  <p className="text-sm text-gray-400">
                    {isStreaming ? (
                      <>
                        视频流已启动
                        {isScrcpyMode && <span className="ml-1 text-purple-400">(Scrcpy 高性能模式)</span>}
                      </>
                    ) : 'Scrcpy 已连接'}
                    {deviceInfo?.resolution && ` · ${deviceInfo.resolution[0]}×${deviceInfo.resolution[1]}`}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap gap-3">
                {/* 实时监看按钮 */}
                {!isLiveMode ? (
                  <>
                    {/* 帧率选择按钮组 */}
                    <div className="flex items-center bg-slate-700 rounded-lg p-1">
                      <button
                        onClick={() => setTargetFps(30)}
                        className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                          targetFps === 30
                            ? 'bg-cyan-500 text-white'
                            : 'text-gray-300 hover:text-white'
                        }`}
                      >
                        30帧
                      </button>
                      <button
                        onClick={() => setTargetFps(60)}
                        className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                          targetFps === 60
                            ? 'bg-cyan-500 text-white'
                            : 'text-gray-300 hover:text-white'
                        }`}
                      >
                        60帧
                      </button>
                    </div>
                    <button
                      onClick={startLiveMode}
                      disabled={autoRefresh}
                      className="px-4 py-2 bg-cyan-500 hover:bg-cyan-600 disabled:bg-cyan-500/50 text-white font-semibold rounded-lg transition-colors flex items-center gap-2"
                    >
                      <Video className="w-5 h-5" />
                      实时监看
                    </button>
                  </>
                ) : (
                  <>
                    {/* 实时监看中的帧率切换 */}
                    <div className="flex items-center bg-slate-700 rounded-lg p-1">
                      <button
                        onClick={() => switchFps(30)}
                        className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                          targetFps === 30
                            ? 'bg-cyan-500 text-white'
                            : 'text-gray-300 hover:text-white'
                        }`}
                      >
                        30帧
                      </button>
                      <button
                        onClick={() => switchFps(60)}
                        className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
                          targetFps === 60
                            ? 'bg-cyan-500 text-white'
                            : 'text-gray-300 hover:text-white'
                        }`}
                      >
                        60帧
                      </button>
                    </div>
                    <button
                      onClick={toggleLivePause}
                      className={`px-4 py-2 ${
                        isLivePaused
                          ? 'bg-green-500 hover:bg-green-600'
                          : 'bg-yellow-500 hover:bg-yellow-600'
                      } text-white font-semibold rounded-lg transition-colors flex items-center gap-2`}
                    >
                      {isLivePaused ? (
                        <>
                          <Play className="w-5 h-5" />
                          继续
                        </>
                      ) : (
                        <>
                          <Pause className="w-5 h-5" />
                          暂停
                        </>
                      )}
                    </button>
                    <button
                      onClick={stopLiveMode}
                      className="px-4 py-2 bg-gray-600 hover:bg-gray-700 text-white font-semibold rounded-lg transition-colors flex items-center gap-2"
                    >
                      <Video className="w-5 h-5" />
                      停止监看
                    </button>
                  </>
                )}
                
                {/* 单次截图按钮 */}
                <button
                  onClick={captureScreen}
                  disabled={isCapturing || isLiveMode}
                  className="px-4 py-2 bg-purple-500 hover:bg-purple-600 disabled:bg-purple-500/50 text-white font-semibold rounded-lg transition-colors flex items-center gap-2"
                >
                  {isCapturing ? (
                    <Loader2 className="w-5 h-5 animate-spin" />
                  ) : (
                    <Camera className="w-5 h-5" />
                  )}
                  截图
                </button>
                
                {/* 自动刷新按钮 - 在非实时模式下显示 */}
                {!isLiveMode && (
                  <button
                    onClick={() => setAutoRefresh(!autoRefresh)}
                    className={`px-4 py-2 ${
                      autoRefresh
                        ? 'bg-green-500 hover:bg-green-600'
                        : 'bg-gray-600 hover:bg-gray-700'
                    } text-white font-semibold rounded-lg transition-colors flex items-center gap-2`}
                  >
                    <RefreshCw
                      className={`w-5 h-5 ${autoRefresh ? 'animate-spin' : ''}`}
                    />
                    {autoRefresh ? '停止刷新' : '自动刷新'}
                  </button>
                )}

                {/* 差异识别按钮 */}
                <button
                  onClick={captureAndDetectDiff}
                  disabled={(!screenData && !isLiveMode) || isDiffDetecting}
                  className="px-4 py-2 bg-orange-500 hover:bg-orange-600 disabled:bg-orange-500/50 text-white font-semibold rounded-lg transition-colors flex items-center gap-2"
                >
                  {isDiffDetecting ? (
                    <>
                      <Loader2 className="w-5 h-5 animate-spin" />
                      识别中...
                    </>
                  ) : (
                    <>
                      <ScanSearch className="w-5 h-5" />
                      差异识别
                    </>
                  )}
                </button>
                
                <button
                  onClick={disconnect}
                  className="px-4 py-2 bg-red-500 hover:bg-red-600 text-white font-semibold rounded-lg transition-colors flex items-center gap-2"
                >
                  <Unplug className="w-5 h-5" />
                  断开连接
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center gap-4">
                <div className="w-4 h-4 rounded-full bg-gray-500" />
                <div>
                  <p className="text-white font-medium">未连接设备</p>
                  <p className="text-sm text-gray-400">
                    输入设备 IP 地址和端口进行连接
                  </p>
                </div>
              </div>

              <div className="flex flex-col md:flex-row gap-4">
                <div className="flex-1">
                  <label className="block text-sm text-gray-400 mb-1">
                    IP 地址
                  </label>
                  <input
                    type="text"
                    value={hostInput}
                    onChange={(e) => setHostInput(e.target.value)}
                    placeholder="例如: 192.168.1.100"
                    className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div className="w-32">
                  <label className="block text-sm text-gray-400 mb-1">
                    端口
                  </label>
                  <input
                    type="text"
                    value={portInput}
                    onChange={(e) => setPortInput(e.target.value)}
                    placeholder="5555"
                    className="w-full px-4 py-2 bg-slate-700 border border-slate-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-purple-500"
                  />
                </div>
                <div className="flex items-end">
                  <button
                    onClick={connect}
                    disabled={isConnecting}
                    className="px-6 py-2 bg-purple-500 hover:bg-purple-600 disabled:bg-purple-500/50 text-white font-semibold rounded-lg transition-colors flex items-center gap-2"
                  >
                    {isConnecting ? (
                      <>
                        <Loader2 className="w-5 h-5 animate-spin" />
                        连接中...
                      </>
                    ) : (
                      <>
                        <Wifi className="w-5 h-5" />
                        连接
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* 错误提示 */}
        {(error || captureError) && (
          <div className="mt-4 p-4 bg-red-500/20 border border-red-500/50 rounded-lg flex items-center gap-3">
            <AlertCircle className="w-6 h-6 text-red-400 flex-shrink-0" />
            <div>
              <p className="text-red-400 font-medium">
                {error ? '连接失败' : '截图失败'}
              </p>
              <p className="text-red-300 text-sm">{error || captureError}</p>
            </div>
          </div>
        )}

        {/* 使用说明 */}
        {!isConnected && !error && (
          <div className="mt-6 p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
            <h3 className="text-blue-400 font-medium mb-2">
              无线调试使用说明
            </h3>
            <ol className="text-gray-300 text-sm space-y-2 list-decimal list-inside">
              <li>
                在手机上进入{' '}
                <span className="text-white">设置 → 开发者选项</span>
              </li>
              <li>
                开启 <span className="text-white">无线调试</span>
              </li>
              <li>
                点击无线调试，查看{' '}
                <span className="text-white">IP 地址和端口</span>
              </li>
              <li>
                如果使用配对，先点击"使用配对码配对设备"，在电脑终端执行:
                <code className="block mt-1 p-2 bg-slate-800 rounded text-green-400">
                  adb pair IP地址:配对端口
                </code>
              </li>
              <li>
                在上方输入手机显示的 IP 地址和端口，点击连接
              </li>
            </ol>
            <div className="mt-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
              <p className="text-yellow-400 text-sm">
                <strong>提示：</strong>手机和电脑需要在同一个 WiFi 网络下
              </p>
            </div>
          </div>
        )}
      </section>

      {/* 屏幕显示和差异结果区域 - 左右布局 */}
      {isConnected && (
        <section className="py-8 px-6">
          <div className="flex gap-6">
            {/* 左侧：手机屏幕区域 - 固定宽度防止帧率变化导致布局抖动 */}
            <div className="flex-shrink-0 w-[400px]">
              <div className="bg-slate-800/50 rounded-xl p-4 border border-slate-700">
                {/* 标题栏 - 使用 whitespace-nowrap 确保不换行 */}
                <div className="flex items-center justify-between mb-3 whitespace-nowrap">
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-bold text-white flex items-center gap-1.5">
                      <Monitor className="w-4 h-4 text-purple-400" />
                      屏幕
                    </h2>
                    {/* 实时监看状态指示器 */}
                    {isLiveMode && (
                      <div className="flex items-center gap-1.5">
                        <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-xs font-medium ${
                          isLivePaused 
                            ? 'bg-yellow-500/20 text-yellow-400' 
                            : 'bg-green-500/20 text-green-400'
                        }`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${
                            isLivePaused ? 'bg-yellow-400' : 'bg-green-400 animate-pulse'
                          }`} />
                          {isLivePaused ? '暂停' : '实时'}
                        </span>
                        {!isLivePaused && (
                          <>
                            <span className="text-cyan-400 text-xs font-mono w-[50px] text-right tabular-nums">
                              {liveFps} FPS
                            </span>
                            {/* 视频源标识 */}
                            <span className={`inline-flex items-center justify-center px-1.5 py-0.5 rounded text-xs font-medium w-[60px] ${
                              videoSource === 'scrcpy'
                                ? 'bg-purple-500/20 text-purple-400'
                                : 'bg-blue-500/20 text-blue-400'
                            }`}>
                              {videoSource === 'scrcpy' ? 'Scrcpy' : 'ADB'}
                            </span>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                  {screenData && (
                    <button
                      onClick={downloadScreenshot}
                      className="px-2 py-1 bg-slate-700 hover:bg-slate-600 text-white text-xs rounded-lg transition-colors flex items-center gap-1 flex-shrink-0"
                    >
                      <Download className="w-3 h-3" />
                      下载
                    </button>
                  )}
                </div>

                {/* 手机屏幕显示区域 - 自适应容器宽度 */}
                <div 
                  className="w-full bg-slate-900/50 rounded-lg border border-slate-600 relative overflow-hidden flex items-center justify-center"
                  style={{
                    height: 'calc(70vh)',
                    minHeight: '500px',
                    maxHeight: '800px',
                  }}
                >
                  {screenData ? (
                    <>
                      <img
                        src={screenData}
                        alt="手机屏幕"
                        className="w-full h-full object-contain rounded-lg"
                        draggable={false}
                      />
                      {/* 实时模式暂停遮罩 */}
                      {isLiveMode && isLivePaused && (
                        <div className="absolute inset-0 bg-black/30 flex items-center justify-center rounded-lg pointer-events-none">
                          <div className="bg-black/60 px-4 py-2 rounded-lg flex items-center gap-2">
                            <Pause className="w-6 h-6 text-white" />
                            <span className="text-white font-medium">已暂停</span>
                          </div>
                        </div>
                      )}
                    </>
                  ) : (
                    <div className="text-center text-gray-400 p-4">
                      <Monitor className="w-12 h-12 mx-auto mb-3 opacity-50" />
                      <p className="text-sm">点击"实时监看"同步手机画面</p>
                      <p className="text-xs mt-1">或点击"截图"获取静态画面</p>
                    </div>
                  )}
                </div>

                {/* 设备信息 */}
                {deviceInfo?.resolution && (
                  <div className="mt-2 text-center text-xs text-gray-500">
                    {deviceInfo.resolution[0]} × {deviceInfo.resolution[1]}
                  </div>
                )}

                {isCapturing && !isLiveMode && (
                  <div className="mt-3 flex items-center justify-center gap-2 text-purple-400 text-sm">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>正在获取...</span>
                  </div>
                )}
              </div>
            </div>

            {/* 右侧：差异识别结果区域 */}
            <div className="flex-1 min-w-0">
              {showDiffResult ? (
                <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700 h-full overflow-auto" style={{ maxHeight: 'calc(70vh + 100px)' }}>
                  <div className="flex items-center justify-between mb-4">
                    <h2 className="text-xl font-bold text-white flex items-center gap-2">
                      <Image className="w-5 h-5 text-cyan-400" />
                      差异识别结果
                    </h2>
                    <div className="flex items-center gap-3">
                      {diffResult && (
                        <div className="bg-cyan-500/20 px-3 py-1.5 rounded-lg">
                          <span className="text-cyan-400 font-semibold text-sm">
                            发现 {diffResult.difference_count} 处差异
                          </span>
                        </div>
                      )}
                      <button
                        onClick={closeDiffResult}
                        className="p-2 bg-slate-700 hover:bg-slate-600 rounded-lg transition-colors"
                        title="关闭"
                      >
                        <X className="w-4 h-4 text-gray-400" />
                      </button>
                    </div>
                  </div>

                  {/* 加载状态 */}
                  {isDiffDetecting && (
                    <div className="flex flex-col items-center justify-center py-12">
                      <Loader2 className="w-10 h-10 text-orange-400 animate-spin mb-4" />
                      <p className="text-gray-300">正在识别差异...</p>
                      <p className="text-sm text-gray-500 mt-1">系统会自动分割图片并进行对比</p>
                    </div>
                  )}

                  {/* 错误提示 */}
                  {diffError && (
                    <div className="p-4 bg-red-500/20 border border-red-500/50 rounded-lg flex items-center gap-3">
                      <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                      <div>
                        <p className="text-red-400 font-medium text-sm">识别失败</p>
                        <p className="text-red-300 text-xs">{diffError}</p>
                      </div>
                    </div>
                  )}

                  {/* 差异区域信息 */}
                  {diffResult && diffResult.differences && diffResult.differences.length > 0 && (
                    <div className="mb-4">
                      <h3 className="text-sm font-medium text-gray-300 mb-2">
                        差异区域详情
                      </h3>
                      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
                        {diffResult.differences.map((diff) => (
                          <div
                            key={diff.index}
                            className="bg-slate-700/50 rounded-lg p-2 text-center"
                          >
                            <div className="text-cyan-400 font-bold text-sm">
                              #{diff.index}
                            </div>
                            <div className="text-xs text-gray-400">
                              ({diff.x}, {diff.y}) {diff.width}×{diff.height}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 结果图片展示 */}
                  {diffResult && (
                    <div className="space-y-4">
                      {/* 拼接标记图 */}
                      {diffResult.marked_image_base64 && (
                        <div>
                          <h3 className="text-sm font-medium text-gray-300 mb-2">
                            对比标记图
                          </h3>
                          <div className="flex justify-center">
                            <img
                              src={`data:image/png;base64,${diffResult.marked_image_base64}`}
                              alt="差异标记图"
                              className="max-w-full max-h-[40vh] rounded-lg shadow-lg border border-slate-600"
                            />
                          </div>
                        </div>
                      )}

                      {/* 热力图 */}
                      {diffResult.heatmap_base64 && (
                        <div>
                          <h3 className="text-sm font-medium text-gray-300 mb-2">
                            差异热力图
                          </h3>
                          <div className="flex justify-center">
                            <img
                              src={`data:image/png;base64,${diffResult.heatmap_base64}`}
                              alt="差异热力图"
                              className="max-w-full max-h-[40vh] rounded-lg shadow-lg border border-slate-600"
                            />
                          </div>
                        </div>
                      )}

                      {/* 单独标记的图片 */}
                      {(diffResult.image1_base64 || diffResult.image2_base64) && (
                        <div>
                          <h3 className="text-sm font-medium text-gray-300 mb-2">
                            单独标记图
                          </h3>
                          <div className="grid md:grid-cols-2 gap-3">
                            {diffResult.image1_base64 && (
                              <div>
                                <p className="text-xs text-gray-400 mb-1 text-center">
                                  图片 1
                                </p>
                                <img
                                  src={`data:image/png;base64,${diffResult.image1_base64}`}
                                  alt="图片1标记"
                                  className="w-full rounded-lg shadow-lg border border-slate-600"
                                />
                              </div>
                            )}
                            {diffResult.image2_base64 && (
                              <div>
                                <p className="text-xs text-gray-400 mb-1 text-center">
                                  图片 2
                                </p>
                                <img
                                  src={`data:image/png;base64,${diffResult.image2_base64}`}
                                  alt="图片2标记"
                                  className="w-full rounded-lg shadow-lg border border-slate-600"
                                />
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ) : (
                <div className="bg-slate-800/50 rounded-xl p-6 border border-slate-700 h-full flex flex-col items-center justify-center text-gray-400" style={{ minHeight: '400px' }}>
                  <ScanSearch className="w-16 h-16 mb-4 opacity-50" />
                  <p className="text-lg font-medium mb-2">差异识别结果将显示在这里</p>
                  <p className="text-sm text-gray-500">点击上方"差异识别"按钮开始检测</p>
                </div>
              )}
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
