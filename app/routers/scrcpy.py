"""
Scrcpy 路由 - 处理设备控制和屏幕镜像相关的 API
"""

import asyncio
import base64

import cv2
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from ..schemas.scrcpy import (
    ScrcpyConnectRequest,
    ScrcpyConnectResponse,
    ScrcpyStatusResponse,
    ScrcpyDevicesResponse,
    ScrcpyDeviceInfo,
    ScrcpyScreenshotRequest,
    ScrcpyScreenshotResponse,
    ScrcpyControlResponse,
    ScrcpyClipboardResponse,
    AdbConnectRequest,
    DeviceInfoResponse,
    ScrcpyRecordingRequest,
    ScrcpyRecordingResponse,
    ScrcpyRecordingStatusResponse,
    ScrcpyInstallationResponse,
    ScrcpyCommandRequest,
    ScrcpyCommandResponse,
)
from ..services.scrcpy_service import scrcpy_service, ScrcpyConfig

router = APIRouter(prefix="/api/v1/scrcpy", tags=["Scrcpy"])


# ============ 连接管理 ============


@router.get("/available", response_model=ScrcpyControlResponse)
async def check_available():
    """检查 scrcpy-client 是否可用"""
    return ScrcpyControlResponse(
        success=scrcpy_service.is_available,
        message="scrcpy-client 可用"
        if scrcpy_service.is_available
        else "scrcpy-client 未安装，请运行: pip install scrcpy-client adbutils",
    )


@router.get("/devices", response_model=ScrcpyDevicesResponse)
async def list_devices():
    """获取已连接的设备列表"""
    result = await scrcpy_service.list_devices()

    devices = []
    if result.get("success") and result.get("devices"):
        for d in result["devices"]:
            devices.append(ScrcpyDeviceInfo(serial=d.get("serial", ""), state=d.get("state", "device")))

    return ScrcpyDevicesResponse(success=result.get("success", False), message=result.get("message"), devices=devices)


@router.post("/adb/connect", response_model=ScrcpyControlResponse)
async def adb_connect(request: AdbConnectRequest):
    """通过 ADB 连接远程设备（用于无线调试）"""
    result = await scrcpy_service.adb_connect(request.host, request.port)
    return ScrcpyControlResponse(**result)


@router.post("/connect", response_model=ScrcpyConnectResponse)
async def connect_device(request: ScrcpyConnectRequest = None):
    """
    连接到设备并启动 scrcpy 视频流

    如果不提供 device_serial，将使用第一个可用设备
    """
    if request is None:
        request = ScrcpyConnectRequest()

    config = ScrcpyConfig(
        max_width=request.max_width,
        bitrate=request.bitrate,
        max_fps=request.max_fps,
    )

    result = await scrcpy_service.connect(device_serial=request.device_serial, config=config)

    device = None
    if result.get("device"):
        d = result["device"]
        device = DeviceInfoResponse(serial=d.get("serial"), name=d.get("name"), resolution=d.get("resolution"))

    return ScrcpyConnectResponse(success=result.get("success", False), message=result.get("message", ""), device=device)


@router.post("/disconnect", response_model=ScrcpyControlResponse)
async def disconnect_device():
    """断开 scrcpy 连接"""
    result = await scrcpy_service.disconnect()
    return ScrcpyControlResponse(**result)


@router.get("/status", response_model=ScrcpyStatusResponse)
async def get_status():
    """获取 scrcpy 连接状态"""
    status = scrcpy_service.get_status()

    device = None
    if status.get("device"):
        d = status["device"]
        device = DeviceInfoResponse(serial=d.get("serial"), name=d.get("name"), resolution=d.get("resolution"))

    return ScrcpyStatusResponse(
        connected=status.get("connected", False),
        streaming=status.get("streaming", False),
        device=device,
        config=status.get("config"),
    )


# ============ 截图 ============


@router.get("/screenshot", response_model=ScrcpyScreenshotResponse)
async def capture_screenshot(
    quality: int = Query(default=80, ge=1, le=100),
    use_original_resolution: bool = Query(default=True, description="使用设备原始分辨率（通过 adb screencap）"),
):
    """截取设备屏幕（默认使用原始分辨率）"""
    result = await scrcpy_service.capture_screen(quality=quality, use_original_resolution=use_original_resolution)
    return ScrcpyScreenshotResponse(**result)


@router.post("/screenshot", response_model=ScrcpyScreenshotResponse)
async def capture_screenshot_post(request: ScrcpyScreenshotRequest = None):
    """截取设备屏幕 (POST)（默认使用原始分辨率）"""
    quality = request.quality if request else 80
    use_original_resolution = request.use_original_resolution if request else True
    result = await scrcpy_service.capture_screen(quality=quality, use_original_resolution=use_original_resolution)
    return ScrcpyScreenshotResponse(**result)


