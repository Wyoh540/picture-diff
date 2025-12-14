"""
Pydantic 数据模型
"""

from .image_diff import (
    DifferenceRegion,
    DiffMetaResponse,
    DiffResponse,
    DiffSaveResponse,
    HealthResponse,
    ImageSize,
    SavedFiles,
)

from .scrcpy import (
    ScrcpyConnectRequest,
    ScrcpyConnectResponse,
    ScrcpyStatusResponse,
    ScrcpyDevicesResponse,
    ScrcpyScreenshotResponse,
    ScrcpyControlResponse,
)

__all__ = [
    # Image diff
    "DifferenceRegion",
    "DiffMetaResponse",
    "DiffResponse",
    "DiffSaveResponse",
    "HealthResponse",
    "ImageSize",
    "SavedFiles",
    # Scrcpy
    "ScrcpyConnectRequest",
    "ScrcpyConnectResponse",
    "ScrcpyStatusResponse",
    "ScrcpyDevicesResponse",
    "ScrcpyScreenshotResponse",
    "ScrcpyControlResponse",
]
