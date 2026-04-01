import os  # noqa: E402
import json  # noqa: E402
import math  # noqa: E402
import asyncio  # noqa: E402
import logging  # noqa: E402
from pathlib import Path

import flet as ft  # noqa: E402
import pdf_gen  # noqa: E402
import utils.utils as bn_utils  # noqa: E402
from settings import settings  # noqa: E402
from utils.flet import (  # noqa: E402
    SUN_DATA,
    WILDLIFE_MAP,
    MOISTURE_DATA,
    RESISTANCE_MAP,
    GalleryShimmer,
    open_url,
    get_flet_caption,
    get_readable_color,
    get_loading_overlay,
)
from models.plant import Plant  # noqa: E402
from views.raw_details import RawPlantSheet  # noqa: E402


class PlantDetails:
    def __init__(self, page: ft.Page, logger: logging.Logger):
        self.page = page
        self.logger = logger
        self.detail_container = ft.Container()
        self.detail_stack = ft.Stack()
        self.full_image_overlay = ft.Container()
        self.bs = ft.BottomSheet(
            content=ft.Container(
                content=self.detail_stack,
                padding=20,
            ),
            open=False,
            on_dismiss=self.close_bs,
        )

        self.is_dark = (
            True
            if page.theme_mode == ft.ThemeMode.DARK
            or (page.platform_brightness == ft.Brightness.DARK if page.theme_mode == ft.ThemeMode.SYSTEM else False)
            else False
        )

        self.full_img_view = ft.Container(
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
                        on_click=lambda _: self.hide_full_image(),
                    ),
                ]
            ),
            bgcolor=ft.Colors.with_opacity(0.9, ft.Colors.PRIMARY),
            alignment=ft.Alignment.CENTER,
            visible=False,
            # opacity=0,
            # expand=True,
        )

        self.logger.debug("Creating detailed stack row")
        # 1. Update your detail_container definition
        # We use a Stack so we can layer the "Full Image" on top of the "Facts"
        self.detail_container = ft.Column(
            scroll=ft.ScrollMode.ADAPTIVE,  # Best for mobile/web consistency
            # expand=True,  # Fills the available BottomSheet height
            spacing=10,
        )

        self.logger.debug("Creating full overlay stack row")

        # 2. Define the Full Image Overlay (Now as a control we can show/hide)
        self.full_image_overlay = ft.Container(
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
                        on_click=lambda _: self.hide_overlay(),
                    ),
                ]
            ),
            visible=False,
            # expand=True,
        )

        self.logger.debug("Define bottom sheet detailed stack row")
        # 3. Update the BottomSheet content
        self.bs = ft.BottomSheet(
            ft.Container(
                # We put the STACK here. It contains the Facts AND the Hidden Image
                content=self.detail_stack,
                padding=20,
                bgcolor=ft.Colors.ON_PRIMARY,
                height=self.page.window.height * 0.9,
                width=self.page.window.width * 0.9,
                border_radius=ft.BorderRadius(top_left=20, top_right=20, bottom_left=0, bottom_right=0),
            ),
            open=False,
            scrollable=True,
        )

        # 4. In your main() or show_details(), initialize the stack:
        self.detail_stack.controls = [self.detail_container, self.full_image_overlay]

        self.page.overlay.append(self.bs)

    def close_bs(self, e):
        self.bs.open = False
        self.bs.update()
        self.page.update()

    async def create_image_gallery(self, plant: Plant):
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

        chip_bg = ft.Colors.BLUE_900 if self.is_dark else ft.Colors.BLUE_50
        chip_text_color = ft.Colors.BLUE_200 if self.is_dark else ft.Colors.BLUE_900
        chip_border_color = ft.Colors.BLUE_700 if self.is_dark else ft.Colors.BLUE_200

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
            self.page.update()

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
                            content=get_flet_caption(img, is_dark=self.is_dark),  # Moved span logic to helper
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

    def get_bloom_indicator(self, bloom_weights: dict, flower_colors: list[str]):
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
        base_color = get_readable_color(prioritized_colors)

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

    def get_attribute_chips(self, json_data, icon_name, label, attr_type="wildlife"):
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
            self.logger.exception("Error parsing %s JSON: %s", attr_type, e)
            return ft.Container(width=0, height=0)

        icon_map = WILDLIFE_MAP if attr_type == "wildlife" else RESISTANCE_MAP
        # Using high-contrast light backgrounds for dark mode
        # We use 'with_opacity' to make them feel integrated but bright
        if self.is_dark:
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

        boarder = ft.Border.all(1, ft.Colors.with_opacity(0.1, text_color)) if not self.is_dark else None
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

    def get_sunlight_row(self, sun_categories_json):
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
                        color=data["color"] if not self.is_dark else ft.Colors.AMBER_200,
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

    def get_moisture_row(self, moisture_json):
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
                        color=data["color"] if not self.is_dark else ft.Colors.BLUE_200,
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

    async def handle_pdf_export(self, plant: Plant, detail_container, gallery_control):
        # 1. Grab the selected images from the gallery
        selected_images = gallery_control.get_selected()

        # --- 1. SHOW PAGE-LEVEL OVERLAY ---
        pdf_shimmer = get_loading_overlay("Generating High-Res PDF...", self.is_dark)
        self.bs.content.content = ft.Container(content=pdf_shimmer, height=400)
        self.page.update()

        # 2. Logic check: If no images selected, maybe export all or show a snackbar?
        if not selected_images:
            self.logger.debug("No specific images selected; exporting text only or all images.")
        else:
            self.logger.debug("User wants to include %s images in the PDF.", len(selected_images))
            for img in selected_images:
                self.logger.debug("Including: %s", img.get("thumbnail_url"))

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
        self.page.update()

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
            self.bs.content.content = self.detail_stack
            gallery_control.selection_mode_chip.selected = False
            gallery_control.sync_chip_ui()
            self.page.update()

        gallery_control.selection_mode_chip.selected = False
        gallery_control.sync_chip_ui()
        self.page.update()

        # 5. Optional: Remove it after a few seconds
        await asyncio.sleep(3)
        detail_container.controls.remove(export_status)
        self.page.update()

    async def handle_copy_bs(self, text, detail_container):
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
        )

        # 2. Insert it at the very top of the BottomSheet content
        self.detail_container.controls.insert(0, status)
        self.page.update()
        # 5. Optional: Remove it after a few seconds
        await asyncio.sleep(3)
        self.detail_container.controls.remove(status)
        self.page.update()

    def hide_overlay(self):
        self.full_image_overlay.visible = False
        self.detail_stack.update()

    def show_full_image(self, img_src):
        self.full_image_overlay.content.controls[0].src = img_src
        self.full_image_overlay.visible = True
        self.detail_stack.update()

    def hide_full_image(self):
        self.full_img_view.visible = False
        # full_img_view.opacity = 0
        self.page.update()

    def fact_row(self, icon, label, value):
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

    async def show_details(self, plant: Plant):
        # --- 1. SET UP THE LOADING STATE ---
        # Create the shimmer/loading content
        shimmer_overlay = get_loading_overlay("Gathering Plant Data...", self.is_dark)

        # Show the BottomSheet immediately with the shimmer
        self.bs.content.content = ft.Container(content=shimmer_overlay, height=400)
        self.bs.open = True
        self.page.update()

        self.bs.content.height = self.page.window.height * 0.9
        self.bs.content.width = self.page.window.width * 0.9
        self.detail_container.controls.clear()

        raw_plant = RawPlantSheet(self.page)

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
                                        on_click=lambda _: self.page.run_task(
                                            self.handle_copy_bs, plant.scientific_name, self.detail_container
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
                    ft.IconButton(ft.Icons.CLOSE, on_click=lambda _: self.close_bs(None)),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.START,
                # expand=True,
            )

            bloom_ui = self.get_bloom_indicator(bloom_weights=plant.bloom_months, flower_colors=plant.flower_colors)

            # Image Thumbnail Section
            # If path exists, create a clickable thumbnail; else, a placeholder icon

            zoom_icon = ft.Container(
                content=ft.Icon(ft.Icons.ZOOM_IN, color=ft.Colors.ON_SECONDARY, size=20),
                bgcolor=ft.Colors.SECONDARY,
                padding=5,
                border_radius=ft.BorderRadius.only(top_left=10, bottom_right=10),
                bottom=0,  # Position at the bottom
                on_click=lambda _: self.show_full_image(img_src) if img_src else None,
                right=0,  # Position at the right
            )

            # Assuming 'plant' is your dictionary from the database
            wildlife_data = plant.wildlife_attracts
            resistance_data = plant.plant_resistances

            self.logger.debug("Creating Image Gallery placeholder")
            gallery_placeholder = GalleryShimmer(is_dark=self.is_dark)
            gallery_switcher = ft.AnimatedSwitcher(
                content=gallery_placeholder,
                transition=ft.AnimatedSwitcherTransition.FADE,
                duration=500,  # 500ms fade duration
                reverse_duration=500,
                switch_in_curve=ft.AnimationCurve.EASE_IN_OUT,
            )

            # --- 4. SWAP SHIMMER FOR REAL CONTENT ---
            # Re-attach the real detail_container to the stack
            self.detail_stack.controls = [self.detail_container, self.full_image_overlay]
            self.bs.content.content = self.detail_stack
            self.logger.debug("Setting all bottom sheet controls")

            # Build the Content
            self.detail_container.controls.extend(
                [
                    header,
                    ft.Divider(),
                    ft.ResponsiveRow(
                        [
                            ft.Column(
                                [
                                    # Standard Facts
                                    self.fact_row(
                                        ft.CupertinoIcons.ARROW_2_CIRCLEPATH,
                                        "Life Cycle",
                                        ", ".join(plant.primary_lifecycle),
                                    ),
                                    self.fact_row(ft.Icons.STRAIGHTEN, "Height", plant.height_str),
                                    self.get_sunlight_row(plant.sunlight_categories),
                                    self.get_moisture_row(plant.moisture_categories),
                                    self.get_attribute_chips(
                                        wildlife_data,
                                        ft.CupertinoIcons.HEART_CIRCLE_FILL,
                                        "Attracts",
                                        attr_type="wildlife",
                                    ),
                                    self.get_attribute_chips(
                                        resistance_data, ft.Icons.SHIELD, "Resistances", "resistance"
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
                                        on_click=lambda _: self.show_full_image(img_src) if img_src else None,
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
                    gallery_switcher,
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
                                on_click=lambda _: raw_plant.show_raw_data(plant),
                                tooltip="View raw database record",
                            ),
                            ft.OutlinedButton(
                                "Export",
                                icon=ft.Icons.PICTURE_AS_PDF,
                                on_click=lambda _: self.page.run_task(
                                    self.handle_pdf_export, plant, self.detail_container, gallery_switcher.content
                                ),
                                tooltip="Save results as PDF",
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.END,
                    ),
                    ft.Container(height=15),
                ]
            )

            # self.detail_container.height = page.height * 0.85
            # self.detail_container.width = page.width * 0.85,
            self.bs.open = True
            self.bs.update()
            self.page.update()
            self.page.run_task(gallery_placeholder.animate_shimmer)

            try:
                real_gallery = await self.create_image_gallery(plant)
                gallery_switcher.content = real_gallery
                gallery_switcher.update()
                self.logger.debug("Cross-fade to real gallery complete")
            except Exception:
                self.logger.debug("The gallery placeholder hasn't loaded or is unavailable, we can continue")
        except Exception as e:
            self.logger.exception("Error showing details")
            self.detail_container.controls.clear()
            self.detail_container.controls.append(ft.Text(f"Failed to load details: {e}", color="red"))
            self.bs.update()
