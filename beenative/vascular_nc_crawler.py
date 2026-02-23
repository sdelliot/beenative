import os
import time
import requests
from bs4 import BeautifulSoup
from typing import Callable, Optional
import polars as pl
from urllib.parse import urljoin, urlparse
from beenative.settings import settings


def get_native_plant_ids(file_path: str):
    """Parses local HTML to find IDs of native plants."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Source file {file_path} not found.")

    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    native_ids = []
    rows = soup.find_all("tr")

    ## Colors
    #  - #ffbb99 (Exotic): Frequently used for non-native, naturalized, or exotic species such as Epipactis helleborine, Zea mays (Corn), and Hedera helix (English Ivy).
    #  - #ffe699 (Uncertain): Often associated with varieties or specific taxonomic statuses, such as Pycnanthemum verticillatum var. verticillatum or Malus glaucescens.
    #  - #ffff99 (Not Valid): Used for specific entries like Hedera hibernica.
    #  - #eeccff (Not in NC): Seen in rows for specific conservation or taxonomic notes, such as for certain Hymenocallis entries.
    #  - #c6d9ec (Hybrid): Used for hybrid species, such as Populus x jackii.
    non_native_colors = {"#ffbb99", "#eeccff", "#ffe699", "#ffff99"}

    for row in rows:
        cells = row.find_all("td")
        if not cells:
            continue

        is_native = True
        for cell in cells:
            style = cell.get("style", "")
            if any(color in style.lower() for color in non_native_colors):
                is_native = False
                break

        if is_native:
            form = row.find("form", {"action": "species_account.php"})
            if form:
                plant_id_input = form.find("input", {"name": "id"})
                if plant_id_input:
                    native_ids.append(plant_id_input["value"])

    return native_ids


def download_plant_data(plant_ids: list, delay: float = 1.0, progress_callback: Optional[Callable] = None):
    """
    Executes POST requests and saves files.
    progress_callback: A function to call after each item is processed.
    """
    if not os.path.exists(settings.crawl_dir):
        os.makedirs(settings.crawl_dir)

    new_downloads = 0
    skipped_count = 0

    for plant_id in plant_ids:
        file_path = os.path.join(settings.crawl_dir, f"{plant_id}.html")

        if os.path.exists(file_path):
            skipped_count += 1
            if progress_callback:
                progress_callback()
            continue

        payload = {"id": plant_id, "submit_form": " Account "}

        try:
            response = requests.post(
                settings.vascular_nc_target_url, headers=settings.vascular_nc_headers, data=payload
            )
            response.raise_for_status()

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(response.text)

            new_downloads += 1
            # For rate limiting
            time.sleep(delay)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching ID {plant_id}: {e}")

        if progress_callback:
            progress_callback()

    return new_downloads, skipped_count


def download_map_image(soup: BeautifulSoup, plant_id: str) -> Optional[str]:
    """Finds, downloads, and returns the local path of the map image."""
    if not os.path.exists(settings.download_maps_dir):
        os.makedirs(settings.download_maps_dir)

    # Find the img tag with the map
    img_tag = soup.find("img", attrs={"usemap": "#Map"})
    if not img_tag or not img_tag.get("src"):
        return None

    # Clean the URL: strip query parameters
    raw_src = img_tag["src"]
    clean_path = urlparse(raw_src).path  # removes ?MT=...
    full_url = urljoin(settings.vascular_nc_base_url, clean_path)

    # Define local filename
    file_extension = os.path.splitext(clean_path)[1]
    local_filename = f"{plant_id}{file_extension}"
    local_path = os.path.join(settings.download_maps_dir, local_filename)

    # Download if not exists
    if not os.path.exists(local_path):
        try:
            response = requests.get(full_url, stream=True)
            response.raise_for_status()
            with open(local_path, "wb") as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
        except Exception:
            return None

    return local_path, full_url


def parse_species_file(file_path: str, include_map: bool = True) -> dict:
    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    plant_id = os.path.basename(file_path).replace(".html", "")
    data = {"id": plant_id}

    # 1. Parsing the Header Section
    # Example: Account for Slender Clubmoss - Pseudolycopodiella caroliniana (L.) Holub
    header_td = soup.find("td", colspan="9")
    if header_td and header_td.strong:
        text = header_td.strong.get_text(strip=True)
        if "Account for" in text:
            clean_text = text.replace("Account for", "")
            # Split by dash to separate common name from scientific
            parts = clean_text.split(" -")
            data["common_name_primary"] = parts[0].strip()

            # Use the <i> tag inside for the scientific name
            sci_tag = header_td.strong.find("i")
            if sci_tag:
                data["scientific_name"] = sci_tag.text.strip()
                # Author is usually what remains after the <i> tag
                data["author"] = sci_tag.next_sibling.strip() if sci_tag.next_sibling else ""

    # 2. Target the SECOND instance of the POST form
    forms = soup.find_all("form", attrs={"method": "POST", "action": "species_account.php"})
    if len(forms) >= 2:
        target_form = forms[1]  # Index 1 is the second instance
        alt_table = target_form.find("table", class_="alternate")

        if alt_table:
            # We iterate through all <strong> tags in the table
            labels = alt_table.find_all("strong")
            for label_tag in labels:
                label_text = label_tag.get_text(strip=True).lower()
                clean_label = label_text.replace(" ", "_").replace("(s)", "s").replace(":", "")

                # NAVIGATION LOGIC:
                # The label is in a <td>. We need the <td> immediately following it.
                parent_td = label_tag.find_parent("td")
                value_td = parent_td.find_next_sibling("td")

                if value_td:
                    # FIX: Instead of get_text() which recurses into unclosed tags,
                    # we only take the strings that are DIRECT children of this <td>.
                    # We join them to handle cases with <br> tags.
                    parts = [s.strip() for s in value_td.find_all(string=True, recursive=False) if s.strip()]
                    data[clean_label] = " ".join(parts)

    # 3. Map File Path (Retooled)
    if include_map:
        data["map_file_path"], data["map_file_url"] = download_map_image(soup, plant_id)

    return data


def build_dataframe(
    files: list, include_maps: bool = False, progress_callback: Optional[Callable] = None
) -> pl.DataFrame:
    """
    Aggregates all parsed dictionaries into a single Polars DataFrame.
    """
    records = []

    for f in files:
        records.append(parse_species_file(f, include_map=include_maps))
        if progress_callback:
            progress_callback()

    return pl.DataFrame(records)
