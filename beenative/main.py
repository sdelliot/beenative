import sys
from pathlib import Path

base_path = Path(Path(__file__).resolve()).parent
if base_path not in sys.path:
    sys.path.insert(0, base_path)

import os  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import asyncio  # noqa: E402
import logging  # noqa: E402
import platform  # noqa: E402

import flet as ft  # noqa: E402
import pdf_gen  # noqa: E402
import utils.utils as bn_utils  # noqa: E402
from settings import settings  # noqa: E402
from db.engine import db_manager  # noqa: E402
from sqlalchemy import inspect  # noqa: E402
from models.plant import Plant  # noqa: E402
from db.repository import search_plants  # noqa: E402


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
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8", delay=True),
            logging.StreamHandler(),  # Still prints to console for active debug sessions
        ],
    )

    # Redirect Flet and other library logs to our file
    logging.getLogger("flet").setLevel(logging.DEBUG)

    return log_file


# Initialize at the very top of your script
current_log_file = setup_production_logging()
logger = logging.getLogger("BeeNative")

logger.info("Session Started. Logs being written to: %s", current_log_file)


def get_markdown_stylesheet(page: ft.Page):
    # Determine colors based on Theme Mode
    is_dark = page.theme_mode == ft.ThemeMode.DARK

    # Blockquote Styling
    # We use a semi-transparent background so it adapts to the page color
    bq_bg = ft.Colors.with_opacity(0.1, ft.Colors.ON_SURFACE)
    bq_border_color = ft.Colors.PRIMARY if is_dark else ft.Colors.OUTLINE

    return ft.MarkdownStyleSheet(
        code_text_style=ft.TextStyle(
            font_family="monospace",
            size=14,
            color=ft.Colors.SECONDARY,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.SECONDARY),
        ),
        blockquote_text_style=ft.TextStyle(italic=True, color=ft.Colors.ON_SURFACE_VARIANT),
        blockquote_decoration=ft.BoxDecoration(
            bgcolor=bq_bg,
            border=ft.Border.only(left=ft.BorderSide(4, bq_border_color)),
            border_radius=ft.BorderRadius.only(top_right=5, bottom_right=5),
        ),
        blockquote_padding=ft.padding.all(15),
    )


def open_documentation(page: ft.Page):
    # Load the markdown content
    assets_dir_name = os.getenv("FLET_ASSETS_DIR", "assets")
    assets_root = Path(assets_dir_name) / "static"
    doc_file = assets_root / "README.md"
    try:
        with doc_file.open("r") as f:
            md_content = f.read()
    except FileNotFoundError:
        md_content = "# Error\nDocumentation file not found."

    def close_docs(e):
        docs_sheet.open = False
        page.update()

    # Create a scrollable container for the Markdown
    docs_content = ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        ft.Text(
                            "How BeeNative Works: Your Guide to Our Plant Data",
                            theme_style=ft.TextThemeStyle.HEADLINE_SMALL,
                        ),
                        ft.IconButton(ft.Icons.CLOSE, on_click=lambda _: close_docs(None)),
                    ],
                    # expand=True,
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(),
                ft.Markdown(
                    md_content,
                    selectable=True,
                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                    md_style_sheet=get_markdown_stylesheet(page),
                    on_tap_link=lambda e: asyncio.create_task(ft.UrlLauncher().launch_url(e.data)),
                ),
            ],
            scroll=ft.ScrollMode.ADAPTIVE,
        ),
        padding=20,
        height=page.height * 0.8,
    )

    docs_sheet = ft.BottomSheet(
        content=docs_content,
        scrollable=True,
        draggable=True,
    )

    page.overlay.append(docs_sheet)
    docs_sheet.open = True
    page.update()


def get_plant_icon(categories):
    if not categories:
        return ft.Icons.ECO

    # Priority mapping for icons
    if "Trees" in categories:
        return ft.Icons.PARK
    if "Shrubs" in categories:
        return ft.Icons.FOREST
    if "Vines" in categories:
        return ft.Icons.ACCOUNT_TREE_ROUNDED  # Looks like a vine/branch
    if "Grasses & Sedges" in categories:
        return ft.Icons.GRASS
    if "Ferns" in categories:
        return ft.Icons.SPA
    if "Forbs" in categories:
        return ft.Icons.LOCAL_FLORIST

    return ft.Icons.ECO  # Fallback


def get_readable_color(raw_color_string):
    """
    Maps raw botanical color names to readable Flet/Material Design colors.
    """
    color_map = {
        "white": ft.Colors.GREY_300,  # Pure white is invisible on light themes
        "yellow": ft.Colors.AMBER_400,  # Amber provides better contrast than bright yellow
        "gold": ft.Colors.AMBER_700,
        "orange": ft.Colors.ORANGE_700,
        "red": ft.Colors.RED_700,
        "pink": ft.Colors.PINK_300,
        "purple": ft.Colors.PURPLE_400,
        "violet": ft.Colors.DEEP_PURPLE_400,
        "blue": ft.Colors.BLUE_700,
        "green": ft.Colors.GREEN_700,
        "brown": ft.Colors.BROWN_600,
        "cream": ft.Colors.DEEP_ORANGE_50,
        "maroon": ft.Colors.RED_900,
    }

    # Clean the input (e.g., "Pale Yellow" -> "yellow")
    clean_input = raw_color_string.lower()

    for key, color_val in color_map.items():
        if key in clean_input:
            return color_val

    # Default if no match found
    return ft.Colors.BLUE_GREY_400


# Mapping for Wildlife (Attracts)
WILDLIFE_MAP = {
    "Bats": ft.Icons.NIGHTS_STAY,  # DO better with this one
    "Bees": ft.Icons.EMOJI_NATURE,
    "Specialized Bees": ft.Icons.HIVE,
    "Birds": ft.Icons.FLIGHT,  # TODO: Make this better
    "Songbirds": ft.CupertinoIcons.DOUBLE_MUSIC_NOTE,
    "Hummingbirds": ft.Icons.FLIGHT_TAKEOFF,  # TODO: Make this better
    "Butterflies": ft.Icons.KEYBOARD_COMMAND_KEY,
    "Moths": ft.Icons.PIX,  # Maybe ft.Icons.KEYBOARD_COMMAND_KEY or ft.Icons.FLUTTER_DASH
    "Pollinators": ft.Icons.LOCAL_FLORIST,
    "Frogs": ft.Icons.WATER_DROP,  # TODO: Make this better
    "Reptiles": ft.CupertinoIcons.TORTOISE_FILL,
    "Small Mammals": ft.CupertinoIcons.HARE_FILL,
    "Predatory Insects": ft.Icons.PEST_CONTROL,
}

