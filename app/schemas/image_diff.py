"""
图片差异检测 API 请求/响应模型
"""

from pydantic import BaseModel, Field


class DifferenceRegion(BaseModel):
    """单个差异区域信息"""

    index: int = Field(..., description="差异区域编号")
    x: int = Field(..., description="差异区域左上角 X 坐标")
    y: int = Field(..., description="差异区域左上角 Y 坐标")
    width: int = Field(..., description="差异区域宽度")
    height: int = Field(..., description="差异区域高度")


class ImageSize(BaseModel):
    """图片尺寸信息"""

    width: int = Field(..., description="图片宽度")
    height: int = Field(..., description="图片高度")


class DiffResponse(BaseModel):
    """差异检测响应（包含 base64 图片）"""

    difference_count: int = Field(..., description="检测到的差异数量")
    differences: list[DifferenceRegion] = Field(default_factory=list, description="差异区域列表")
    image_size: ImageSize = Field(..., description="处理后的图片尺寸")
    marked_image_base64: str | None = Field(None, description="标记后的拼接图片（base64 编码）")
    heatmap_base64: str | None = Field(None, description="差异热力图（base64 编码）")
    image1_base64: str | None = Field(None, description="标记后的图片1（base64 编码）")
    image2_base64: str | None = Field(None, description="标记后的图片2（base64 编码）")


class DiffMetaResponse(BaseModel):
    """差异检测响应（仅元数据，不包含图片）"""

    difference_count: int = Field(..., description="检测到的差异数量")
    differences: list[DifferenceRegion] = Field(default_factory=list, description="差异区域列表")
    image_size: ImageSize = Field(..., description="处理后的图片尺寸")


class SavedFiles(BaseModel):
    """保存的文件路径信息"""

    combined: str = Field(..., description="拼接结果图片路径")
    heatmap: str = Field(..., description="热力图路径")
    image1_marked: str = Field(..., description="标记后的图片1路径")
    image2_marked: str = Field(..., description="标记后的图片2路径")


class DiffSaveResponse(BaseModel):
    """差异检测响应（保存文件版本）"""

    difference_count: int = Field(..., description="检测到的差异数量")
    differences: list[DifferenceRegion] = Field(default_factory=list, description="差异区域列表")
    saved_files: SavedFiles = Field(..., description="保存的文件路径")


class HealthResponse(BaseModel):
    """健康检查响应"""

    status: str = Field(..., description="服务状态")
    version: str = Field(..., description="API 版本")
