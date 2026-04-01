import asyncio
from typing import List

import flet as ft


class GalleryShimmer(ft.Column):
    def __init__(self, is_dark: bool):
        super().__init__(tight=True, key="gallery_shimmer_skeleton")
        self.is_dark = is_dark
        # Use the colors!
        self.base_color = ft.Colors.GREY_900 if is_dark else ft.Colors.GREY_300
        self.highlight_color = ft.Colors.GREY_800 if is_dark else ft.Colors.GREY_200

        # Build the internal UI
        self.controls = [
            ft.Container(
                content=ft.Row(
                    [self._make_shimmer_item() for _ in range(3)],
                    spacing=20,
                    scroll=ft.ScrollMode.HIDDEN,
                ),
                padding=ft.Padding.only(bottom=10),
            ),
            # Chip Placeholder
            ft.Container(
                width=180,
                height=40,
                bgcolor=self.base_color,
                border_radius=20,
                animate_opacity=ft.Animation(800, "easeInOut"),
            ),
        ]

    def did_mount(self):
        """Runs automatically when the control is added to the page."""
        # Create the task for the animation loop
        self.running = True
        self.page.run_task(self.animate_shimmer)

    def will_unmount(self):
        """Runs automatically when the control is removed."""
        self.running = False

    def _make_shimmer_item(self):
        """Creates a single card + caption skeleton."""
        return ft.Column(
            [
                ft.Card(
                    content=ft.Container(
                        width=220,
                        height=300,
                        bgcolor=self.base_color,
                        border_radius=8,
                        # We'll animate the bgcolor itself for a 'shimmer' feel
                        animate=ft.Animation(800, "easeInOut"),
                    ),
                    elevation=4,
                ),
                ft.Container(
                    height=20,
                    width=150,
                    bgcolor=self.base_color,
                    border_radius=4,
                    margin=ft.Margin.only(bottom=60),
                    animate=ft.Animation(800, "easeInOut"),
                ),
            ],
            tight=True,
        )

    async def animate_shimmer(self):
        """The loop that handles the pulsing effect."""
        while self.page and getattr(self, "running", False):
            # Toggle between base and highlight
            new_color = self.highlight_color if self.controls[1].bgcolor == self.base_color else self.base_color

            # Update the chip placeholder
            self.controls[1].bgcolor = new_color

            # Update the cards and caption bars
            # Row -> controls (list of items) -> Column -> Card/Container
            for item_column in self.controls[0].content.controls:
                item_column.controls[0].content.bgcolor = new_color  # The Card Image
                item_column.controls[1].bgcolor = new_color  # The Caption bar

            self.update()
            await asyncio.sleep(0.8)


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


def get_readable_color(raw_color_list: List):
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

    clean_input = ""
    if raw_color_list:
        # Let's just get the first color
        clean_input = raw_color_list[0].lower()

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


# 2. Update the URL launcher (Fixes launch_url deprecation and RuntimeWarning)
async def open_url(url):
    if url:
        # Newer Flet uses page.launch_url as a coroutine
        await ft.UrlLauncher().launch_url(url)
