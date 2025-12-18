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
    - 使用边缘检测来精确定位图片边界

    Args:
        screenshot: 输入的游戏截图，BGR格式的numpy数组

    Returns:
        tuple: (上半部分图片, 下半部分图片)
    """
    height, width = screenshot.shape[:2]

    # ========== 第一步：使用边缘检测找到水平边界线 ==========
    # 计算每行与下一行之间的颜色差异（垂直梯度）
    gray = cv2.cvtColor(screenshot, cv2.COLOR_BGR2GRAY)

    # 计算垂直方向的Sobel梯度
    sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    # 计算每行的梯度绝对值之和（水平边缘强度）
    row_edge_strength = np.sum(np.abs(sobel_y), axis=1)

    # 平滑边缘强度曲线
    kernel_size = 3
    row_edge_smooth = np.convolve(row_edge_strength, np.ones(kernel_size) / kernel_size, mode="same")

    # ========== 第二步：计算每行的颜色方差 ==========
    row_variance = np.array([np.std(screenshot[y, :, :]) for y in range(height)])
    kernel_size = 5
    row_variance_smooth = np.convolve(row_variance, np.ones(kernel_size) / kernel_size, mode="same")

    # ========== 第三步：确定方差阈值 ==========
    mean_var = np.mean(row_variance_smooth)
    var_threshold = mean_var * 0.6

    # ========== 第四步：识别所有内容区域 ==========
    content_regions = []
    in_content = False
    content_start = 0

    for y in range(height):
        is_content = row_variance_smooth[y] > var_threshold

        if is_content and not in_content:
            in_content = True
            content_start = y
        elif not is_content and in_content:
            in_content = False
            region_height = y - content_start
            if region_height > height * 0.15:
                content_regions.append((content_start, y))

    if in_content:
        region_height = height - content_start
        if region_height > height * 0.15:
            content_regions.append((content_start, height))

    # ========== 第五步：根据检测结果确定两张图片的区域 ==========
    if len(content_regions) >= 2:
        # 情况1：检测到两个或更多内容区域
        # 策略：找到高度最接近的两个区域（游戏图片通常高度相同）
        # 同时这两个区域应该是相邻的（排除UI区域）

        if len(content_regions) == 2:
            # 只有两个区域，直接使用
            regions = sorted(content_regions, key=lambda r: r[0])
            region1, region2 = regions
        else:
            # 有3个或更多区域，需要智能选择
            # 计算每个区域的高度
            region_heights = [(r, r[1] - r[0]) for r in content_regions]

            # 找到高度最接近的相邻区域对
            best_pair = None
            best_height_diff = float("inf")

            # 按位置排序
            sorted_regions = sorted(content_regions, key=lambda r: r[0])

            for i in range(len(sorted_regions) - 1):
                r1 = sorted_regions[i]
                r2 = sorted_regions[i + 1]
                h1 = r1[1] - r1[0]
                h2 = r2[1] - r2[0]
                height_diff = abs(h1 - h2)

                # 优先选择高度相近的相邻区域
                if height_diff < best_height_diff:
                    best_height_diff = height_diff
                    best_pair = (r1, r2)

            if best_pair:
                region1, region2 = best_pair
            else:
                # 回退：选择最大的两个
                content_regions.sort(key=lambda r: r[1] - r[0], reverse=True)
                regions = content_regions[:2]
                regions.sort(key=lambda r: r[0])
                region1, region2 = regions

    elif len(content_regions) == 1:
        # 情况2：只检测到一个连续的内容区域
        # 说明两张图片紧密相连，需要在中间找到分割点
        region = content_regions[0]
        region_start, region_end = region
        region_height = region_end - region_start

        # 在区域的中间40%-60%范围内寻找分割点（缩小范围以提高精度）
        mid_start = region_start + int(region_height * 0.40)
        mid_end = region_start + int(region_height * 0.60)

        # 方法1：使用边缘强度找分割线（适用于有明显边框的情况）
        mid_edges = row_edge_smooth[mid_start:mid_end]

        # 方法2：使用方差找分割点
        mid_variance = row_variance_smooth[mid_start:mid_end]

        # 综合评分：边缘强度高且方差低的位置更可能是分割线
        # 归一化两个指标
        if np.max(mid_edges) > np.min(mid_edges):
            edges_norm = (mid_edges - np.min(mid_edges)) / (np.max(mid_edges) - np.min(mid_edges))
        else:
            edges_norm = np.zeros_like(mid_edges)

        if np.max(mid_variance) > np.min(mid_variance):
            var_norm = (mid_variance - np.min(mid_variance)) / (np.max(mid_variance) - np.min(mid_variance))
        else:
            var_norm = np.ones_like(mid_variance)

        # 综合评分：高边缘强度 + 低方差 = 高分
        combined_score = edges_norm * 2 + (1 - var_norm)

        # 找到最佳分割位置
        split_offset = np.argmax(combined_score)
        split_row = mid_start + split_offset

        # 寻找连续的高边缘强度区域作为分割带
        edge_threshold = row_edge_smooth[split_row] * 0.5
        split_start = split_row
        split_end = split_row

        # 向上扩展分割区域（找边框上边界）
        for y in range(split_row, mid_start, -1):
            if row_edge_smooth[y] > edge_threshold:
                split_start = y
            else:
                # 继续往上找几行，确认是真正的边界
                look_ahead = min(5, y - mid_start)
                if look_ahead > 0 and np.max(row_edge_smooth[y - look_ahead : y]) < edge_threshold:
                    break

        # 向下扩展分割区域（找边框下边界）
        for y in range(split_row, mid_end):
            if row_edge_smooth[y] > edge_threshold:
                split_end = y
            else:
                look_ahead = min(5, mid_end - y - 1)
                if look_ahead > 0 and np.max(row_edge_smooth[y : y + look_ahead]) < edge_threshold:
                    break

        # 确保分割区域有最小宽度（防止分割点过于接近）
        min_split_gap = max(2, int(region_height * 0.005))  # 至少0.5%的高度或2像素
        if split_end - split_start < min_split_gap:
            split_start = split_row - min_split_gap // 2
            split_end = split_row + min_split_gap // 2

        # 上半图片：从区域开始到分割区域的上边界
        # 下半图片：从分割区域的下边界到区域结束
        region1 = (region_start, split_start)
        region2 = (split_end + 1, region_end)

    else:
        # 情况3：未检测到明显的内容区域（异常情况）
        # 使用默认的固定比例进行分割
        region1 = (int(height * 0.17), int(height * 0.48))
        region2 = (int(height * 0.52), int(height * 0.83))

    # ========== 第六步：提取并处理图片区域 ==========
    img1_region = screenshot[region1[0] : region1[1], :]
    img2_region = screenshot[region2[0] : region2[1], :]

    # 使用统一裁剪，确保两张图片裁剪一致
    img1, img2 = crop_image_borders_unified(img1_region, img2_region)

    return img1, img2


def crop_image_borders_unified(
    img1: np.ndarray, img2: np.ndarray, margin: int = 3, h_margin: int = 5
) -> tuple[np.ndarray, np.ndarray]:
    """
    对两张图片使用统一的裁剪参数，确保裁剪后内容对齐。

    分别检测两张图片的边框，然后使用较保守（较小）的裁剪值，
    确保两张图片裁剪后的内容区域一致。

    Args:
        img1: 第一张图片
        img2: 第二张图片
        margin: 额外的安全边距
        h_margin: 水平方向额外裁剪边距

    Returns:
        裁剪后的两张图片
    """
    h1, w1 = img1.shape[:2]
    h2, w2 = img2.shape[:2]

    # 检测两张图片的均匀边框
    # 图片1
    left1 = detect_uniform_border_width(img1, "left", max_search=int(w1 * 0.2))
    right1 = detect_uniform_border_width(img1, "right", max_search=int(w1 * 0.2))
    top1 = detect_uniform_border_width(img1, "top", max_search=int(h1 * 0.1))
    bottom1 = detect_uniform_border_width(img1, "bottom", max_search=int(h1 * 0.1))

    # 图片2
    left2 = detect_uniform_border_width(img2, "left", max_search=int(w2 * 0.2))
    right2 = detect_uniform_border_width(img2, "right", max_search=int(w2 * 0.2))
    top2 = detect_uniform_border_width(img2, "top", max_search=int(h2 * 0.1))
    bottom2 = detect_uniform_border_width(img2, "bottom", max_search=int(h2 * 0.1))

    # 使用两张图片中较小的裁剪值（保守裁剪，避免裁掉内容）
    # 但如果差距太大，说明检测可能有问题，使用较大的值
    def get_unified_crop(v1: int, v2: int) -> int:
        if v1 == 0 and v2 == 0:
            return 0
        # 如果两个值差距不大（<50%），使用较小值
        # 如果差距很大，使用较大值的一半（保守估计）
        if v1 > 0 and v2 > 0:
            ratio = min(v1, v2) / max(v1, v2)
            if ratio > 0.5:
                return min(v1, v2)
            else:
                return max(v1, v2) // 2
        return max(v1, v2)

    left = get_unified_crop(left1, left2)
    right = get_unified_crop(right1, right2)
    top = get_unified_crop(top1, top2)
    bottom = get_unified_crop(bottom1, bottom2)

    # 应用统一裁剪
    def apply_crop(img: np.ndarray) -> np.ndarray:
        h, w = img.shape[:2]
        t = min(top + margin, h // 4)
        b = max(h - bottom - margin, h * 3 // 4)
        l = min(left + h_margin, w // 4)
        r = max(w - right - h_margin, w * 3 // 4)

        # 确保裁剪区域有效
        if b - t < 10 or r - l < 10:
            margin_h = int(h * 0.02)
            margin_w = int(w * 0.02)
            return img[margin_h : h - margin_h, margin_w : w - margin_w]

        return img[t:b, l:r]

    return apply_crop(img1), apply_crop(img2)


def crop_white_borders(img: np.ndarray, threshold: int = 235, h_margin: int = 30) -> np.ndarray:
    """
    精确裁剪白色边框（保留用于兼容性）
    h_margin: 水平方向额外裁剪的边缘像素数
    """
    return crop_image_borders(img)


def detect_uniform_border_width(img: np.ndarray, side: str, max_search: int = 100) -> int:
    """
    检测图片边缘的均匀色带宽度。

    均匀色带是指颜色变化很小的边缘区域，如纯色或渐变背景。

    Args:
        img: 输入图片，BGR格式
        side: 检测的边，可选 'left', 'right', 'top', 'bottom'
        max_search: 最大搜索像素数

    Returns:
        检测到的均匀色带宽度（像素）
    """
    h, w = img.shape[:2]

    if side in ("left", "right"):
        # 检测垂直条带
        search_range = min(max_search, w // 4)

        # 采样中间区域的行，避免边缘干扰
        sample_start = h // 4
        sample_end = h * 3 // 4
        sample_rows = img[sample_start:sample_end, :, :]

        border_width = 0

        for offset in range(1, search_range):
            if side == "left":
                col = offset
            else:  # right
                col = w - 1 - offset

            # 获取当前列的像素
            current_col = sample_rows[:, col, :]

            # 计算该列的颜色方差（衡量颜色是否单一）
            col_std = np.std(current_col)

            # 与边缘第一列比较颜色差异
            if side == "left":
                edge_col = sample_rows[:, 0, :]
            else:
                edge_col = sample_rows[:, w - 1, :]

            color_diff = np.mean(np.abs(current_col.astype(float) - edge_col.astype(float)))

            # 如果颜色方差较小（接近单色或渐变）且与边缘颜色相近，认为是边框
            # 放宽阈值以处理渐变边缘
            if col_std < 60 and color_diff < 80:
                border_width = offset
            else:
                # 遇到内容区域，停止搜索
                break

        return border_width

    else:  # top or bottom
        search_range = min(max_search, h // 4)

        sample_start = w // 4
        sample_end = w * 3 // 4
        sample_cols = img[:, sample_start:sample_end, :]

        border_height = 0

        for offset in range(1, search_range):
            if side == "top":
                row = offset
            else:  # bottom
                row = h - 1 - offset

            current_row = sample_cols[row, :, :]
            row_std = np.std(current_row)

            if side == "top":
                edge_row = sample_cols[0, :, :]
            else:
                edge_row = sample_cols[h - 1, :, :]

            color_diff = np.mean(np.abs(current_row.astype(float) - edge_row.astype(float)))

            if row_std < 60 and color_diff < 80:
                border_height = offset
            else:
                break

        return border_height


def crop_image_borders(img: np.ndarray, margin: int = 3, h_margin: int = 5) -> np.ndarray:
    """
    智能裁剪图片边框，支持任意颜色的边框。

    使用多种方法分析来找到真正的图片内容区域：
    1. 边缘检测和颜色变化分析
    2. 均匀色带检测（专门处理纯色/渐变边缘）

    Args:
        img: 输入图片，BGR格式
        margin: 额外的安全边距（像素）
        h_margin: 水平方向额外裁剪边距（像素）

    Returns:
        裁剪后的图片
    """
    if img.size == 0:
        return img

    h, w = img.shape[:2]
    if h < 20 or w < 20:
        return img

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # ========== 方法1：使用颜色变化检测边界 ==========
    # 计算每行/列的颜色方差
    row_variance = np.array([np.std(img[y, :, :]) for y in range(h)])
    col_variance = np.array([np.std(img[:, x, :]) for x in range(w)])

    # 平滑方差曲线
    kernel = np.ones(3) / 3
    row_var_smooth = np.convolve(row_variance, kernel, mode="same")
    col_var_smooth = np.convolve(col_variance, kernel, mode="same")

    # 计算阈值（使用中位数更稳健）
    row_threshold = np.median(row_var_smooth) * 0.4
    col_threshold = np.median(col_var_smooth) * 0.4

    # ========== 方法2：使用边缘检测辅助 ==========
    # 计算Sobel梯度
    sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)

    # 每行的水平边缘强度（用于检测上下边界）
    row_edge = np.sum(np.abs(sobel_y), axis=1)
    # 每列的垂直边缘强度（用于检测左右边界）
    col_edge = np.sum(np.abs(sobel_x), axis=0)

    row_edge_smooth = np.convolve(row_edge, kernel, mode="same")
    col_edge_smooth = np.convolve(col_edge, kernel, mode="same")

    row_edge_threshold = np.median(row_edge_smooth) * 0.3
    col_edge_threshold = np.median(col_edge_smooth) * 0.3

    # ========== 方法3：检测均匀色带边框 ==========
    uniform_left = detect_uniform_border_width(img, "left", max_search=int(w * 0.2))
    uniform_right = detect_uniform_border_width(img, "right", max_search=int(w * 0.2))
    uniform_top = detect_uniform_border_width(img, "top", max_search=int(h * 0.1))
    uniform_bottom = detect_uniform_border_width(img, "bottom", max_search=int(h * 0.1))

    # ========== 寻找上边界 ==========
    top = uniform_top  # 从均匀边框后开始
    search_range = min(int(h * 0.15), 100)
    for y in range(top, min(top + search_range, h)):
        # 综合判断：方差足够高 或 边缘强度足够高
        is_content = row_var_smooth[y] > row_threshold or row_edge_smooth[y] > row_edge_threshold
        if is_content:
            top = y
            break

    # ========== 寻找下边界 ==========
    bottom = h - uniform_bottom
    for y in range(bottom - 1, max(bottom - search_range, top), -1):
        is_content = row_var_smooth[y] > row_threshold or row_edge_smooth[y] > row_edge_threshold
        if is_content:
            bottom = y + 1
            break

    # ========== 寻找左边界 ==========
    left = uniform_left  # 从均匀边框后开始
    search_range_w = min(int(w * 0.15), 100)
    for x in range(left, min(left + search_range_w, w)):
        is_content = col_var_smooth[x] > col_threshold or col_edge_smooth[x] > col_edge_threshold
        if is_content:
            left = x
            break

    # ========== 寻找右边界 ==========
    right = w - uniform_right
    for x in range(right - 1, max(right - search_range_w, left), -1):
        is_content = col_var_smooth[x] > col_threshold or col_edge_smooth[x] > col_edge_threshold
        if is_content:
            right = x + 1
            break

    # ========== 应用安全边距 ==========
    top = min(top + margin, bottom - 1)
    bottom = max(bottom - margin, top + 1)
    # 水平方向使用专门的边距
    left = min(left + h_margin, right - 1)
    right = max(right - h_margin, left + 1)

    # 确保裁剪区域有效
    if bottom - top < 10 or right - left < 10:
        # 如果裁剪后太小，返回一个保守的裁剪
        margin_h = int(h * 0.02)
        margin_w = int(w * 0.02)
        return img[margin_h : h - margin_h, margin_w : w - margin_w]

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
