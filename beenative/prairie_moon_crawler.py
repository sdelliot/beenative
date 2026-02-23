import json
import requests
from pathlib import Path
from typing import Any, Optional, Callable

import polars as pl
from settings import settings


class PrairieMoonJSONParser:
    def __init__(self):
        self.json_file_base = "pm.json"

    def _to_bool(self, value: Any) -> bool:
        """Converts "1" or 1 to True, otherwise False."""
        return str(value) == "1"

    def download_all_pm(self, progress_callback: Optional[Callable] = None):
        total_pages = 1
        cur_page = 1
        while cur_page <= total_pages:
            prairie_moon_params: dict = {
                "siteId": "qfh40u",
                "resultsFormat": "native",
                "resultsPerPage": "24",
                "page": str(cur_page),
                "bgfilter.hierarchy": "Seeds",
            }
            total_pages = self.download_pm_json(prairie_moon_params)
            cur_page += 1
            if progress_callback:
                progress_callback(total_pages)

    def download_pm_json(self, prairie_moon_params):
        try:
            response = requests.get(
                settings.prairie_moon_base_url, params=prairie_moon_params, headers=settings.prairie_moon_headers
            )
            response.raise_for_status()

            data = response.json()
            file_path = Path(settings.crawl_dir) / f"{prairie_moon_params['page']}_{self.json_file_base}"
            with open(file_path, "w") as f:
                json.dump(data, f)

        except requests.exceptions.RequestException as e:
            print(f"An error occurred: {e}")

        # Now we should return the total pages
        return int(data["pagination"]["totalPages"])

    def process_pm_data(self, progress_callback: Optional[Callable] = None):
        """
        Parses the downloaded JSON files and returns a subset of each
        flower as a dictionary.
        """
        base_path = Path(settings.crawl_dir)
        prairie_cat = []

        total_flowers = 0

        # 1. Define a strict schema for the DataFrame
        pm_schema = {
            "scientific_name": pl.String,
            "common_name": pl.String,
            "catalog_code": pl.String,
            "about": pl.String,
            "bloom_color": pl.List(pl.String),
            "bloom_time": pl.List(pl.String),
            "life_cycle": pl.List(pl.String),
            "native_states": pl.List(pl.String),
            "height": pl.List(pl.String),
            "sun_exposure": pl.List(pl.String),
            "soil_moisture": pl.List(pl.String),
            "germination_code": pl.List(pl.String),
            "adv_bee": pl.Boolean,
            "adv_bird": pl.Boolean,
            "adv_deer": pl.Boolean,
            "adv_stars": pl.Boolean,
            "image_url": pl.String,
            "url": pl.String,
        }

        # '*.json' matches any file ending in 'pm.json'
        # 'rglob' searches recursively through all subfolders
        for file_path in base_path.rglob(f"*{self.json_file_base}"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Could not read {file_path}: {e}")

            results = data.get("results", [])
            total_flowers += len(results)
            for product in results:
                # Extract product for failing fast
                catalog_code = product.get("sku") or product.get("code")
                if not catalog_code:
                    continue

                # Map the data according to requirements
                flower_data = {
                    "scientific_name": product.get("name"),
                    "common_name": product.get("cmn_name"),
                    "catalog_code": catalog_code,
                    "about": product.get("description"),
                    "image_url": product.get("imageUrl"),
                    "bloom_color": product.get("bloom_color", []),
                    "bloom_time": product.get("bloom_time", []),
                    "life_cycle": product.get("life_cycle", []),
                    "native_states": product.get("native_states", []),
                    "height": product.get("search_spring_ht", []),
                    "sun_exposure": product.get("sun_exposure", []),
                    "soil_moisture": product.get("soil_moisture", []),
                    "germination_code": product.get("germination_code", []),
                    "adv_bee": self._to_bool(product.get("adv_bee")),
                    "adv_bird": self._to_bool(product.get("adv_bird")),
                    "adv_deer": self._to_bool(product.get("adv_deer")),
                    "adv_stars": self._to_bool(product.get("adv_stars")),
                    "url": f"https://www.prairiemoon.com{product.get('url')}",
                }
                prairie_cat.append(flower_data)
                progress_callback(total_flowers)

        return pl.DataFrame(prairie_cat, schema=pm_schema)
