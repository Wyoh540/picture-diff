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

__all__ = [
    "DifferenceRegion",
    "DiffMetaResponse",
    "DiffResponse",
    "DiffSaveResponse",
    "HealthResponse",
    "ImageSize",
    "SavedFiles",
]
