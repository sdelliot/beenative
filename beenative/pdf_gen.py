import io
import os
import re
from io import BytesIO
from pathlib import Path
from datetime import datetime

import segno
import requests
from models.plant import Plant
from reportlab.lib import colors
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPDF
from reportlab.platypus import Image, Table, Spacer, Flowable, Paragraph, TableStyle, SimpleDocTemplate
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter, landscape


class InlineSVG(Flowable):
    def __init__(self, source, width=12, color="#1B5E20"):
        Flowable.__init__(self)
        if hasattr(source, "read"):
            svg_text = source.read().decode("utf-8")
        else:
            with open(source, "r") as f:
                svg_text = f.read()

        # Color normalization for ReportLab compatibility
        if isinstance(color, colors.Color):
            color_str = f"#{color.hexval()[2:]}"
        elif isinstance(color, str):
            color_str = color.replace("0x", "#")
            if not color_str.startswith("#"):
                color_str = f"#{color_str}"
        else:
            color_str = "#1B5E20"

        # Regex to force color into the SVG paths
        svg_text = re.sub(r'fill="[^"]+"', f'fill="{color_str}"', svg_text)
        svg_text = re.sub(r'fill:\s*[^;"]+', f"fill:{color_str}", svg_text)
        if "fill=" not in svg_text and "fill:" not in svg_text:
            svg_text = svg_text.replace("<svg ", f'<svg fill="{color_str}" ')

        self.drawing = svg2rlg(BytesIO(svg_text.encode("utf-8")))

        # 1. Calculate Bounds ONCE and store the CONTENT dimensions
        bounds = self.drawing.getBounds()
        self._content_x = bounds[0]
        self._content_y = bounds[1]
        self._content_w = bounds[2] - bounds[0]
        self._content_h = bounds[3] - bounds[1]

        # Avoid division by zero for empty SVGs
        if self._content_w == 0:
            self._content_w = 1
        if self._content_h == 0:
            self._content_h = 1

        self.width = width
        # Initial height calculation
        self.height = self._content_h * (width / self._content_w)

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        # 2. FIX: Calculate scale based on CONTENT width, not drawing.width
        # This ensures the visible pixels expand to fill 'self.width' exactly
        scale = self.width / self._content_w

        self.canv.saveState()
        self.canv.scale(scale, scale)

        # 3. FIX: Shift using the stored content offsets
        # This aligns the top-left visible pixel to (0,0) on the canvas
        renderPDF.draw(self.drawing, self.canv, -self._content_x, -self._content_y)
        self.canv.restoreState()


class QRWithLogo(Flowable):
    def __init__(self, qr_stream, logo_path, size=1.0 * inch, logo_color="#1B5E20"):
        Flowable.__init__(self)
        self.qr = InlineSVG(qr_stream, width=size, color="#000000")
        self.logo_path = logo_path
        self.logo_color = logo_color
        self.width = self.qr.width
        self.height = self.qr.height

    def wrap(self, availWidth, availHeight):
        return self.width, self.height

    def draw(self):
        # 1. Center the QR Code in the container
        # Even if the container is rectangular, we draw the QR square
        qr_size = min(self.width, self.height)
        qr_x = (self.width - qr_size) / 2
        qr_y = (self.height - qr_size) / 2

        # Update QR width and draw
        self.qr.width = qr_size
        self.canv.saveState()
        self.canv.translate(qr_x, qr_y)
        self.qr.canv = self.canv
        self.qr.draw()
        self.canv.restoreState()

        # 2. Overlay the Logo (Centered relative to the CONTAINER)
        if os.path.exists(self.logo_path):
            # Logo is 22% of the QR code size (not the container width)
            logo_w = qr_size * 0.22
            logo = InlineSVG(self.logo_path, width=logo_w, color=self.logo_color)

            # Calculate offsets relative to the full container dimensions
            logo_offset_x = (self.width - logo.width) / 2
            logo_offset_y = (self.height - logo.height) / 2

            self.canv.saveState()
            self.canv.setFillColor(colors.white)

            # Draw White Box
            self.canv.rect(logo_offset_x - 1, logo_offset_y - 1, logo.width + 2, logo.height + 2, fill=1, stroke=0)

            # Draw Logo
            self.canv.translate(logo_offset_x, logo_offset_y)
            logo.canv = self.canv
            logo.draw()
            self.canv.restoreState()