# Mapping for Resistances
RESISTANCE_MAP = {
    "Deer": ft.Icons.FOREST,  # TODO: Make this icon better?
    "Rabbits": ft.Icons.CRUELTY_FREE,
    "Squirrels": ft.CupertinoIcons.TREE,  # TODO: Make this icon better?
    "Voles": ft.Icons.PEST_CONTROL_RODENT,
    "Slugs": ft.Icons.GESTURE,  # Maybe ft.Icons.MOVING? or TEXTURE
    "Drought": ft.Icons.WAVES_OUTLINED,
    "Poor Soil": ft.CupertinoIcons.BURN,  # Or maybe ft.CupertinoIcons.HAND_THUMBSDOWN_FILL
    "Dry Soil": ft.Icons.OPACITY,  # maybe  ft.Icons.WATER_DROP_OUTLINED
    "Wet Soil": ft.Icons.WATER_DROP,  # or ft.Icons.FLOOD or ft.Icons.WATER_DROP or ft.Icons.WATER
    "Salt": ft.Icons.WAVES,  # TODO: Make this icon better?
    "Pollution": ft.Icons.FACTORY,  # Or ft.Icons.OIL_BARREL
    "Urban Conditions": ft.Icons.LOCATION_CITY,
    "Heat": ft.CupertinoIcons.THERMOMETER_SUN,  # Or maybe ft.Icons.WB_SUNNY
    "Humidity": ft.Icons.DEW_POINT,  # Maybe ft.CupertinoIcons.CLOUD_FOG or ft.CupertinoIcons.SUN_HAZE or ft.Icons.FOGGY
    "Wind": ft.CupertinoIcons.WIND,
    "Fire": ft.CupertinoIcons.FLAME_FILL,  # or ft.Icons.LOCAL_FIRE_DEPARTMENT
    "Erosion": ft.Icons.LANDSLIDE,
    "Black Walnut": ft.Icons.DO_NOT_DISTURB_ON,
    "Foot Traffic": ft.Icons.DO_NOT_STEP,
    "Compaction": ft.Icons.COMPRESS,
    "Heavy Shade": ft.Icons.ROLLER_SHADES_CLOSED,  # Or Icons: BEDTIME, CupertinoIcons: CLOUD, CLOUD_SUN_FILL
    "Diseases": ft.Icons.CORONAVIRUS,
    "Insect Pests": ft.CupertinoIcons.ANT,
    "Storm Damage": ft.Icons.THUNDERSTORM,  # Or cupertino HURRICANE or TORNADO
}


SUN_DATA = {
    "Full Sun": {
        "icon": ft.Icons.WB_SUNNY,
        "color": ft.Colors.AMBER,
        "tooltip": "6 or more hours of direct sunlight a day",
    },
    "Partial Shade": {
        "icon": ft.CupertinoIcons.CLOUD_SUN,
        "color": ft.Colors.AMBER_700,
        "tooltip": "Direct sunlight only part of the day, 2-6 hours",
    },
    "Dappled Sunlight": {
        "icon": ft.CupertinoIcons.SUN_DUST,
        "color": ft.Colors.BLUE_GREY_400,
        "tooltip": "Shade through upper canopy all day",
    },
    "Deep Shade": {
        "icon": ft.Icons.NIGHTLIGHT_ROUNDED,
        "color": ft.Colors.BLUE_GREY_700,
        "tooltip": "Less than 2 hours to no direct sunlight",
    },
    "Unknown": {"icon": ft.Icons.QUESTION_MARK, "color": ft.Colors.BLUE_GREY_400, "tooltip": "No data available"},
}

MOISTURE_DATA = {
    "Wet": {
        "icon": ft.Icons.WATER_DROP,
        "color": ft.Colors.BLUE_800,
        "tooltip": "Wet: Soggy or marshy most of the year",
    },
    "Medium-Wet": {
        "icon": ft.Icons.OPACITY,
        "color": ft.Colors.BLUE_400,
        "tooltip": "Medium-Wet: Excessively wet in winter/spring, dries in summer",
    },
    "Medium": {
        "icon": ft.Icons.WATER_DROP_OUTLINED,
        "color": ft.Colors.CYAN_400,
        "tooltip": "Medium (mesic): Average garden soil, no run-off",
    },
    "Medium-Dry": {
        "icon": ft.Icons.WAVES,
        "color": ft.Colors.AMBER_600,
        "tooltip": "Medium-Dry: Well-drained, water removed readily but not rapidly",
    },
    "Dry": {"icon": ft.Icons.GRAIN, "color": ft.Colors.BROWN_400, "tooltip": "Dry: Excessively drained"},
    "Unknown": {"icon": ft.Icons.QUESTION_MARK, "color": ft.Colors.BLUE_GREY_400, "tooltip": "No data available"},
}


def get_flet_caption(info, is_dark=True):
    """Returns a Flet Text control with clickable spans."""
    if not info:
        return ft.Text("")
    spans = []

    text_color = ft.Colors.GREY_400 if is_dark else ft.Colors.GREY_700
    link_color = ft.Colors.BLUE_200 if is_dark else ft.Colors.BLUE_700

    cap_style = ft.TextStyle(size=10, italic=True, color=text_color)

    url_style = ft.TextStyle(
        size=10,
        color=link_color,
        weight=ft.FontWeight.BOLD,
    )

    # Title Span
    if info["source_url"]:
        spans.append(ft.TextSpan(f'"{info["title"]}"', style=url_style, url=info["source_url"]))
    else:
        spans.append(ft.TextSpan(f'"{info["title"]}"', style=cap_style))

    # Author Span
    spans.append(ft.TextSpan(f" by {info['author']}", style=cap_style))

    # License Span
    if info["license_text"]:
        spans.append(ft.TextSpan(" (", style=cap_style))
        if info["license_url"]:
            spans.append(ft.TextSpan(info["license_text"], style=url_style, url=info["license_url"]))
        else:
            spans.append(ft.TextSpan(info["license_text"]))
        spans.append(ft.TextSpan(")", style=cap_style))

    return ft.Text(
        spans=spans,
        # color=ft.Colors.ON_SURFACE_VARIANT,
        text_align=ft.TextAlign.CENTER,
    )


