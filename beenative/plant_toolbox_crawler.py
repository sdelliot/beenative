import re
import time
from typing import Callable, Optional
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import polars as pl
import requests
from bs4 import BeautifulSoup

import beenative.utils.ingest_utils as bn_utils
from beenative.settings import settings


def get_all_plants(plant_list, delay, progress_callback: Optional[Callable] = None):
    results = []
    for name in plant_list:
        if progress_callback:
            progress_callback(name)
        data, inet_call = get_plant_data(name)
        if data:
            results.append({"scientific_name": name, "content": data})

        if inet_call:
            time.sleep(delay)
    return results


def get_plant_data(scientific_name):
    """
    Builds the URL, fetches the page, and parses plant information.
    """
    not_found = "NOT FOUND"

    # 1. Build the URL
    # Formats 'Ilex decidua' into 'ilex-decidua'
    formatted_name = scientific_name.lower().replace(" ", "-")
    url = f"{settings.ncsu_plant_toolbox_plants_url}/{formatted_name}/"

    file_path = Path(settings.crawl_dir) / f"{scientific_name}_ncsu.html"

    content = ""
    inet_call = False
    if file_path.exists():
        with file_path.open("r") as f:
            content = f.read()
        if content.strip() == not_found:
            return None, inet_call
    else:
        inet_call = True
        try:
            response = requests.get(url, headers=settings.requests_headers, timeout=10)
            response.raise_for_status()
            with file_path.open("wb") as f:
                f.write(response.content)
            content = response.content
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {url}: {e}")
            with file_path.open("w", encoding="utf-8") as f:
                f.write(not_found)
            return None
    return content, inet_call


def process_all_plants(input_df: pl.DataFrame, progress_callback: Optional[Callable] = None):
    """
    Processes plant data by targeting the first column of the input DataFrame.
    """
    if input_df.is_empty():
        return pl.DataFrame()

    results = []

    # We use named=True so we can still access other columns if needed,
    # but we access the data via the dynamic variable target_col.
    for row in input_df.iter_rows(named=True):
        content = row.get("content")
        sci_name = row.get("scientific_name")

        if progress_callback:
            progress_callback(f"{sci_name}")

        # Process the content
        processed_row = process_ncsu_data(sci_name, content)

        if processed_row:
            results.append(processed_row)

    return pl.DataFrame(results).unnest("attributes")


def process_ncsu_data(sci_name: str, content: str):
    """
    Parses plant information from the content already present in the row.
    """

    if not content:
        return None

    soup = BeautifulSoup(content, "html.parser")
    formatted_name = sci_name.lower().replace(" ", "-")
    data = {"scientific_name": sci_name, "url": f"{settings.ncsu_plant_toolbox_plants_url}/{formatted_name}/"}

    # 2. Parse "Other Common Name(s)"
    common_names_div = soup.find("div", class_="common_name_space")
    if common_names_div:
        names_list = common_names_div.find("ul", id="common_names")
        if names_list:
            data["other_common_names"] = [li.get_text(strip=True) for li in names_list.find_all("li")]

    # 3. Parse Phonetic Spelling
    phonetic_dt = soup.find("dt", string="Phonetic Spelling")
    if phonetic_dt:
        data["phonetic_spelling"] = phonetic_dt.find_next_sibling("dd").get_text(strip=True)

    # 4. Parse Description
    description_dt = soup.find("dt", string="Description")
    if description_dt:
        dd_content = description_dt.find_next_sibling("dd")
        data["html_description"] = str(dd_content)
        data["description"] = _clean_toolbox_desc(dd_content)

    # 5. Parse Cultivars / Varieties
    cultivar_dt = soup.find("dt", string="Cultivars / Varieties:")
    if cultivar_dt:
        cultivar_dd = cultivar_dt.find_next_sibling("dd")
        if cultivar_dd:
            data["cultivars"] = [li.get_text(strip=True) for li in cultivar_dd.find_all("li")]

    # 6. Parse all content within "bricks"
    # This captures categorical data like Genus, Species, Family, Leaf Arrangement, etc.
    bricks_container = soup.find("div", class_="bricks")
    if bricks_container:
        brick_data = {}
        # Iterate through all <dt> (labels) and their associated <dd> (values)
        for dt in bricks_container.find_all("dt"):
            label = dt.get_text(strip=True).rstrip(":")

            # Find all subsequent <dd> tags until the next <dt>
            values = []
            next_node = dt.find_next_sibling()
            while next_node and next_node.name == "dd":
                # Check for the span class used in your example
                span = next_node.find("span", class_="detail_display_attribute")
                if span:
                    values.append(span.get_text(strip=True))
                else:
                    values.append(next_node.get_text(strip=True))
                next_node = next_node.find_next_sibling()

            # Store as a list if multiple values exist, otherwise a single string
            if values:
                brick_data[label] = values if len(values) > 1 else values[0]

        data["attributes"] = brick_data

    data["images"] = extract_gallery_data(soup)

    return data


