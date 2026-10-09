import time
from typing import Callable, Optional
from pathlib import Path
from urllib.parse import urljoin, urlparse

import polars as pl
import requests
from bs4 import BeautifulSoup

from beenative.settings import settings


def get_plant_provenance_records(file_path: str):
    """
    Parses local HTML to extract plant IDs along with their
    determined provenance status and notes based on table row colors and text ranks.
    """
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        raise FileNotFoundError(f"Source file {file_path} not found.")

    with file_path_obj.open("r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    plant_records = []
    rows = soup.find_all("tr")

    # Background color mapping based on your notes:
    # - #ffbb99: Exotic
    # - #ffe699: Uncertain
    # - #ffff99 / #eeccff: Not valid / Not in NC / Exotics

    for row in rows:
        cells = row.find_all("td")
        if not cells:
            continue

        provenance_status = "native"
        notes_parts = []

        for cell in cells:
            style = cell.get("style", "").lower()
            cell_text = cell.get_text(strip=True)

            # 1. Check background colors
            if "#ffe699" in style:
                provenance_status = "uncertain"
                break
            elif "#ffbb99" in style:
                provenance_status = "non_native_benign"
            elif "#eeccff" in style or "#ffff99" in style:
                provenance_status = "non_native_benign"

            # 2. Look for SE? explicitly in text cells (State rank column)
            if "se?" in cell_text.lower():
                provenance_status = "uncertain"
                notes_parts.append(f"State rank indicates uncertainty: {cell_text}")
                break

        # Find the species account form ID
        form = row.find("form", {"action": "species_account.php"})
        if form:
            plant_id_input = form.find("input", {"name": "id"})
            if plant_id_input and provenance_status in {"native", "uncertain"}:
                plant_id = plant_id_input["value"]
                plant_records.append({
                    "id": plant_id,
                    "provenance_status": provenance_status,
                    "provenance_notes": "; ".join(notes_parts) if notes_parts else None
                })

    return plant_records


def download_plant_data(plant_ids: list, delay: float = 1.0, progress_callback: Optional[Callable] = None):
    """
    Executes POST requests and saves files.
    progress_callback: A function to call after each item is processed.
    """
    crawl_dir = Path(settings.crawl_dir)
    if not crawl_dir.exists():
        crawl_dir.mkdir(parents=True)

    new_downloads = 0
    skipped_count = 0

    for plant_id in plant_ids:
        file_path = crawl_dir / f"{plant_id}.html"

        if file_path.exists():
            skipped_count += 1
            if progress_callback:
                progress_callback()
            continue

        payload = {"id": plant_id, "submit_form": " Account "}

        try:
            response = requests.post(
                settings.vascular_nc_target_url,
                headers=settings.vascular_nc_headers,
                data=payload,
                timeout=settings.crawl_timout,
            )
            response.raise_for_status()

            with file_path.open("w", encoding="utf-8") as f:
                f.write(response.text)

            new_downloads += 1
            # For rate limiting
            time.sleep(delay)

        except requests.exceptions.RequestException as e:
            print(f"Error fetching ID {plant_id}: {e}")

        if progress_callback:
            progress_callback()

    return new_downloads, skipped_count


def download_map_image(soup: BeautifulSoup, plant_id: str, should_download: bool = False) -> Optional[str]:
    """Finds, downloads, and returns the local path of the map image."""
    if not Path(settings.download_maps_dir).exists():
        Path(settings.download_maps_dir).mkdir(parents=True)

    # Find the img tag with the map
    img_tag = soup.find("img", attrs={"usemap": "#Map"})
    if not img_tag or not img_tag.get("src"):
        return None, None

    # Clean the URL: strip query parameters
    raw_src = img_tag["src"]
    clean_path = urlparse(raw_src).path  # removes ?MT=...
    full_url = urljoin(settings.vascular_nc_base_url, clean_path)

    # Define local filename
    file_extension = Path(clean_path).suffix
    local_filename = Path(f"{plant_id}{file_extension}")
    local_path = Path(settings.download_maps_dir) / local_filename

    # Download if not exists
    if should_download and not local_path.exists():
        try:
            response = requests.get(full_url, stream=True, timeout=settings.crawl_timout)
            response.raise_for_status()
            with local_path.open("wb") as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
        except Exception:
            return None, None

    return str(local_path), str(full_url)


def parse_species_file(file_path: str, include_map: bool = True) -> dict:
    file_path_obj = Path(file_path)
    with file_path_obj.open("r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    plant_id = file_path_obj.name.replace(".html", "")
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
    alternate_tables = soup.find_all("table", class_="alternate")
    target_table = None

    # Iterate through alternate tables to find the one with actual attributes like 'Distribution' or 'Habitat'
    for tbl in alternate_tables:
        tbl_text = tbl.get_text()
        if "Distribution" in tbl_text or "Habitat" in tbl_text:
            target_table = tbl
            break

    if target_table:
        # We iterate through all <strong> tags in the table
        labels = target_table.find_all("strong")
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
