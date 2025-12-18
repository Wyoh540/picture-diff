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
  Info,
} from 'lucide-react'
import {
  getStatusApiV1ScrcpyStatusGetOptions,
  adbConnectApiV1ScrcpyAdbConnectPostMutation,
  connectDeviceApiV1ScrcpyConnectPostMutation,
  disconnectDeviceApiV1ScrcpyDisconnectPostMutation,
  detectDifferencesApiV1DiffDetectPostMutation,
} from '../client/@tanstack/react-query.gen'
import { captureScreenshotApiV1ScrcpyScreenshotGet } from '../client/sdk.gen'
import type { DiffResponse } from '../client/types.gen'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'

export const Route = createFileRoute('/screen')({ component: ScreenPage })

// WebSocket 消息类型
interface WsFrameMessage {
  type: 'frame'
  image: string
  width: number
  height: number
  size: number
  fps: number
  source: 'scrcpy' | 'adb'
}

interface WsStatusMessage {
  type: 'status'
  streaming: boolean
  interval: number
  quality?: number
  scrcpy_mode?: boolean
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
  const [targetFps, setTargetFps] = useState<30 | 60>(60)
  const [videoSource, setVideoSource] = useState<'scrcpy' | 'adb' | null>(null)
  const [isScrcpyMode, setIsScrcpyMode] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)

  // 差异识别相关状态
  const [diffResult, setDiffResult] = useState<DiffResponse | null>(null)
  const [isDiffDetecting, setIsDiffDetecting] = useState(false)
  const [diffError, setDiffError] = useState<string | null>(null)
  const [showDiffResult, setShowDiffResult] = useState(false)

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
  const { data: statusData, refetch: refetchStatus } = useQuery({
    ...getStatusApiV1ScrcpyStatusGetOptions(),
    refetchInterval: false,
  })

  const isConnected = statusData?.connected ?? false
  const isStreaming = statusData?.streaming ?? false
  const deviceInfo = statusData?.device ?? null

  // ADB 连接 mutation
  const adbConnectMutation = useMutation({
    ...adbConnectApiV1ScrcpyAdbConnectPostMutation(),
    onSuccess: (data) => {
      if (data.success) {
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

  const error =
    adbConnectMutation.error?.message ||
    scrcpyConnectMutation.error?.message ||
    (adbConnectMutation.data && !adbConnectMutation.data.success
      ? adbConnectMutation.data.message
      : null) ||
    (scrcpyConnectMutation.data && !scrcpyConnectMutation.data.success
      ? scrcpyConnectMutation.data.message
      : null)
  const isConnecting =
    adbConnectMutation.isPending || scrcpyConnectMutation.isPending

  const connect = async () => {
    if (!hostInput.trim()) return
    adbConnectMutation.mutate({
      body: {
        host: hostInput.trim(),
        port: parseInt(portInput) || 5555,
      },
    })
  }

  const disconnect = async () => {
    disconnectMutation.mutate({})
  }

  const captureScreen = useCallback(async () => {
    setIsCapturing(true)
    setCaptureError(null)

    try {
      const { data } = await captureScreenshotApiV1ScrcpyScreenshotGet()

      if (data?.success && data.image) {
        setScreenData(`data:image/jpeg;base64,${data.image}`)
        console.log(
          `截图成功: ${data.size} 字节, ${data.width}x${data.height}`,
        )
      } else {
        setCaptureError(data?.message || '截图失败')
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

  useEffect(() => {
    if (!isConnected) {
      setAutoRefresh(false)
      stopLiveMode()
    }
  }, [isConnected])

  const getWsUrl = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.hostname
    const port = '8000'
    return `${protocol}//${host}:${port}/api/v1/scrcpy/stream`
  }, [])

  const startLiveMode = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(getWsUrl())
    wsRef.current = ws

    ws.onopen = () => {
      console.log('实时监看 WebSocket 已连接')
      setIsLiveMode(true)
      setIsLivePaused(false)
      setCaptureError(null)
      ws.send(
        JSON.stringify({ action: 'set_interval', interval: fpsToInterval(targetFps) }),
      )
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

  const toggleLivePause = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return

    if (isLivePaused) {
      wsRef.current.send(JSON.stringify({ action: 'resume' }))
    } else {
      wsRef.current.send(JSON.stringify({ action: 'pause' }))
    }
    setIsLivePaused(!isLivePaused)
  }, [isLivePaused])

  const switchFps = useCallback(
    (fps: 30 | 60) => {
      setTargetFps(fps)
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(
          JSON.stringify({ action: 'set_interval', interval: fpsToInterval(fps) }),
        )
      }
    },
    [fpsToInterval],
  )

  useEffect(() => {
    return () => {
      stopLiveMode()
    }
  }, [stopLiveMode])

  const downloadScreenshot = () => {
    if (!screenData) return

    const link = document.createElement('a')
    link.href = screenData
    link.download = `screenshot_${new Date().toISOString().replace(/[:.]/g, '-')}.png`
    link.click()
  }

  const captureAndDetectDiff = useCallback(async () => {
    setIsDiffDetecting(true)
    setDiffError(null)
    setDiffResult(null)
    setShowDiffResult(true)

    try {
      let imageData: string | null = screenData

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

      const response = await fetch(imageData)
      const blob = await response.blob()
      const file = new File([blob], 'screenshot.png', { type: 'image/png' })

      diffMutation.mutate({
        body: {
          file,
        },
      })
    } catch (err) {
      setDiffError(
        '差异识别失败: ' + (err instanceof Error ? err.message : '未知错误'),
      )
      setIsDiffDetecting(false)
    }
  }, [screenData, diffMutation])

  const closeDiffResult = useCallback(() => {
    setShowDiffResult(false)
    setDiffResult(null)
    setDiffError(null)
  }, [])

  return (
    <div className="min-h-screen bg-background">
      {/* 连接控制区域 */}
      <section className="py-8 px-6 max-w-4xl mx-auto">
        <Card>
          <CardContent className="pt-6">
            {isConnected ? (
              <div className="flex flex-col md:flex-row items-center justify-between gap-4">
                <div className="flex items-center gap-4">
                  <div
                    className={`size-4 rounded-full ${isStreaming ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'}`}
                  />
                  <div>
                    <p className="font-medium">
                      已连接: {deviceInfo?.serial || deviceInfo?.name || '设备'}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {isStreaming ? (
                        <>
                          视频流已启动
                          {isScrcpyMode && (
                            <Badge variant="secondary" className="ml-2">
                              Scrcpy 高性能模式
                            </Badge>
                          )}
                        </>
                      ) : (
                        'Scrcpy 已连接'
                      )}
                      {deviceInfo?.resolution &&
                        ` · ${deviceInfo.resolution[0]}×${deviceInfo.resolution[1]}`}
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  {/* 实时监看按钮 */}
                  {!isLiveMode ? (
                    <>
                      {/* 帧率选择 */}
                      <div className="flex items-center rounded-md border p-1">
                        <Button
                          variant={targetFps === 30 ? 'default' : 'ghost'}
                          size="sm"
                          onClick={() => setTargetFps(30)}
                        >
                          30帧
                        </Button>
                        <Button
                          variant={targetFps === 60 ? 'default' : 'ghost'}
                          size="sm"
                          onClick={() => setTargetFps(60)}
                        >
                          60帧
                        </Button>
                      </div>
                      <Button
                        onClick={startLiveMode}
                        disabled={autoRefresh}
                        className="bg-cyan-600 hover:bg-cyan-700"
                      >
                        <Video className="size-4" />
                        实时监看
                      </Button>
                    </>
                  ) : (
                    <>
                      {/* 实时监看中的帧率切换 */}
                      <div className="flex items-center rounded-md border p-1">
                        <Button
                          variant={targetFps === 30 ? 'default' : 'ghost'}
                          size="sm"
                          onClick={() => switchFps(30)}
                        >
                          30帧
                        </Button>
                        <Button
                          variant={targetFps === 60 ? 'default' : 'ghost'}
                          size="sm"
                          onClick={() => switchFps(60)}
                        >
                          60帧
                        </Button>
                      </div>
                      <Button
                        variant={isLivePaused ? 'default' : 'secondary'}
                        onClick={toggleLivePause}
                        className={
                          isLivePaused
                            ? 'bg-green-600 hover:bg-green-700'
                            : 'bg-yellow-600 hover:bg-yellow-700 text-white'
                        }
                      >
                        {isLivePaused ? (
                          <>
                            <Play className="size-4" />
                            继续
                          </>
                        ) : (
                          <>
                            <Pause className="size-4" />
                            暂停
                          </>
                        )}
                      </Button>
                      <Button variant="secondary" onClick={stopLiveMode}>
                        <Video className="size-4" />
                        停止监看
                      </Button>
                    </>
                  )}

                  {/* 单次截图 */}
                  <Button
                    variant="outline"
                    onClick={captureScreen}
                    disabled={isCapturing || isLiveMode}
                    className="border-purple-500 text-purple-500 hover:bg-purple-500 hover:text-white"
                  >
                    {isCapturing ? (
                      <Loader2 className="size-4 animate-spin" />
                    ) : (
                      <Camera className="size-4" />
                    )}
                    截图
                  </Button>

                  {/* 自动刷新 */}
                  {!isLiveMode && (
                    <Button
                      variant={autoRefresh ? 'default' : 'secondary'}
                      onClick={() => setAutoRefresh(!autoRefresh)}
                      className={autoRefresh ? 'bg-green-600 hover:bg-green-700' : ''}
                    >
                      <RefreshCw
                        className={`size-4 ${autoRefresh ? 'animate-spin' : ''}`}
                      />
                      {autoRefresh ? '停止刷新' : '自动刷新'}
                    </Button>
                  )}

                  {/* 差异识别 */}
                  <Button
                    variant="outline"
                    onClick={captureAndDetectDiff}
                    disabled={(!screenData && !isLiveMode) || isDiffDetecting}
                    className="border-orange-500 text-orange-500 hover:bg-orange-500 hover:text-white"
                  >
                    {isDiffDetecting ? (
                      <>
                        <Loader2 className="size-4 animate-spin" />
                        识别中...
                      </>
                    ) : (
                      <>
                        <ScanSearch className="size-4" />
                        差异识别
                      </>
                    )}
                  </Button>

                  <Button variant="destructive" onClick={disconnect}>
                    <Unplug className="size-4" />
                    断开连接
                  </Button>
                </div>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center gap-4">
                  <div className="size-4 rounded-full bg-muted" />
                  <div>
                    <p className="font-medium">未连接设备</p>
                    <p className="text-sm text-muted-foreground">
                      输入设备 IP 地址和端口进行连接
                    </p>
                  </div>
                </div>

                <div className="flex flex-col md:flex-row gap-4">
                  <div className="flex-1 space-y-2">
                    <Label htmlFor="host">IP 地址</Label>
                    <Input
                      id="host"
                      type="text"
                      value={hostInput}
                      onChange={(e) => setHostInput(e.target.value)}
                      placeholder="例如: 192.168.1.100"
                    />
                  </div>
                  <div className="w-32 space-y-2">
                    <Label htmlFor="port">端口</Label>
                    <Input
                      id="port"
                      type="text"
                      value={portInput}
                      onChange={(e) => setPortInput(e.target.value)}
                      placeholder="5555"
                    />
                  </div>
                  <div className="flex items-end">
                    <Button
                      onClick={connect}
                      disabled={isConnecting}
                      className="bg-purple-600 hover:bg-purple-700"
                    >
                      {isConnecting ? (
                        <>
                          <Loader2 className="size-4 animate-spin" />
                          连接中...
                        </>
                      ) : (
                        <>
                          <Wifi className="size-4" />
                          连接
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* 错误提示 */}
        {(error || captureError) && (
          <Alert variant="destructive" className="mt-4">
            <AlertCircle className="size-4" />
            <AlertTitle>{error ? '连接失败' : '截图失败'}</AlertTitle>
            <AlertDescription>{error || captureError}</AlertDescription>
          </Alert>
        )}

        {/* 使用说明 */}
        {!isConnected && !error && (
          <Alert className="mt-6">
            <Info className="size-4" />
            <AlertTitle>无线调试使用说明</AlertTitle>
            <AlertDescription>
              <ol className="mt-2 space-y-2 list-decimal list-inside">
                <li>
                  在手机上进入 <strong>设置 → 开发者选项</strong>
                </li>
                <li>
                  开启 <strong>无线调试</strong>
                </li>
                <li>
                  点击无线调试，查看 <strong>IP 地址和端口</strong>
                </li>
                <li>
                  如果使用配对，先点击"使用配对码配对设备"，在电脑终端执行:
                  <code className="block mt-1 p-2 bg-muted rounded text-sm font-mono">
                    adb pair IP地址:配对端口
                  </code>
                </li>
                <li>在上方输入手机显示的 IP 地址和端口，点击连接</li>
              </ol>
              <div className="mt-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
                <p className="text-yellow-600 dark:text-yellow-400 text-sm">
                  <strong>提示：</strong>手机和电脑需要在同一个 WiFi 网络下
                </p>
              </div>
            </AlertDescription>
          </Alert>
        )}
      </section>

      {/* 屏幕显示和差异结果区域 */}
      {isConnected && (
        <section className="py-8 px-6">
          <div className="flex gap-6">
            {/* 左侧：手机屏幕区域 */}
            <div className="flex-shrink-0 w-[400px]">
              <Card className="h-full">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Monitor className="size-4 text-purple-500" />
                      屏幕
                      {/* 实时监看状态 */}
                      {isLiveMode && (
                        <div className="flex items-center gap-2">
                          <Badge
                            variant={isLivePaused ? 'secondary' : 'default'}
                            className={
                              isLivePaused
                                ? ''
                                : 'bg-green-500 hover:bg-green-500'
                            }
                          >
                            <span
                              className={`size-1.5 rounded-full mr-1 ${
                                isLivePaused
                                  ? 'bg-yellow-500'
                                  : 'bg-white animate-pulse'
                              }`}
                            />
                            {isLivePaused ? '暂停' : '实时'}
                          </Badge>
                          {!isLivePaused && (
                            <>
                              <span className="text-sm font-mono text-muted-foreground">
                                {liveFps} FPS
                              </span>
                              <Badge
                                variant="outline"
                                className={
                                  videoSource === 'scrcpy'
                                    ? 'border-purple-500 text-purple-500'
                                    : 'border-blue-500 text-blue-500'
                                }
                              >
                                {videoSource === 'scrcpy' ? 'Scrcpy' : 'ADB'}
                              </Badge>
                            </>
                          )}
                        </div>
                      )}
                    </CardTitle>
                    {screenData && (
                      <Button variant="ghost" size="sm" onClick={downloadScreenshot}>
                        <Download className="size-3" />
                        下载
                      </Button>
                    )}
                  </div>
                </CardHeader>
                <CardContent>
                  {/* 手机屏幕显示区域 */}
                  <div
                    className="w-full bg-muted/50 rounded-lg border relative overflow-hidden flex items-center justify-center"
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
                        {isLiveMode && isLivePaused && (
                          <div className="absolute inset-0 bg-black/30 flex items-center justify-center rounded-lg pointer-events-none">
                            <div className="bg-black/60 px-4 py-2 rounded-lg flex items-center gap-2">
                              <Pause className="size-6 text-white" />
                              <span className="text-white font-medium">已暂停</span>
                            </div>
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="text-center text-muted-foreground p-4">
                        <Monitor className="size-12 mx-auto mb-3 opacity-50" />
                        <p className="text-sm">点击"实时监看"同步手机画面</p>
                        <p className="text-xs mt-1">或点击"截图"获取静态画面</p>
                      </div>
                    )}
                  </div>

                  {/* 设备信息 */}
                  {deviceInfo?.resolution && (
                    <div className="mt-2 text-center text-xs text-muted-foreground">
                      {deviceInfo.resolution[0]} × {deviceInfo.resolution[1]}
                    </div>
                  )}

                  {isCapturing && !isLiveMode && (
                    <div className="mt-3 flex items-center justify-center gap-2 text-purple-500 text-sm">
                      <Loader2 className="size-4 animate-spin" />
                      <span>正在获取...</span>
                    </div>
                  )}
                </CardContent>
              </Card>
            </div>

            {/* 右侧：差异识别结果区域 */}
            <div className="flex-1 min-w-0">
              {showDiffResult ? (
                <Card
                  className="h-full overflow-auto"
                  style={{ maxHeight: 'calc(70vh + 100px)' }}
                >
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="flex items-center gap-2">
                        <Image className="size-5 text-primary" />
                        差异识别结果
                      </CardTitle>
                      <div className="flex items-center gap-3">
                        {diffResult && (
                          <Badge variant="secondary">
                            发现 {diffResult.difference_count} 处差异
                          </Badge>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={closeDiffResult}
                        >
                          <X className="size-4" />
                        </Button>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent>
                    {/* 加载状态 */}
                    {isDiffDetecting && (
                      <div className="flex flex-col items-center justify-center py-12">
                        <Loader2 className="size-10 text-orange-500 animate-spin mb-4" />
                        <p>正在识别差异...</p>
                        <p className="text-sm text-muted-foreground mt-1">
                          系统会自动分割图片并进行对比
                        </p>
                      </div>
                    )}

                    {/* 错误提示 */}
                    {diffError && (
                      <Alert variant="destructive">
                        <AlertCircle className="size-4" />
                        <AlertTitle>识别失败</AlertTitle>
                        <AlertDescription>{diffError}</AlertDescription>
                      </Alert>
                    )}

                    {/* 差异区域信息 */}
                    {diffResult &&
                      diffResult.differences &&
                      diffResult.differences.length > 0 && (
                        <div className="mb-4">
                          <h3 className="text-sm font-medium mb-2">差异区域详情</h3>
                          <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
                            {diffResult.differences.map((diff) => (
                              <Card key={diff.index} className="py-2">
                                <CardContent className="text-center p-0">
                                  <div className="text-primary font-bold text-sm">
                                    #{diff.index}
                                  </div>
                                  <div className="text-xs text-muted-foreground">
                                    ({diff.x}, {diff.y}) {diff.width}×{diff.height}
                                  </div>
                                </CardContent>
                              </Card>
                            ))}
                          </div>
                        </div>
                      )}

                    {/* 结果图片展示 */}
                    {diffResult && (
                      <div className="space-y-4">
                        {diffResult.marked_image_base64 && (
                          <div>
                            <h3 className="text-sm font-medium mb-2">对比标记图</h3>
                            <div className="flex justify-center">
                              <img
                                src={`data:image/png;base64,${diffResult.marked_image_base64}`}
                                alt="差异标记图"
                                className="max-w-full max-h-[40vh] rounded-lg shadow-lg border"
                              />
                            </div>
                          </div>
                        )}

                        {diffResult.heatmap_base64 && (
                          <div>
                            <h3 className="text-sm font-medium mb-2">差异热力图</h3>
                            <div className="flex justify-center">
                              <img
                                src={`data:image/png;base64,${diffResult.heatmap_base64}`}
                                alt="差异热力图"
                                className="max-w-full max-h-[40vh] rounded-lg shadow-lg border"
                              />
                            </div>
                          </div>
                        )}

                        {(diffResult.image1_base64 || diffResult.image2_base64) && (
                          <div>
                            <h3 className="text-sm font-medium mb-2">单独标记图</h3>
                            <div className="grid md:grid-cols-2 gap-3">
                              {diffResult.image1_base64 && (
                                <div>
                                  <p className="text-xs text-muted-foreground mb-1 text-center">
                                    图片 1
                                  </p>
                                  <img
                                    src={`data:image/png;base64,${diffResult.image1_base64}`}
                                    alt="图片1标记"
                                    className="w-full rounded-lg shadow-lg border"
                                  />
                                </div>
                              )}
                              {diffResult.image2_base64 && (
                                <div>
                                  <p className="text-xs text-muted-foreground mb-1 text-center">
                                    图片 2
                                  </p>
                                  <img
                                    src={`data:image/png;base64,${diffResult.image2_base64}`}
                                    alt="图片2标记"
                                    className="w-full rounded-lg shadow-lg border"
                                  />
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ) : (
                <Card
                  className="h-full flex flex-col items-center justify-center"
                  style={{ minHeight: '400px' }}
                >
                  <CardContent className="text-center text-muted-foreground">
                    <ScanSearch className="size-16 mb-4 opacity-50 mx-auto" />
                    <p className="text-lg font-medium mb-2">
                      差异识别结果将显示在这里
                    </p>
                    <p className="text-sm">点击上方"差异识别"按钮开始检测</p>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
