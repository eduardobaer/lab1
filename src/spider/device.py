import time
from io import BytesIO
from pathlib import Path

import uiautomator2 as u2


def get_package_from_apk(apk_path: Path) -> str:
    """Extract the package name from an APK without installing it."""
    try:
        from pyaxmlparser import APK

        return APK(str(apk_path)).package
    except Exception as e:
        raise RuntimeError(
            f"Could not extract package name from {apk_path}: {e}. "
            "Ensure pyaxmlparser is installed (it is a dependency of spider)."
        )


class Device:
    def __init__(self, serial: str | None = None):
        self.d = u2.connect(serial) if serial else u2.connect()

    def install_apk(self, apk_path: Path) -> str:
        """Install APK; return package name."""
        package = get_package_from_apk(apk_path)
        self.d.app_install(str(apk_path))
        return package

    def launch_app(self, package: str) -> None:
        self.d.app_start(package, stop=True)
        time.sleep(2)

    def current_app(self) -> dict:
        try:
            return self.d.app_current() or {}
        except Exception:
            return {}

    def screenshot(self) -> bytes:
        img = self.d.screenshot()
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    def hierarchy(self) -> str:
        return self.d.dump_hierarchy()

    def display_size(self) -> tuple[int, int]:
        info = self.d.info
        return (info["displayWidth"], info["displayHeight"])

    def tap(self, x: int, y: int) -> None:
        self.d.click(x, y)

    def long_press(self, x: int, y: int, duration: float = 1.0) -> None:
        self.d.long_click(x, y, duration)

    def swipe(self, direction: str, duration: float = 0.3) -> None:
        w, h = self.display_size()
        cx, cy = w // 2, h // 2
        d = min(w, h) // 3
        if direction == "up":
            self.d.swipe(cx, cy + d, cx, cy - d, duration)
        elif direction == "down":
            self.d.swipe(cx, cy - d, cx, cy + d, duration)
        elif direction == "left":
            self.d.swipe(cx + d, cy, cx - d, cy, duration)
        elif direction == "right":
            self.d.swipe(cx - d, cy, cx + d, cy, duration)
        else:
            raise ValueError(f"Unknown swipe direction: {direction}")

    def type_text(self, text: str) -> None:
        self.d.send_keys(text, clear=False)

    def press_back(self) -> None:
        self.d.press("back")

    def press_home(self) -> None:
        self.d.press("home")

    def restart_app(self, package: str) -> None:
        try:
            self.d.app_stop(package)
        except Exception:
            pass
        time.sleep(0.5)
        self.d.app_start(package)
        time.sleep(2)
