import sys
from pathlib import Path

base_path = Path(Path(__file__).resolve()).parent
if base_path not in sys.path:
    sys.path.insert(0, base_path)

import os  # noqa: E402
import logging  # noqa: E402
import platform  # noqa: E402

import flet as ft  # noqa: E402
from db.engine import db_manager  # noqa: E402
from views.search import SearchPage  # noqa: E402
from views.documentation import open_documentation  # noqa: E402


def get_log_path(app_name):
    system = platform.system()
    home = Path.home()
    if system == "Darwin":  # iOS or macOS
        # On iOS, 'HOME' points to the App's Sandbox
        if (home / "Library").is_dir():  # macOS
            log_dir = home / "Library/Logs" / app_name
        else:  # iOS Sandbox
            # Documents is the only place we can reliably write/read on iOS
            log_dir = home / "Documents" / "Logs"

    elif system == "Linux":  # Likely Android
        # Android path for app-specific data
        log_dir = Path("/data/user/0") / app_name / "files/logs"
    elif system == "Windows":
        log_dir = Path(os.getenv("LOCALAPPDATA", home / "AppData/Local")) / app_name / "Logs"
    else:
        log_dir = home / ".local/state" / app_name / "logs"

    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / "debug_log.txt"


def setup_production_logging(app_name="com.beenative.app"):
    log_file = get_log_path(app_name)

    # Configure the logging module
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8", delay=True),
            logging.StreamHandler(),  # Still prints to console for active debug sessions
        ],
    )

    # Redirect Flet and other library logs to our file
    logging.getLogger("flet").setLevel(logging.WARNING)
    logging.getLogger("flet_core").setLevel(logging.WARNING)
    logging.getLogger("flet_controls").setLevel(logging.WARNING)
    logging.getLogger("flet_transport").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)

    return log_file


# Initialize at the very top of your script
current_log_file = setup_production_logging()
logger = logging.getLogger("BeeNative")

logger.info("Session Started. Logs being written to: %s", current_log_file)

search_task = None


async def main(page: ft.Page):
    db_manager.initialize_db()
    title = "BeeNative Explorer"
    page.title = title
    page.padding = 20
    logger.info("Starting up %s", title)

    # Set initial mode
    page.theme_mode = ft.ThemeMode.DARK

    def toggle_theme(e):
        if page.theme_mode == ft.ThemeMode.DARK:
            page.theme_mode = ft.ThemeMode.LIGHT
            theme_icon.icon = ft.Icons.DARK_MODE
        else:
            page.theme_mode = ft.ThemeMode.DARK
            theme_icon.icon = ft.Icons.LIGHT_MODE

        page.update()

    theme_icon = ft.IconButton(icon=ft.Icons.LIGHT_MODE, on_click=toggle_theme, tooltip="Toggle Light/Dark Mode")

    doc_icon = ft.IconButton(
        icon=ft.Icons.HELP_OUTLINE, tooltip="Documentation", on_click=lambda _: open_documentation(page)
    )

    page.appbar = ft.AppBar(
        title=ft.Text("BeeNative NC Plant Database"),
        actions=[
            doc_icon,
            theme_icon,
        ],
        bgcolor=ft.Colors.SURFACE_CONTAINER,
    )

    search_page = SearchPage(page, logger)
    search_page.setup_ui()


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
