# 图片差异检测 API

一个用于找不同游戏的图片差异检测 FastAPI 服务。自动从游戏截图中提取上下两张图片，检测并标记差异区域。

## 功能特性

- 🔍 **自动提取**: 从游戏截图中自动提取上下两张待比较图片
- 🎯 **差异检测**: 精确检测两张图片的差异区域
- ⭕ **可视化标记**: 用圆圈标记差异位置，并添加编号
- 🌡️ **热力图生成**: 生成差异热力图，直观展示差异程度
- 📦 **多种输出格式**: 支持 Base64 返回或保存到本地文件

## 快速开始

### 环境要求

- Python 3.11+
- uv (推荐) 或 pip

### 安装依赖

```bash
# 使用 uv (推荐)
uv sync

# 或使用 pip
pip install -e .
```

### 启动服务

```bash
# 开发模式（热重载）
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 生产模式
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 访问文档

启动服务后，访问以下地址查看 API 文档：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API 接口

### 检测图片差异

**POST** `/api/v1/diff/detect`

上传游戏截图，返回差异检测结果（包含 Base64 编码的结果图片）。

```bash
curl -X POST "http://localhost:8000/api/v1/diff/detect" \
  -F "file=@screenshot.jpg" \
  -F "min_area=80" \
  -F "diff_threshold=35"
```

### 检测图片差异（仅元数据）

**POST** `/api/v1/diff/detect/meta`

上传游戏截图，仅返回差异区域的元数据信息。

```bash
curl -X POST "http://localhost:8000/api/v1/diff/detect/meta" \
  -F "file=@screenshot.jpg"
```

### 检测并保存结果

**POST** `/api/v1/diff/detect/save`

上传游戏截图，检测差异并将结果图片保存到指定目录。

```bash
curl -X POST "http://localhost:8000/api/v1/diff/detect/save" \
  -F "file=@screenshot.jpg" \
  -F "output_dir=./output" \
  -F "filename_prefix=result"
```

## 请求参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| file | File | - | 游戏截图文件（必填） |
| min_area | int | 80 | 最小差异区域面积 |
| diff_threshold | int | 35 | 差异阈值（越大越宽松） |
| output_dir | str | ./output | 输出目录（仅 save 接口） |
| filename_prefix | str | result | 文件名前缀（仅 save 接口） |

## 响应示例

```json
{
  "difference_count": 5,
  "differences": [
    {
      "index": 1,
      "x": 120,
      "y": 85,
      "width": 45,
      "height": 38
    }
  ],
  "image_size": {
    "width": 800,
    "height": 600
  },
  "marked_image_base64": "...",
  "heatmap_base64": "...",
  "image1_base64": "...",
  "image2_base64": "..."
}
```

## 项目结构

```
pic_diff/
├── app/
│   ├── __init__.py          # 应用初始化
│   ├── main.py               # FastAPI 入口
│   ├── routers/
│   │   ├── __init__.py
│   │   └── image_diff.py     # 差异检测路由
│   ├── schemas/
│   │   ├── __init__.py
│   │   └── image_diff.py     # Pydantic 数据模型
│   ├── services/
│   │   ├── __init__.py
│   │   └── image_diff.py     # 核心业务逻辑
│   └── utils/
│       └── __init__.py
├── pyproject.toml            # 项目配置
├── README.md
└── .gitignore
```

## 开发

### 安装开发依赖

```bash
uv sync --extra dev
```

### 代码格式化

```bash
uv run ruff format .
uv run ruff check --fix .
```

### 运行测试

```bash
uv run pytest
```

## License

MIT