# ============ 剪贴板 ============


@router.get("/clipboard", response_model=ScrcpyClipboardResponse)
async def get_clipboard():
    """获取设备剪贴板内容（需要 Android 10+）"""
    result = await scrcpy_service.get_clipboard()
    return ScrcpyClipboardResponse(**result)


# ============ Scrcpy 安装检查 ============


@router.get("/installation", response_model=ScrcpyInstallationResponse)
async def check_installation():
    """
    检查 scrcpy 安装状态

    返回 scrcpy 目录下各组件的存在状态
    """
    result = scrcpy_service.check_scrcpy_installation()
    return ScrcpyInstallationResponse(**result)


# ============ 录制功能 ============


@router.post("/recording/start", response_model=ScrcpyRecordingResponse)
async def start_recording(request: ScrcpyRecordingRequest):
    """
    开始录制屏幕

    使用 scrcpy.exe 进行录制。参考文档: https://github.com/Genymobile/scrcpy

    注意：
    - 录制功能需要 scrcpy.exe 可执行文件
    - 支持 H.264、H.265、AV1 编码
    - 设置 no_playback=true 时只录制不显示画面
    """
    result = await scrcpy_service.start_recording(
        output_file=request.output_file,
        device_serial=request.device_serial,
        max_size=request.max_size,
        max_fps=request.max_fps,
        video_codec=request.video_codec.value,
        audio=request.audio,
        no_playback=request.no_playback,
    )
    return ScrcpyRecordingResponse(**result)


@router.post("/recording/stop", response_model=ScrcpyRecordingResponse)
async def stop_recording():
    """停止录制"""
    result = await scrcpy_service.stop_recording()
    return ScrcpyRecordingResponse(**result)


@router.get("/recording/status", response_model=ScrcpyRecordingStatusResponse)
async def get_recording_status():
    """获取录制状态"""
    result = scrcpy_service.get_recording_status()
    return ScrcpyRecordingStatusResponse(**result)


# ============ 设备信息查询 ============


@router.get("/displays")
async def list_displays(device_serial: str = None):
    """
    列出设备的所有显示器

    使用 scrcpy --list-displays 命令
    """
    result = await scrcpy_service.list_displays(device_serial)
    return result


@router.get("/cameras")
async def list_cameras(device_serial: str = None):
    """
    列出设备的所有摄像头

    使用 scrcpy --list-cameras 命令（需要 Android 12+）
    """
    result = await scrcpy_service.list_cameras(device_serial)
    return result


@router.get("/encoders")
async def list_encoders(device_serial: str = None):
    """
    列出设备支持的编码器

    使用 scrcpy --list-encoders 命令
    """
    result = await scrcpy_service.list_encoders(device_serial)
    return result


# ============ 自定义 scrcpy 命令 ============


@router.post("/command", response_model=ScrcpyCommandResponse)
async def run_scrcpy_command(request: ScrcpyCommandRequest):
    """
    执行自定义 scrcpy 命令

    可以传入任意 scrcpy 命令行参数。参考文档: https://github.com/Genymobile/scrcpy

    示例参数:
    - ["--version"] - 获取版本
    - ["--list-displays", "-s", "device_serial"] - 列出特定设备的显示器
    - ["-s", "device_serial", "--record", "output.mp4", "--no-playback"] - 录制
    """
    result = await scrcpy_service.run_scrcpy_command(
        args=request.args,
        wait=request.wait,
        timeout=request.timeout,
    )
    return ScrcpyCommandResponse(**result)


# ============ WebSocket 实时视频流 ============


