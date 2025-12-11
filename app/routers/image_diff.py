"""
图片差异检测 API 路由
"""

from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.schemas.image_diff import DiffMetaResponse, DiffResponse, DiffSaveResponse
from app.services.image_diff import process_screenshot, save_result_images

router = APIRouter(prefix="/api/v1/diff", tags=["图片差异检测"])


@router.post(
    "/detect",
    response_model=DiffResponse,
    summary="检测图片差异",
    description="上传游戏截图，自动提取上下两张图片并检测差异区域，返回标记后的图片（base64 编码）",
)
async def detect_differences(
    file: Annotated[UploadFile, File(description="游戏截图文件")],
    min_area: Annotated[int, Form(description="最小差异区域面积")] = 80,
    diff_threshold: Annotated[int, Form(description="差异阈值")] = 35,
) -> DiffResponse:
    """检测图片差异并返回 base64 编码的结果图片"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传有效的图片文件")

    try:
        image_bytes = await file.read()
        result = process_screenshot(
            image_bytes=image_bytes,
            min_area=min_area,
            diff_threshold=diff_threshold,
            return_images=True,
        )
        return DiffResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理图片时发生错误: {str(e)}")


@router.post(
    "/detect/meta",
    response_model=DiffMetaResponse,
    summary="检测图片差异（仅元数据）",
    description="上传游戏截图，仅返回差异区域的元数据，不返回图片",
)
async def detect_differences_meta(
    file: Annotated[UploadFile, File(description="游戏截图文件")],
    min_area: Annotated[int, Form(description="最小差异区域面积")] = 80,
    diff_threshold: Annotated[int, Form(description="差异阈值")] = 35,
) -> DiffMetaResponse:
    """检测图片差异，仅返回元数据"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传有效的图片文件")

    try:
        image_bytes = await file.read()
        result = process_screenshot(
            image_bytes=image_bytes,
            min_area=min_area,
            diff_threshold=diff_threshold,
            return_images=False,
        )
        return DiffMetaResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理图片时发生错误: {str(e)}")


@router.post(
    "/detect/save",
    response_model=DiffSaveResponse,
    summary="检测图片差异并保存结果",
    description="上传游戏截图，检测差异并将结果图片保存到指定目录",
)
async def detect_and_save(
    file: Annotated[UploadFile, File(description="游戏截图文件")],
    output_dir: Annotated[str, Form(description="输出目录路径")] = "./output",
    filename_prefix: Annotated[str, Form(description="文件名前缀")] = "result",
    min_area: Annotated[int, Form(description="最小差异区域面积")] = 80,
    diff_threshold: Annotated[int, Form(description="差异阈值")] = 35,
) -> DiffSaveResponse:
    """检测图片差异并保存结果到指定目录"""
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="请上传有效的图片文件")

    try:
        image_bytes = await file.read()
        result = save_result_images(
            image_bytes=image_bytes,
            output_dir=output_dir,
            filename_prefix=filename_prefix,
            min_area=min_area,
            diff_threshold=diff_threshold,
        )
        return DiffSaveResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理图片时发生错误: {str(e)}")