def generate_qr_flowable(plant: Plant, size=0.8 * inch):
    target_url = plant.ncsu_url or plant.pm_url or plant.ncbg_permalink
    if not target_url:
        return None

    logo_path = FULL_ICON_MAP["Pollinators"]

    # Generate QR with High error correction (H)
    qr = segno.make(target_url, error="H")
    qr_buffer = BytesIO()
    qr.save(qr_buffer, kind="svg", border=1)
    qr_buffer.seek(0)

    # Return our fancy overlay class
    return QRWithLogo(qr_buffer, logo_path, size=size, logo_color="#1B5E20")


MONTH_ORDER = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def sort_bloom_dict(data):
    """Parses the JSON string and returns a list of (Month, Intensity) tuples in calendar order."""
    if not data:
        return []

    # Sort based on our master MONTH_ORDER
    return [(m_name, data[m_name]) for m_name in MONTH_ORDER if m_name in data]


def get_intensity_color(base_color, intensity):
    """
    Returns the base color for peak (2),
    or a manually faded version for partial (1).
    """
    if intensity == 2:
        return base_color

    # Manually 'fade' the color to 40% white
    # Formula: (BaseColor * 0.6) + (White * 0.4)
    return colors.Color(
        red=(base_color.red * 0.6) + (1.0 * 0.4),
        green=(base_color.green * 0.6) + (1.0 * 0.4),
        blue=(base_color.blue * 0.6) + (1.0 * 0.4),
        alpha=1,
    )


def sort_categories(plant_categories, master_order):
    """
    Sorts the categories found in the plant data to match the botanical order.
    """
    if not plant_categories:
        return []

    # Sort based on the index in our master_order list
    # Items not in master_order will be pushed to the end
    return sorted(plant_categories, key=lambda x: master_order.index(x) if x in master_order else 999)


# 1. Global Color Mappings (Best kept outside for performance/reusability)
SUN_MAP = {
    "Full Sun": colors.HexColor("#FFD600"),  # Amber 700-ish
    "Partial Shade": colors.HexColor("#FFF176"),  # Yellow 300
    "Dappled Sunlight": colors.HexColor("#E0E0E0"),  # Grey 300
    "Deep Shade": colors.HexColor("#90A4AE"),  # Blue Grey 300
}

# Flet-matched Moisture Map
MOIST_MAP = {
    "Wet": colors.HexColor("#0D47A1"),  # Blue 900
    "Medium-Wet": colors.HexColor("#1976D2"),  # Blue 700
    "Medium": colors.HexColor("#42A5F5"),  # Blue 400
    "Medium-Dry": colors.HexColor("#90CAF9"),  # Blue 200
    "Dry": colors.HexColor("#E3F2FD"),  # Blue 50
}

# The order in which you want categories to appear in the PDF bar
SUN_ORDER = ["Full Sun", "Partial Shade", "Dappled Sunlight", "Deep Shade"]
MOIST_ORDER = ["Wet", "Medium-Wet", "Medium", "Medium-Dry", "Dry"]

# Flet-style Light Mode Colors (Converted to ReportLab Hex)
FLET_WILDLIFE_TEXT = colors.HexColor("#1B5E20")  # Green 800
FLET_WILDLIFE_BG = colors.HexColor("#E8F5E9")  # Green 50
FLET_RESIST_TEXT = colors.HexColor("#C62828")  # Red 800
FLET_RESIST_BG = colors.HexColor("#FFEBEE")  # Red 5

# Base directory for your icons


BASE_DIR = Path(__file__).resolve().parent
ICON_DIR = BASE_DIR / "assets" / "static" / "icons"

# Comprehensive mapping of Plant Attributes to your downloaded SVGs
ICON_MAPPING = {
    # --- Wildlife / Attracts ---
    "Bats": "bedtime_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Bees": "emoji_nature_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Specialized Bees": "hive_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Birds": "raven_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Songbirds": "music_note_2_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Hummingbirds": "flight_takeoff_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Butterflies": "keyboard_command_key_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Moths": "drone_2_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Pollinators": "local_florist_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Predatory Insects": "pest_control_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Frogs": "water_drop_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Small Mammals": "pets_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    # --- Resistances ---
    "Deer": "nature_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Rabbits": "cruelty_free_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Voles": "pest_control_rodent_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Slugs": "gesture_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Drought": "mode_heat_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Dry Soil": "salinity_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Wet Soil": "flood_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Salt": "waves_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Pollution": "factory_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Urban Conditions": "location_city_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Erosion": "landslide_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Black Walnut": "do_not_disturb_on_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Foot Traffic": "do_not_step_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Compaction": "compress_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Heavy Shade": "blinds_closed_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Diseases": "coronavirus_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Storm Damage": "thunderstorm_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Insect Pests": "pest_control_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Heat": "device_thermostat_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Humidity": "dew_point_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Wind": "air_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
    "Poor Soil": "skull_24dp_E3E3E3_FILL0_wght400_GRAD0_opsz24.svg",
}