@router.websocket("/stream")
async def video_stream(websocket: WebSocket):
    """
    WebSocket 实时视频流

    使用真正的 scrcpy H.264 视频流，提供高性能的实时画面传输。
    当 scrcpy 流可用时，直接从视频流获取帧；否则回退到 adb screencap 模式。

    消息格式:
    - 帧数据: {"type": "frame", "image": "base64...", "width": 1080, "height": 1920, "fps": 30, "source": "scrcpy"|"adb"}
    - 错误: {"type": "error", "message": "错误信息"}
    - 状态: {"type": "status", "streaming": true/false, "interval": 33, "scrcpy_mode": true/false}

    客户端可发送:
    - {"action": "set_interval", "interval": 33}  设置帧间隔(毫秒)，最小8ms(约120fps)
    - {"action": "set_quality", "quality": 80}  设置 JPEG 质量 (1-100)
    - {"action": "pause"}  暂停推送
    - {"action": "resume"}  恢复推送
    - {"action": "stop"}  停止
    """
    await websocket.accept()

    if not scrcpy_service.is_connected:
        await websocket.send_json({"type": "error", "message": "设备未连接，请先调用 /connect 接口"})
        await websocket.close()
        return

    # 默认帧间隔 16ms（约60帧/秒）- scrcpy 模式下可以更快
    interval_ms = 16
    quality = 80
    is_paused = False
    is_streaming = True
    frame_count = 0
    fps_start_time = asyncio.get_event_loop().time()
    last_frame_hash = None  # 用于检测帧是否变化

    async def send_frame():
        """发送一帧画面"""
        nonlocal frame_count, fps_start_time, last_frame_hash

        try:
            frame = None
            source = "scrcpy"

            # 优先从 scrcpy 视频流获取帧
            if scrcpy_service.is_scrcpy_streaming:
                frame = scrcpy_service.get_latest_frame()
                if frame is None:
                    # 如果没有新帧，使用 last_frame
                    frame = scrcpy_service.last_frame

            # 如果 scrcpy 不可用或没有帧，回退到截图模式（视频流不需要原始分辨率）
            if frame is None:
                result = await scrcpy_service.capture_screen(quality=quality, use_original_resolution=False)
                if result.get("success") and result.get("image"):
                    # 计算 FPS
                    frame_count += 1
                    current_time = asyncio.get_event_loop().time()
                    elapsed = current_time - fps_start_time
                    fps = frame_count / elapsed if elapsed > 0 else 0

                    if elapsed > 5:
                        frame_count = 1
                        fps_start_time = current_time

                    await websocket.send_json(
                        {
                            "type": "frame",
                            "image": result["image"],
                            "width": result.get("width", 0),
                            "height": result.get("height", 0),
                            "size": result.get("size", 0),
                            "fps": round(fps, 1),
                            "source": result.get("source", "adb"),
                        }
                    )
                return

            # 编码帧为 JPEG
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            _, buffer = cv2.imencode(".jpg", frame, encode_param)
            image_base64 = base64.b64encode(buffer).decode("utf-8")

            # 计算 FPS
            frame_count += 1
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - fps_start_time
            fps = frame_count / elapsed if elapsed > 0 else 0

            # 每 5 秒重置计数器
            if elapsed > 5:
                frame_count = 1
                fps_start_time = current_time

            await websocket.send_json(
                {
                    "type": "frame",
                    "image": image_base64,
                    "width": frame.shape[1],
                    "height": frame.shape[0],
                    "size": len(buffer),
                    "fps": round(fps, 1),
                    "source": source,
                }
            )
        except Exception as e:
            await websocket.send_json({"type": "error", "message": f"帧获取失败: {str(e)}"})

    try:
        # 发送初始状态
        await websocket.send_json(
            {
                "type": "status",
                "streaming": True,
                "interval": interval_ms,
                "quality": quality,
                "scrcpy_mode": scrcpy_service.is_scrcpy_streaming,
            }
        )

        # 创建接收消息的任务
        async def receive_messages():
            nonlocal interval_ms, quality, is_paused, is_streaming
            while is_streaming:
                try:
                    data = await asyncio.wait_for(
                        websocket.receive_json(),
                        timeout=0.01,  # 10ms 超时，更快响应
                    )
                    action = data.get("action")

                    if action == "set_interval":
                        new_interval = data.get("interval", 16)
                        interval_ms = max(8, min(2000, new_interval))  # 最小 8ms (约120fps)
                        await websocket.send_json(
                            {
                                "type": "status",
                                "streaming": not is_paused,
                                "interval": interval_ms,
                                "quality": quality,
                                "scrcpy_mode": scrcpy_service.is_scrcpy_streaming,
                            }
                        )
                    elif action == "set_quality":
                        new_quality = data.get("quality", 80)
                        quality = max(1, min(100, new_quality))
                        await websocket.send_json(
                            {
                                "type": "status",
                                "streaming": not is_paused,
                                "interval": interval_ms,
                                "quality": quality,
                                "scrcpy_mode": scrcpy_service.is_scrcpy_streaming,
                            }
                        )
                    elif action == "pause":
                        is_paused = True
                        await websocket.send_json(
                            {
                                "type": "status",
                                "streaming": False,
                                "interval": interval_ms,
                                "quality": quality,
                                "scrcpy_mode": scrcpy_service.is_scrcpy_streaming,
                            }
                        )
                    elif action == "resume":
                        is_paused = False
                        await websocket.send_json(
                            {
                                "type": "status",
                                "streaming": True,
                                "interval": interval_ms,
                                "quality": quality,
                                "scrcpy_mode": scrcpy_service.is_scrcpy_streaming,
                            }
                        )
                    elif action == "stop":
                        is_streaming = False
                except TimeoutError:
                    pass
                except Exception:
                    break

        # 主循环：发送屏幕帧
        receive_task = asyncio.create_task(receive_messages())

        while is_streaming:
            if not is_paused and scrcpy_service.is_connected:
                await send_frame()
            await asyncio.sleep(interval_ms / 1000.0)

        receive_task.cancel()

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"流异常: {str(e)}",
                }
            )
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
