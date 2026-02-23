import flet as ft
import json
from urllib.parse import urljoin
from bs4 import NavigableString, BeautifulSoup
import requests
from io import BytesIO
from PIL import Image
import asyncio
import pprint


def format_value(val):
    """Parses JSON strings and cleans up falsy data."""
    # 1. Handle actual None or empty strings
    if val is None or val == "" or val == "None":
        return None

    # 2. Check if it's a JSON-style string (starts with [ or {)
    if isinstance(val, str) and (val.startswith("[") or val.startswith("{")):
        try:
            parsed = json.loads(val)
            # If the parsed list/dict is empty, treat as Falsy
            if not parsed:
                return None
            # If it's a list, join it with commas for readability
            if isinstance(parsed, list):
                return ", ".join(map(str, parsed))

            if isinstance(parsed, dict):
                return pprint.pformat(parsed)
            return str(parsed)
        except json.JSONDecodeError:
            # Not actually JSON, just a string that happens to start with [
            pass

    if isinstance(val, list):
        return ", ".join(map(str, val))

    if isinstance(val, dict):
        return pprint.pformat(val)

    # 3. Handle Boolean False
    if val is False:
        return None

    if isinstance(val, str) and (val.startswith("[") and val.endswith("]")):
        parsed = val.replace("[", "").replace("]", "")
        parsed_lst = parsed.split(",")
        return ", ".join(parsed_lst)

    return str(val)


# Incuding large sections of https://github.com/Benitmulindwa/FletifyHTML


class _HTML:
    # ----------------------------------------------------------------------------------------------
    """
    Supported HTML tags and attributes
    """

    class Tags:
        IMG = "img"
        UL = "ul"
        OL = "ol"
        LI = "li"
        A = "a"
        B = "b"
        STRONG = "strong"
        I = "i"  # noqa: E741
        EM = "em"
        U = "u"
        MARK = "mark"
        SPAN = "span"
        DIV = "div"
        P = "p"
        CODE = "code"
        H1 = "h1"
        H2 = "h2"
        H3 = "h3"
        H4 = "h4"
        H5 = "h5"
        H6 = "h6"
        TABLE = "table"
        TR = "tr"
        TH = "th"
        TD = "td"
        DD = "dd"

    class Attrs:
        STYLE = "style"
        HREF = "href"
        SRC = "src"
        WIDTH = "width"
        HEIGHT = "height"
        TYPE = "type"

    TEXT_STYLE_DECORATION = ["underline", "line-through", "overline"]

    HEADINGS_TEXT_SIZE = {
        Tags.H1: 32,
        Tags.H2: 24,
        Tags.H3: 18,
        Tags.H4: 16,
        Tags.H5: 13,
        Tags.H6: 10,
    }

    ##UPCOMING STYLE ATTRIBUTES


"""
    style_attributes = [
            "box-shadow",
            "line-height",
            "letter-spacing",
            "word-spacing",
            "overflow",
            "position",
            "top",
            "right",
            "bottom",
            "left",
        ]
"""


