"""
Scrcpy 服务 - 使用 scrcpy-server 实现设备控制和实时视频流传输
提供高性能的 H.264 视频流、触摸/滑动/按键等控制功能

使用真正的 scrcpy 协议：
1. 推送 scrcpy-server.jar 到设备
2. 在设备上运行 scrcpy-server
3. 通过 socket 连接获取 H.264 编码的视频流
4. 使用 PyAV 解码 H.264 帧
"""

import asyncio
import base64
import struct
import socket
import threading
import time
from pathlib import Path
from typing import Callable, Optional
from dataclasses import dataclass
import cv2
import numpy as np
from queue import Queue, Empty

try:
    from adbutils import adb, AdbDevice, AdbTimeout, AdbConnection, Network

    ADBUTILS_AVAILABLE = True
except ImportError:
    ADBUTILS_AVAILABLE = False
    adb = None
    AdbDevice = None
    AdbTimeout = None
    AdbConnection = None
    Network = None

# PyAV 用于 H.264 解码
try:
    from av.codec import CodecContext
    from av.error import InvalidDataError

    PYAV_AVAILABLE = True
except ImportError:
    PYAV_AVAILABLE = False
    CodecContext = None
    InvalidDataError = Exception


@dataclass
class DeviceInfo:
    """设备信息"""

    serial: str
    name: str = ""
    resolution: tuple[int, int] = (0, 0)
    is_connected: bool = False


@dataclass
class ScrcpyConfig:
    """Scrcpy 配置"""

    max_width: int = 1920  # 最大宽度，支持1080p高清，降低可减少CPU使用
    bitrate: int = 8_000_000  # 比特率 8Mbps，高分辨率需要更高比特率
    max_fps: int = 60  # 最大帧率
    lock_screen_orientation: int = -1  # -1 不锁定
    stay_awake: bool = True  # 保持唤醒