FLOWER_COLOR_MAP = {
    "white": colors.HexColor("#E0E0E0"),  # Grey 300 (Visible on white)
    "yellow": colors.HexColor("#FFCA28"),  # Amber 400
    "gold": colors.HexColor("#FFA000"),  # Amber 700
    "orange": colors.HexColor("#F57C00"),  # Orange 700
    "red": colors.HexColor("#D32F2F"),  # Red 700
    "pink": colors.HexColor("#F06292"),  # Pink 300
    "purple": colors.HexColor("#AB47BC"),  # Purple 400
    "violet": colors.HexColor("#7E57C2"),  # Deep Purple 400
    "blue": colors.HexColor("#1976D2"),  # Blue 700
    "green": colors.HexColor("#388E3C"),  # Green 700
    "brown": colors.HexColor("#795548"),  # Brown 600
    "cream": colors.HexColor("#FBE9E7"),  # Deep Orange 50 (Soft cream)
    "maroon": colors.HexColor("#B71C1C"),  # Red 900
}

# --- Usage in generate_plant_pdf ---
# This creates a lookup dict with absolute or relative paths
FULL_ICON_MAP = {k: os.path.join(ICON_DIR, v) for k, v in ICON_MAPPING.items()}


def get_bloom_colors(plant: Plant):
    """Returns the hex colors for the plant's flowers."""
    raw_colors = plant.flower_colors

    # Map to our PDF colors, default to Green 800 if not found
    return [FLOWER_COLOR_MAP.get(c.lower(), FLET_WILDLIFE_TEXT) for c in raw_colors]


def p_text(text, style=None, alignment=1, custom_color=None, custom_size=None):
    """
    Advanced paragraph helper.
    Uses 'Normal' as base unless 'style' is provided, then applies overrides.
    """
    # Use provided style or default to Normal
    styles = getSampleStyleSheet()
    base_style = style if style else styles["Normal"]
    p_style = base_style.clone("dynamic_p")

    # Apply overrides
    p_style.alignment = alignment
    if custom_color:
        p_style.textColor = custom_color
    if custom_size:
        p_style.fontSize = custom_size
        p_style.leading = custom_size + 2

    return Paragraph(text, p_style)


def get_pdf_caption(info):
    """Returns an XML string for ReportLab Paragraphs."""
    if not info:
        return ""

    parts = []

    # Title (Linked)
    if info["source_url"]:
        parts.append(f'<a href="{info["source_url"]}" color="#1976D2">"{info["title"]}"</a>')
    else:
        parts.append(f'"{info["title"]}"')

    # Author
    parts.append(f" by {info['author']}")

    # License
    if info["license_text"]:
        if info["license_url"]:
            parts.append(f' (<a href="{info["license_url"]}" color="#1976D2">{info["license_text"]}</a>)')
        else:
            parts.append(f" ({info['license_text']})")

    return "".join(parts) + "."