def _parse_html_to_flet(element, base_url=""):
    if isinstance(element, NavigableString):
        cleaned_text = " ".join(element.split())
        if not cleaned_text:
            return None
        return ft.Text(cleaned_text)
    if element.name == _HTML.Tags.DIV:
        style, align_style = _get_style(element, is_a_mapping=True)

        # Map <div> to ft.Column
        main_container = ft.Container(
            content=ft.Row([], **align_style) if "alignment" in align_style else ft.Column([]),
            **style,
        )
        for child in element.children:
            if child.name:
                # If there's a table ,
                if child.name == _HTML.Tags.TABLE:
                    # Call "html_table_to_flet()" function to display the table
                    _html_table_to_flet(element, main_container)

                # Recursively parse child elements
                child_flet = _parse_html_to_flet(child, base_url=base_url)
                main_container.content.controls.append(child_flet)
        return main_container

    # Heading tags
    elif element.name in _HTML.HEADINGS_TEXT_SIZE.keys():
        heading_text = ft.Text(value=element.text, size=_HTML.HEADINGS_TEXT_SIZE[element.name])
        return heading_text
    # Paragraph tag
    # Paragraph tag - NOW USES SPANS FOR WRAPPING
    elif element.name == _HTML.Tags.P:
        style_props, align_style = _get_style(element, is_a_mapping=True)

        # We create ONE Text object and fill it with spans
        paragraph = ft.Text(
            spans=[],
            theme_style=ft.TextThemeStyle.BODY_LARGE,
            **style_props,  # Apply color, size, etc.
        )

        for child in element.children:
            if isinstance(child, NavigableString):
                paragraph.spans.append(ft.TextSpan(child))
            else:
                # Recursively get the Span version of nested tags
                # Note: We need a helper to return a TextSpan instead of a Widget
                paragraph.spans.append(_parse_inline_to_span(child, base_url))

        # Wrap in a Container if you need alignment/padding
        return ft.Container(content=paragraph, **align_style)

    # Link tag
    elif element.name == _HTML.Tags.A:
        href = element.get(_HTML.Attrs.HREF, "")
        full_url = urljoin(base_url, href) if href else ""
        # Map <a> to ft.Text with a URL
        link = ft.Text(
            spans=[
                ft.TextSpan(
                    element.text,
                    url=full_url,
                    style=ft.TextStyle(italic=True, color=ft.Colors.BLUE_200),
                )
            ]
        )
        return link

    # Image tag
    elif element.name == _HTML.Tags.IMG:
        img_style, _ = _get_style(element, is_a_mapping=True)

        # Map <img> to ft.Image with a source URL
        image = ft.Container(content=ft.Image(src=element.get(_HTML.Attrs.SRC)), **img_style)
        return image

    # _HTML lists
    elif element.name in [_HTML.Tags.UL, _HTML.Tags.OL]:
        # 'spacing' here controls the gap between bullet points
        list_container = ft.Column(spacing=4)

        items = element.find_all(_HTML.Tags.LI, recursive=False)
        text_size = 16
        line_height = 1.2  # Tighter line spacing for a compact look

        for i, li in enumerate(items):
            # 1. Define the leading element (Bullet or Number)
            if element.name == _HTML.Tags.UL:
                leading_widget = ft.Icon(ft.Icons.CIRCLE, size=6, color=ft.Colors.ON_SURFACE_VARIANT)
            else:
                leading_widget = ft.Text(f"{i + 1}.", size=text_size, weight=ft.FontWeight.BOLD)

            # 2. Build the row with precise vertical alignment
            list_item = ft.Row(
                controls=[
                    # The Container 'height' ensures the bullet is centered
                    # relative to the FIRST line of text specifically.
                    ft.Container(
                        content=leading_widget,
                        height=text_size * line_height,
                        alignment=ft.Alignment.CENTER,
                        width=20,  # Fixed width ensures text aligns horizontally
                    ),
                    ft.Text(
                        value=li.get_text(strip=True),
                        size=text_size,
                        expand=True,  # Allows text to wrap
                    ),
                ],
                vertical_alignment=ft.CrossAxisAlignment.START,
                spacing=5,  # Horizontal gap between bullet and text
            )

            list_container.controls.append(list_item)

        return ft.Container(content=list_container, padding=ft.Padding.only(left=10))

    # Bold Tags
    elif element.name == _HTML.Tags.B or element.name == _HTML.Tags.STRONG:
        bold_text = ft.Text(
            value=element.text,
            weight=ft.FontWeight.BOLD if element.name == _HTML.Tags.B else ft.FontWeight.W_900,
        )
        return bold_text

    # Italic Tag
    elif element.name == _HTML.Tags.I or element.name == _HTML.Tags.EM:
        italic_text = ft.Text(element.text, italic=True)
        return italic_text

    # Underline Tag
    elif element.name == _HTML.Tags.U:
        underlined_text = ft.Text(
            spans=[
                ft.TextSpan(
                    element.text,
                    style=ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE),
                )
            ]
        )
        return underlined_text
    # mark Tag
    elif element.name == _HTML.Tags.MARK:
        style_props, _ = _get_style(element, is_a_mapping=True)

        return ft.Text(
            spans=[
                ft.TextSpan(
                    element.text,
                    style=ft.TextStyle(**style_props),
                )
            ]
        )
    # Code Tag
    elif element.name == _HTML.Tags.CODE:
        return ft.Markdown(
            element.text,
            selectable=True,
            extension_set="gitHubWeb",
            code_theme="atom-one-dark",
        )
    elif element.name == _HTML.Tags.DD:
        # Create a container for the DD content
        list_item_container = ft.Column(spacing=5)

        # Parse the CHILDREN of the DD, not the DD itself
        for child in element.children:
            if child.name or (isinstance(child, NavigableString) and child.strip()):
                child_flet = _parse_html_to_flet(child, base_url=base_url)
                if child_flet:
                    list_item_container.controls.append(child_flet)

        return ft.Container(content=list_item_container, padding=ft.padding.only(left=20))
    # Span Tag
    elif element.name == _HTML.Tags.SPAN:
        span_style = _get_style(element)
        return ft.Text(spans=[ft.TextSpan(element.text, style=span_style[0])])

    else:
        # Default fallback: Process children of unknown tags without re-processing the parent
        container = ft.Column()
        for child in element.children:
            if child.name or (isinstance(child, NavigableString) and child.strip()):
                res = _parse_html_to_flet(child, base_url=base_url)
                if res:
                    container.controls.append(res)
        return container


