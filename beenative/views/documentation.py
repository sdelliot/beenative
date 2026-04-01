import os
import asyncio
from pathlib import Path

import flet as ft


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
        blockquote_padding=ft.Padding.all(15),
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
        height=page.height * 0.9,
    )

    docs_sheet = ft.BottomSheet(
        content=docs_content,
        scrollable=True,
        draggable=True,
    )

    page.overlay.append(docs_sheet)
    docs_sheet.open = True
    page.update()