def create_justified_photo_gallery(selected_images, available_width, qr_flowable=None):
    """
    Creates a modern, justified photo grid where images are scaled to fill rows perfectly.
    The QR code is integrated as the first 'photo'.
    """
    if not selected_images and not qr_flowable:
        return []

    elements = []
    styles = getSampleStyleSheet()

    # --- Justified Row Logic ---
    TARGET_HEIGHT = 1.7 * inch  # Ideal height for the first row
    spacing = 10

    # 1. Fetch and Pre-process Image Dimensions
    processed_items = []

    # Treat QR code as a 1:1 aspect ratio 'image'
    if qr_flowable:
        processed_items.append({"obj": qr_flowable, "aspect": 1.0, "caption": "Scan for more details"})

    for img_data in selected_images or []:
        url = img_data.get("thumbnail_url") or img_data.get("original_url")
        caption_xml = get_pdf_caption(img_data)
        try:
            resp = requests.get(url, timeout=10)
            img = Image(BytesIO(resp.content))
            aspect = img.imageWidth / float(img.imageHeight)
            processed_items.append({"obj": img, "aspect": aspect, "caption": caption_xml})
        except requests.ConnectTimeout:
            continue

    if not processed_items:
        return []

    # 2. Group into Rows and Scale
    current_row = []
    current_row_aspect_sum = 0

    for item in processed_items:
        current_row.append(item)
        current_row_aspect_sum += item["aspect"]

        # Determine if row is "full" enough to justify
        if (current_row_aspect_sum * TARGET_HEIGHT) > (available_width * 0.85):
            total_spacing = spacing * (len(current_row) - 1)
            row_height = (available_width - total_spacing) / current_row_aspect_sum

            row_content = []
            row_widths = []
            for r_item in current_row:
                w = row_height * r_item["aspect"]
                # Apply calculated dimensions
                if isinstance(r_item["obj"], Image):
                    r_item["obj"].drawWidth, r_item["obj"].drawHeight = w, row_height
                else:  # Handle QR Flowable
                    r_item["obj"].width, r_item["obj"].height = w, row_height

                caption = Paragraph(r_item["caption"], styles["Normal"].clone("tiny", fontSize=6, alignment=1))
                unit = Table([[r_item["obj"]], [caption]], colWidths=[w])
                unit.setStyle(
                    TableStyle(
                        [
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ]
                    )
                )
                row_content.append(unit)
                row_widths.append(w + spacing)

            t = Table([row_content], colWidths=row_widths)
            t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
            elements.append(t)
            elements.append(Spacer(1, spacing))

            current_row, current_row_aspect_sum = [], 0

    # 3. Handle Remaining Images (Last row - no justification stretching)
    if current_row:
        row_content, row_widths = [], []
        for r_item in current_row:
            w = TARGET_HEIGHT * r_item["aspect"]
            if isinstance(r_item["obj"], Image):
                r_item["obj"].drawWidth, r_item["obj"].drawHeight = w, TARGET_HEIGHT
            else:
                r_item["obj"].width, r_item["obj"].height = w, TARGET_HEIGHT

            caption = Paragraph(
                r_item["caption"], styles["Normal"].clone("tiny", textColor=colors.grey, fontSize=6, alignment=1)
            )
            unit = Table([[r_item["obj"]], [caption]], colWidths=[w])
            row_content.append(unit)
            row_widths.append(w + spacing)

        t = Table([row_content], colWidths=row_widths, hAlign="LEFT")
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
        elements.append(t)

    return elements