# ____________________________________________________________________________________________________________________________________
# Parser function for html tables


def _html_table_to_flet(element, container):
    table = element.find("table", border="1")
    flet_table = ft.DataTable(columns=[], rows=[])

    if table is not None:
        for row in table.find_all("tr"):
            headers = row.find_all("th")
            columns = row.find_all("td")
            if headers != []:
                for i in range(len(headers)):
                    header_text = headers[i].text
                    flet_table.columns.append(ft.DataColumn(ft.Text(header_text)))

            if columns != []:
                data_cells = []
                for i in range(len(columns)):
                    cell_text = columns[i].text
                    data_cells.append(ft.DataCell(ft.Text(cell_text)))
                flet_table.rows.append(ft.DataRow(cells=data_cells))
        container.content.controls.append(flet_table)


def _parse_inline_styles(style_string):
    # ___________________________________________________________________________________________________________________________________
    # Associate html inline styles to the corresponding flet style properties
    # ____________________________________________________________________________________________________________________________________
    html_to_flet_style_mapping = {
        "color": "color",
        "background-color": "bgcolor",
        "font-family": "font_family",
        "font-size": "size",
        "text-align": "text_align",
        "text-decoration": "decoration",
        "display": "display",
        "justify-content": "alignment",
        "margin": "margin",
        "padding": "padding",
        "border-radius": "border_radius",
        "border": "border",
        "width": "width",
        "height": "height",
    }

    # Parse inline styles and convert to Flet properties
    style_properties = {}
    for style_declaration in style_string.split(";"):
        if ":" in style_declaration:
            property_name, property_value = style_declaration.split(":")
            property_name = property_name.strip()
            property_value = property_value.strip()

            # Convert property_name to Flet style name if needed
            property_name = html_to_flet_style_mapping.get(property_name, None)

            if property_name:
                # Map html text-decoration values to their corresponding Flet decoration values
                deco_values = {
                    "underline": ft.TextDecoration.UNDERLINE,
                    "line-through": ft.TextDecoration.LINE_THROUGH,
                    "overline": ft.TextDecoration.OVERLINE,
                }
                # Map html justify-content values to their corresponding Flet alignment values
                alignment_values = {
                    "flex-start": ft.MainAxisAlignment.START,
                    "center": ft.MainAxisAlignment.CENTER,
                    "flex-end": ft.MainAxisAlignment.END,
                    "space-between": ft.MainAxisAlignment.SPACE_BETWEEN,
                    "space-around": ft.MainAxisAlignment.SPACE_AROUND,
                    "space-evenly": ft.MainAxisAlignment.SPACE_EVENLY,
                }

                # Convert property_value to integer if it's a digit otherwise, keep the original value
                style_properties[property_name] = int(property_value) if property_value.isdigit() else property_value
                # handle decoration property
                if property_name == "decoration" and property_value in deco_values:
                    style_properties["decoration"] = deco_values[property_value]
                # handle border property
                elif property_name == "border" and property_value is not None:
                    property_value = property_value.split(" ")
                    style_properties["border"] = ft.border.all(property_value[0], property_value[-1])
                elif property_name == "alignment" and property_value in alignment_values:
                    style_properties["alignment"] = alignment_values[property_value]

    style_properties.pop("display", None)
    return style_properties