def extract_gallery_data(soup):
    images = []

    gallery_container = soup.find("div", class_="gallery")

    if not gallery_container:
        return []

    # 2. Only look for figures inside that specific container
    figures = gallery_container.find_all("figure", class_="figure")

    for fig in figures:
        img_tag = fig.find("img")
        if not img_tag:
            continue

        # 1. Extract and Strip URL Query Parameters
        raw_url = img_tag.get("src")
        if raw_url:
            u = urlparse(raw_url)
            # Reconstruct without query (?...) or fragment (#...)
            clean_url = urlunparse((u.scheme, u.netloc, u.path, "", "", ""))
        else:
            continue

        # 2. Extract Metadata from data-attributes
        # These provide the cleanest version of the text strings
        caption = img_tag.get("data-caption", "").strip()
        attribution = img_tag.get("data-attrib", "").strip()
        alt_text = img_tag.get("data-alt", "").strip()
        image_id = img_tag.get("data-image-id", "")

        # 3. Handle License and License URL
        # data-license contains escaped HTML: <a href='...'>CC BY 2.0</a>
        license_raw = img_tag.get("data-license", "")
        license_soup = BeautifulSoup(license_raw, "html.parser")
        license_link_tag = license_soup.find("a")

        license_text = license_soup.get_text().strip()
        license_url = license_link_tag.get("href", "") if license_link_tag else ""

        # 4. Extract the high-res download link (also stripped)
        download_raw = img_tag.get("data-downloadurl", "")
        download_url = ""
        if download_raw:
            du = urlparse(download_raw)
            download_url = urlunparse((du.scheme, du.netloc, du.path, "", "", ""))

        img_metadata = {
            "thumbnail_url": clean_url,
            "original_url": download_url,
            "caption": caption,
            "copyright": attribution,
            "license": license_text,
            "license_url": license_url,
            "alt_text": alt_text,
            "image_id": image_id,
        }
        images.append(bn_utils.normalize_image_data(img_metadata))

    return images


def _clean_toolbox_desc(dd_content):
    # 1. Configuration
    block_tags = {"p", "div", "dd", "section", "article"}
    break_tags = {"br", "li"}
    output = []
    processed_ids = set()

    # 2. Iterate through elements
    for element in dd_content.descendants:
        if id(element) in processed_ids:
            continue

        # Handle Link Tags
        if element.name == "a":
            link_text = element.get_text(strip=True)
            href = element.get("href", "")
            # Convert relative (/path) to absolute (https://site.com/path)
            full_url = urljoin(settings.ncsu_plant_toolbox_base_url, href) if href else ""

            # Mark children as processed so we don't grab the text again
            for child in element.descendants:
                processed_ids.add(id(child))

            if link_text and full_url:
                output.append(f"{link_text} ({full_url})")
            elif link_text:
                output.append(link_text)

        # Handle Block/Break Tags
        elif element.name in block_tags:
            output.append("\n\n")
        elif element.name in break_tags:
            output.append("\n")

        # Handle Plain Text
        elif isinstance(element, str):
            text = " ".join(element.split())
            if text:
                output.append(text)

    # 3. The "Clean Join"
    # This prevents "onMonarda" by forcing a space between every chunk
    raw_text = " ".join(output)

    # 4. Final Polish
    final_text = re.sub(r" +", " ", raw_text)  # Collapse multi-spaces
    final_text = re.sub(r"\s+([,.!?;:])", r"\1", final_text)  # Fix "word ." -> "word."
    final_text = re.sub(r"\s*\n\s*", "\n", final_text)  # Trim space around newlines
    final_text = re.sub(r"\n{1,}", "\n\n", final_text).strip()

    return final_text
