import { useState, useCallback, useRef } from 'react'
import { Adb, AdbDaemonTransport } from '@yume-chan/adb'
import {
  AdbDaemonWebUsbDeviceManager,
  AdbDaemonWebUsbDevice,
} from '@yume-chan/adb-daemon-webusb'

// ADB 私钥类型
interface AdbPrivateKey {
  buffer: Uint8Array
  name?: string
}

// 密钥存储
const CredentialStore = {
  async generateKey(): Promise<AdbPrivateKey> {
    const { privateKey } = await crypto.subtle.generateKey(
      {
        name: 'RSASSA-PKCS1-v1_5',
        modulusLength: 2048,
        publicExponent: new Uint8Array([0x01, 0x00, 0x01]),
        hash: 'SHA-1',
      },
      true,
      ['sign']
    )

    const exported = await crypto.subtle.exportKey('pkcs8', privateKey)
    const keyData = new Uint8Array(exported)

    // 保存密钥
    const base64 = btoa(String.fromCharCode(...keyData))
    localStorage.setItem('adb-private-key', base64)

    return {
      buffer: keyData,
      name: 'WebADB@Browser',
    }
  },

  async *iterateKeys(): AsyncGenerator<AdbPrivateKey> {
    const stored = localStorage.getItem('adb-private-key')
    if (stored) {
      const bytes = Uint8Array.from(atob(stored), (c) => c.charCodeAt(0))
      yield {
        buffer: bytes,
        name: 'WebADB@Browser',
      }
    }
  },
}

export interface UseAdbResult {
  device: Adb | null
  deviceName: string | null
  isConnecting: boolean
  isConnected: boolean
  error: string | null
  connect: () => Promise<void>
  disconnect: () => Promise<void>
}

export function useAdb(): UseAdbResult {
  const [device, setDevice] = useState<Adb | null>(null)
  const [deviceName, setDeviceName] = useState<string | null>(null)
  const [isConnecting, setIsConnecting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const deviceRef = useRef<AdbDaemonWebUsbDevice | null>(null)

  const connect = useCallback(async () => {
    setIsConnecting(true)
    setError(null)

    try {
      // 创建设备管理器
      const Manager = AdbDaemonWebUsbDeviceManager.BROWSER

      if (!Manager) {
        throw new Error(
          '您的浏览器不支持 WebUSB。请使用 Chrome、Edge 或其他基于 Chromium 的浏览器。'
        )
      }

      // 请求用户选择设备
      const selectedDevice = await Manager.requestDevice()

      if (!selectedDevice) {
        throw new Error('未选择设备')
      }

      deviceRef.current = selectedDevice

      // 连接设备获取连接
      const connection = await selectedDevice.connect()

      // 创建 ADB 传输层并进行认证
      const transport = await AdbDaemonTransport.authenticate({
        serial: selectedDevice.serial,
        connection,
        credentialStore: CredentialStore,
      })

      // 创建 ADB 实例
      const adb = new Adb(transport)

      setDevice(adb)
      setDeviceName(selectedDevice.name || selectedDevice.serial)
    } catch (err) {
      const message =
        err instanceof Error ? err.message : '连接设备时发生未知错误'
      setError(message)
      console.error('ADB 连接错误:', err)
    } finally {
      setIsConnecting(false)
    }
  }, [])

  const disconnect = useCallback(async () => {
    try {
      if (device) {
        await device.close()
      }
    } catch (err) {
      console.error('断开连接错误:', err)
    } finally {
      setDevice(null)
      setDeviceName(null)
      deviceRef.current = null
    }
  }, [device])

  return {
    device,
    deviceName,
    isConnecting,
    isConnected: device !== null,
    error,
    connect,
    disconnect,
  }
}