def _get_style(element, is_a_mapping: bool = False):
    alignment_props = {}
    if element.get(_HTML.Attrs.STYLE):
        style_props = _parse_inline_styles(element.get(_HTML.Attrs.STYLE))
        if "alignment" in style_props:
            val = style_props.pop("alignment")
            alignment_props = {"alignment": val}

        _style = style_props if is_a_mapping else ft.TextStyle(**style_props)

    else:
        _style = {}
    return _style, alignment_props


def _parse_inline_to_span(element, base_url=""):
    style_props, _ = _get_style(element, is_a_mapping=True)

    # Handle Bold
    if element.name in [_HTML.Tags.B, _HTML.Tags.STRONG]:
        return ft.TextSpan(element.text, style=ft.TextStyle(weight=ft.FontWeight.BOLD, **style_props))

    # Handle Italic
    elif element.name in [_HTML.Tags.I, _HTML.Tags.EM]:
        return ft.TextSpan(element.text, style=ft.TextStyle(italic=True, **style_props))

    # Handle Links
    elif element.name == _HTML.Tags.A:
        href = element.get(_HTML.Attrs.HREF, "")
        full_url = urljoin(base_url, href) if href else ""
        return ft.TextSpan(
            element.text,
            url=full_url,
            style=ft.TextStyle(
                italic=True,
                color=ft.Colors.BLUE_200,
                decoration=ft.TextDecoration.UNDERLINE,
                decoration_color=ft.Colors.BLUE_200,
            ),
        )

    # Default fallback for other inline tags
    return ft.TextSpan(element.text, style=ft.TextStyle(**style_props))


def convert_html_to_flet(html_content, base_url=""):
    soup = BeautifulSoup(html_content, "html.parser")
    flet_code = _parse_html_to_flet(soup, base_url=base_url)
    return flet_code


async def get_image_dimensions(url, target_height=300):
    """Asynchronous wrapper to offload blocking I/O to a thread."""
    # Pass arguments directly to asyncio.to_thread
    return await asyncio.to_thread(fetch_and_calculate, url, target_height)


def fetch_and_calculate(url, target_height=300):
    """The blocking worker function."""
    try:
        width, height = get_img_size(url)
        # Handle cases where image failed to load or has 0 height
        if height == 0:
            return 300  # Fallback width

        return calculate_scaled_width(width, height, target_height)
    except Exception as e:
        print(f"Error calculating dimensions for {url}: {e}")
        return 300  # Fallback width


def get_img_size(url):
    """Performs the network request and extracts image dimensions."""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        with Image.open(BytesIO(response.content)) as img:
            # .size returns (width, height)
            return img.size
    except Exception as e:
        print(f"Error getting image {url}: {e}")
        return 0, 0


def calculate_scaled_width(original_width, original_height, target_height):
    """Calculates width based on a fixed height while maintaining aspect ratio."""
    aspect_ratio = original_width / original_height
    return int(aspect_ratio * target_height)
