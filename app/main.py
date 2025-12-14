"""
FastAPI 应用入口
图片差异检测服务
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.routers import image_diff_router
from app.routers.adb import router as adb_router
from app.routers.scrcpy import router as scrcpy_router
from app.schemas import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    print(f"🚀 图片差异检测服务启动 v{__version__}")
    yield
    # 关闭时执行
    print("👋 服务关闭")


app = FastAPI(
    title="图片差异检测 API",
    description="""
## 功能说明

这是一个用于找不同游戏的图片差异检测 API 服务。

### 主要功能

- **图片差异检测**: 自动从游戏截图中提取上下两张图片，检测差异区域
- **差异标记**: 用圆圈标记差异位置，并生成可视化结果
- **热力图生成**: 生成差异热力图，直观展示差异程度

### 使用方式

1. 上传一张包含上下两张待比较图片的游戏截图
2. 系统自动提取并对比两张图片
3. 返回差异区域信息和标记后的图片
    """,
    version=__version__,
    lifespan=lifespan,
)

# CORS 中间件配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(image_diff_router)
app.include_router(adb_router)
app.include_router(scrcpy_router)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["系统"],
    summary="健康检查",
)
def health_check() -> HealthResponse:
    """检查服务健康状态"""
    return HealthResponse(status="healthy", version=__version__)


@app.get(
    "/",
    tags=["系统"],
    summary="API 根路径",
)
def root():
    """API 根路径，返回服务基本信息"""
    return {
        "name": "图片差异检测 API",
        "version": __version__,
        "docs": "/docs",
        "redoc": "/redoc",
    }
