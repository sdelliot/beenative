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
    page.theme_mode = ft.ThemeMode.DARK

    main_content = ft.Container(expand=True)

    async def handle_change(e: ft.Event[ft.NavigationDrawer]):

        await page.close_drawer()

        index = e.control.selected_index
        logger.info("Navigating to index: %s", index)

        # Swap the content based on index
        if index == 0:
            main_content.content = SearchPage(page, logger).setup_ui()
        elif index == 1:
            main_content.content = ft.Text("My Garden", size=30)

        page.update()

    def toggle_theme(e):
        page.theme_mode = ft.ThemeMode.LIGHT if page.theme_mode == ft.ThemeMode.DARK else ft.ThemeMode.DARK
        theme_icon.icon = ft.Icons.DARK_MODE if page.theme_mode == ft.ThemeMode.LIGHT else ft.Icons.LIGHT_MODE
        page.update()

    async def open_drawer(e):
        await page.show_drawer()

    page.drawer = ft.NavigationDrawer(
        on_change=handle_change,
        controls=[
            ft.Container(height=12),  # Top padding
            ft.NavigationDrawerDestination(
                label="Find a Plant",
                icon=ft.Icons.SEARCH_OUTLINED,
                selected_icon=ft.Icons.SEARCH,
            ),
        ],
    )

    theme_icon = ft.IconButton(icon=ft.Icons.LIGHT_MODE, on_click=lambda e: toggle_theme(e), tooltip="Toggle Light/Dark Mode")

    page.appbar = ft.AppBar(
        leading=ft.IconButton(
            icon=ft.Icons.MENU,
            on_click=open_drawer,
        ),
        title=ft.Text("BeeNative NC Plant Database"),
        actions=[
            ft.IconButton(
                ft.Icons.HELP_OUTLINE,
                tooltip="Documentation",
                on_click=lambda _: open_documentation(page)
            ),
            theme_icon,
        ],
        bgcolor=ft.Colors.SURFACE_CONTAINER,
    )

    main_content.content = SearchPage(page, logger).setup_ui()

    page.add(main_content)
    page.update()


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