def get_loading_overlay(message="Processing...", is_dark=True):
    # Adaptive colors for the shimmer card
    card_bg = ft.Colors.GREY_900 if is_dark else ft.Colors.WHITE
    text_color = ft.Colors.GREY_400 if is_dark else ft.Colors.GREY_700

    return ft.Container(
        content=ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.ProgressRing(width=40, height=40, stroke_width=4, color=ft.Colors.BLUE_400),
                        ft.Text(message, size=16, weight=ft.FontWeight.W_500, color=text_color),
                        # "Shimmer" bars to mimic data loading
                        ft.Container(
                            height=10, width=150, bgcolor=ft.Colors.with_opacity(0.1, text_color), border_radius=5
                        ),
                        ft.Container(
                            height=10, width=100, bgcolor=ft.Colors.with_opacity(0.1, text_color), border_radius=5
                        ),
                    ],
                    tight=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                padding=30,
            ),
            elevation=10,
        ),
        alignment=ft.Alignment.CENTER,
        bgcolor=card_bg,
    )


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

    # State keys MUST match your Database Column Names exactly
    # TODO: Many of these don't
    state = {
        "flower_colors": [],
        "plant_categories": [],
        "wildlife_attracts": False,
        "attr_butterflies": False,
        "deer_resistant": False,
        "sun_full": False,
        "sun_shade": False,
        "is_tall": False,  # Example for future height filter
        "page_offset": 0,
        "page_limit": 20,
        "is_loading": False,
        "has_more": True,
    }

    search_input = ft.TextField(
        # hint_text="Search plants...", expand=True, on_change=run_search
        hint_text="Search plants...",
        expand=True,
        input_filter=ft.InputFilter(allow=True, regex_string=r"^[A-Za-z\s\-\.]*$"),
        on_change=lambda _: asyncio.create_task(run_search()),
    )
    results_grid = ft.Column(
        scroll=ft.ScrollMode.AUTO, expand=True, on_scroll=lambda e: asyncio.create_task(on_scroll(e))
    )

    logger.debug("Before run_search")

    async def output_search(offset=0, limit=20):
        # 1. Get text from input
        search_term = search_input.value if search_input.value else None

        # 2. Build filters from the 'state' dictionary
        active_filters = {}
        if state["flower_colors"]:
            active_filters["flower_colors"] = state["flower_colors"]

        if state["plant_categories"]:
            active_filters["plant_categories"] = state["plant_categories"]

        async with db_manager.get_session() as session:
            # Pass both the text search and the structured filters
            plants = await search_plants(
                session,
                search_term=search_term,
                filters=active_filters,
                offset=state["page_offset"],
                limit=state["page_limit"],
            )
        return plants

    async def add_plants_to_results(plants):
        for plant in plants:
            # Display Logic: Prefer Primary Common Name, fall back to PM, then Sci Name
            display_name = (plant.vasc_common_name_primary or plant.pm_common_name or plant.scientific_name).title()

            # Logic for icons based on categories
            categories = plant.plant_categories or []
            plant_icon = get_plant_icon(categories)  # Use your existing helper

            results_grid.controls.append(
                ft.ListTile(
                    leading=ft.Icon(plant_icon, color=ft.Colors.GREEN_400),
                    title=ft.Text(display_name, weight=ft.FontWeight.W_500),
                    subtitle=ft.Text(plant.scientific_name, italic=True),
                    trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                    on_click=lambda _, p=plant: asyncio.create_task(show_details(p)),
                )
            )

    async def on_scroll(e: ft.OnScrollEvent):
        # Check if we are near the bottom (within 100 pixels)
        if e.pixels >= e.max_scroll_extent - 100:
            if not state["is_loading"]:
                await load_more_plants()

    async def load_more_plants():
        state["is_loading"] = True

        # 1. Update offset for the next batch
        state["page_offset"] += state["page_limit"]

        # 2. Add a loading indicator at the bottom
        loading_indicator = ft.ProgressRing(width=16, height=16, stroke_width=2)
        results_grid.controls.append(loading_indicator)
        page.update()

        plants = await output_search()

        # Remove the loading indicator
        results_grid.controls.remove(loading_indicator)

        if not plants:
            # Optional: Add a "No more results" message
            if state["has_more"]:
                results_grid.controls.append(
                    ft.Text("End of Matching Plants", size=12, italic=True, text_align=ft.TextAlign.CENTER)
                )
            state["has_more"] = False
        else:
            await add_plants_to_results(plants)

        state["is_loading"] = False
        page.update()

    async def run_search(e=None):
        global search_task
        if search_task:
            search_task.cancel()

        state["page_offset"] = 0
        state["has_more"] = True

        # 3. Define a small inner function to wrap the logic with a sleep
        async def debounced_search():
            try:
                # Wait for 500ms (adjust as needed)
                await asyncio.sleep(0.5)

                results_grid.controls = [ft.ProgressRing()]
                page.update()
                plants = await output_search()
                results_grid.controls.clear()
                await add_plants_to_results(plants)

            except asyncio.CancelledError:
                # This happens when the user types a new character before 500ms is up
                return
            except Exception as ex:
                results_grid.controls = [ft.Text(f"Error: {ex}", color="red")]

            page.update()

        search_task = asyncio.create_task(debounced_search())

    async def create_image_gallery(plant: Plant, is_dark=True):
        """
        Creates a horizontal scrollable gallery from the extracted NCBG JSON data.
        """
        if not plant:
            return ft.Container(width=0, height=0)

        # Get image_data_list (NC Botanical Gargen)
        image_data_list = getattr(plant, "ncbg_images", []) or []

        # Get any Plant Toolbox images
        ncsu_images = getattr(plant, "ncsu_images", []) or []

        image_data_list.extend(ncsu_images)

        if not image_data_list:
            return ft.Container(width=0, height=0)

        target_h = 300
        gallery_cards = []

        # 1. Filter out entries without URLs
        valid_images = [img for img in image_data_list if img.get("thumbnail_url")]

        # 2. FIRE ALL REQUESTS IN PARALLEL
        # This creates a list of "get_image_dimensions" tasks and runs them at the same time
        widths = await asyncio.gather(
            *[bn_utils.get_image_dimensions(img["thumbnail_url"], target_h) for img in valid_images]
        )

        chip_bg = ft.Colors.BLUE_900 if is_dark else ft.Colors.BLUE_50
        chip_text_color = ft.Colors.BLUE_200 if is_dark else ft.Colors.BLUE_900
        chip_border_color = ft.Colors.BLUE_700 if is_dark else ft.Colors.BLUE_200

        def toggle_selection(e, card_container, check_icon):
            # Check if we are in "Selection Mode"
            if selection_mode_chip.selected:
                is_selected = card_container.border is None
                e.control.border = ft.Border.all(4, chip_border_color) if is_selected else None
                check_icon.visible = is_selected

                # Visual feedback: dim the image slightly when selected
                card_container.content.controls[0].opacity = 0.7 if is_selected else 1.0

                e.page.update()
            else:
                # Normal mode: Preview
                asyncio.create_task(open_url(card_container.data["original_url"]))

        def sync_chip_ui():
            """Updates the chip visuals based on its current selected state."""
            active = selection_mode_chip.selected
            if active:
                selection_mode_chip.label.content = ft.Text("Cancel Selection", color=chip_text_color, weight="bold")
                selection_mode_chip.leading.content = ft.Icon(ft.Icons.CLOSE, color=chip_text_color)
                selection_mode_chip.border = ft.Border.all(1, chip_border_color)
            else:
                selection_mode_chip.label.content = ft.Text(
                    "Select Photos for Export", color=ft.Colors.ON_SURFACE_VARIANT
                )
                selection_mode_chip.leading.content = ft.Icon(ft.Icons.PHOTO_LIBRARY_OUTLINED)
                selection_mode_chip.border = None
                clear_selections()  # This removes the blue borders/dimming from images

        def clear_selections():
            for card in gallery_cards:
                # content is the Stack, content.controls[1] is the Icon
                # card.content.data is the container holding everything
                container = card.content
                container.border = None
                container.content.controls[0].opacity = 1.0  # The Image
                container.content.controls[1].visible = False  # The Checkmark
            page.update()

        chip_label_text = ft.Text("Select Photos for Export", color=ft.Colors.ON_SURFACE_VARIANT)
        chip_leading_icon = ft.Icon(ft.Icons.PHOTO_LIBRARY_OUTLINED)

        # A clean "Selection Mode" toggle using a ChoiceChip
        selection_mode_chip = ft.Chip(
            label=ft.AnimatedSwitcher(
                chip_label_text,
                transition=ft.AnimatedSwitcherTransition.FADE,
                duration=ft.Duration(microseconds=100),
                reverse_duration=ft.Duration(microseconds=100),
            ),
            leading=ft.AnimatedSwitcher(
                chip_leading_icon,
                transition=ft.AnimatedSwitcherTransition.SCALE,
                duration=ft.Duration(microseconds=100),
                reverse_duration=ft.Duration(microseconds=100),
            ),
            # Active styles
            selected_color=chip_bg,
            show_checkmark=False,
            check_color=chip_text_color,
            # Trigger the UI update
            on_select=lambda e: sync_chip_ui() or e.page.update(),
        )

        gallery_items = []
        # 3. Zip the results back together to build the UI
        for img, current_w in zip(valid_images, widths, strict=True):
            # The Checkmark Icon (Hidden by default)
            check_mark = ft.Icon(
                ft.Icons.CHECK_CIRCLE, color=ft.Colors.BLUE_ACCENT, size=30, visible=False, top=10, right=10
            )

            # The Stack allows the icon to sit ON TOP of the image
            img_stack = ft.Stack(
                [
                    ft.Image(
                        src=img["thumbnail_url"],
                        height=target_h,
                        fit=ft.BoxFit.FILL,
                        border_radius=8,
                    ),
                    check_mark,
                ]
            )

            img_container = ft.Container(
                content=img_stack,
                data=img,
                on_click=lambda e, c=None, i=check_mark: toggle_selection(e, e.control, i),
                border_radius=8,
                animate=ft.Animation(duration=ft.Duration(microseconds=100), curve=ft.AnimationCurve.DECELERATE),
                animate_scale=ft.Animation(
                    duration=ft.Duration(microseconds=100), curve=ft.AnimationCurve.EASE_OUT_BACK
                ),
                animate_opacity=ft.Animation(
                    duration=ft.Duration(microseconds=100), curve=ft.AnimationCurve.EASE_IN_OUT
                ),
            )

            card = ft.Card(elevation=4, content=img_container)
            gallery_cards.append(card)

            gallery_items.append(
                ft.Column(
                    [
                        card,
                        ft.Container(
                            content=get_flet_caption(img, is_dark=is_dark),  # Moved span logic to helper
                            width=current_w,
                            padding=ft.Padding.only(bottom=30),
                        ),
                    ],
                    tight=True,
                )
            )

        # Attach the data retrieval method
        layout = ft.Column(
            [
                ft.Container(
                    content=ft.Row(
                        gallery_items,
                        scroll=ft.ScrollMode.ALWAYS,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        spacing=20,
                    ),
                    padding=ft.Padding.only(bottom=10),
                ),
                ft.Row(
                    [
                        selection_mode_chip,
                    ],
                    alignment=ft.MainAxisAlignment.START,
                ),
            ]
        )

        layout.get_selected = lambda: [c.content.data for c in gallery_cards if c.content.border is not None]
        layout.sync_chip_ui = sync_chip_ui
        layout.selection_mode_chip = selection_mode_chip
        return layout

    def get_bloom_indicator(bloom_weights: dict, flower_colors: list[str]):
        if not bloom_weights:
            return ft.Text("No bloom data available", italic=True, size=12)

        bloom_months = list(bloom_weights.keys())

        if isinstance(flower_colors, str):
            flower_colors = json.loads(flower_colors)

        all_months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        # 1. Logic to find the "Peak"
        # We want the color to be brightest in the middle of the bloom period
        bloom_indices = [all_months.index(m[:3].title()) for m in bloom_months if m[:3].title() in all_months]
        if not bloom_indices:
            return ft.Text("No bloom data available", italic=True, size=12, color=ft.Colors.GREY_400)

        # CIRCULAR MATH: Convert indices to vectors on a unit circle
        sum_x = 0
        sum_y = 0
        for idx in bloom_indices:
            angle = (idx / 12) * 2 * math.pi
            sum_x += math.cos(angle)
            sum_y += math.sin(angle)

        # Calculate the average angle to find the "Circular Peak"
        avg_angle = math.atan2(sum_y, sum_x)
        peak_idx = (avg_angle / (2 * math.pi)) * 12
        if peak_idx < 0:
            peak_idx += 12

        prioritized_colors = sorted(flower_colors, key=lambda x: x.lower() == "white")
        base_color = get_readable_color(prioritized_colors[0])

        month_chips = []
        for i, month_name in enumerate(all_months):
            weight = bloom_weights.get(month_name, 0)
            is_blooming = weight > 0
            if is_blooming:
                # Distance must also be circular (e.g., distance between 11 and 0 is 1, not 11)
                diff = abs(i - peak_idx)
                dist = min(diff, 12 - diff)
                base_opacity = max(0.3, 1.0 - (dist / 3.0))

                # Use a narrower fade factor so the peak is clear
                opacity = max(0.3, 1.0 - (dist / 2.5))
                bg_color = ft.Colors.with_opacity(opacity, base_color)
                text_color = ft.Colors.WHITE

                # 2. Visual Weight Bonus
                # If weight > 1 (confirmed by multiple sources), we boost brightness
                weight_bonus = 0.3 if weight > 1 else 0.0
                final_opacity = min(1.0, base_opacity + weight_bonus)

                # 3. Add a border to "Double-Confirmed" months
                border = ft.Border.all(2, ft.Colors.with_opacity(0.5, ft.Colors.WHITE)) if weight > 1 else None

                bg_color = ft.Colors.with_opacity(final_opacity, base_color)
                text_color = ft.Colors.WHITE

                # ADAPTIVE TEXT LOGIC:
                # If the background is both a bright color AND has high opacity
                is_bright_color = base_color in [
                    ft.Colors.GREY_300,
                    ft.Colors.ORANGE_700,
                    ft.Colors.PINK_300,
                    ft.Colors.AMBER_400,
                    ft.Colors.DEEP_ORANGE_50,
                ]
                if is_bright_color and opacity > 0.3:
                    text_color = ft.Colors.BLACK_87  # Soft black for better readability
                else:
                    text_color = ft.Colors.WHITE

                # DESIGN TIP: Add a tiny shadow to the text for white-on-light situations
                text_shadow = (
                    [ft.BoxShadow(blur_radius=1, color=ft.Colors.BLACK_26)] if text_color == ft.Colors.WHITE else None
                )

            else:
                bg_color = ft.Colors.with_opacity(0.1, ft.Colors.BLACK)
                text_color = ft.Colors.GREY_500
                text_shadow = None
                border = None

            month_chips.append(
                ft.Container(
                    content=ft.Text(
                        month_name, weight="bold", color=text_color, theme_style=ft.TextStyle(shadow=text_shadow)
                    ),
                    height=33,
                    bgcolor=bg_color,
                    border=border,
                    border_radius=ft.BorderRadius.all(5),
                    padding=ft.Padding.symmetric(horizontal=5, vertical=5),
                )
            )

        return ft.Column(
            spacing=10,
            controls=[
                ft.Text("Bloom Season", size=16, weight=ft.FontWeight.BOLD),
                ft.Row(
                    controls=month_chips,
                    alignment=ft.MainAxisAlignment.START,
                    wrap=True,
                    spacing=10,
                    run_spacing=10,
                    tight=True,
                ),
            ],
            tight=True,
        )

    async def toggle_changed(e, key):
        # 1. Multi-select logic for Categories
        if key == "plant_categories":
            if state[key] is None:
                state[key] = []

            category = e.control.label.value
            if e.control.selected:
                if category not in state[key]:
                    state[key].append(category)
            elif category in state[key]:
                state[key].remove(category)

        # 2. Mutually exclusive logic for Colors (Your existing logic)
        elif key == "flower_colors":
            state[key] = e.control.label.value if e.control.selected else None
            for chip in color_row.controls:
                if chip != e.control:
                    chip.selected = False

        # 3. Standard Boolean toggles
        else:
            state[key] = e.control.selected

        await run_search()

    # --- UI COMPONENTS ---
    color_map = {
        "Yellow": ft.Colors.AMBER_400,
        "White": ft.Colors.GREY_300,
        "Blue": ft.Colors.BLUE_700,
        "Purple": ft.Colors.PURPLE_400,
        "Pink": ft.Colors.PINK_300,
        "Red": ft.Colors.RED_700,
        "Orange": ft.Colors.ORANGE_700,
        "Green": ft.Colors.GREEN_700,
        "Brown": ft.Colors.BROWN_600,
        "Grey": ft.Colors.GREY_700,
    }

    def get_attribute_chips(json_data, icon_name, label, attr_type="wildlife", is_dark=True):
        """
        attr_type: "wildlife" or "resistance"
        """
        # 1. Parse the JSON string safely
        try:
            if not json_data or json_data == "null":
                return ft.Container(width=0, height=0)

            # If it's already a list, use it; if it's a string, parse it
            data_list = json.loads(json_data) if isinstance(json_data, str) else json_data

            if not isinstance(data_list, list) or len(data_list) == 0:
                return ft.Container(width=0, height=0)
        except Exception as e:
            logger.exception("Error parsing %s JSON: %s", attr_type, e)
            return ft.Container(width=0, height=0)

        icon_map = WILDLIFE_MAP if attr_type == "wildlife" else RESISTANCE_MAP
        # Using high-contrast light backgrounds for dark mode
        # We use 'with_opacity' to make them feel integrated but bright
        if is_dark:
            # DARK MODE: Vibrant Accents
            if attr_type == "wildlife":
                text_color = ft.Colors.GREEN_ACCENT_400
                bg_color = ft.Colors.with_opacity(0.15, ft.Colors.GREEN_ACCENT_700)
            else:
                text_color = ft.Colors.RED_ACCENT_100
                bg_color = ft.Colors.with_opacity(0.15, ft.Colors.RED_ACCENT_700)
        # LIGHT MODE: Richer Darks on Soft Backgrounds
        elif attr_type == "wildlife":
            text_color = ft.Colors.GREEN_800  # Darker for contrast on light
            bg_color = ft.Colors.GREEN_50  # Soft pastel background
        else:
            text_color = ft.Colors.RED_800
            bg_color = ft.Colors.RED_50

        boarder = ft.Border.all(1, ft.Colors.with_opacity(0.1, text_color)) if not is_dark else None
        chips = []
        for item in data_list:
            icon = icon_map.get(item, ft.Icons.LABEL_IMPORTANT_OUTLINE)
            chips.append(
                ft.Container(
                    content=ft.Row(
                        controls=[
                            ft.Icon(icon, size=14, color=text_color),
                            ft.Text(item, size=11, color=text_color, weight=ft.FontWeight.W_500),
                        ],
                        tight=True,
                        spacing=5,
                    ),
                    bgcolor=bg_color,
                    padding=ft.Padding.symmetric(horizontal=10, vertical=5),
                    border_radius=20,  # Makes it look like a Chip
                    border=boarder,
                    shadow=ft.BoxShadow(
                        blur_radius=4, color=ft.Colors.with_opacity(0.2, ft.Colors.BLACK), offset=ft.Offset(0, 2)
                    ),
                )
            )

        return ft.Row(
            [
                ft.Icon(icon_name, size=20, color=ft.Colors.GREEN_400),
                ft.Text(
                    spans=[
                        ft.TextSpan(f"{label}: ", ft.TextStyle(weight=ft.FontWeight.BOLD)),
                    ]
                ),
                ft.Row(
                    controls=chips,
                    alignment=ft.MainAxisAlignment.SPACE_EVENLY,
                    wrap=True,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
            wrap=True,
        )

    # WRAPPER: This lambda fixes the RuntimeWarning
    def handle_click(key):
        return lambda e: asyncio.create_task(toggle_changed(e, key))

    async def color_box_clicked(e, color_name):
        # Toggle logic
        if state["flower_colors"] == color_name:
            state["flower_colors"] = None  # Deselect
        else:
            state["flower_colors"] = color_name

        # Update UI borders
        for box in color_row.controls:
            is_selected = state["flower_colors"] == box.data
            box.border = ft.Border.all(3, ft.Colors.INVERSE_SURFACE) if is_selected else None

        color_row.update()

        # Trigger the search
        await run_search()

    def get_sunlight_row(sun_categories_json, is_dark):
        # Parse the list from the new DB column
        try:
            categories = (
                json.loads(sun_categories_json) if isinstance(sun_categories_json, str) else sun_categories_json
            )
            if not categories:
                categories = ["Unknown"]
        except json.JSONDecodeError:
            categories = ["Unknown"]

        sun_icons = []
        for cat in categories:
            data = SUN_DATA.get(cat)
            if data:
                sun_icons.append(
                    ft.Icon(
                        icon=data["icon"],
                        color=data["color"] if not is_dark else ft.Colors.AMBER_200,
                        tooltip=f"{cat}: {data['tooltip']}",
                        size=20,
                    )
                )

        return ft.Row(
            [
                ft.Icon(ft.Icons.LIGHT_MODE_OUTLINED, size=20, color=ft.Colors.GREEN_400),
                ft.Text(
                    spans=[
                        ft.TextSpan("Sunlight: ", ft.TextStyle(weight=ft.FontWeight.BOLD)),
                    ]
                ),
                ft.Column(
                    [
                        ft.Row(sun_icons, spacing=10),
                    ],
                    spacing=2,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    def get_moisture_row(moisture_json, is_dark):
        try:
            categories = json.loads(moisture_json) if isinstance(moisture_json, str) else moisture_json
            if not categories:
                categories = ["Unknown"]
        except json.JSONDecodeError:
            categories = ["Unknown"]

        moisture_icons = []
        # Sort categories from Wet to Dry for consistent visual order
        order = ["Wet", "Medium-Wet", "Medium", "Medium-Dry", "Dry"]
        sorted_cats = sorted(categories, key=lambda x: order.index(x) if x in order else 99)

        for cat in sorted_cats:
            data = MOISTURE_DATA.get(cat)
            if data:
                moisture_icons.append(
                    ft.Icon(
                        icon=data["icon"],
                        color=data["color"] if not is_dark else ft.Colors.BLUE_200,
                        tooltip=data["tooltip"],
                        size=20,
                    )
                )

        return ft.Row(
            [
                ft.Icon(ft.Icons.WATER_DROP_OUTLINED, size=20, color=ft.Colors.GREEN_400),
                ft.Text(
                    spans=[
                        ft.TextSpan("Soil Moisture: ", ft.TextStyle(weight=ft.FontWeight.BOLD)),
                    ]
                ),
                ft.Column(
                    [
                        ft.Row(moisture_icons, spacing=10),
                    ],
                    spacing=2,
                ),
            ],
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

    async def handle_pdf_export(plant: Plant, detail_container, gallery_control):
        # 1. Grab the selected images from the gallery
        selected_images = gallery_control.get_selected()

        # --- 1. SHOW PAGE-LEVEL OVERLAY ---
        is_dark = page.theme_mode == ft.ThemeMode.DARK
        pdf_shimmer = get_loading_overlay("Generating High-Res PDF...", is_dark)
        bs.content.content = ft.Container(content=pdf_shimmer, height=400)
        page.update()

        # 2. Logic check: If no images selected, maybe export all or show a snackbar?
        if not selected_images:
            logger.debug("No specific images selected; exporting text only or all images.")
        else:
            logger.debug("User wants to include %s images in the PDF.", len(selected_images))
            for img in selected_images:
                logger.debug("Including: %s", img.get("thumbnail_url"))

        # 1. Create a local notification control
        export_status = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.DOWNLOAD_FOR_OFFLINE, color=ft.Colors.WHITE),
                    ft.Text("Generating PDF...", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                ]
            ),
            bgcolor=ft.Colors.BLUE_700,
            padding=10,
            border_radius=8,
            visible=True,
        )

        # 2. Insert it at the very top of the BottomSheet content
        detail_container.controls.insert(0, export_status)
        page.update()

        try:
            # 3. Generate bytes and save
            loop = asyncio.get_running_loop()
            pdf_buffer = await loop.run_in_executor(None, pdf_gen.generate_plant_pdf, plant, selected_images)
            pdf_bytes = pdf_buffer.getvalue()
            result = await ft.FilePicker().save_file(
                src_bytes=pdf_bytes, file_name=f"{plant.scientific_name}_details.pdf"
            )

            # 4. Update status to success
            if result:
                export_status.content.controls[1].value = "PDF Exported Successfully!"
                export_status.bgcolor = ft.Colors.GREEN_700
            else:
                export_status.content.controls[1].value = "PDF Export Canceled!"
                export_status.bgcolor = ft.Colors.AMBER_700

        except Exception as err:
            export_status.content.controls[1].value = f"Error: {err}"
            export_status.bgcolor = ft.Colors.RED_700
            raise
        finally:
            # --- 3. ALWAYS REMOVE OVERLAY ---
            bs.content.content = detail_stack
            gallery_control.selection_mode_chip.selected = False
            gallery_control.sync_chip_ui()
            page.update()

        gallery_control.selection_mode_chip.selected = False
        gallery_control.sync_chip_ui()
        page.update()

        # 5. Optional: Remove it after a few seconds
        await asyncio.sleep(3)
        detail_container.controls.remove(export_status)
        page.update()

    logger.debug("Creating filter row")

    # 2. Create the Filter Row
    filter_row = ft.Row(
        controls=[
            ft.Chip(
                label=ft.Text(cat),
                leading=ft.Icon(get_plant_icon(cat)),
                on_select=handle_click("plant_categories"),
                selected_color=ft.Colors.GREEN_700,
            )
            for cat in ["Trees", "Shrubs", "Vines", "Forbs", "Grasses & Sedges", "Ferns"]
        ],
        wrap=True,
        # scroll=ft.ScrollMode.ALWAYS,  # Allows horizontal swiping if too many chips
        spacing=10,
    )

    logger.debug("Creating color row")
    # Create the row of squares
    color_row = ft.Row(
        wrap=True,
        spacing=10,
        controls=[
            ft.Container(
                width=40,
                height=40,
                bgcolor=val,
                border_radius=4,
                tooltip=f"Bloom Color: {name}",  # Direct property, no wrapper needed
                data=name,  # Storing the name here makes it easy to find during the click event
                on_click=lambda e, n=name: asyncio.create_task(color_box_clicked(e, n)),
            )
            for name, val in color_map.items()
        ],
    )

    logger.debug("Creating detailed stack row")
    # 1. Update your detail_container definition
    # We use a Stack so we can layer the "Full Image" on top of the "Facts"
    detail_stack = ft.Stack(
        # expand=True,
    )
    detail_container = ft.Column(
        scroll=ft.ScrollMode.ADAPTIVE,  # Best for mobile/web consistency
        # expand=True,  # Fills the available BottomSheet height
        spacing=10,
    )

    logger.debug("Creating full overlay stack row")

    # 2. Define the Full Image Overlay (Now as a control we can show/hide)
    full_image_overlay = ft.Container(
        content=ft.Stack(
            [
                ft.Image(
                    src="https://upload.wikimedia.org/wikipedia/commons/6/65/No-Image-Placeholder.svg",
                    fit=ft.BoxFit.CONTAIN,
                    # expand=True,
                ),
                ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    bgcolor=ft.Colors.ON_SECONDARY,
                    top=10,
                    right=10,
                    on_click=lambda _: hide_overlay(),
                ),
            ]
        ),
        visible=False,
        # expand=True,
    )

    async def handle_copy_bs(text, detail_container):
        # Sets the text to the user's clipboard
        await ft.Clipboard().set(text)
        # Optional: Show a quick snackbar to confirm
        # page.show_snackbar(ft.SnackBar(ft.Text(f"Copied {name} to clipboard"), duration=1500))

        # 1. Create a local notification control
        status = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.CupertinoIcons.DOC_ON_CLIPBOARD_FILL, color=ft.Colors.WHITE),
                    ft.Text("Copied to clipboard", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD),
                ]
            ),
            bgcolor=ft.Colors.BLUE_700,
            padding=10,
            border_radius=8,
            visible=True,
            # opacity=1,
        )

        # 2. Insert it at the very top of the BottomSheet content
        detail_container.controls.insert(0, status)
        page.update()
        # 5. Optional: Remove it after a few seconds
        await asyncio.sleep(3)
        detail_container.controls.remove(status)
        page.update()

    def hide_overlay():
        full_image_overlay.visible = False
        detail_stack.update()

    def show_full_image(img_src):
        full_image_overlay.content.controls[0].src = img_src
        full_image_overlay.visible = True
        detail_stack.update()

    logger.debug("Define bottom sheet detailed stack row")
    # 3. Update the BottomSheet content
    bs = ft.BottomSheet(
        ft.Container(
            # We put the STACK here. It contains the Facts AND the Hidden Image
            content=detail_stack,
            padding=20,
            bgcolor=ft.Colors.ON_PRIMARY,
            height=page.window.height * 0.9,
            width=page.window.width * 0.9,
            border_radius=ft.BorderRadius(top_left=20, top_right=20, bottom_left=0, bottom_right=0),
        ),
        open=False,
        scrollable=True,
    )

    # 4. In your main() or show_details(), initialize the stack:
    detail_stack.controls = [detail_container, full_image_overlay]

    page.overlay.append(bs)

    # 1. Define the Raw Data Sheet once in main()
    raw_data_container = ft.Column(scroll=ft.ScrollMode.AUTO)
    raw_bs = ft.BottomSheet(
        ft.Container(
            raw_data_container,
            padding=20,
            bgcolor=ft.Colors.ON_PRIMARY,  # Contrast with the main sheet
            height=page.window.height * 0.8,
            width=page.window.width * 0.8,
            border_radius=ft.BorderRadius(top_left=20, top_right=20, bottom_left=0, bottom_right=0),
        ),
        scrollable=True,
    )
    page.overlay.append(raw_bs)

    full_img_view = ft.Container(
        content=ft.Stack(
            [
                # 1. The Image itself
                ft.Image(
                    src="https://upload.wikimedia.org/wikipedia/commons/6/65/No-Image-Placeholder.svg",
                    fit=ft.BoxFit.CONTAIN,
                    # expand=True,
                ),
                # 2. A close button in the top right
                ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    icon_color=ft.Colors.PRIMARY,
                    bgcolor=ft.Colors.ON_PRIMARY,
                    top=20,
                    right=20,
                    on_click=lambda _: hide_full_image(),
                ),
            ]
        ),
        bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.PRIMARY),
        alignment=ft.Alignment.CENTER,
        visible=False,
        # opacity=0,
        # expand=True,
    )

    def hide_full_image():
        full_img_view.visible = False
        # full_img_view.opacity = 0
        page.update()

    def show_raw_data(plant: Plant):
        raw_data_container.controls.clear()

        # Build a DataTable with all keys/values
        # TODO: Update this!!!

        mapper = inspect(plant).mapper

        rows = []
        for column in mapper.attrs:
            key = column.key  # The name of the field (e.g., 'scientific_name')
            value = getattr(plant, key)  # The actual data
            cleaned_value = bn_utils.format_value(value)
            if cleaned_value:
                rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(
                                ft.Text(str(key), selectable=True, weight=ft.FontWeight.BOLD, color=ft.Colors.PRIMARY)
                            ),
                            ft.DataCell(
                                ft.Row(
                                    [ft.Text(cleaned_value, selectable=True)],
                                    scroll=ft.ScrollMode.ADAPTIVE,
                                    width=300,
                                )
                            ),
                        ],
                    )
                )

        raw_data_container.controls.extend(
            [
                ft.Row(
                    [
                        ft.Text("Technical Data", size=20, weight="bold"),
                        ft.IconButton(
                            ft.Icons.CLOSE, on_click=lambda _: setattr(raw_bs, "open", False) or raw_bs.update()
                        ),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Divider(),
                ft.DataTable(
                    columns=[
                        ft.DataColumn(ft.Text("Field")),
                        ft.DataColumn(ft.Text("Value")),
                    ],
                    rows=rows,
                    column_spacing=20,
                    data_row_max_height=float("inf"),
                ),
            ]
        )

        raw_bs.open = True
        raw_bs.update()

    def fact_row(icon, label, value):
        return ft.Row(
            [
                ft.Icon(icon, size=20, color=ft.Colors.GREEN_400),
                ft.Text(
                    spans=[
                        ft.TextSpan(f"{label}: ", ft.TextStyle(weight=ft.FontWeight.BOLD)),
                        ft.TextSpan(str(value) if value else "Not specified"),
                    ]
                ),
            ]
        )

    # 2. Update the URL launcher (Fixes launch_url deprecation and RuntimeWarning)
    async def open_url(url):
        if url:
            # Newer Flet uses page.launch_url as a coroutine
            await ft.UrlLauncher().launch_url(url)

    async def show_details(plant: Plant):
        # --- 1. SET UP THE LOADING STATE ---
        # Create the shimmer/loading content
        is_dark = page.theme_mode == ft.ThemeMode.DARK or (
            page.platform_brightness == ft.Brightness.DARK if page.theme_mode == ft.ThemeMode.SYSTEM else False
        )
        shimmer_overlay = get_loading_overlay("Gathering Plant Data...", is_dark)

        # Show the BottomSheet immediately with the shimmer
        bs.content.content = ft.Container(content=shimmer_overlay, height=400)
        bs.open = True
        page.update()

        bs.content.height = page.window.height * 0.9
        bs.content.width = page.window.width * 0.9
        detail_container.controls.clear()

        try:
            description = "No description available."
            if plant.ncsu_html_description:
                description = bn_utils.convert_html_to_flet(
                    plant.ncsu_html_description, base_url=settings.ncsu_plant_toolbox_base_url
                )
            elif plant.pm_about:
                description = bn_utils.clean_pm_plant_description(plant.pm_about)
            elif plant.vasc_distribution:
                description = plant.vasc_distribution
            elif plant.vasc_identification:
                description = plant.vasc_identification

            assets_dir_name = os.getenv("FLET_ASSETS_DIR", "assets")
            assets_root = Path(assets_dir_name) / "static"

            img_path_raw = plant.vasc_map_file_path

            raw_url = plant.vasc_map_file_url
            img_src = raw_url if (raw_url and str(raw_url).lower() not in ["", "none", "null"]) else None

            if img_path_raw:
                # Construct the full system path dynamically
                full_system_path = assets_root / img_path_raw

                if full_system_path.exists():
                    # Flet always treats the assets_dir as the web root "/"
                    img_src = f"/{img_path_raw}"

            header = ft.Row(
                [
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Text(
                                        plant.scientific_name,
                                        size=28,
                                        weight="bold",
                                        overflow=ft.TextOverflow.FADE,
                                    ),
                                    ft.IconButton(
                                        icon=ft.Icons.COPY_ROUNDED,
                                        icon_size=18,
                                        icon_color=ft.Colors.SECONDARY,
                                        tooltip="Copy scientific name",
                                        on_click=lambda _: page.run_task(
                                            handle_copy_bs, plant.scientific_name, detail_container
                                        ),
                                        # Adjusting padding to keep it tight to the text
                                        padding=0,
                                        visual_density=ft.VisualDensity.COMPACT,
                                    ),
                                ],
                                spacing=5,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                wrap=True,
                            ),
                            ft.Text(
                                "; ".join(plant.all_common_names) or "Native Plant",
                                italic=True,
                                color=ft.Colors.SECONDARY,
                                overflow=ft.TextOverflow.ELLIPSIS,
                                max_lines=3,
                                selectable=True,
                            ),
                        ],
                        expand=True,
                    ),
                    ft.IconButton(ft.Icons.CLOSE, on_click=lambda _: close_bs(None)),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.START,
                # expand=True,
            )

            bloom_ui = get_bloom_indicator(bloom_weights=plant.bloom_months, flower_colors=plant.flower_colors)

            # Image Thumbnail Section
            # If path exists, create a clickable thumbnail; else, a placeholder icon

            zoom_icon = ft.Container(
                content=ft.Icon(ft.Icons.ZOOM_IN, color=ft.Colors.ON_SECONDARY, size=20),
                bgcolor=ft.Colors.SECONDARY,
                padding=5,
                border_radius=ft.BorderRadius.only(top_left=10, bottom_right=10),
                bottom=0,  # Position at the bottom
                on_click=lambda _: show_full_image(img_src) if img_src else None,
                right=0,  # Position at the right
            )

            # Assuming 'plant' is your dictionary from the database
            wildlife_data = plant.wildlife_attracts
            resistance_data = plant.plant_resistances

            try:
                logger.debug("Creating Image Gallery object")
                gallery = await create_image_gallery(plant, is_dark=is_dark)
            except Exception:
                logger.exception("Gallery load failed")
                gallery = ft.Container(width=0, height=0)  # Provide empty container so the rest of the UI loads

            logger.debug("Image gallery loaded successfully")
            # --- 4. SWAP SHIMMER FOR REAL CONTENT ---
            # Re-attach the real detail_container to the stack
            detail_stack.controls = [detail_container, full_image_overlay]
            bs.content.content = detail_stack
            logger.debug("Seeting all bottom sheet controls")

            # Build the Content
            detail_container.controls.extend(
                [
                    header,
                    ft.Divider(),
                    ft.ResponsiveRow(
                        [
                            ft.Column(
                                [
                                    # Standard Facts
                                    fact_row(
                                        ft.CupertinoIcons.ARROW_2_CIRCLEPATH,
                                        "Life Cycle",
                                        ", ".join(plant.primary_lifecycle),
                                    ),
                                    fact_row(ft.Icons.STRAIGHTEN, "Height", plant.height_str),
                                    get_sunlight_row(plant.sunlight_categories, is_dark),
                                    get_moisture_row(plant.moisture_categories, is_dark),
                                    get_attribute_chips(
                                        wildlife_data,
                                        ft.CupertinoIcons.HEART_CIRCLE_FILL,
                                        "Attracts",
                                        attr_type="wildlife",
                                        is_dark=is_dark,
                                    ),
                                    get_attribute_chips(
                                        resistance_data, ft.Icons.SHIELD, "Resistances", "resistance", is_dark=is_dark
                                    ),
                                ],
                                spacing=14,
                                # expand=True,  # Allows the sidebar to take up the majority of the width
                                alignment=ft.MainAxisAlignment.START,
                                col=8,
                            ),
                            ft.Stack(
                                controls=[
                                    ft.Container(
                                        content=(
                                            ft.Image(
                                                src=img_src,
                                                fit=ft.BoxFit.CONTAIN,
                                            )
                                            if img_src
                                            else ft.Icon(ft.Icons.IMAGE_NOT_SUPPORTED, size=50)
                                        ),
                                        on_click=lambda _: show_full_image(img_src) if img_src else None,
                                        alignment=ft.Alignment.TOP_RIGHT,
                                    ),
                                    zoom_icon if img_src else ft.Container(width=0, height=0),
                                ],
                                col=4,
                            ),
                        ],
                        columns=12,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Divider(),
                    bloom_ui,
                    ft.Divider(),
                    ft.Column(
                        [
                            ft.Text("Description", weight="bold", size=18),
                            ft.Text(description, theme_style=ft.TextThemeStyle.BODY_LARGE, selectable=True)
                            if isinstance(description, str)
                            else description,
                        ]
                    ),
                    gallery,
                    ft.Divider(),
                    ft.Row(
                        [
                            ft.OutlinedButton(
                                "Plant Toolbox",
                                icon=ft.Icons.OPEN_IN_NEW,
                                on_click=lambda _: asyncio.create_task(open_url(plant.ncsu_url)),
                                tooltip="Visit the NC Plant Toolbox Entry",
                            )
                            if plant.ncsu_url
                            else ft.Container(width=0, height=0),
                            ft.OutlinedButton(
                                "Prairie Moon",
                                icon=ft.Icons.OPEN_IN_NEW,
                                on_click=lambda _: asyncio.create_task(open_url(plant.pm_url)),
                                tooltip="Visit the Prairie Moon catalogue",
                            )
                            if plant.pm_url
                            else ft.Container(width=0, height=0),
                            ft.OutlinedButton(
                                "All Data",
                                icon=ft.Icons.STORAGE,
                                on_click=lambda _: show_raw_data(plant),
                                tooltip="View raw database record",
                            ),
                            ft.OutlinedButton(
                                "Export",
                                icon=ft.Icons.PICTURE_AS_PDF,
                                on_click=lambda _: page.run_task(handle_pdf_export, plant, detail_container, gallery),
                                tooltip="Save results as PDF",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                    ft.Container(height=15),
                ]
            )

            # detail_container.height = page.height * 0.85
            # detail_container.width = page.width * 0.85,
            logger.debug("1450 - before setting controls")
            bs.open = True
            logger.debug("1454 After open")
            bs.update()
            logger.debug("1456 after bs.update")
            page.update()
            logger.debug("1458 after page.update")
        except Exception as e:
            logger.exception("Error showing details")
            detail_container.controls.clear()
            detail_container.controls.append(ft.Text(f"Failed to load details: {e}", color="red"))
            bs.update()

    def close_bs(e):
        bs.open = False
        bs.update()
        page.update()

    page.add(
        # ft.Text("BeeNative Finder", size=32, weight="bold"),
        ft.Row([search_input]),
        # ft.Text("Conditions:", size=14, weight="bold"),
        # ft.Row([sun_row, ft.Chip(label=ft.Text("Deer Resistant"), on_select=handle_click("deer_resistant"))]),
        # ft.Text("Wildlife:", size=14, weight="bold"),
        # wildlife_row,
        filter_row,
        ft.Text("Bloom Color:", size=14, weight="bold"),
        color_row,
        ft.Divider(),
        results_grid,
    )
    page.update()


if __name__ == "__main__":
    ft.run(main, assets_dir="assets")