def generate_plant_pdf(plant: Plant, selected_images=None):
    buffer = io.BytesIO()
    PAGE_WIDTH = 11 * inch
    MARGIN = 15
    AVAILABLE_WIDTH = PAGE_WIDTH - (2 * MARGIN)

    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(letter), rightMargin=MARGIN, leftMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN
    )
    elements = []
    styles = getSampleStyleSheet()

    # --- Styles ---
    LEFT_COLUMN_WIDTH = 4.0 * inch
    RIGHT_COLUMN_WIDTH = 6 * inch
    SPACER_COLUMN_WIDTH = AVAILABLE_WIDTH - LEFT_COLUMN_WIDTH - RIGHT_COLUMN_WIDTH

    scientific_style = styles["Title"].clone("SciName", alignment=0, fontSize=24, spaceAfter=12)
    common_name_style = styles["Normal"].clone("CommonNames", textColor=colors.grey, fontSize=12)

    section_header_style = styles["Normal"].clone(
        "SectionHeader",
        fontSize=12,
        leading=10,
        alignment=1,  # Centered
        fontName="Helvetica-Bold",
        textColor=colors.grey,
        spaceAfter=4,
    )

    # --- Internal Helpers ---
    def get_contrast_color(bg_color):
        luminance = (0.299 * bg_color.red) + (0.587 * bg_color.green) + (0.114 * bg_color.blue)
        return colors.white if luminance < 0.5 else colors.black

    def draw_footer(canvas, doc):
        canvas.saveState()
        # Footer text
        footer_text = f"BeeNative Plant Data Sheet | Generated: {datetime.now().astimezone().strftime('%Y-%m-%d')}"
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)

        # Draw text (Centered)
        canvas.drawCentredString(doc.pagesize[0] / 2, 0.4 * inch, footer_text)

        # Draw Page Number (Right)
        canvas.drawRightString(doc.pagesize[0] - MARGIN, 0.4 * inch, f"Page {doc.page}")
        canvas.restoreState()

    def create_segmented_bar(categories, color_map, total_width):
        if not categories:
            return Table([[p_text("N/A")]], colWidths=[total_width])

        col_width = total_width / len(categories)
        row_content = []

        # We define a list of background colors for the cells
        cell_styles = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            # Add rounded corners to the entire bar container
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ]

        for i, cat in enumerate(categories):
            bg_color = color_map.get(cat, colors.lightgrey)
            text_color = get_contrast_color(bg_color)

            # 12pt centered text to match headers
            cell_style = styles["Normal"].clone(
                f"bar_{cat}",
                alignment=1,
                fontSize=10,  # Slightly smaller than headers to fit
                textColor=text_color,
            )

            row_content.append(Paragraph(cat, cell_style))
            cell_styles.append(("BACKGROUND", (i, 0), (i, 0), bg_color))

        t = Table([row_content], colWidths=[col_width] * len(categories))
        t.setStyle(TableStyle(cell_styles))
        return t

    def create_bloom_legend(primary_color, total_width):
        """Creates a small legend right-justified below the bloom bar."""
        peak_color = primary_color
        partial_color = get_intensity_color(primary_color, 1)

        def make_swatch(color):
            t = Table([[""]], colWidths=[10], rowHeights=[10])
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (0, 0), color),
                        ("BOX", (0, 0), (0, 0), 0.5, colors.grey),
                        ("ROUNDEDCORNERS", [2, 2, 2, 2]),
                    ]
                )
            )
            return t

        # Legend contents
        legend_data = [
            [
                make_swatch(peak_color),
                p_text("Peak Bloom", alignment=0, custom_size=8),
                # Spacer(10, 1), # Small gap between the two legend items
                make_swatch(partial_color),
                p_text("Potential Bloom", alignment=0, custom_size=8),
            ]
        ]

        # ColWidths: None tells ReportLab to shrink-wrap the content
        # hAlign='RIGHT' pushes the whole table to the right edge of the column
        t = Table(legend_data, colWidths=[12, 50, 12, None], hAlign="RIGHT")
        t.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 2),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return t

    def create_bloom_bar(bloom_dict, flower_colors_list, total_width):
        sorted_data = sort_bloom_dict(bloom_dict)
        if not sorted_data:
            return None

        # Pick primary flower color
        primary_color = flower_colors_list[0] if flower_colors_list else FLET_WILDLIFE_TEXT

        num_segments = len(sorted_data)
        col_width = total_width / num_segments

        row_content = []
        cell_styles = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]

        for i, (month, intensity) in enumerate(sorted_data):
            bg_color = get_intensity_color(primary_color, intensity)
            text_color = get_contrast_color(bg_color)

            # Peak blooms (2) get bold text, partial (1) get normal
            weight = "Helvetica-Bold" if intensity == 2 else "Helvetica"
            month_style = styles["Normal"].clone(
                f"bloom_{month}", fontSize=10, fontName=weight, textColor=text_color, alignment=1
            )

            row_content.append(Paragraph(month, month_style))
            cell_styles.append(("BACKGROUND", (i, 0), (i, 0), bg_color))

        # Add white dividers between months
        if num_segments > 1:
            cell_styles.append(("GRID", (0, 0), (-1, -1), 1, colors.white))

        t = Table([row_content], colWidths=[col_width] * num_segments)
        t.setStyle(TableStyle(cell_styles))
        return t

    def create_badge_row(attributes, attr_type, label_text, max_width):
        if not attributes:
            return []

        # Determine colors based on type
        if attr_type == "wildlife":
            text_color, bg_color = FLET_WILDLIFE_TEXT, FLET_WILDLIFE_BG
        else:
            text_color, bg_color = FLET_RESIST_TEXT, FLET_RESIST_BG

        badges = []
        for attr in attributes:
            # 1. Setup SVG with matching text color
            badge_contents = []
            svg_path = FULL_ICON_MAP.get(attr)
            if svg_path and os.path.exists(svg_path):
                # Using 12pt icon to match 12pt text
                badge_contents.append(InlineSVG(svg_path, width=16, color=text_color.hexval()))

            # 2. Text Style (12pt)
            p_style = styles["BodyText"].clone("badge_p", fontSize=10, leading=14, textColor=text_color)
            badge_contents.append(Paragraph(attr, p_style))

            # 3. Inner Table (Tighten spacing between icon and text)
            inner_table = Table([badge_contents], colWidths=[18, None], hAlign="LEFT")
            inner_table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 0),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 0),  # Tight gap
                    ]
                )
            )

            # 4. Outer Pill Table
            pill = Table([[inner_table]], colWidths=None, hAlign="LEFT")
            pill.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), bg_color),
                        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ]
                )
            )
            badges.append(pill)

        # --- WRAPPING LOGIC (Adjusted for 12pt width) ---
        rows, current_row, current_w = [], [], 0
        for b in badges:
            attr_name = attributes[badges.index(b)]
            # Heuristic for 12pt: ~7.5pts per char + 25pts for icon/padding
            est_w = (len(attr_name) * 7.5) + 25
            if current_w + est_w > max_width:
                rows.append(current_row)
                current_row, current_w = [b], est_w
            else:
                current_row.append(b)
                current_w += est_w
        if current_row:
            rows.append(current_row)

        return [
            p_text(f"<b>{label_text}</b>", alignment=0),
            Table(
                rows,
                hAlign="LEFT",
                colWidths=None,
                style=[
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),  # Space between tag lines
                ],
            ),
        ]

    # --- Build Right Column ---

    # 1. Gather all right-side elements into a list
    # 1. Define your data
    headers = ["Germ. Code(s)", "Family", "Life Cycle", "Growth Forms", "Height"]

    plant_categories = plant.plant_categories
    if not plant_categories:
        plant_categories = ["Not Specified"]

    germ_code = plant.pm_germination_code
    if not germ_code:
        germ_code = ["Not Specified"]

    family = plant.ncsu_family
    if not family:
        family = "Not Specified"

    lifecycle = plant.primary_lifecycle
    if not lifecycle:
        lifecycle = "Not Specified"

    height_str = plant.height_str
    if not height_str:
        height_str = "Not Specified"

    data_row = [
        ", ".join(germ_code),
        family,
        ", ".join(lifecycle),
        ", ".join(plant_categories),
        height_str,
    ]

    # 2. Calculate dynamic widths
    # This divides the total available width by the number of columns (5)
    num_cols = len(headers)
    dynamic_widths = [RIGHT_COLUMN_WIDTH / num_cols] * num_cols

    # 3. Build the table
    right_stack = [
        # 1. Main Info Grid (Top)
        [
            Table(
                [
                    [p_text(h, alignment=1) for h in headers],  # Header Row
                    [p_text(d, alignment=1) for d in data_row],  # Data Row
                ],
                colWidths=dynamic_widths,
                style=[
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),  # Dropped to 7pt to help fit 5 columns
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ],
            )
        ],
        # [Spacer(1, 10)],
    ]

    # 1. Prepare the Bars
    sorted_sun = sort_categories(plant.sunlight_categories, SUN_ORDER)
    sun_bar = create_segmented_bar(sorted_sun, SUN_MAP, (RIGHT_COLUMN_WIDTH / 2) - 5)

    sorted_moist = sort_categories(plant.moisture_categories, MOIST_ORDER)
    moist_bar = create_segmented_bar(sorted_moist, MOIST_MAP, (RIGHT_COLUMN_WIDTH / 2) - 5)

    # 2. Create Combined Headers
    # We use alignment=0 (Left) and alignment=2 (Right) for the headers to match the bars
    sun_header = p_text("<b>Sun Exposure</b>", alignment=1, custom_color=colors.gray, custom_size=10)
    moist_header = p_text("<b>Soil Moisture</b>", alignment=1, custom_color=colors.gray, custom_size=10)

    # 3. Build the Side-by-Side Table
    # Row 1: Headers | Row 2: Bars
    exposure_table = Table([[sun_header, moist_header], [sun_bar, moist_bar]], colWidths=[RIGHT_COLUMN_WIDTH / 2.0] * 2)

    exposure_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (1, 0), 2),  # Small gap between header and bar
            ]
        )
    )

    # 4. Add to the right stack
    right_stack.append([exposure_table])

    bloom_dict = plant.bloom_months
    if bloom_dict:
        flower_colors = get_bloom_colors(plant)
        primary_color = flower_colors[0] if flower_colors else FLET_WILDLIFE_TEXT
        bloom_bar = create_bloom_bar(bloom_dict, flower_colors, RIGHT_COLUMN_WIDTH)

        if bloom_bar:
            right_stack.append([Paragraph("Bloom Season", section_header_style)])
            right_stack.append([bloom_bar])
            # Add the legend here
            if len(flower_colors) > 1:
                right_stack.append([create_bloom_legend(primary_color, RIGHT_COLUMN_WIDTH)])

    # 4. Wildlife Badges (Centered Title)
    wildlife = create_badge_row(plant.wildlife_attracts, "wildlife", "Attracts", RIGHT_COLUMN_WIDTH)
    if wildlife:
        right_stack.append([Paragraph("Attracts", section_header_style)])
        right_stack.append([wildlife[1]])  # Just the badge row, header is now manual

    # 5. Resistance Badges (Centered Title)
    resist = create_badge_row(plant.plant_resistances, "resistance", "Resistances", RIGHT_COLUMN_WIDTH)
    if resist:
        right_stack.append([Paragraph("Resistances", section_header_style)])
        right_stack.append([resist[1]])

    qr_flowable = generate_qr_flowable(plant, size=1.5 * inch)
    if not selected_images and qr_flowable:
        qr_table = Table([[qr_flowable]], colWidths=[RIGHT_COLUMN_WIDTH])
        qr_table.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT")]))
        right_stack.append([qr_table])

    # Assemble the final column
    right_side_table = Table(right_stack, colWidths=[RIGHT_COLUMN_WIDTH])
    right_side_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    # --- Build Left Column (Common names + Map + Badges) ---
    map_raw_path = plant.vasc_map_file_path
    map_url = plant.vasc_map_file_url
    assets_dir = os.getenv("FLET_ASSETS_DIR", "static")
    map_path = Path(assets_dir) / map_raw_path if map_raw_path else None

    # 1. Attempt Local File, then URL
    map_img = None
    if map_path and map_path.exists():
        map_img = Image(str(map_path.absolute()))
    elif map_url:
        try:
            resp = requests.get(map_url, timeout=5)
            if resp.status_code == 200:
                map_img = Image(BytesIO(resp.content))
        except Exception:
            pass  # Fallback handled below

    # 2. Handle Success vs Failure
    if map_img:
        # Ensure dimensions exist before calculation
        img_w = map_img.imageWidth
        img_h = map_img.imageHeight

        aspect = img_h / float(img_w)
        map_img.drawWidth = LEFT_COLUMN_WIDTH
        map_img.drawHeight = LEFT_COLUMN_WIDTH * aspect
    else:
        # Use a placeholder if both methods failed
        map_img = p_text("[Map Data Unavailable]", style=styles["Italic"])

    left_stack = [
        [p_text(", ".join(plant.all_common_names), style=common_name_style, alignment=0)],
        [Spacer(1, 8)],
        [map_img],
        [Spacer(1, 8)],
    ]

    # 3. Create the final Left Column Table
    left_side_table = Table(left_stack, colWidths=[LEFT_COLUMN_WIDTH])
    left_side_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    left_side_table = Table(left_stack, colWidths=[LEFT_COLUMN_WIDTH])

    # --- Page Assembly ---
    elements.append(p_text(f"<b>{plant.scientific_name}</b>", scientific_style, alignment=0))

    # TODO: If we use this, update with the right field
    # Add a full-width description if it exists
    # description = plant.description_text #
    # if description:
    #     elements.append(Spacer(1, 20))
    #     elements.append(HRFlowable(width="100%", thickness=1, color=colors.lightgrey))
    #     elements.append(Spacer(1, 10))
    #     elements.append(Paragraph("<b>Description</b>", section_header_style))
    #     elements.append(Paragraph(description, styles['BodyText']))

    # This aligns the subtitle/map column and the data column at the top
    master_layout = Table(
        [[left_side_table, "", right_side_table]],
        colWidths=[LEFT_COLUMN_WIDTH, SPACER_COLUMN_WIDTH, RIGHT_COLUMN_WIDTH],
    )
    master_layout.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]))

    elements.append(master_layout)

    # --- ADD THE PHOTO GALLERY ---
    if selected_images:
        # Pass the QR flowable to the gallery function to use as the first item
        gallery_elements = create_justified_photo_gallery(selected_images, AVAILABLE_WIDTH, qr_flowable=qr_flowable)
        elements.extend(gallery_elements)

    # Build the document
    doc.build(elements, onFirstPage=draw_footer, onLaterPages=draw_footer)
    buffer.seek(0)
    return buffer
