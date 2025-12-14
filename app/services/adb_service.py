"""
ADB 服务 - 处理无线调试连接和屏幕截图
使用系统 adb 命令行工具，支持 Android 11+ TLS 连接
"""

import base64
import asyncio
import subprocess
import shutil
from typing import Optional


class AdbService:
    """ADB 服务类 - 使用系统 adb 命令"""

    def __init__(self):
        self._connected_address: Optional[str] = None
        self._adb_path: Optional[str] = None

    def _find_adb(self) -> str:
        """查找 adb 可执行文件路径"""
        if self._adb_path:
            return self._adb_path

        # 尝试在 PATH 中查找
        adb_path = shutil.which("adb")
        if adb_path:
            self._adb_path = adb_path
            return adb_path

        # 常见安装路径
        common_paths = [
            r"C:\platform-tools\adb.exe",
            r"C:\Android\platform-tools\adb.exe",
            r"C:\Users\admin\AppData\Local\Android\Sdk\platform-tools\adb.exe",
        ]

        for path in common_paths:
            if shutil.which(path):
                self._adb_path = path
                return path

        raise FileNotFoundError("未找到 adb 工具，请确保已安装 Android SDK Platform Tools 并添加到 PATH")

    async def _run_adb(self, *args: str, timeout: float = 30.0) -> tuple[int, bytes, bytes]:
        """运行 adb 命令"""
        adb_path = self._find_adb()
        cmd = [adb_path] + list(args)

        loop = asyncio.get_event_loop()

        def run_command():
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    timeout=timeout,
                )
                return result.returncode, result.stdout, result.stderr
            except subprocess.TimeoutExpired:
                return -1, b"", b"Command timed out"
            except Exception as e:
                return -1, b"", str(e).encode()

        return await loop.run_in_executor(None, run_command)

    async def connect(self, host: str, port: int = 5555) -> dict:
        """连接到设备"""
        try:
            address = f"{host}:{port}"

            # 先断开之前的连接（如果有）
            if self._connected_address:
                await self._run_adb("disconnect", self._connected_address)

            # 连接设备
            returncode, stdout, stderr = await self._run_adb("connect", address, timeout=15.0)

            output = stdout.decode("utf-8", errors="ignore").strip()
            error = stderr.decode("utf-8", errors="ignore").strip()

            # 检查连接结果
            if "connected" in output.lower() or "already connected" in output.lower():
                self._connected_address = address
                return {
                    "success": True,
                    "message": f"已连接到 {address}",
                    "address": address,
                }
            else:
                error_msg = output or error or "连接失败"
                return {"success": False, "message": f"连接失败: {error_msg}"}

        except FileNotFoundError as e:
            return {"success": False, "message": str(e)}
        except Exception as e:
            return {"success": False, "message": f"连接失败: {str(e)}"}

    async def disconnect(self) -> dict:
        """断开连接"""
        try:
            if self._connected_address:
                await self._run_adb("disconnect", self._connected_address)
                self._connected_address = None
            return {"success": True, "message": "已断开连接"}
        except Exception as e:
            return {"success": False, "message": f"断开连接失败: {str(e)}"}

    async def capture_screen(self) -> dict:
        """截取屏幕"""
        if not self._connected_address:
            return {"success": False, "message": "设备未连接"}

        try:
            # 使用 adb exec-out 直接获取二进制数据（比 shell 更快）
            returncode, stdout, stderr = await self._run_adb(
                "-s", self._connected_address, "exec-out", "screencap", "-p", timeout=10.0
            )

            if returncode != 0 or len(stdout) == 0:
                error = stderr.decode("utf-8", errors="ignore").strip()
                # 尝试检查设备是否还在连接
                await self._check_connection()
                return {"success": False, "message": f"截图失败: {error or '未收到数据'}"}

            # 转换为 base64
            image_base64 = base64.b64encode(stdout).decode("utf-8")

            return {
                "success": True,
                "image": image_base64,
                "size": len(stdout),
            }
        except Exception as e:
            await self._check_connection()
            return {"success": False, "message": f"截图失败: {str(e)}"}

    async def _check_connection(self):
        """检查连接状态"""
        if not self._connected_address:
            return

        try:
            returncode, stdout, _ = await self._run_adb("devices", timeout=5.0)
            output = stdout.decode("utf-8", errors="ignore")

            # 检查设备是否还在列表中
            if self._connected_address not in output or "offline" in output:
                self._connected_address = None
        except Exception:
            self._connected_address = None

    async def get_devices(self) -> dict:
        """获取已连接的设备列表"""
        try:
            returncode, stdout, stderr = await self._run_adb("devices", "-l")

            if returncode != 0:
                error = stderr.decode("utf-8", errors="ignore").strip()
                return {"success": False, "message": f"获取设备列表失败: {error}"}

            output = stdout.decode("utf-8", errors="ignore")
            lines = output.strip().split("\n")[1:]  # 跳过 "List of devices attached"

            devices = []
            for line in lines:
                line = line.strip()
                if line:
                    parts = line.split()
                    if len(parts) >= 2:
                        devices.append(
                            {"address": parts[0], "state": parts[1], "info": " ".join(parts[2:]) if len(parts) > 2 else ""}
                        )

            return {"success": True, "devices": devices}
        except FileNotFoundError as e:
            return {"success": False, "message": str(e)}
        except Exception as e:
            return {"success": False, "message": f"获取设备列表失败: {str(e)}"}

    def get_status(self) -> dict:
        """获取连接状态"""
        return {
            "connected": self._connected_address is not None,
            "address": self._connected_address,
        }

    async def get_screen_info(self) -> dict:
        """获取屏幕分辨率信息"""
        if not self._connected_address:
            return {"success": False, "message": "设备未连接"}

        try:
            # 使用 wm size 获取屏幕尺寸
            returncode, stdout, stderr = await self._run_adb("-s", self._connected_address, "shell", "wm", "size", timeout=5.0)

            if returncode != 0:
                error = stderr.decode("utf-8", errors="ignore").strip()
                return {"success": False, "message": f"获取屏幕信息失败: {error}"}

            output = stdout.decode("utf-8", errors="ignore").strip()
            # 输出格式: "Physical size: 1080x2400"
            if "x" in output:
                size_part = output.split(":")[-1].strip()
                width, height = size_part.split("x")

                # 获取密度
                _, density_stdout, _ = await self._run_adb("-s", self._connected_address, "shell", "wm", "density", timeout=5.0)
                density_output = density_stdout.decode("utf-8", errors="ignore").strip()
                density = None
                if ":" in density_output:
                    try:
                        density = int(density_output.split(":")[-1].strip())
                    except ValueError:
                        pass

                return {
                    "success": True,
                    "width": int(width),
                    "height": int(height),
                    "density": density,
                }

            return {"success": False, "message": "无法解析屏幕尺寸"}

        except Exception as e:
            return {"success": False, "message": f"获取屏幕信息失败: {str(e)}"}

    async def input_tap(self, x: int, y: int) -> dict:
        """模拟点击"""
        if not self._connected_address:
            return {"success": False, "message": "设备未连接"}

        try:
            returncode, stdout, stderr = await self._run_adb(
                "-s", self._connected_address, "shell", "input", "tap", str(x), str(y), timeout=5.0
            )

            if returncode != 0:
                error = stderr.decode("utf-8", errors="ignore").strip()
                return {"success": False, "message": f"点击失败: {error}"}

            return {"success": True, "message": f"点击 ({x}, {y})"}

        except Exception as e:
            return {"success": False, "message": f"点击失败: {str(e)}"}

    async def input_swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = 300) -> dict:
        """模拟滑动"""
        if not self._connected_address:
            return {"success": False, "message": "设备未连接"}

        try:
            returncode, stdout, stderr = await self._run_adb(
                "-s",
                self._connected_address,
                "shell",
                "input",
                "swipe",
                str(x1),
                str(y1),
                str(x2),
                str(y2),
                str(duration),
                timeout=10.0,
            )

            if returncode != 0:
                error = stderr.decode("utf-8", errors="ignore").strip()
                return {"success": False, "message": f"滑动失败: {error}"}

            return {"success": True, "message": f"滑动 ({x1}, {y1}) -> ({x2}, {y2})"}

        except Exception as e:
            return {"success": False, "message": f"滑动失败: {str(e)}"}

    async def input_keyevent(self, keycode: str) -> dict:
        """模拟按键"""
        if not self._connected_address:
            return {"success": False, "message": "设备未连接"}

        try:
            returncode, stdout, stderr = await self._run_adb(
                "-s", self._connected_address, "shell", "input", "keyevent", keycode, timeout=5.0
            )

            if returncode != 0:
                error = stderr.decode("utf-8", errors="ignore").strip()
                return {"success": False, "message": f"按键失败: {error}"}

            return {"success": True, "message": f"按键 {keycode}"}

        except Exception as e:
            return {"success": False, "message": f"按键失败: {str(e)}"}

    async def input_text(self, text: str) -> dict:
        """输入文本"""
        if not self._connected_address:
            return {"success": False, "message": "设备未连接"}

        try:
            # 替换空格为 %s，其他特殊字符转义
            escaped_text = text.replace(" ", "%s")

            returncode, stdout, stderr = await self._run_adb(
                "-s", self._connected_address, "shell", "input", "text", escaped_text, timeout=10.0
            )

            if returncode != 0:
                error = stderr.decode("utf-8", errors="ignore").strip()
                return {"success": False, "message": f"输入文本失败: {error}"}

            return {"success": True, "message": f"已输入文本"}

        except Exception as e:
            return {"success": False, "message": f"输入文本失败: {str(e)}"}


# 单例实例
adb_service = AdbService()
