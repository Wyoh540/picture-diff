"""
Scrcpy 相关的 Pydantic 模型
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


# ============ 连接相关 ============


class ScrcpyConnectRequest(BaseModel):
    """Scrcpy 连接请求"""

    device_serial: Optional[str] = Field(default=None, description="设备序列号，不填则使用第一个设备")
    max_width: int = Field(default=1920, ge=100, le=4096, description="最大视频宽度（1920=1080p），降低可减少 CPU 使用")
    bitrate: int = Field(default=8_000_000, ge=100_000, le=50_000_000, description="视频比特率 (bps)，高分辨率建议8Mbps以上")
    max_fps: int = Field(default=60, ge=1, le=120, description="最大帧率")


class AdbConnectRequest(BaseModel):
    """ADB 远程连接请求"""

    host: str = Field(..., description="设备 IP 地址")
    port: int = Field(default=5555, ge=1, le=65535, description="ADB 端口")


class DeviceInfoResponse(BaseModel):
    """设备信息"""

    serial: Optional[str] = None
    name: Optional[str] = None
    resolution: Optional[tuple[int, int]] = None


class ScrcpyConnectResponse(BaseModel):
    """Scrcpy 连接响应"""

    success: bool
    message: str
    device: Optional[DeviceInfoResponse] = None


class ScrcpyStatusResponse(BaseModel):
    """Scrcpy 状态响应"""

    connected: bool
    streaming: bool
    device: Optional[DeviceInfoResponse] = None
    config: Optional[dict] = None


class ScrcpyDeviceInfo(BaseModel):
    """设备信息"""

    serial: str
    state: str = "device"


class ScrcpyDevicesResponse(BaseModel):
    """设备列表响应"""

    success: bool
    message: Optional[str] = None
    devices: List[ScrcpyDeviceInfo] = Field(default_factory=list)


# ============ 截图相关 ============


class ScrcpyScreenshotRequest(BaseModel):
    """截图请求"""

    quality: int = Field(default=80, ge=1, le=100, description="JPEG 压缩质量 (1-100)")
    use_original_resolution: bool = Field(
        default=True, description="使用设备原始分辨率（通过 adb screencap），否则使用 scrcpy 流帧"
    )


class ScrcpyScreenshotResponse(BaseModel):
    """截图响应"""

    success: bool
    message: Optional[str] = None
    image: Optional[str] = Field(default=None, description="Base64 编码的 JPEG 图片")
    size: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    format: Optional[str] = None


# ============ 控制相关 ============


class ScrcpyControlResponse(BaseModel):
    """控制操作响应"""

    success: bool
    message: Optional[str] = None


class ScrcpyClipboardResponse(BaseModel):
    """剪贴板响应"""

    success: bool
    message: Optional[str] = None
    text: Optional[str] = None


# ============ 录制相关 ============


class VideoCodec(str, Enum):
    """视频编解码器"""

    H264 = "h264"
    H265 = "h265"
    AV1 = "av1"


class ScrcpyRecordingRequest(BaseModel):
    """录制请求"""

    output_file: str = Field(..., description="输出文件路径（如 recording.mp4）")
    device_serial: Optional[str] = Field(default=None, description="设备序列号")
    max_size: int = Field(default=0, ge=0, le=4096, description="最大尺寸（0 表示不限制）")
    max_fps: int = Field(default=0, ge=0, le=120, description="最大帧率（0 表示不限制）")
    video_codec: VideoCodec = Field(default=VideoCodec.H264, description="视频编解码器")
    audio: bool = Field(default=True, description="是否录制音频")
    no_playback: bool = Field(default=True, description="是否禁用画面显示（仅录制）")


class ScrcpyRecordingResponse(BaseModel):
    """录制响应"""

    success: bool
    message: Optional[str] = None
    output_file: Optional[str] = None
    pid: Optional[int] = None
    command: Optional[str] = None


class ScrcpyRecordingStatusResponse(BaseModel):
    """录制状态响应"""

    is_recording: bool
    recording_file: Optional[str] = None
    pid: Optional[int] = None


class ScrcpyInstallationResponse(BaseModel):
    """Scrcpy 安装检查响应"""

    scrcpy_dir: str
    scrcpy_dir_exists: bool
    scrcpy_exe: str
    scrcpy_exe_exists: bool
    scrcpy_server: str
    scrcpy_server_exists: bool
    adb_exe: str
    adb_exe_exists: bool
    version: str


class ScrcpyCommandRequest(BaseModel):
    """自定义 scrcpy 命令请求"""

    args: List[str] = Field(..., description="scrcpy 命令行参数列表")
    wait: bool = Field(default=True, description="是否等待命令完成")
    timeout: float = Field(default=30.0, ge=1.0, le=300.0, description="超时时间（秒）")


class ScrcpyCommandResponse(BaseModel):
    """自定义 scrcpy 命令响应"""

    success: bool
    message: Optional[str] = None
    return_code: Optional[int] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None
    pid: Optional[int] = None
    command: Optional[str] = None
