"""
ADB 相关的 Pydantic 模型
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class AdbConnectRequest(BaseModel):
    """ADB 连接请求"""

    host: str = Field(..., description="设备 IP 地址")
    port: int = Field(default=5555, description="ADB 端口，默认 5555")


# ============ 输入控制相关 ============


class AdbTapRequest(BaseModel):
    """点击请求"""

    x: int = Field(..., description="点击 X 坐标")
    y: int = Field(..., description="点击 Y 坐标")


class AdbSwipeRequest(BaseModel):
    """滑动请求"""

    x1: int = Field(..., description="起始 X 坐标")
    y1: int = Field(..., description="起始 Y 坐标")
    x2: int = Field(..., description="结束 X 坐标")
    y2: int = Field(..., description="结束 Y 坐标")
    duration: int = Field(default=300, description="滑动持续时间（毫秒）")


class KeyCode(str, Enum):
    """常用 Android 按键代码"""

    HOME = "3"
    BACK = "4"
    CALL = "5"
    END_CALL = "6"
    VOLUME_UP = "24"
    VOLUME_DOWN = "25"
    POWER = "26"
    CAMERA = "27"
    MENU = "82"
    APP_SWITCH = "187"  # Recent apps
    ENTER = "66"
    DEL = "67"
    TAB = "61"
    ESCAPE = "111"
    DPAD_UP = "19"
    DPAD_DOWN = "20"
    DPAD_LEFT = "21"
    DPAD_RIGHT = "22"
    DPAD_CENTER = "23"


class AdbKeyEventRequest(BaseModel):
    """按键事件请求"""

    keycode: str = Field(..., description="Android 按键代码")


class AdbInputTextRequest(BaseModel):
    """文本输入请求"""

    text: str = Field(..., description="要输入的文本")


class AdbInputResponse(BaseModel):
    """输入操作响应"""

    success: bool
    message: Optional[str] = None


class AdbScreenInfoResponse(BaseModel):
    """屏幕信息响应"""

    success: bool
    message: Optional[str] = None
    width: Optional[int] = Field(default=None, description="屏幕宽度")
    height: Optional[int] = Field(default=None, description="屏幕高度")
    density: Optional[int] = Field(default=None, description="屏幕密度")


class AdbConnectResponse(BaseModel):
    """ADB 连接响应"""

    success: bool
    message: str
    address: Optional[str] = None


class AdbStatusResponse(BaseModel):
    """ADB 状态响应"""

    connected: bool
    address: Optional[str] = None


class AdbScreenshotResponse(BaseModel):
    """ADB 截图响应"""

    success: bool
    message: Optional[str] = None
    image: Optional[str] = Field(default=None, description="Base64 编码的 PNG 图片")
    size: Optional[int] = Field(default=None, description="图片大小（字节）")


class AdbDeviceInfo(BaseModel):
    """ADB 设备信息"""

    address: str = Field(..., description="设备地址")
    state: str = Field(..., description="设备状态")
    info: str = Field(default="", description="设备附加信息")


class AdbDevicesResponse(BaseModel):
    """ADB 设备列表响应"""

    success: bool
    message: Optional[str] = None
    devices: List[AdbDeviceInfo] = Field(default=[], description="设备列表")
