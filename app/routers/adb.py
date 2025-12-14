"""
ADB 路由 - 处理无线调试相关的 API
"""

import asyncio
import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..schemas.adb import (
    AdbConnectRequest,
    AdbConnectResponse,
    AdbStatusResponse,
    AdbScreenshotResponse,
    AdbDevicesResponse,
    AdbTapRequest,
    AdbSwipeRequest,
    AdbKeyEventRequest,
    AdbInputTextRequest,
    AdbInputResponse,
    AdbScreenInfoResponse,
)
from ..services.adb_service import adb_service

router = APIRouter(prefix="/api/v1/adb", tags=["ADB"])


@router.post("/connect", response_model=AdbConnectResponse)
async def connect_device(request: AdbConnectRequest):
    """连接到 ADB 设备（无线调试）"""
    result = await adb_service.connect(request.host, request.port)
    return AdbConnectResponse(**result)


@router.post("/disconnect", response_model=AdbConnectResponse)
async def disconnect_device():
    """断开 ADB 连接"""
    result = await adb_service.disconnect()
    return AdbConnectResponse(**result)


@router.get("/status", response_model=AdbStatusResponse)
async def get_status():
    """获取 ADB 连接状态"""
    return AdbStatusResponse(**adb_service.get_status())


@router.get("/screenshot", response_model=AdbScreenshotResponse)
async def capture_screenshot():
    """截取设备屏幕"""
    result = await adb_service.capture_screen()
    return AdbScreenshotResponse(**result)


@router.get("/devices", response_model=AdbDevicesResponse)
async def get_devices():
    """获取已连接的设备列表"""
    result = await adb_service.get_devices()
    return AdbDevicesResponse(**result)


@router.get("/screen-info", response_model=AdbScreenInfoResponse)
async def get_screen_info():
    """获取设备屏幕分辨率信息"""
    result = await adb_service.get_screen_info()
    return AdbScreenInfoResponse(**result)


@router.post("/input/tap", response_model=AdbInputResponse)
async def input_tap(request: AdbTapRequest):
    """模拟点击操作"""
    result = await adb_service.input_tap(request.x, request.y)
    return AdbInputResponse(**result)


@router.post("/input/swipe", response_model=AdbInputResponse)
async def input_swipe(request: AdbSwipeRequest):
    """模拟滑动操作"""
    result = await adb_service.input_swipe(request.x1, request.y1, request.x2, request.y2, request.duration)
    return AdbInputResponse(**result)


@router.post("/input/keyevent", response_model=AdbInputResponse)
async def input_keyevent(request: AdbKeyEventRequest):
    """模拟按键操作"""
    result = await adb_service.input_keyevent(request.keycode)
    return AdbInputResponse(**result)


@router.post("/input/text", response_model=AdbInputResponse)
async def input_text(request: AdbInputTextRequest):
    """输入文本"""
    result = await adb_service.input_text(request.text)
    return AdbInputResponse(**result)


@router.websocket("/stream")
async def screen_stream(websocket: WebSocket):
    """
    WebSocket 实时屏幕流
    客户端连接后，持续推送屏幕截图

    消息格式:
    - 成功: {"type": "frame", "image": "base64...", "size": 12345, "fps": 5.2}
    - 错误: {"type": "error", "message": "错误信息"}
    - 状态: {"type": "status", "streaming": true/false}

    客户端可发送:
    - {"action": "set_interval", "interval": 200}  设置截图间隔(毫秒)，最小100ms
    - {"action": "pause"}  暂停推送
    - {"action": "resume"}  恢复推送
    """
    await websocket.accept()

    # 默认截图间隔 200ms（约5帧/秒）
    interval_ms = 200
    is_paused = False
    is_streaming = True
    frame_count = 0
    fps_start_time = asyncio.get_event_loop().time()

    async def send_frame():
        """发送一帧画面"""
        nonlocal frame_count, fps_start_time

        result = await adb_service.capture_screen()

        if result.get("success") and result.get("image"):
            # 计算 FPS
            frame_count += 1
            current_time = asyncio.get_event_loop().time()
            elapsed = current_time - fps_start_time
            fps = frame_count / elapsed if elapsed > 0 else 0

            # 每5秒重置计数器
            if elapsed > 5:
                frame_count = 1
                fps_start_time = current_time

            await websocket.send_json(
                {
                    "type": "frame",
                    "image": result["image"],
                    "size": result.get("size", 0),
                    "fps": round(fps, 1),
                }
            )
        else:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": result.get("message", "截图失败"),
                }
            )

    try:
        # 发送初始状态
        await websocket.send_json(
            {
                "type": "status",
                "streaming": True,
                "interval": interval_ms,
            }
        )

        # 创建接收消息的任务
        async def receive_messages():
            nonlocal interval_ms, is_paused, is_streaming
            while is_streaming:
                try:
                    data = await asyncio.wait_for(
                        websocket.receive_json(),
                        timeout=0.05,  # 50ms 超时
                    )
                    action = data.get("action")

                    if action == "set_interval":
                        new_interval = data.get("interval", 200)
                        interval_ms = max(15, min(2000, new_interval))  # 限制在15ms-2000ms，支持60帧
                        await websocket.send_json(
                            {
                                "type": "status",
                                "streaming": not is_paused,
                                "interval": interval_ms,
                            }
                        )
                    elif action == "pause":
                        is_paused = True
                        await websocket.send_json(
                            {
                                "type": "status",
                                "streaming": False,
                                "interval": interval_ms,
                            }
                        )
                    elif action == "resume":
                        is_paused = False
                        await websocket.send_json(
                            {
                                "type": "status",
                                "streaming": True,
                                "interval": interval_ms,
                            }
                        )
                    elif action == "stop":
                        is_streaming = False
                except asyncio.TimeoutError:
                    pass
                except Exception:
                    break

        # 主循环：发送屏幕帧
        receive_task = asyncio.create_task(receive_messages())

        while is_streaming:
            if not is_paused:
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