class ScrcpyService:
    """
    Scrcpy 服务类

    使用 scrcpy-server 进行实时视频流传输和设备控制
    支持:
    - 设备列表和连接
    - H.264 实时视频流
    - 屏幕截图
    - 触摸/滑动控制
    - 按键事件
    - 文本输入
    - 录制功能（通过 scrcpy.exe）

    参考文档: https://github.com/Genymobile/scrcpy
    """

    # Scrcpy 目录路径（项目根目录下的 scrcpy 文件夹）
    SCRCPY_DIR = Path(__file__).parent.parent.parent / "scrcpy"
    # Scrcpy server 文件路径
    SCRCPY_SERVER_PATH = SCRCPY_DIR / "scrcpy-server"
    SCRCPY_SERVER_DEVICE_PATH = "/data/local/tmp/scrcpy-server.jar"
    SCRCPY_SERVER_VERSION = "3.3.3"  # scrcpy-server 版本
    # Scrcpy 可执行文件路径
    SCRCPY_EXE_PATH = SCRCPY_DIR / "scrcpy.exe"
    # ADB 可执行文件路径
    ADB_EXE_PATH = SCRCPY_DIR / "adb.exe"

    def __init__(self):
        self._device: Optional[AdbDevice] = None
        self._device_info: Optional[DeviceInfo] = None
        self._config = ScrcpyConfig()
        self._last_frame: Optional[np.ndarray] = None
        self._frame_listeners: list[Callable] = []
        self._lock = threading.Lock()
        self._is_streaming = False
        self._stream_thread: Optional[threading.Thread] = None
        self._stop_stream = False

        # Scrcpy 视频流相关
        self._server_stream: Optional[AdbConnection] = None
        self._video_socket: Optional[socket.socket] = None
        self._control_socket: Optional[socket.socket] = None
        self._frame_queue: Queue = Queue(maxsize=5)  # 帧队列，限制大小避免内存溢出
        self._scrcpy_running = False
        self._device_name: Optional[str] = None

        # 录制功能相关（使用 scrcpy.exe）
        self._recording_process: Optional[asyncio.subprocess.Process] = None
        self._is_recording = False
        self._recording_file: Optional[str] = None

    @property
    def is_available(self) -> bool:
        """检查 adbutils 和 PyAV 库是否可用"""
        return ADBUTILS_AVAILABLE and PYAV_AVAILABLE

    @property
    def is_scrcpy_exe_available(self) -> bool:
        """检查 scrcpy.exe 可执行文件是否存在"""
        return self.SCRCPY_EXE_PATH.exists()

    @property
    def is_scrcpy_server_available(self) -> bool:
        """检查 scrcpy-server 文件是否存在"""
        return self.SCRCPY_SERVER_PATH.exists()

    @property
    def is_recording(self) -> bool:
        """检查是否正在录制"""
        return self._is_recording and self._recording_process is not None

    @property
    def is_scrcpy_streaming(self) -> bool:
        """检查 scrcpy 视频流是否正在运行"""
        return self._scrcpy_running and self._is_streaming

    @property
    def is_connected(self) -> bool:
        """检查是否已连接设备"""
        return self._device is not None and self._device_info is not None

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        """获取设备信息"""
        return self._device_info

    @property
    def resolution(self) -> Optional[tuple[int, int]]:
        """获取设备分辨率"""
        if self._device_info:
            return self._device_info.resolution
        return None

    @property
    def last_frame(self) -> Optional[np.ndarray]:
        """获取最新帧"""
        with self._lock:
            return self._last_frame.copy() if self._last_frame is not None else None

    async def list_devices(self) -> dict:
        """列出所有可用设备"""
        if not ADBUTILS_AVAILABLE:
            return {"success": False, "message": "adbutils 未安装，请运行: pip install adbutils"}

        try:
            loop = asyncio.get_event_loop()
            devices = await loop.run_in_executor(None, adb.device_list)

            device_list = []
            for device in devices:
                device_list.append(
                    {
                        "serial": device.serial,
                        "state": "device",
                    }
                )

            return {"success": True, "devices": device_list}
        except Exception as e:
            return {"success": False, "message": f"获取设备列表失败: {str(e)}"}

    async def adb_connect(self, host: str, port: int = 5555) -> dict:
        """通过 ADB 连接到远程设备"""
        if not ADBUTILS_AVAILABLE:
            return {"success": False, "message": "adbutils 未安装"}

        try:
            address = f"{host}:{port}"
            loop = asyncio.get_event_loop()

            # 使用 adbutils 连接设备
            def do_connect():
                return adb.connect(address, timeout=10.0)

            result = await loop.run_in_executor(None, do_connect)

            if result:
                return {"success": True, "message": f"ADB 已连接到 {address}", "address": address}
            else:
                return {"success": False, "message": f"ADB 连接失败"}
        except Exception as e:
            return {"success": False, "message": f"ADB 连接失败: {str(e)}"}

    async def connect(self, device_serial: Optional[str] = None, config: Optional[ScrcpyConfig] = None) -> dict:
        """
        连接到设备

        Args:
            device_serial: 设备序列号，None 则使用第一个设备
            config: scrcpy 配置
        """
        if not ADBUTILS_AVAILABLE:
            return {"success": False, "message": "adbutils 未安装，请运行: pip install adbutils"}

        # 先断开现有连接
        if self._device:
            await self.disconnect()

        if config:
            self._config = config

        try:
            loop = asyncio.get_event_loop()

            # 获取设备
            def get_device():
                devices = adb.device_list()
                if not devices:
                    return None

                if device_serial:
                    for d in devices:
                        if d.serial == device_serial:
                            return d
                    return None
                else:
                    return devices[0]

            self._device = await loop.run_in_executor(None, get_device)

            if not self._device:
                return {"success": False, "message": "未找到指定的 Android 设备"}

            # 获取设备信息
            def get_device_info():
                try:
                    # 获取设备名称
                    name = self._device.prop.get("ro.product.model", "Unknown")

                    # 获取分辨率
                    output = self._device.shell("wm size")
                    width, height = 0, 0
                    if "x" in output:
                        size_part = output.split(":")[-1].strip()
                        if "x" in size_part:
                            w, h = size_part.split("x")
                            width, height = int(w), int(h)

                    return name, (width, height)
                except Exception:
                    return "Unknown", (0, 0)

            name, resolution = await loop.run_in_executor(None, get_device_info)

            self._device_info = DeviceInfo(serial=self._device.serial, name=name, resolution=resolution, is_connected=True)

            # 启动 scrcpy 视频流
            scrcpy_result = await self._start_scrcpy_stream()
            if not scrcpy_result.get("success"):
                # 如果 scrcpy 启动失败，仍然保持 ADB 连接，可以使用截图模式
                return {
                    "success": True,
                    "message": f"已连接到设备 {name}（scrcpy 启动失败: {scrcpy_result.get('message')}，使用截图模式）",
                    "device": {
                        "serial": self._device.serial,
                        "name": name,
                        "resolution": resolution,
                    },
                    "scrcpy_mode": False,
                }

            return {
                "success": True,
                "message": f"已连接到设备 {name}（scrcpy 视频流模式）",
                "device": {
                    "serial": self._device.serial,
                    "name": name,
                    "resolution": resolution,
                },
                "scrcpy_mode": True,
            }

        except Exception as e:
            self._device = None
            self._device_info = None
            return {"success": False, "message": f"连接失败: {str(e)}"}

    async def _start_scrcpy_stream(self) -> dict:
        """
        启动 scrcpy-server 并建立视频流连接
        """
        if not PYAV_AVAILABLE:
            return {"success": False, "message": "PyAV 未安装，请运行: pip install av"}

        if not self._device:
            return {"success": False, "message": "设备未连接"}

        try:
            loop = asyncio.get_event_loop()

            # 1. 推送 scrcpy-server.jar 到设备
            def push_server():
                if not self.SCRCPY_SERVER_PATH.exists():
                    raise FileNotFoundError(f"scrcpy-server.jar 未找到: {self.SCRCPY_SERVER_PATH}")
                self._device.sync.push(str(self.SCRCPY_SERVER_PATH), self.SCRCPY_SERVER_DEVICE_PATH)

            await loop.run_in_executor(None, push_server)

            # 2. 启动 scrcpy-server
            def start_server():
                commands = [
                    f"CLASSPATH={self.SCRCPY_SERVER_DEVICE_PATH}",
                    "app_process",
                    "/",
                    "com.genymobile.scrcpy.Server",
                    self.SCRCPY_SERVER_VERSION,
                    "log_level=info",
                    f"max_size={self._config.max_width}",
                    f"max_fps={self._config.max_fps}",
                    f"video_bit_rate={self._config.bitrate}",
                    "video_codec=h264",
                    "tunnel_forward=true",
                    "send_frame_meta=false",  # 不发送帧元数据，直接传输原始 H.264
                    "control=true",
                    "audio=false",
                    "show_touches=false",
                    "stay_awake=true" if self._config.stay_awake else "stay_awake=false",
                    "power_off_on_close=false",
                    "clipboard_autosync=false",
                ]

                self._server_stream = self._device.shell(commands, stream=True)
                # 等待服务器启动
                time.sleep(0.5)
                return True

            await loop.run_in_executor(None, start_server)

            # 3. 连接视频 socket
            def connect_sockets():
                for _ in range(30):  # 最多等待 3 秒
                    try:
                        self._video_socket = self._device.create_connection(Network.LOCAL_ABSTRACT, "scrcpy")
                        break
                    except Exception:
                        time.sleep(0.1)
                else:
                    raise ConnectionError("无法连接到 scrcpy-server 视频 socket")

                # 接收 dummy byte
                dummy_byte = self._video_socket.recv(1)
                if not dummy_byte or dummy_byte != b"\x00":
                    raise ConnectionError("未收到 Dummy Byte")

                # 连接控制 socket
                self._control_socket = self._device.create_connection(Network.LOCAL_ABSTRACT, "scrcpy")

                # 接收设备名称 (64 bytes)
                device_name_bytes = self._video_socket.recv(64)
                self._device_name = device_name_bytes.decode("utf-8").rstrip("\x00")

                # 接收分辨率 (4 bytes: width, height as u16)
                res_bytes = self._video_socket.recv(4)
                width, height = struct.unpack(">HH", res_bytes)
                if self._device_info:
                    self._device_info.resolution = (width, height)

                # 设置非阻塞模式
                self._video_socket.setblocking(False)

                return True

            await loop.run_in_executor(None, connect_sockets)

            # 4. 启动视频流解码线程
            self._scrcpy_running = True
            self._stop_stream = False
            self._stream_thread = threading.Thread(target=self._video_stream_loop, daemon=True)
            self._stream_thread.start()
            self._is_streaming = True

            return {"success": True, "message": "scrcpy 视频流已启动"}

        except Exception as e:
            self._stop_scrcpy()
            return {"success": False, "message": f"启动 scrcpy 失败: {str(e)}"}

    def _video_stream_loop(self):
        """
        视频流解码循环（在独立线程中运行）
        """
        if not PYAV_AVAILABLE:
            return

        codec = CodecContext.create("h264", "r")

        while not self._stop_stream and self._scrcpy_running:
            try:
                # 从 socket 接收 H.264 数据
                raw_h264 = self._video_socket.recv(0x10000)
                if raw_h264 == b"":
                    # 连接断开
                    break

                # 解析 H.264 包
                packets = codec.parse(raw_h264)
                for packet in packets:
                    frames = codec.decode(packet)
                    for frame in frames:
                        # 转换为 numpy 数组 (BGR 格式)
                        np_frame = frame.to_ndarray(format="bgr24")

                        # 更新最新帧
                        with self._lock:
                            self._last_frame = np_frame

                        # 放入帧队列（如果队列满则丢弃旧帧）
                        try:
                            if self._frame_queue.full():
                                try:
                                    self._frame_queue.get_nowait()
                                except Empty:
                                    pass
                            self._frame_queue.put_nowait(np_frame)
                        except Exception:
                            pass

                        # 通知监听器
                        for listener in self._frame_listeners:
                            try:
                                listener(np_frame)
                            except Exception:
                                pass

            except BlockingIOError:
                # 非阻塞模式下没有数据可读
                time.sleep(0.001)
            except InvalidDataError:
                # 解码错误，跳过
                time.sleep(0.001)
            except (ConnectionError, OSError):
                # 连接断开
                break
            except Exception:
                time.sleep(0.01)

        self._is_streaming = False
        self._scrcpy_running = False

    def _stop_scrcpy(self):
        """停止 scrcpy 服务"""
        self._stop_stream = True
        self._scrcpy_running = False

        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=2.0)

        if self._video_socket:
            try:
                self._video_socket.close()
            except Exception:
                pass
            self._video_socket = None

        if self._control_socket:
            try:
                self._control_socket.close()
            except Exception:
                pass
            self._control_socket = None

        if self._server_stream:
            try:
                self._server_stream.close()
            except Exception:
                pass
            self._server_stream = None

        self._is_streaming = False

        # 清空帧队列
        while not self._frame_queue.empty():
            try:
                self._frame_queue.get_nowait()
            except Empty:
                break

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """
        获取最新的视频帧（从帧队列中）

        Returns:
            numpy 数组格式的帧，如果没有可用帧则返回 None
        """
        try:
            # 获取队列中最新的帧
            frame = None
            while not self._frame_queue.empty():
                frame = self._frame_queue.get_nowait()
            return frame
        except Empty:
            return None

    async def get_frame_async(self, timeout: float = 0.1) -> Optional[np.ndarray]:
        """
        异步获取视频帧

        Args:
            timeout: 超时时间（秒）

        Returns:
            numpy 数组格式的帧，如果超时则返回 None
        """
        loop = asyncio.get_event_loop()

        def get_frame():
            try:
                return self._frame_queue.get(timeout=timeout)
            except Empty:
                return None

        return await loop.run_in_executor(None, get_frame)

    async def disconnect(self) -> dict:
        """断开连接"""
        try:
            # 停止 scrcpy 视频流
            self._stop_scrcpy()

            self._device = None
            self._device_info = None
            self._last_frame = None
            self._is_streaming = False
            self._stop_stream = False
            self._scrcpy_running = False

            return {"success": True, "message": "已断开连接"}
        except Exception as e:
            return {"success": False, "message": f"断开连接失败: {str(e)}"}

    def get_status(self) -> dict:
        """获取连接状态"""
        return {
            "connected": self.is_connected,
            "streaming": self._is_streaming,
            "scrcpy_mode": self._scrcpy_running,
            "device": {
                "serial": self._device_info.serial if self._device_info else None,
                "name": self._device_info.name if self._device_info else None,
                "resolution": self._device_info.resolution if self._device_info else None,
            }
            if self._device_info
            else None,
            "config": {
                "max_width": self._config.max_width,
                "bitrate": self._config.bitrate,
                "max_fps": self._config.max_fps,
            },
        }

    async def capture_screen(self, quality: int = 80, use_original_resolution: bool = True) -> dict:
        """
        截取当前屏幕

        Args:
            quality: JPEG 压缩质量 (1-100)
            use_original_resolution: 使用设备原始分辨率（默认 True，通过 adb screencap 获取）
        """
        if not self.is_connected or not self._device:
            return {"success": False, "message": "设备未连接"}

        try:
            frame = None
            source = "adb"

            # 如果不要求原始分辨率，优先从 scrcpy 视频流获取帧
            if not use_original_resolution and self._scrcpy_running and self._is_streaming:
                with self._lock:
                    if self._last_frame is not None:
                        frame = self._last_frame.copy()
                        source = "scrcpy"

            # 默认使用 adb screencap 获取原始分辨率，或者 scrcpy 帧不可用时回退
            if frame is None:
                loop = asyncio.get_event_loop()

                def take_screenshot():
                    png_data = self._device.shell("screencap -p", encoding=None)
                    return png_data

                png_data = await loop.run_in_executor(None, take_screenshot)

                if not png_data or len(png_data) < 100:
                    return {"success": False, "message": "截图失败：未收到数据"}

                # 解码 PNG
                nparr = np.frombuffer(png_data, np.uint8)
                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                if frame is None:
                    return {"success": False, "message": "截图失败：无法解码图像"}

                source = "adb"

                # 更新最新帧
                with self._lock:
                    self._last_frame = frame

            # 编码为 JPEG
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            _, buffer = cv2.imencode(".jpg", frame, encode_param)
            image_base64 = base64.b64encode(buffer).decode("utf-8")

            return {
                "success": True,
                "image": image_base64,
                "size": len(buffer),
                "width": frame.shape[1],
                "height": frame.shape[0],
                "format": "jpeg",
                "source": source,
            }
        except Exception as e:
            return {"success": False, "message": f"截图失败: {str(e)}"}

    async def touch(self, x: int, y: int, action: str = "tap") -> dict:
        """
        触摸操作

        Args:
            x: X 坐标
            y: Y 坐标
            action: "down" | "up" | "tap" | "move"
        """
        if not self.is_connected or not self._device:
            return {"success": False, "message": "设备未连接"}

        try:
            loop = asyncio.get_event_loop()

            if action == "tap":
                await loop.run_in_executor(None, lambda: self._device.shell(f"input tap {x} {y}"))
            elif action in ("down", "up", "move"):
                # ADB input 不直接支持 down/up/move，使用 sendevent 或 swipe 模拟
                if action == "down":
                    # 短暂的点击开始
                    await loop.run_in_executor(None, lambda: self._device.shell(f"input swipe {x} {y} {x} {y} 0"))
                # up 和 move 在标准 adb 中较难直接实现
            else:
                return {"success": False, "message": f"未知操作: {action}"}

            return {"success": True, "message": f"触摸 {action} ({x}, {y})"}
        except Exception as e:
            return {"success": False, "message": f"触摸操作失败: {str(e)}"}

    async def swipe(self, start_x: int, start_y: int, end_x: int, end_y: int, duration_ms: int = 300, steps: int = 20) -> dict:
        """
        滑动操作

        Args:
            start_x, start_y: 起始坐标
            end_x, end_y: 结束坐标
            duration_ms: 滑动持续时间（毫秒）
            steps: 滑动步数（用于 scrcpy 模式）
        """
        if not self.is_connected or not self._device:
            return {"success": False, "message": "设备未连接"}

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, lambda: self._device.shell(f"input swipe {start_x} {start_y} {end_x} {end_y} {duration_ms}")
            )

            return {"success": True, "message": f"滑动 ({start_x}, {start_y}) -> ({end_x}, {end_y})"}
        except Exception as e:
            return {"success": False, "message": f"滑动操作失败: {str(e)}"}

    async def keycode(self, keycode: int, action: str = "press") -> dict:
        """
        发送按键事件

        Args:
            keycode: Android keycode
            action: "down" | "up" | "press"
        """
        if not self.is_connected or not self._device:
            return {"success": False, "message": "设备未连接"}

        try:
            loop = asyncio.get_event_loop()

            if action == "press":
                await loop.run_in_executor(None, lambda: self._device.shell(f"input keyevent {keycode}"))
            elif action == "down":
                await loop.run_in_executor(None, lambda: self._device.shell(f"input keyevent --down {keycode}"))
            elif action == "up":
                await loop.run_in_executor(None, lambda: self._device.shell(f"input keyevent --up {keycode}"))
            else:
                return {"success": False, "message": f"未知操作: {action}"}

            return {"success": True, "message": f"按键 {keycode} ({action})"}
        except Exception as e:
            return {"success": False, "message": f"按键操作失败: {str(e)}"}

    async def text(self, text: str) -> dict:
        """
        输入文本

        Args:
            text: 要输入的文本
        """
        if not self.is_connected or not self._device:
            return {"success": False, "message": "设备未连接"}

        try:
            loop = asyncio.get_event_loop()
            # 替换空格和特殊字符
            escaped_text = text.replace(" ", "%s").replace("'", "\\'").replace('"', '\\"')
            await loop.run_in_executor(None, lambda: self._device.shell(f"input text '{escaped_text}'"))
            return {"success": True, "message": f"已输入文本"}
        except Exception as e:
            return {"success": False, "message": f"文本输入失败: {str(e)}"}

    async def back(self) -> dict:
        """返回键"""
        return await self.keycode(4)  # KEYCODE_BACK = 4

    async def home(self) -> dict:
        """Home 键"""
        return await self.keycode(3)  # KEYCODE_HOME = 3

    async def recent_apps(self) -> dict:
        """最近应用键"""
        return await self.keycode(187)  # KEYCODE_APP_SWITCH = 187

    async def power(self) -> dict:
        """电源键"""
        return await self.keycode(26)  # KEYCODE_POWER = 26

    async def volume_up(self) -> dict:
        """音量+"""
        return await self.keycode(24)  # KEYCODE_VOLUME_UP = 24

    async def volume_down(self) -> dict:
        """音量-"""
        return await self.keycode(25)  # KEYCODE_VOLUME_DOWN = 25

    async def get_clipboard(self) -> dict:
        """获取剪贴板内容（需要 Android 10+）"""
        if not self.is_connected or not self._device:
            return {"success": False, "message": "设备未连接"}

        try:
            loop = asyncio.get_event_loop()
            # 注意：此方法在某些设备上可能不可用
            text = await loop.run_in_executor(None, lambda: self._device.shell("service call clipboard 1"))
            return {"success": True, "text": text}
        except Exception as e:
            return {"success": False, "message": f"获取剪贴板失败: {str(e)}"}

    async def expand_notification_panel(self) -> dict:
        """展开通知面板"""
        if not self.is_connected or not self._device:
            return {"success": False, "message": "设备未连接"}

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self._device.shell("cmd statusbar expand-notifications"))
            return {"success": True, "message": "已展开通知面板"}
        except Exception as e:
            return {"success": False, "message": f"展开通知面板失败: {str(e)}"}

    async def expand_settings_panel(self) -> dict:
        """展开设置面板"""
        if not self.is_connected or not self._device:
            return {"success": False, "message": "设备未连接"}

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self._device.shell("cmd statusbar expand-settings"))
            return {"success": True, "message": "已展开设置面板"}
        except Exception as e:
            return {"success": False, "message": f"展开设置面板失败: {str(e)}"}

    async def collapse_panels(self) -> dict:
        """收起所有面板"""
        if not self.is_connected or not self._device:
            return {"success": False, "message": "设备未连接"}

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self._device.shell("cmd statusbar collapse"))
            return {"success": True, "message": "已收起所有面板"}
        except Exception as e:
            return {"success": False, "message": f"收起面板失败: {str(e)}"}

    async def screen_on(self) -> dict:
        """点亮屏幕"""
        if not self.is_connected or not self._device:
            return {"success": False, "message": "设备未连接"}

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self._device.shell("input keyevent KEYCODE_WAKEUP"))
            return {"success": True, "message": "屏幕已点亮"}
        except Exception as e:
            return {"success": False, "message": f"点亮屏幕失败: {str(e)}"}

    async def screen_off(self) -> dict:
        """关闭屏幕"""
        if not self.is_connected or not self._device:
            return {"success": False, "message": "设备未连接"}

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self._device.shell("input keyevent KEYCODE_SLEEP"))
            return {"success": True, "message": "屏幕已关闭"}
        except Exception as e:
            return {"success": False, "message": f"关闭屏幕失败: {str(e)}"}

    async def rotate_screen(self) -> dict:
        """旋转屏幕"""
        if not self.is_connected or not self._device:
            return {"success": False, "message": "设备未连接"}

        try:
            loop = asyncio.get_event_loop()
            # 获取当前旋转状态
            output = await loop.run_in_executor(None, lambda: self._device.shell("settings get system user_rotation"))
            current = int(output.strip()) if output.strip().isdigit() else 0
            new_rotation = (current + 1) % 4

            await loop.run_in_executor(None, lambda: self._device.shell(f"settings put system user_rotation {new_rotation}"))
            return {"success": True, "message": f"屏幕已旋转到 {new_rotation * 90}°"}
        except Exception as e:
            return {"success": False, "message": f"旋转屏幕失败: {str(e)}"}

    def add_frame_listener(self, listener: Callable[[np.ndarray], None]) -> None:
        """添加帧监听器"""
        if listener not in self._frame_listeners:
            self._frame_listeners.append(listener)

    def remove_frame_listener(self, listener: Callable[[np.ndarray], None]) -> None:
        """移除帧监听器"""
        if listener in self._frame_listeners:
            self._frame_listeners.remove(listener)

    def check_scrcpy_installation(self) -> dict:
        """
        检查 scrcpy 安装状态

        Returns:
            包含各组件安装状态的字典
        """
        return {
            "scrcpy_dir": str(self.SCRCPY_DIR),
            "scrcpy_dir_exists": self.SCRCPY_DIR.exists(),
            "scrcpy_exe": str(self.SCRCPY_EXE_PATH),
            "scrcpy_exe_exists": self.SCRCPY_EXE_PATH.exists(),
            "scrcpy_server": str(self.SCRCPY_SERVER_PATH),
            "scrcpy_server_exists": self.SCRCPY_SERVER_PATH.exists(),
            "adb_exe": str(self.ADB_EXE_PATH),
            "adb_exe_exists": self.ADB_EXE_PATH.exists(),
            "version": self.SCRCPY_SERVER_VERSION,
        }

    async def start_recording(
        self,
        output_file: str,
        device_serial: Optional[str] = None,
        max_size: int = 0,
        max_fps: int = 0,
        video_codec: str = "h264",
        audio: bool = True,
        no_playback: bool = True,
    ) -> dict:
        """
        使用 scrcpy.exe 开始录制

        参考: https://github.com/Genymobile/scrcpy

        Args:
            output_file: 输出文件路径（如 recording.mp4）
            device_serial: 设备序列号（可选）
            max_size: 最大尺寸（0 表示不限制）
            max_fps: 最大帧率（0 表示不限制）
            video_codec: 视频编解码器（h264, h265, av1）
            audio: 是否录制音频
            no_playback: 是否禁用画面显示（仅录制）

        Returns:
            操作结果字典
        """
        if not self.SCRCPY_EXE_PATH.exists():
            return {
                "success": False,
                "message": f"scrcpy.exe 未找到: {self.SCRCPY_EXE_PATH}",
            }

        if self._is_recording:
            return {
                "success": False,
                "message": "已有录制任务正在进行中",
            }

        try:
            # 构建命令行参数
            cmd = [str(self.SCRCPY_EXE_PATH)]

            # 录制到文件
            cmd.extend(["--record", output_file])

            # 设备序列号
            if device_serial:
                cmd.extend(["--serial", device_serial])
            elif self._device_info:
                cmd.extend(["--serial", self._device_info.serial])

            # 视频设置
            if max_size > 0:
                cmd.extend(["--max-size", str(max_size)])
            if max_fps > 0:
                cmd.extend(["--max-fps", str(max_fps)])

            cmd.extend(["--video-codec", video_codec])

            # 音频设置
            if not audio:
                cmd.append("--no-audio")

            # 禁用画面显示（仅录制）
            if no_playback:
                cmd.append("--no-playback")

            # 启动 scrcpy 进程
            self._recording_process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.SCRCPY_DIR),  # 设置工作目录以确保 DLL 可被找到
            )

            self._is_recording = True
            self._recording_file = output_file

            return {
                "success": True,
                "message": f"录制已开始",
                "output_file": output_file,
                "pid": self._recording_process.pid,
                "command": " ".join(cmd),
            }

        except Exception as e:
            self._is_recording = False
            self._recording_process = None
            return {
                "success": False,
                "message": f"启动录制失败: {str(e)}",
            }

    async def stop_recording(self) -> dict:
        """
        停止录制

        Returns:
            操作结果字典
        """
        if not self._is_recording or not self._recording_process:
            return {
                "success": False,
                "message": "没有正在进行的录制任务",
            }

        try:
            # 发送终止信号
            self._recording_process.terminate()

            # 等待进程结束（最多 5 秒）
            try:
                await asyncio.wait_for(self._recording_process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                # 强制结束
                self._recording_process.kill()
                await self._recording_process.wait()

            output_file = self._recording_file
            self._is_recording = False
            self._recording_process = None
            self._recording_file = None

            return {
                "success": True,
                "message": "录制已停止",
                "output_file": output_file,
            }

        except Exception as e:
            self._is_recording = False
            self._recording_process = None
            self._recording_file = None
            return {
                "success": False,
                "message": f"停止录制失败: {str(e)}",
            }

    def get_recording_status(self) -> dict:
        """
        获取录制状态

        Returns:
            录制状态字典
        """
        return {
            "is_recording": self._is_recording,
            "recording_file": self._recording_file,
            "pid": self._recording_process.pid if self._recording_process else None,
        }

    async def run_scrcpy_command(
        self,
        args: list[str],
        wait: bool = True,
        timeout: float = 30.0,
    ) -> dict:
        """
        运行自定义 scrcpy 命令

        参考 scrcpy 文档获取可用选项: https://github.com/Genymobile/scrcpy

        Args:
            args: scrcpy 命令行参数列表
            wait: 是否等待命令完成
            timeout: 超时时间（秒）

        Returns:
            命令执行结果
        """
        if not self.SCRCPY_EXE_PATH.exists():
            return {
                "success": False,
                "message": f"scrcpy.exe 未找到: {self.SCRCPY_EXE_PATH}",
            }

        try:
            cmd = [str(self.SCRCPY_EXE_PATH)] + args

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.SCRCPY_DIR),
            )

            if wait:
                try:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=timeout,
                    )
                    return {
                        "success": process.returncode == 0,
                        "return_code": process.returncode,
                        "stdout": stdout.decode("utf-8", errors="replace"),
                        "stderr": stderr.decode("utf-8", errors="replace"),
                        "command": " ".join(cmd),
                    }
                except asyncio.TimeoutError:
                    process.kill()
                    return {
                        "success": False,
                        "message": f"命令执行超时 ({timeout}秒)",
                        "command": " ".join(cmd),
                    }
            else:
                return {
                    "success": True,
                    "message": "命令已启动（后台运行）",
                    "pid": process.pid,
                    "command": " ".join(cmd),
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"执行命令失败: {str(e)}",
            }

    async def list_displays(self, device_serial: Optional[str] = None) -> dict:
        """
        列出设备的所有显示器

        Args:
            device_serial: 设备序列号

        Returns:
            显示器列表
        """
        args = ["--list-displays"]
        if device_serial:
            args.extend(["--serial", device_serial])
        elif self._device_info:
            args.extend(["--serial", self._device_info.serial])

        return await self.run_scrcpy_command(args)

    async def list_cameras(self, device_serial: Optional[str] = None) -> dict:
        """
        列出设备的所有摄像头

        Args:
            device_serial: 设备序列号

        Returns:
            摄像头列表
        """
        args = ["--list-cameras"]
        if device_serial:
            args.extend(["--serial", device_serial])
        elif self._device_info:
            args.extend(["--serial", self._device_info.serial])

        return await self.run_scrcpy_command(args)

    async def list_encoders(self, device_serial: Optional[str] = None) -> dict:
        """
        列出设备支持的编码器

        Args:
            device_serial: 设备序列号

        Returns:
            编码器列表
        """
        args = ["--list-encoders"]
        if device_serial:
            args.extend(["--serial", device_serial])
        elif self._device_info:
            args.extend(["--serial", self._device_info.serial])

        return await self.run_scrcpy_command(args)


# 单例实例
scrcpy_service = ScrcpyService()
