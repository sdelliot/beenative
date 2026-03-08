import os
import time
from typing import Callable, Optional

import polars as pl
import requests
from bs4 import BeautifulSoup

import beenative.utils.ingest_utils as bn_utils
from beenative.settings import settings

# https://fsus.ncbg.unc.edu/main.php?pg=show-taxon.php&family=&plantname=Acetosa+acetosella


class NCBGParser:
    def __init__(self):
        self.json_file_base = "pm.json"
        self.not_found = "NOT FOUND"

        self.ncbg_params: dict = {
            "pg": "show-taxon.php",
            "family": "",
            "plantname": "",
        }

    def download_all_ncbg(self, plant_list, delay, progress_callback: Optional[Callable] = None):
        results = []
        with requests.Session() as session:
            session.headers.update(settings.requests_headers)
            initial_cookies = {
                "PHPSESSID": "798a2bc91ea62aa089519d23301e2c4c",
                "TS01afcdf3": (
                    "018e15451906d7edfd21d10f1d816bfaa7afb16f2cffabc030c584843591edf019f650"
                    "d67cc1f65a86bb904b8d6e924edf3df46b3b"
                ),
            }
            session.cookies.update(initial_cookies)
            for name in plant_list:
                if progress_callback:
                    progress_callback(name)
                data, inet_call = self.get_plant_data(name, session)
                if data:
                    results.append({"scientific_name": name, "content": data})

                if inet_call:
                    time.sleep(delay)
            return results

    def get_plant_data(self, scientific_name, session):
        """
        Builds the URL, fetches the page, and parses plant information.
        """
        # 1. Build the URL
        formatted_name = scientific_name.lower()
        self.ncbg_params["plantname"] = formatted_name
        file_path = os.path.join(settings.crawl_dir, f"{scientific_name}_ncbg.html")

        content = ""
        inet_call = False
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                content = f.read()
            if content.strip() != self.not_found:
                return content, inet_call

        inet_call = True
        try:
            response = session.get(settings.ncbg_target_url, params=self.ncbg_params, timeout=10)
            response.raise_for_status()
            with open(file_path, "wb") as f:
                f.write(response.content)
            content = response.content
        except requests.exceptions.RequestException as e:
            print(f"Error fetching {formatted_name}: {e}")
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(self.not_found)
            return None, inet_call
        return content, inet_call

    def process_ncbg_data(self, scientific_name: str, content: str):
        """
        Parses plant information from the content already present in the row.
        """
        if not content:
            return None

        soup = BeautifulSoup(content, "html.parser")
        data = {"scientific_name": scientific_name}

        # 1. Extract Permalink
        permalink_div = soup.find("div", id="permalink")
        data["permalink"] = permalink_div.get_text(strip=True) if permalink_div else None

        # 2. Extract Image Information
        image_list = []
        # Each image and its metadata is wrapped in an 'img-container' div
        containers = soup.find_all("div", class_="img-container")

        for container in containers:
            # Skip the distribution map (it uses an <object> tag rather than <img>)
            img_tag = container.find("img")
            if not img_tag:
                continue

            # The high-res link is usually the last <a> tag in the container
            img_metadata = {
                "thumbnail_url": img_tag.get("src"),
                "original_url": None,
                "copyright": None,
                "source_url": None,
                "license": None,
            }

            # Extract high-res link
            orig_link = container.find("a", title=lambda x: x and "original" in x.lower())
            if orig_link:
                img_metadata["original_url"] = orig_link.get("href")

            # Extract copyright/attribution from the span with 'auditlog' in the ID
            caption_span = container.find("span", id=lambda x: x and "auditlog" in x)
            if caption_span:
                img_metadata["copyright"] = caption_span.get_text(strip=True)

            # Extract External Source (e.g., iNaturalist)
            source_link = container.find("a", string=lambda x: x and "source" in x.lower())
            if source_link:
                img_metadata["source_url"] = source_link.get("href")

            # Extract License (e.g., CC-BY)
            license_link = container.find("a", href=lambda x: x and "creativecommons" in x)
            if license_link:
                img_metadata["license"] = license_link.get_text(strip=True)

            image_list.append(bn_utils.normalize_image_data(img_metadata))

        # Store images as a list of dicts (Polars can handle this as a List/Struct column)
        data["images"] = image_list

        return data

    def process_all_plants(self, input_df: pl.DataFrame, progress_callback: Optional[Callable] = None):
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
            processed_row = self.process_ncbg_data(sci_name, content)

            if processed_row:
                results.append(processed_row)

        return pl.DataFrame(results)
