"""
图片差异检测核心服务
提供游戏截图的差异检测功能
"""

import cv2
import numpy as np
from pathlib import Path
import base64
from typing import Optional


def load_image_from_bytes(image_bytes: bytes) -> np.ndarray:
    """从字节数据加载图片"""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("无法解码图片数据")
    return img


def load_image_from_path(image_path: str) -> np.ndarray:
    """从文件路径加载图片"""
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"无法加载图片: {image_path}")
    return img


def image_to_base64(img: np.ndarray, format: str = ".png") -> str:
    """将图片转换为 base64 字符串"""
    _, buffer = cv2.imencode(format, img)
    return base64.b64encode(buffer).decode("utf-8")


def extract_game_images(screenshot: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    从游戏截图中提取上下两张待比较的图片。

    算法原理：
    - 游戏"找不同"截图通常包含上下两张图片，中间有分隔区域
    - 通过分析每一行像素的颜色方差来区分"内容区域"和"空白/分隔区域"
    - 内容区域（图片）的颜色方差较高，空白区域的方差较低

    Args:
        screenshot: 输入的游戏截图，BGR格式的numpy数组

    Returns:
        tuple: (上半部分图片, 下半部分图片)
    """
    height, width = screenshot.shape[:2]

    # ========== 第一步：计算每行的颜色方差 ==========
    # 对于每一行，计算该行所有像素的标准差
    # 标准差高表示该行颜色变化丰富（有实际图像内容）
    # 标准差低表示该行颜色单一（可能是空白区域或纯色分隔线）
    row_variance = np.array([np.std(screenshot[y, :, :]) for y in range(height)])

    # ========== 第二步：平滑方差曲线 ==========
    # 使用滑动窗口平均来平滑方差曲线，消除噪声和局部波动
    # kernel_size=5 表示使用5行的窗口进行平均
    kernel_size = 5
    row_variance_smooth = np.convolve(row_variance, np.ones(kernel_size) / kernel_size, mode="same")

    # ========== 第三步：确定方差阈值 ==========
    # 计算平均方差，并取其60%作为阈值
    # 高于阈值的行被认为是"内容区域"，低于阈值的是"空白区域"
    mean_var = np.mean(row_variance_smooth)
    var_threshold = mean_var * 0.6

    # ========== 第四步：识别所有内容区域 ==========
    # 通过状态机的方式扫描每一行，找出连续的高方差区域
    content_regions = []  # 存储找到的内容区域，格式为 (起始行, 结束行)
    in_content = False  # 标记当前是否在内容区域内
    content_start = 0  # 当前内容区域的起始行

    for y in range(height):
        is_content = row_variance_smooth[y] > var_threshold

        if is_content and not in_content:
            # 从空白区域进入内容区域：记录起始位置
            in_content = True
            content_start = y
        elif not is_content and in_content:
            # 从内容区域进入空白区域：结束当前区域
            in_content = False
            region_height = y - content_start
            # 只保留高度超过总高度15%的区域，过滤掉小的噪声区域
            if region_height > height * 0.15:
                content_regions.append((content_start, y))

    # 处理扫描结束时仍在内容区域的情况
    if in_content:
        region_height = height - content_start
        if region_height > height * 0.15:
            content_regions.append((content_start, height))

    # ========== 第五步：根据检测结果确定两张图片的区域 ==========
    if len(content_regions) >= 2:
        # 情况1：检测到两个或更多内容区域
        # 选择最大的两个区域作为上下两张图片
        content_regions.sort(key=lambda r: r[1] - r[0], reverse=True)  # 按区域大小降序排列
        regions = content_regions[:2]  # 取最大的两个
        regions.sort(key=lambda r: r[0])  # 按位置升序排列（上面的在前）
        region1, region2 = regions

    elif len(content_regions) == 1:
        # 情况2：只检测到一个连续的内容区域
        # 说明两张图片紧密相连，需要在中间找到分割点
        region = content_regions[0]
        region_start, region_end = region
        region_height = region_end - region_start

        # 在区域的中间35%-65%范围内寻找分割点
        # 分割点通常是两张图片之间的间隙，方差最低的位置
        mid_start = region_start + int(region_height * 0.35)
        mid_end = region_start + int(region_height * 0.65)

        # 找到中间区域方差最小的位置作为分割点
        mid_variance = row_variance_smooth[mid_start:mid_end]
        split_offset = np.argmin(mid_variance)
        split_row = mid_start + split_offset

        # 扩展分割区域：从分割点向两边扩展，找到完整的低方差分隔带
        split_threshold = row_variance_smooth[split_row] * 1.5
        split_start = split_row
        split_end = split_row

        # 向上扩展分割区域
        for y in range(split_row, mid_start, -1):
            if row_variance_smooth[y] < split_threshold:
                split_start = y
            else:
                break

        # 向下扩展分割区域
        for y in range(split_row, mid_end):
            if row_variance_smooth[y] < split_threshold:
                split_end = y
            else:
                break

        # 上半图片：从区域开始到分割区域的上边界
        # 下半图片：从分割区域的下边界到区域结束
        region1 = (region_start, split_start)
        region2 = (split_end, region_end)

    else:
        # 情况3：未检测到明显的内容区域（异常情况）
        # 使用默认的固定比例进行分割
        # 假设上半图片在17%-48%的高度范围，下半图片在52%-83%的高度范围
        region1 = (int(height * 0.17), int(height * 0.48))
        region2 = (int(height * 0.52), int(height * 0.83))

    # ========== 第六步：提取并处理图片区域 ==========
    # 根据计算出的区域范围裁剪图片
    img1_region = screenshot[region1[0] : region1[1], :]
    img2_region = screenshot[region2[0] : region2[1], :]

    # 裁剪图片周围的白色边框，得到干净的图片内容
    img1 = crop_white_borders(img1_region)
    img2 = crop_white_borders(img2_region)

    return img1, img2


def crop_white_borders(img: np.ndarray, threshold: int = 235, h_margin: int = 30) -> np.ndarray:
    """
    精确裁剪白色边框
    h_margin: 水平方向额外裁剪的边缘像素数
    """
    if img.size == 0:
        return img

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # 上边界
    top = 0
    for y in range(min(50, h)):
        start_x, end_x = w // 10, w - w // 10
        row_mean = np.mean(gray[y, start_x:end_x])
        if row_mean < threshold:
            top = y
            break

    # 下边界
    bottom = h
    for y in range(h - 1, max(h - 50, -1), -1):
        start_x, end_x = w // 10, w - w // 10
        row_mean = np.mean(gray[y, start_x:end_x])
        if row_mean < threshold:
            bottom = y + 1
            break

    # 左边界
    left = 0
    for x in range(min(50, w)):
        start_y, end_y = h // 10, h - h // 10
        col_mean = np.mean(gray[start_y:end_y, x])
        if col_mean < threshold:
            left = x
            break

    # 右边界
    right = w
    for x in range(w - 1, max(w - 50, -1), -1):
        start_y, end_y = h // 10, h - h // 10
        col_mean = np.mean(gray[start_y:end_y, x])
        if col_mean < threshold:
            right = x + 1
            break

    # 安全边距（垂直方向）
    margin = 5
    top = min(top + margin, h - 1)

    # 水平方向额外裁剪边缘
    left = min(left + h_margin, w - 1)
    right = max(right - h_margin, left + 1)
    bottom = max(bottom - margin, top + 1)
    left = min(left + margin, w - 1)
    right = max(right - margin, left + 1)

    return img[top:bottom, left:right]


def align_images(img1: np.ndarray, img2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """对齐两张图片"""
    h1, w1 = img1.shape[:2]
    h2, w2 = img2.shape[:2]

    min_h = min(h1, h2)
    min_w = min(w1, w2)

    def center_crop(img, target_h, target_w):
        h, w = img.shape[:2]
        start_h = (h - target_h) // 2
        start_w = (w - target_w) // 2
        return img[start_h : start_h + target_h, start_w : start_w + target_w]

    return center_crop(img1, min_h, min_w), center_crop(img2, min_h, min_w)


def find_differences(
    img1: np.ndarray,
    img2: np.ndarray,
    min_area: int = 100,
    diff_threshold: int = 30,
) -> list[tuple[int, int, int, int]]:
    """
    找出两张图片的差异区域
    使用更精确的检测方法，过滤边缘和噪声
    """
    img1, img2 = align_images(img1, img2)

    # 计算差异
    diff = cv2.absdiff(img1, img2)

    # 转为灰度
    gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)

    # 使用更强的模糊来减少噪声
    blurred = cv2.GaussianBlur(gray_diff, (7, 7), 0)

    # 二值化 - 使用较高的阈值过滤微小差异
    _, thresh = cv2.threshold(blurred, diff_threshold, 255, cv2.THRESH_BINARY)

    # 去除边缘区域的误检（边缘20像素）
    edge_margin = 20
    thresh[:edge_margin, :] = 0
    thresh[-edge_margin:, :] = 0
    thresh[:, :edge_margin] = 0
    thresh[:, -edge_margin:] = 0

    # 形态学操作：先腐蚀去除噪点，再膨胀连接区域
    kernel_small = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    kernel_big = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))

    # 先腐蚀去除小噪点
    thresh = cv2.erode(thresh, kernel_small, iterations=1)
    # 再膨胀连接相近区域
    thresh = cv2.dilate(thresh, kernel_big, iterations=3)
    # 腐蚀回来一点
    thresh = cv2.erode(thresh, kernel_small, iterations=2)

    # 找轮廓
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    differences = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area >= min_area:
            x, y, w, h = cv2.boundingRect(contour)
            # 过滤太大的区域（可能是误检）
            if w < img1.shape[1] * 0.8 and h < img1.shape[0] * 0.8:
                differences.append((x, y, w, h))

    # 合并重叠区域
    differences = merge_overlapping_regions(differences)

    return differences


def merge_overlapping_regions(regions: list, padding: int = 20) -> list:
    """合并重叠区域"""
    if not regions:
        return []

    expanded = [(x - padding, y - padding, w + 2 * padding, h + 2 * padding) for x, y, w, h in regions]

    merged = list(expanded)
    changed = True

    while changed:
        changed = False
        new_merged = []
        used = [False] * len(merged)

        for i in range(len(merged)):
            if used[i]:
                continue

            x1, y1, w1, h1 = merged[i]

            for j in range(i + 1, len(merged)):
                if used[j]:
                    continue

                x2, y2, w2, h2 = merged[j]

                if x1 < x2 + w2 and x1 + w1 > x2 and y1 < y2 + h2 and y1 + h1 > y2:
                    x1 = min(x1, x2)
                    y1 = min(y1, y2)
                    w1 = max(x1 + w1, x2 + w2) - x1
                    h1 = max(y1 + h1, y2 + h2) - y1
                    used[j] = True
                    changed = True

            new_merged.append((x1, y1, w1, h1))
            used[i] = True

        merged = new_merged

    return [(x + padding, y + padding, w - 2 * padding, h - 2 * padding) for x, y, w, h in merged]


def draw_differences(
    img: np.ndarray,
    differences: list,
    color: tuple = (0, 0, 255),
    thickness: int = 3,
    aspect_ratio_threshold: float = 0.6,
) -> np.ndarray:
    """
    标记差异区域
    根据差异区域的形状选择使用圆圈或矩形：
    - 接近正方形的区域（宽高比在 threshold ~ 1/threshold 之间）使用圆圈
    - 细长形状的区域使用矩形

    Args:
        img: 输入图片
        differences: 差异区域列表 [(x, y, w, h), ...]
        color: 标记颜色
        thickness: 线条粗细
        aspect_ratio_threshold: 宽高比阈值，低于此值使用矩形
    """
    result = img.copy()
    padding = 15  # 标记框与差异区域的边距

    for i, (x, y, w, h) in enumerate(differences):
        center_x = x + w // 2
        center_y = y + h // 2

        # 计算宽高比，判断使用圆圈还是矩形
        aspect_ratio = min(w, h) / max(w, h) if max(w, h) > 0 else 1

        if aspect_ratio >= aspect_ratio_threshold:
            # 接近正方形，使用圆圈
            radius = max(w, h) // 2 + padding

            # 确保圆圈在图片范围内
            radius = min(
                radius,
                min(
                    center_x,
                    center_y,
                    result.shape[1] - center_x,
                    result.shape[0] - center_y,
                )
                - 5,
            )
            radius = max(radius, 20)

            cv2.circle(result, (center_x, center_y), radius, color, thickness)
            text_y = max(20, center_y - radius - 8)
        else:
            # 细长形状，使用矩形
            rect_x1 = max(0, x - padding)
            rect_y1 = max(0, y - padding)
            rect_x2 = min(result.shape[1] - 1, x + w + padding)
            rect_y2 = min(result.shape[0] - 1, y + h + padding)

            cv2.rectangle(result, (rect_x1, rect_y1), (rect_x2, rect_y2), color, thickness)
            text_y = max(20, rect_y1 - 8)

        # 绘制序号标签
        font = cv2.FONT_HERSHEY_SIMPLEX
        text = str(i + 1)
        text_size = cv2.getTextSize(text, font, 0.7, 2)[0]
        text_x = max(5, center_x - text_size[0] // 2)
        cv2.putText(result, text, (text_x, text_y), font, 0.7, color, 2)

    return result


def generate_heatmap(img1: np.ndarray, img2: np.ndarray) -> np.ndarray:
    """生成差异热力图"""
    img1_aligned, img2_aligned = align_images(img1, img2)
    diff = cv2.absdiff(img1_aligned, img2_aligned)
    gray_diff = cv2.cvtColor(diff, cv2.COLOR_BGR2GRAY)
    gray_diff = cv2.normalize(gray_diff, None, 0, 255, cv2.NORM_MINMAX)
    heatmap = cv2.applyColorMap(gray_diff, cv2.COLORMAP_JET)
    return heatmap


def process_screenshot(
    image_bytes: bytes,
    min_area: int = 80,
    diff_threshold: int = 35,
    return_images: bool = True,
) -> dict:
    """
    处理游戏截图，返回差异检测结果

    Args:
        image_bytes: 图片字节数据
        min_area: 最小差异区域面积
        diff_threshold: 差异阈值
        return_images: 是否返回结果图片的 base64

    Returns:
        包含差异信息和可选结果图片的字典
    """
    # 加载图片
    screenshot = load_image_from_bytes(image_bytes)

    # 提取游戏图片区域
    img1, img2 = extract_game_images(screenshot)

    # 检测差异
    differences = find_differences(img1, img2, min_area=min_area, diff_threshold=diff_threshold)

    # 对齐图片
    img1_aligned, img2_aligned = align_images(img1, img2)

    result = {
        "difference_count": len(differences),
        "differences": [{"index": i + 1, "x": x, "y": y, "width": w, "height": h} for i, (x, y, w, h) in enumerate(differences)],
        "image_size": {"width": img1_aligned.shape[1], "height": img1_aligned.shape[0]},
    }

    if return_images:
        # 标记差异
        marked_img1 = draw_differences(img1_aligned, differences, color=(0, 0, 255), thickness=3)
        marked_img2 = draw_differences(img2_aligned, differences, color=(0, 255, 0), thickness=3)

        # 拼接结果
        combined = np.hstack([marked_img1, marked_img2])

        # 生成热力图
        heatmap = generate_heatmap(img1, img2)

        result["marked_image_base64"] = image_to_base64(combined)
        result["heatmap_base64"] = image_to_base64(heatmap)
        result["image1_base64"] = image_to_base64(marked_img1)
        result["image2_base64"] = image_to_base64(marked_img2)

    return result


def save_result_images(
    image_bytes: bytes,
    output_dir: str,
    filename_prefix: str = "result",
    min_area: int = 80,
    diff_threshold: int = 35,
) -> dict:
    """
    处理截图并保存结果图片到指定目录

    Returns:
        包含保存路径的字典
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 加载和处理图片
    screenshot = load_image_from_bytes(image_bytes)
    img1, img2 = extract_game_images(screenshot)
    differences = find_differences(img1, img2, min_area=min_area, diff_threshold=diff_threshold)

    img1_aligned, img2_aligned = align_images(img1, img2)
    marked_img1 = draw_differences(img1_aligned, differences, color=(0, 0, 255), thickness=3)
    marked_img2 = draw_differences(img2_aligned, differences, color=(0, 255, 0), thickness=3)
    combined = np.hstack([marked_img1, marked_img2])
    heatmap = generate_heatmap(img1, img2)

    # 保存文件
    combined_path = output_path / f"{filename_prefix}_combined.png"
    heatmap_path = output_path / f"{filename_prefix}_heatmap.png"
    img1_path = output_path / f"{filename_prefix}_img1_marked.png"
    img2_path = output_path / f"{filename_prefix}_img2_marked.png"

    cv2.imwrite(str(combined_path), combined)
    cv2.imwrite(str(heatmap_path), heatmap)
    cv2.imwrite(str(img1_path), marked_img1)
    cv2.imwrite(str(img2_path), marked_img2)

    return {
        "difference_count": len(differences),
        "differences": [{"index": i + 1, "x": x, "y": y, "width": w, "height": h} for i, (x, y, w, h) in enumerate(differences)],
        "saved_files": {
            "combined": str(combined_path),
            "heatmap": str(heatmap_path),
            "image1_marked": str(img1_path),
            "image2_marked": str(img2_path),
        },
    }
