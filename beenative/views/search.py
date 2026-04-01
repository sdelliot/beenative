import asyncio  # noqa: E402
import logging  # noqa: E402

import flet as ft  # noqa: E402
from db.engine import db_manager  # noqa: E402
from utils.flet import (  # noqa: E402
    get_plant_icon,
)
from db.repository import search_plants  # noqa: E402
from views.plant_details import PlantDetails


class SearchPage:
    def __init__(self, page: ft.Page, logger: logging.Logger):
        self.page = page
        self.logger = logger
        self.state = {
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
        self.search_input = None
        self.results_grid = None
        self.search_task = None
        self.plant_details = PlantDetails(self.page, self.logger)

        # --- UI COMPONENTS ---
        self.color_map = {
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

    def setup_ui(self):
        self.search_input = ft.TextField(
            # hint_text="Search plants...", expand=True, on_change=run_search
            hint_text="Search plants...",
            expand=True,
            input_filter=ft.InputFilter(allow=True, regex_string=r"^[A-Za-z\s\-\.]*$"),
            on_change=lambda _: asyncio.create_task(self.run_search()),
        )
        self.results_grid = ft.Column(
            scroll=ft.ScrollMode.AUTO, expand=True, on_scroll=lambda e: asyncio.create_task(self.on_scroll(e))
        )

        self.logger.debug("Creating filter row")

        # 2. Create the Filter Row
        filter_row = ft.Row(
            controls=[
                ft.Chip(
                    label=ft.Text(cat),
                    leading=ft.Icon(get_plant_icon(cat)),
                    on_select=self.handle_click("plant_categories"),
                    selected_color=ft.Colors.GREEN_700,
                )
                for cat in ["Trees", "Shrubs", "Vines", "Forbs", "Grasses & Sedges", "Ferns"]
            ],
            wrap=True,
            # scroll=ft.ScrollMode.ALWAYS,  # Allows horizontal swiping if too many chips
            spacing=10,
        )

        self.logger.debug("Creating color row")
        # Create the row of squares
        self.color_row = ft.Row(
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
                    on_click=lambda e, n=name: asyncio.create_task(self.color_box_clicked(e, n)),
                )
                for name, val in self.color_map.items()
            ],
        )

        self.page.add(
            # ft.Text("BeeNative Finder", size=32, weight="bold"),
            ft.Row([self.search_input]),
            # ft.Text("Conditions:", size=14, weight="bold"),
            # ft.Row([sun_row, ft.Chip(label=ft.Text("Deer Resistant"), on_select=handle_click("deer_resistant"))]),
            # ft.Text("Wildlife:", size=14, weight="bold"),
            # wildlife_row,
            filter_row,
            ft.Text("Bloom Color:", size=14, weight="bold"),
            self.color_row,
            ft.Divider(),
            self.results_grid,
        )
        self.page.update()

    async def output_search(self, offset=0, limit=20):
        # 1. Get text from input
        search_term = self.search_input.value if self.search_input.value else None

        # 2. Build filters from the 'state' dictionary
        active_filters = {}
        if self.state["flower_colors"]:
            active_filters["flower_colors"] = self.state["flower_colors"]

        if self.state["plant_categories"]:
            active_filters["plant_categories"] = self.state["plant_categories"]

        async with db_manager.get_session() as session:
            # Pass both the text search and the structured filters
            plants = await search_plants(
                session,
                search_term=search_term,
                filters=active_filters,
                offset=self.state["page_offset"],
                limit=self.state["page_limit"],
            )
        return plants

    async def add_plants_to_results(self, plants):
        for plant in plants:
            # Display Logic: Prefer Primary Common Name, fall back to PM, then Sci Name
            display_name = (plant.vasc_common_name_primary or plant.pm_common_name or plant.scientific_name).title()

            # Logic for icons based on categories
            categories = plant.plant_categories or []
            plant_icon = get_plant_icon(categories)  # Use your existing helper

            self.results_grid.controls.append(
                ft.ListTile(
                    leading=ft.Icon(plant_icon, color=ft.Colors.GREEN_400),
                    title=ft.Text(display_name, weight=ft.FontWeight.W_500),
                    subtitle=ft.Text(plant.scientific_name, italic=True),
                    trailing=ft.Icon(ft.Icons.CHEVRON_RIGHT),
                    on_click=lambda _, p=plant: asyncio.create_task(self.plant_details.show_details(p)),
                )
            )

    async def on_scroll(self, e: ft.OnScrollEvent):
        # Check if we are near the bottom (within 100 pixels)
        if e.pixels >= e.max_scroll_extent - 100:
            if not self.state["is_loading"]:
                await self.load_more_plants()

    async def load_more_plants(self):
        self.state["is_loading"] = True

        # 1. Update offset for the next batch
        self.state["page_offset"] += self.state["page_limit"]

        # 2. Add a loading indicator at the bottom
        loading_indicator = ft.ProgressRing(width=16, height=16, stroke_width=2)
        self.results_grid.controls.append(loading_indicator)
        self.page.update()

        plants = await self.output_search()

        # Remove the loading indicator
        self.results_grid.controls.remove(loading_indicator)

        if not plants:
            # Optional: Add a "No more results" message
            if self.state["has_more"]:
                self.results_grid.controls.append(
                    ft.Text("End of Matching Plants", size=12, italic=True, text_align=ft.TextAlign.CENTER)
                )
            self.state["has_more"] = False
        else:
            await self.add_plants_to_results(plants)

        self.state["is_loading"] = False
        self.page.update()

    async def run_search(self, e=None):
        if self.search_task:
            self.search_task.cancel()

        self.state["page_offset"] = 0
        self.state["has_more"] = True

        # 3. Define a small inner function to wrap the logic with a sleep
        async def debounced_search():
            try:
                # Wait for 500ms (adjust as needed)
                await asyncio.sleep(0.5)

                self.results_grid.controls = [ft.ProgressRing()]
                self.page.update()
                plants = await self.output_search()
                self.results_grid.controls.clear()
                await self.add_plants_to_results(plants)

            except asyncio.CancelledError:
                # This happens when the user types a new character before 500ms is up
                return
            except Exception as ex:
                self.results_grid.controls = [ft.Text(f"Error: {ex}", color="red")]

            self.page.update()

        self.search_task = asyncio.create_task(debounced_search())

    async def toggle_changed(self, e, key):
        # 1. Multi-select logic for Categories
        if key == "plant_categories":
            if self.state[key] is None:
                self.state[key] = []

            category = e.control.label.value
            if e.control.selected:
                if category not in self.state[key]:
                    self.state[key].append(category)
            elif category in self.state[key]:
                self.state[key].remove(category)

        # 2. Mutually exclusive logic for Colors (Your existing logic)
        elif key == "flower_colors":
            self.state[key] = e.control.label.value if e.control.selected else None
            for chip in self.color_row.controls:
                if chip != e.control:
                    chip.selected = False

        # 3. Standard Boolean toggles
        else:
            self.state[key] = e.control.selected

        await self.run_search()

    # WRAPPER: This lambda fixes the RuntimeWarning
    def handle_click(self, key):
        return lambda e: asyncio.create_task(self.toggle_changed(e, key))

    async def color_box_clicked(self, e, color_name):
        # Toggle logic
        if self.state["flower_colors"] == color_name:
            self.state["flower_colors"] = None  # Deselect
        else:
            self.state["flower_colors"] = color_name

        # Update UI borders
        for box in self.color_row.controls:
            is_selected = self.state["flower_colors"] == box.data
            box.border = ft.Border.all(3, ft.Colors.INVERSE_SURFACE) if is_selected else None

        self.color_row.update()

        # Trigger the search
        await self.run_search()
