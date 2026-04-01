
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
from utils.flet import (  # noqa: E402
    SUN_DATA,
    WILDLIFE_MAP,
    MOISTURE_DATA,
    RESISTANCE_MAP,
    GalleryShimmer,
    get_plant_icon,
    get_flet_caption,
    get_readable_color,
    get_loading_overlay,
)
from views.documentation import open_documentation  # noqa: E402

class RawPlantSheet:
    def __init__(self, page: ft.Page):
        self.page = page
        self.raw_data_container = ft.Column(scroll=ft.ScrollMode.AUTO)
        self.raw_bs = ft.BottomSheet(
            ft.Container(
                self.raw_data_container,
                padding=20,
                bgcolor=ft.Colors.ON_PRIMARY,  # Contrast with the main sheet
                height=page.window.height * 0.8,
                width=page.window.width * 0.8,
                border_radius=ft.BorderRadius(top_left=20, top_right=20, bottom_left=0, bottom_right=0),
            ),
            scrollable=True,
        )
        self.page.overlay.append(self.raw_bs)

    def show_raw_data(self, plant: Plant):
        self.raw_data_container.controls.clear()

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

        self.raw_data_container.controls.extend(
            [
                ft.Row(
                    [
                        ft.Text("Technical Data", size=20, weight="bold"),
                        ft.IconButton(
                            ft.Icons.CLOSE, on_click=lambda _: setattr(self.raw_bs, "open", False) or self.raw_bs.update()
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

        self.raw_bs.open = True
        self.raw_bs.update()
