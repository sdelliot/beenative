import re
import json
from typing import Any, Dict, List, Tuple
from pathlib import Path
from functools import reduce
from collections import Counter

import polars as pl
from rich.panel import Panel
from rich.table import Column
from rich.console import Console
from rich.progress import Progress, BarColumn, TextColumn, SpinnerColumn, TaskProgressColumn, TimeRemainingColumn

import beenative.utils.ingest_utils as bn_utils
from beenative import vascular_nc_crawler, plant_toolbox_crawler
from beenative.settings import settings
from beenative.ncbg_crawler import NCBGParser
from beenative.prairie_moon_crawler import PrairieMoonJSONParser


class BeeNativeAPI:
    """High-level API to coordinate crawling and processing logic."""

    @staticmethod
    def initialize(
        nc_source: str, delay: float, get_maps: bool, output_vasc: str, output_ncsu: str, output_ncbg: str
    ) -> None:
        """
        Runs all initial collecting of data and some initial processing.
        This does not attempt to merge all data sources yet, rather it collects data
        from the various sources and outputs the desired results into parqet format,
        which can be used in future steps.

        In the future, this could end up using a database backend rather than static files.
        """
        if not Path(settings.crawl_dir).exists():
            Path(settings.crawl_dir).mkdir(parents=True)

        console = Console()
        # 1. NC Vascular Plant Crawler
        with console.status("[cyan]Starting to get all native plants in NC..."):
            native_ids = vascular_nc_crawler.get_native_plant_ids(nc_source)
            console.print(f"[green] Identified {len(native_ids)} native plants!")

        # Progress bar setup
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}", table_column=Column(width=50)),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            auto_refresh=True,
        ) as progress:
            task = progress.add_task("[cyan]⬇️ Downloading data...", total=len(native_ids))
            new, skipped = vascular_nc_crawler.download_plant_data(
                native_ids, delay=delay, progress_callback=lambda: progress.update(task, advance=1)
            )

            files = [(Path(settings.crawl_dir) / f"{native_id}.html") for native_id in native_ids]
            total_files = len(files)

            description = "📸 Getting Maps & Parsing" if get_maps else "📄 Parsing HTML"
            get_maps_task = progress.add_task(f"[cyan]{description}...", total=total_files)

            # Define the callback to advance the bar
            def update_bar() -> None:
                progress.advance(get_maps_task)

            # Execute logic
            vascular_df = vascular_nc_crawler.build_dataframe(
                files, include_maps=get_maps, progress_callback=update_bar
            )

        if vascular_df.is_empty():
            print("No data found.")
            return

        # If output is CSV, Base64 strings will make it huge.
        # Parquet or IPC is better for binary/large text data.
        if output_vasc.endswith(".parquet"):
            vascular_df.write_parquet(output_vasc)
        else:
            vascular_df.write_csv(output_vasc)

        console.print(f"[green]Processed {len(vascular_df)} entries into [magenta]{output_vasc}")

        # 2. Prairie Moon Parser
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}", table_column=Column(width=50)),
            BarColumn(),
            TaskProgressColumn(),
            auto_refresh=True,
        ) as progress:
            task = progress.add_task("[green]🌻 Collecting native plant seed data from Prairie Moon...")

            def update_pm_bar(total: int) -> None:
                progress.update(task, advance=1, total=total)

            pm_parser = PrairieMoonJSONParser()
            pm_parser.download_all_pm(progress_callback=update_pm_bar)

        console.print("[green]Collected all native Prairie Moon data!")

        # 3. NCSU
        plant_list = vascular_df["scientific_name"].unique().to_list()
        ncsu_print_str = f"[green]🔍 Analyzing NC Plant Toolbox for {len(plant_list)} unique scientific names...."
        console.print(ncsu_print_str)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}", table_column=Column(width=50)),
            BarColumn(),
            TaskProgressColumn(),
            auto_refresh=True,
        ) as progress:
            task = progress.add_task(ncsu_print_str, total=len(plant_list))

            def update_ncsu_bar(name: str) -> None:
                progress.update(task, advance=1, description=f"[cyan]🌱 Processing: {name}")

            results = plant_toolbox_crawler.get_all_plants(plant_list, delay, progress_callback=update_ncsu_bar)

        # Save results
        df = pl.DataFrame(results)
        if output_ncsu.endswith(".parquet"):
            df.write_parquet(output_ncsu)
        else:
            df.write_csv(output_ncsu)

        console.print(f"[green]Processed {len(results)} entries into [magenta]{output_ncsu}")

        ncbg_print_str = (
            "[green]🔍 Analyzing 'Flora of the Southeastern United States' (NC Botanical Garden) for "
            f"{len(plant_list)} unique scientific names..."
        )
        console.print(ncbg_print_str)
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}", table_column=Column(width=50)),
            BarColumn(),
            TaskProgressColumn(),
            auto_refresh=True,
        ) as progress:
            task = progress.add_task(ncbg_print_str, total=len(plant_list))

            def update_ncbg_bar(name: str) -> None:
                progress.update(task, advance=1, description=f"[cyan]⬇️ Downloading: {name}")

            ncbg_parser = NCBGParser()
            results = ncbg_parser.download_all_ncbg(plant_list, delay, progress_callback=update_ncbg_bar)

        # Save results
        df = pl.DataFrame(results)
        if output_ncbg.endswith(".parquet"):
            df.write_parquet(output_ncbg)
        else:
            df.write_csv(output_ncbg)

        console.print(f"[green]Processed {len(results)} entries into [magenta]{output_ncbg}")

    @staticmethod
    def process_data(
        input_vasc: str = "", input_ncsu: str = "", input_ncbg: str = "", output_path: str = "merged.parquet"
    ) -> pl.DataFrame:
        """Processes raw HTML/JSON into a unified structured formats."""

        console = Console()
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}", table_column=Column(width=50)),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            # Determine the extension
            if input_vasc:
                input_vasc_file = Path(input_vasc)

                task_vasc = progress.add_task("[cyan]🌻 Loading Vascular NC data...", total=1)

                # 1. Reading logic based on input extension
                if input_vasc_file.suffix == ".parquet":
                    vasc_df = pl.read_parquet(input_vasc_file)
                elif input_vasc_file.suffix == ".csv":
                    vasc_df = pl.read_csv(input_vasc_file, infer_schema_length=10000)
                else:
                    raise ValueError(f"Unsupported input format: {input_vasc_file.suffix}")
                progress.update(task_vasc, advance=1)
            else:
                base_path = Path(settings.crawl_dir)

                vasc_files = [f for f in base_path.glob("*.html") if f.stem.isnumeric()]

                task_vasc = progress.add_task("[cyan]🌻 Loading Vascular NC data...", total=len(vasc_files))

                # Define the callback to advance the bar
                def update_bar() -> None:
                    progress.advance(task_vasc)

                vasc_df = vascular_nc_crawler.build_dataframe(vasc_files, progress_callback=update_bar)

            ncsu_df = None
            if input_ncsu:
                input_ncsu_file = Path(input_ncsu)

                # 1. Reading logic based on input extension
                if input_ncsu_file.suffix == ".parquet":
                    ncsu_input_df = pl.read_parquet(input_ncsu_file)
                elif input_ncsu_file.suffix == ".csv":
                    ncsu_input_df = pl.read_csv(input_ncsu_file, infer_schema_length=10000)
                else:
                    raise ValueError(f"Unsupported input format: {input_ncsu_file.suffix}")
            else:
                plant_list = vasc_df["scientific_name"].unique().to_list()
                task_ncsu = progress.add_task(
                    "[green]🔍 Analyzing NC Plant Toolbox for {len(plant_list)} unique scientific names....",
                    total=len(plant_list),
                )

                def update_ncsu_bar(name: str) -> None:
                    progress.update(task_ncsu, advance=1, description=f"[cyan]🐺 Parsing: {name}")

                ncsu_input_df = plant_toolbox_crawler.get_all_plants(
                    plant_list, delay=settings.crawl_timout, progress_callback=update_ncsu_bar
                )

            task_ncsu_desc = "[cyan]🐺 Processing NC Plant Toolbox data: "
            task_ncsu = progress.add_task(f"{task_ncsu_desc}", total=len(ncsu_input_df))

            # Define the callback to advance the bar
            def process_ncsu_bar(name: str) -> None:
                progress.update(task_ncsu, advance=1, description=f"{task_ncsu_desc} {name}")

            ncsu_df = plant_toolbox_crawler.process_all_plants(ncsu_input_df, progress_callback=process_ncsu_bar)

            # Botanical Gargdens
            ncbg_df = None
            if input_ncbg:
                input_ncbg_file = Path(input_ncbg)

                # 1. Reading logic based on input extension
                if input_ncbg_file.suffix == ".parquet":
                    ncbg_input_df = pl.read_parquet(input_ncbg_file)
                elif input_ncbg_file.suffix == ".csv":
                    ncbg_input_df = pl.read_csv(input_ncbg_file, infer_schema_length=10000)
                else:
                    raise ValueError(f"Unsupported input format: {input_ncbg_file.suffix}")
            else:
                console.print(
                    "[warning]⚠️ Must have input file to process 'Flora of the Southeastern United States' "
                    "(NC Botanical Garden) data!"
                )

            task_ncbg_desc = "[cyan]🌳 Processing Flora of the Southeastern United States (NC Botanical Garden) data: "
            task_ncbg = progress.add_task(f"{task_ncbg_desc}", total=len(ncbg_input_df))

            # Define the callback to advance the bar
            def process_ncbg_bar(name: str) -> None:
                progress.update(task_ncbg, advance=1, description=f"{task_ncbg_desc} {name}")

            ncbg_parser = NCBGParser()
            ncbg_df = ncbg_parser.process_all_plants(ncbg_input_df, progress_callback=process_ncbg_bar)

            # Determine the extension
            pm_parser = PrairieMoonJSONParser()
            task_pm = progress.add_task("[cyan]🌿 Processing Prairie Moon data...")

            def process_pm_bar(total: int) -> None:
                progress.update(task_pm, total=total, advance=1)

            pm_df = pm_parser.process_pm_data(progress_callback=process_pm_bar)

        return BeeNativeAPI().merge(output_path, [pm_df, ncsu_df, vasc_df, ncbg_df])

    @staticmethod
    def merge(output_path: str, data_frame_list: list) -> pl.DataFrame:
        """Processes raw dataframes into a unified structured format."""

        console = Console()
        output_file = Path(output_path)

        labels = ["pm", "ncsu", "vasc", "ncbg"]

        # 1. Normalize names
        dfs = [bn_utils.normalize_names(df) for df in data_frame_list]

        # 2. Handle Suffix Collisions by prefixing columns
        # We'll use a simple list of labels for the sources
        prepped_dfs = []

        for i, df in enumerate(dfs):
            label = labels[i] if i < len(labels) else f"source_{i}"

            # Rename every column except 'scientific_name'
            renamed = df.select(
                [pl.col("scientific_name"), *[pl.all().exclude("scientific_name").name.prefix(f"{label}_")]]
            )
            prepped_dfs.append(renamed)

        # 3. Join all dataframes
        df_merged = reduce(
            lambda left, right: left.join(right, on="scientific_name", how="outer_coalesce"), prepped_dfs
        )

        df_merged = bn_utils.sanitize_column_names(df_merged)

        # 4. Write to file using pathlib
        if output_file.suffix == ".parquet":
            df_merged.write_parquet(output_file)
        else:
            df_merged.write_csv(output_file)

        console.print(
            Panel(
                f"[green]Merged [bold cyan]{len(df_merged)}[/bold cyan] unique scientific names.\n"
                f"Output saved to: [magenta italic]{output_file.absolute()}[/magenta italic]",
                title="Final Dataset Info",
                expand=False,
            )
        )

        return df_merged

    @staticmethod
    def create_common_names(df: pl.DataFrame) -> pl.DataFrame:
        # Filter to ground truth: Only NC Vascular Plants
        df_nc_native = df.filter(pl.col("vasc_id").is_not_null())

        print(f"Total records anchored to VASC ground truth: {df_nc_native.height}")

        # Fill Nulls based on data type for the whole DataFrame
        df = df.with_columns(
            [
                pl.col(pl.Utf8).fill_null(""),  # All strings become ""
                pl.col(pl.List(pl.Utf8)).fill_null([]),  # All lists of strings become []
                pl.col(pl.Boolean).fill_null(False),  # All null booleans become False
            ]
        )

        # Patterns
        quoted_pattern = r'"([^"]+)"'

        # Refined name_pattern (Hyphen-Safe):
        # [A-Z][a-z\-]+ -> Match a Capital letter followed by lowercase letters OR hyphens
        # (?:[ -][A-Z][a-z\-]+){1,4} -> Match 1 to 4 subsequent words starting with Caps
        name_pattern = r"\b[A-Z][a-z\-]+(?:[ -][A-Z][a-z\-]+){1,4}\b"

        junk_words = ["Most", "With", "Reference", "Some", "From", "This", "When", "There"]

        df = df.with_columns(
            vasc_other_common_names_clean=(
                pl.col("vasc_other_common_names")
                .str.extract_all(quoted_pattern)
                .fill_null([])
                .list.concat(
                    # Replace periods with pipes to create a hard stop
                    pl.col("vasc_other_common_names")
                    .str.replace_all(r"\.", "|")
                    .str.extract_all(name_pattern)
                    .fill_null([])
                )
                .list.eval(
                    pl.element()
                    .str.strip_chars(' "|.')
                    .str.replace_all(r"x+", "")
                    .str.strip_chars("- ")  # Clean up trailing hyphens if any
                    .filter(
                        (~pl.element().is_in(junk_words))
                        & (pl.element().str.len_chars() > 3)
                        & (pl.element().str.contains(r"[ -]"))
                    )
                )
                .list.unique()
            )
        )

        # 1. Define the specific columns for this merge
        # We use the 'clean' version for the messy VASC column
        cols_to_merge = [
            "vasc_common_name_primary",
            "pm_common_name",
            "ncsu_other_common_names",
            "vasc_other_common_names_clean",
        ]

        # 2. Get the schema to handle List vs String types automatically
        schema = df.schema

        processing_exprs = []
        for col_name in cols_to_merge:
            dtype = schema.get(col_name)

            if isinstance(dtype, pl.List):
                # If it's our cleaned list, join it into a string temporarily
                expr = pl.col(col_name).list.join(", ")
            else:
                # If it's a string, cast to Utf8 and handle nulls
                expr = pl.col(col_name).cast(pl.Utf8)

            processing_exprs.append(expr.fill_null(""))

        # 3. Create the final 'all_common_names' Master Column
        df_final = df.with_columns(
            all_common_names=(
                pl.concat_str(processing_exprs, separator=", ")
                .str.split(", ")
                .list.eval(
                    pl.element()
                    .str.strip_chars(" .")  # Final polish for trailing dots or spaces
                    .filter((pl.element() != "") & (pl.element().is_not_null()))
                )
                .list.unique()
            )
        )
        return df_final

    @staticmethod
    def merge_wildlife(df: pl.DataFrame) -> pl.DataFrame:
        # 1. Standardize and Merge Strings
        df_final = df.with_columns(
            [
                # WILDLIFE: Combine PM + NCSU Attracts + NCSU Wildlife Value
                pl.concat_str(
                    [
                        pl.when(pl.col("pm_adv_bee")).then(pl.lit("Bees")).otherwise(pl.lit("")),
                        pl.when(pl.col("pm_adv_bird")).then(pl.lit("Birds")).otherwise(pl.lit("")),
                        pl.col("ncsu_attracts").cast(pl.Utf8).fill_null(""),
                    ],
                    separator=",",
                ).alias("_wildlife_raw"),
                # RESISTANCE: Combine PM Deer + NCSU Resistance + NCSU Problems (Resistant To)
                pl.concat_str(
                    [
                        pl.when(pl.col("pm_adv_deer")).then(pl.lit("Deer")).otherwise(pl.lit("")),
                        pl.col("ncsu_resistance_to_challenges").cast(pl.Utf8).fill_null(""),
                    ],
                    separator=",",
                ).alias("_res_raw"),
            ]
        )

        # 2. Convert to Clean Lists
        def final_tag_cleanup(col: str) -> pl.Expr:
            return (
                pl.col(col)
                .str.replace_all(r'[\[\]"\' ]', " ")
                .str.split(",")
                .list.eval(
                    pl.element().str.strip_chars(" .").str.to_titlecase().filter(pl.element().str.len_chars() > 2)
                )
                .list.unique()
            )

        df_final = df_final.with_columns(
            [
                final_tag_cleanup("_wildlife_raw").alias("wildlife_attracts"),
                final_tag_cleanup("_res_raw").alias("plant_resistances"),
            ]
        ).drop(["_wildlife_raw", "_res_raw"])

        return df_final

    @staticmethod
    def deduplicate_plants(df: pl.DataFrame) -> pl.DataFrame:
        """
        Consolidates rows with the same scientific_name by taking the first
        available non-null value for each column.
        """
        # Define how to aggregate: for each column, take the first non-null value
        aggs = [pl.col(c).drop_nulls().first().alias(c) for c in df.columns if c != "scientific_name"]

        return df.group_by("scientific_name").agg(aggs)

    @staticmethod
    def parse_dimensions(df: pl.DataFrame) -> pl.DataFrame:
        # 1. Flatten list columns into strings
        df_working = df.with_columns(
            [
                pl.col("pm_height").list.join(" ").fill_null("").alias("_pm_raw"),
                pl.col("ncsu_dimensions").list.join(" ").fill_null("").alias("_ncsu_raw"),
            ]
        )

        # 2. Isolate NCSU segments
        df_working = df_working.with_columns(
            [
                pl.col("_ncsu_raw").str.extract(r"(?i)height:\s*(.*?)(?:width:|$)").alias("_ncsu_h_seg"),
                pl.col("_ncsu_raw").str.extract(r"(?i)width:\s*(.*)").alias("_ncsu_w_seg"),
            ]
        )

        def extract_stats(col_expr: pl.Expr) -> Tuple[pl.Expr, pl.Expr]:
            # Normalize and clean markers
            clean = (
                col_expr.str.to_lowercase()
                .str.replace_all(r"&quot;", '"')
                .str.replace_all(r"ft\.|feet|'", "ft")
                .str.replace_all(r"in\.|inches|\"", "in")
            )

            # 3. Extract feet and inches safely using list methods that handle empty lists
            ft_list = clean.str.extract_all(r"\d+(?:\.\d+)?\s*ft").list.eval(
                pl.element().str.replace("ft", "").str.strip_chars().cast(pl.Float64)
            )
            in_list = clean.str.extract_all(r"\d+(?:\.\d+)?\s*in").list.eval(
                pl.element().str.replace("in", "").str.strip_chars().cast(pl.Float64)
            )

            # General fallback for raw numbers
            num_list = clean.str.extract_all(r"\d+(?:\.\d+)?").list.eval(pl.element().cast(pl.Float64))

            # Safe extraction: .list.get(0, null_on_oob=True) prevents the Out of Bounds error
            f1 = ft_list.list.get(0, null_on_oob=True).fill_null(0.0)
            f2 = ft_list.list.get(1, null_on_oob=True).fill_null(0.0)
            i1 = in_list.list.get(0, null_on_oob=True).fill_null(0.0)
            i2 = in_list.list.get(1, null_on_oob=True).fill_null(0.0)

            # Calculate decimal feet
            v1_ft = f1 + (i1 / 12.0)
            v2_ft = f2 + (i2 / 12.0)

            fallback_v1 = num_list.list.get(0, null_on_oob=True)
            fallback_v2 = num_list.list.get(1, null_on_oob=True).fill_null(fallback_v1)

            # Final Min/Max Logic: prioritize the ft/in calculated value if it's > 0
            final_min = pl.when(v1_ft > 0).then(v1_ft).otherwise(fallback_v1)

            # If v2_ft exists and is > 0, use it. Otherwise use fallback_v2.
            # If those are null, fallback to final_min.
            final_max = pl.when(v2_ft > 0).then(v2_ft).otherwise(fallback_v2).fill_null(final_min)

            return final_min, final_max

        # 4. Apply
        pm_h_min, pm_h_max = extract_stats(pl.col("_pm_raw"))
        ncsu_h_min, ncsu_h_max = extract_stats(pl.col("_ncsu_h_seg"))
        ncsu_w_min, ncsu_w_max = extract_stats(pl.col("_ncsu_w_seg"))

        # 5. Combine (PM Priority for height)
        df_final = df_working.with_columns(
            [
                pl.coalesce([pm_h_min, ncsu_h_min]).alias("height_min_ft"),
                pl.coalesce([pm_h_max, ncsu_h_max]).alias("height_max_ft"),
                ncsu_w_min.alias("width_min_ft"),
                ncsu_w_max.alias("width_max_ft"),
            ]
        )

        # 6. Display formatting
        return df_final.with_columns(
            [
                pl.when(pl.col("height_min_ft").is_not_null())
                .then(pl.format("{}–{} ft", pl.col("height_min_ft").round(1), pl.col("height_max_ft").round(1)))
                .otherwise(pl.lit(""))
                .alias("height_str"),
                pl.when(pl.col("width_min_ft").is_not_null())
                .then(pl.format("{}–{} ft", pl.col("width_min_ft").round(1), pl.col("width_max_ft").round(1)))
                .otherwise(pl.lit(""))
                .alias("width_str"),
            ]
        ).drop(["_pm_raw", "_ncsu_raw", "_ncsu_h_seg", "_ncsu_w_seg"])

    @staticmethod
    def extract_sunlight_values(df: pl.DataFrame) -> pl.DataFrame:
        """
        Normalizes sunlight requirements from NCSU and Prairie Moon columns
        into a unified list column 'sunlight_categories'.
        """

        # Mapping for NCSU long-form strings
        ncsu_map = {
            "Full sun": "Full Sun",
            "Partial Shade": "Partial Shade",
            "Dappled Sunlight": "Dappled Sunlight",
            "Deep shade": "Deep Shade",
        }

        # Helper function to process individual rows
        def normalize_row(row: Dict) -> List[str]:
            ncsu_val = row["ncsu_light"]
            pm_val = row["pm_sun_exposure"]
            results = set()

            # 1. Process NCSU
            if ncsu_val:
                # NCSU can have multiple values separated by commas
                parts = [p.strip() for p in ncsu_val.split(",")]
                for part in parts:
                    for key, target in ncsu_map.items():
                        if key in part:
                            results.add(target)

            # 2. Process Prairie Moon
            if pm_val:
                if "Full" in pm_val:
                    results.add("Full Sun")
                if "Partial" in pm_val:
                    results.add("Partial Shade")
                if "Shade" in pm_val:
                    results.add("Deep Shade")

            return list(results) if results else []

        # Apply the logic across the dataframe
        return df.with_columns(
            [
                pl.struct(["ncsu_light", "pm_sun_exposure"])
                .map_elements(normalize_row, return_dtype=pl.List(pl.Utf8))
                .alias("sunlight_categories")
            ]
        )

    @staticmethod
    def extract_lifecycle(df: pl.DataFrame) -> pl.DataFrame:
        """
        Extracts the primary growth cycle, ignoring 'Woody' and 'Bulb'.
        """

        def parse_lifecycle(data: List | str) -> str:
            found = [""]
            targets = ["Annual", "Biennial", "Perennial"]
            if isinstance(data, list):
                found = [x for x in data if x in targets]
            elif isinstance(data, str):
                if data in targets:
                    found = [data]
            return found[0] if found else ""

        return df.with_columns(
            [pl.col("ncsu_life_cycle").map_elements(parse_lifecycle, return_dtype=pl.Utf8).alias("primary_lifecycle")]
        )

    @staticmethod
    def extract_moisture_values(df: pl.DataFrame) -> pl.DataFrame:
        # Mapping for NCSU Drainage to standard categories
        ncsu_moisture_map = {
            "Frequent Standing Water": "Wet",
            "Occasional Flooding": "Wet",
            "Moist": "Medium-Wet",
            "Occasionally Wet": "Medium-Wet",
            "Good Drainage": "Medium",
            "Occasionally Dry": "Medium-Dry",
            "Very Dry": "Dry",
        }

        def normalize_moisture(row: Dict[str, Any]) -> List[str]:
            ncsu_val = row["ncsu_soil_drainage"]
            pm_val = row["pm_soil_moisture"]
            results = set()

            # 1. Process NCSU using substring matching
            if ncsu_val:
                # Handle comma-separated lists if they exist
                parts = [p.strip() for p in ncsu_val.split(",")]
                for part in parts:
                    for key, target in ncsu_moisture_map.items():
                        # Check if the map key is found anywhere in the NCSU description
                        if key.lower() in part.lower():
                            results.add(target)

            # Process Prairie Moon
            if pm_val:
                for part in pm_val:
                    results.add(part)

            return list(results) if results else []

        return df.with_columns(
            [
                pl.struct(["ncsu_soil_drainage", "pm_soil_moisture"])
                .map_elements(normalize_moisture, return_dtype=pl.List(pl.Utf8))
                .alias("moisture_categories")
            ]
        )

    @staticmethod
    def extract_precision_months(text: str) -> str:
        if not text or text.lower() in ["null", ""]:
            return json.dumps({})

        season_map = {
            "winter": ["Jan", "Feb", "Dec"],
            "spring": ["Mar", "Apr", "May"],
            "summer": ["Jun", "Jul", "Aug"],
            "fall": ["Sep", "Oct", "Nov"],
        }
        month_map = {
            "jan": 1,
            "feb": 2,
            "mar": 3,
            "apr": 4,
            "may": 5,
            "jun": 6,
            "jul": 7,
            "aug": 8,
            "sep": 9,
            "oct": 10,
            "nov": 11,
            "dec": 12,
        }
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        # Use Counter to track how many sources/phrases confirm a month
        weights: Dict = Counter()

        # 1. Capture Ranges (Weight = 1)
        range_pattern = r"(\b[a-z]{3,}\b)\s*(?:to|–|-|through|into|until)\s*(\b[a-z]{3,}\b)"
        for start_s, end_s in re.findall(range_pattern, text.lower()):
            s_idx, e_idx = month_map.get(start_s[:3]), month_map.get(end_s[:3])
            if s_idx and e_idx:
                curr = s_idx
                while True:
                    weights[month_names[curr - 1]] += 1
                    if curr == e_idx:
                        break
                    curr = (curr % 12) + 1

        # 2. Capture Standalone Months and Seasons (Weight = 1 per mention)
        words = re.findall(r"\b\w{3,}\b", text.lower())
        for word in words:
            if word in season_map:
                for m in season_map[word]:
                    weights[m] += 1
            for m_short, m_idx in month_map.items():
                if m_short == word[:3]:
                    weights[month_names[m_idx - 1]] += 1

        return json.dumps(dict(weights))  # Returns e.g., {"May": 2, "Jun": 2, "Apr": 1}

    @staticmethod
    def format_col(col_name: str, df_final: pl.DataFrame) -> pl.Expr:
        # Check if column exists, then handle list vs string
        if col_name not in df_final.columns:
            return pl.lit("Missing").alias(col_name)

        dtype = df_final.schema.get(col_name)
        if isinstance(dtype, pl.List):
            return pl.col(col_name).list.join(", ").alias(col_name)
        return pl.col(col_name).cast(pl.Utf8).fill_null("null").alias(col_name)

    @staticmethod
    def update_bloomtime(df: pl.DataFrame) -> pl.DataFrame:
        return df.with_columns(
            bloom_months=pl.when(
                # Check for non-empty lists or non-empty strings in precision columns
                (pl.col("pm_bloom_time").is_not_null()) | (pl.col("ncsu_flower_bloom_time").is_not_null())
            )
            .then(
                pl.concat_str(
                    [
                        # Join PM if it's a list; if it's already a string, this safely handles it
                        pl.col("pm_bloom_time").cast(pl.List(pl.Utf8)).list.join(" ").fill_null(""),
                        # Join NCSU if it's a list
                        pl.col("ncsu_flower_bloom_time").cast(pl.List(pl.Utf8)).list.join(" ").fill_null(""),
                    ],
                    separator=" ",
                )
            )
            .otherwise(
                # Vasc is a string, so we just fill nulls
                pl.col("vasc_phenology").fill_null("")
            )
            .map_elements(
                lambda x: BeeNativeAPI().extract_precision_months(str(x)),
                return_dtype=pl.Utf8,  # Stores the {Month: Weight} dictionary
            )
        )

    @staticmethod
    def prepare_for_sqlite(df: pl.DataFrame) -> pl.DataFrame:
        # 1. Standard Type Sanitization
        df = df.with_columns(
            [
                pl.col(pl.String).fill_null(""),
                pl.col(pl.Boolean).fill_null(False),
                # Ensure numeric columns don't have Nulls if you want 0 as default
                pl.col(pl.Int64, pl.Float64).fill_null(0),
            ]
        )
        return df

    @staticmethod
    def remove_non_nc_plants(df: pl.DataFrame) -> pl.DataFrame:
        df = df.filter((pl.col("vasc_id").cast(pl.String).is_not_null()) & (pl.col("vasc_id").cast(pl.String) != ""))
        return df

    @staticmethod
    def standardize_colors(df: pl.DataFrame) -> pl.DataFrame:
        COLOR_MAP = {
            "Yellow": ["yellow", "gold", "lemon", "chartreuse", "goldenrod"],
            "White": ["white", "cream", "off-white", "whitish"],
            "Red": ["red", "crimson", "scarlet", "maroon", "burgundy"],
            "Blue": ["blue", "indigo", "azure", "violet"],
            "Purple": ["purple", "lavender", "mauve", "lilac", "magenta"],
            "Orange": ["orange", "apricot", "copper", "bronze", "peach"],
            "Pink": ["pink", "rose", "fuchsia"],
            "Green": ["green", "lime", "olive", "insignificant"],
            "Brown": ["brown", "tan", "chocolate"],
            "Grey": ["gray", "grey", "silver"],
        }

        # Helper to convert List or String to a flat lowercase string for searching
        def to_searchable_str(col_name: str) -> pl.Expr:
            dtype = df.schema.get(col_name)
            if isinstance(dtype, pl.List):
                return pl.col(col_name).list.join(" ").fill_null("")
            return pl.col(col_name).cast(pl.Utf8).fill_null("")

        df_working = df.with_columns(
            _color_search=(
                pl.concat_str(
                    [to_searchable_str("pm_bloom_color"), to_searchable_str("ncsu_flower_color")], separator=" "
                )
                .str.to_lowercase()
                .str.replace_all(r"[\[\]/,]", " ")  # Clean brackets and slashes
            )
        )

        color_exprs = []
        for master, keywords in COLOR_MAP.items():
            pattern = "|".join([master.lower()] + keywords)
            color_exprs.append(
                pl.when(pl.col("_color_search").str.contains(pattern))
                .then(pl.lit(master))
                .otherwise(None)
                .alias(f"_is_{master.lower()}")
            )

        df_final = df_working.with_columns(color_exprs).with_columns(
            flower_colors=pl.concat_list([pl.col(f"_is_{m.lower()}") for m in COLOR_MAP.keys()]).list.drop_nulls()
        )

        return df_final.drop([f"_is_{m.lower()}" for m in COLOR_MAP.keys()] + ["_color_search"])

    @staticmethod
    def categorize_plants(df: pl.DataFrame) -> pl.DataFrame:
        WOODY_MAP = {
            "Trees": ["tree", "arborescent", "canopy", "conifer", "pine", "fir", "cedar"],
            "Shrubs": ["shrub", "bush", "multistemmed"],
            "Vines": ["vine", "climbing", "liana"],
        }

        # "Forb" now includes all non-woody herbaceous keywords
        HERB_KEYWORDS = ["wildflower", "forb", "herb", "perennial", "annual", "herbaceous"]
        GRASS_KEYWORDS = ["grass", "sedge", "graminoid", "rush"]
        FERN_KEYWORDS = ["fern", "frond", "spore"]

        def to_searchable_str(cols: List[str]) -> pl.Expr:
            return (
                pl.concat_str(
                    [
                        (
                            pl.col(c).list.join(" ")
                            if df.schema.get(c) == pl.List(pl.Utf8)
                            else pl.col(c).cast(pl.Utf8)
                        ).fill_null("")
                        for c in cols
                        if c in df.columns
                    ],
                    separator=" ",
                )
                .str.to_lowercase()
                .str.replace_all(r"[\[\]/,.\(\)]", " ")
            )

        # Prepare search strings
        df_working = df.with_columns(
            _strict_search=to_searchable_str(["ncsu_plant_type"]),
            _fuzzy_search=to_searchable_str(["all_common_names", "vasc_identification", "ncsu_description"]),
        )

        # 1. Identify "Woody" status FIRST
        # We combine strict and fuzzy here to ensure we catch 'Tree' anywhere
        woody_exprs = []
        for master, keywords in WOODY_MAP.items():
            pattern = "|".join([rf"\b{master.lower()}\b"] + [rf"\b{k}\b" for k in keywords])
            woody_exprs.append(
                pl.when(pl.col("_strict_search").str.contains(pattern) | pl.col("_fuzzy_search").str.contains(pattern))
                .then(pl.lit(master))
                .otherwise(None)
                .alias(f"_is_{master.lower()}")
            )

        df_working = df_working.with_columns(woody_exprs)

        # 2. Define the absolute blocker
        # If it's a Tree, Shrub, or Vine, this is TRUE
        is_woody_flag = pl.any_horizontal(
            [pl.col("_is_trees").is_not_null(), pl.col("_is_shrubs").is_not_null(), pl.col("_is_vines").is_not_null()]
        )

        # 3. Apply Herbaceous logic with an "Absolute Override"
        # Even if NCSU says 'Perennial', if it's a Tree, we skip the Forb label.
        def build_herb_expr(name: str, keywords: List[str], block_completely: bool = False) -> pl.Expr:
            pattern = "|".join([rf"\b{name.lower()}\b"] + [rf"\b{k}\b" for k in keywords])
            col_alias = f"_is_{name.replace(' & ', '_').lower()}"

            # The logic waterfall:
            # 1. If it's woody and we want to block, return None immediately.
            # 2. Else check Strict tags.
            # 3. Else check Fuzzy keywords.
            return (
                pl.when(block_completely & is_woody_flag)
                .then(None)
                .otherwise(
                    pl.when(pl.col("_strict_search").str.contains(pattern))
                    .then(pl.lit(name))
                    .otherwise(
                        pl.when(pl.col("_fuzzy_search").str.contains(pattern)).then(pl.lit(name)).otherwise(None)
                    )
                )
                .alias(col_alias)
            )

        df_working = df_working.with_columns(
            [
                build_herb_expr("Grasses & Sedges", GRASS_KEYWORDS, block_completely=True),
                build_herb_expr("Ferns", FERN_KEYWORDS, block_completely=True),
                build_herb_expr("Forbs", HERB_KEYWORDS, block_completely=True),  # The Fraser Fir Blocker
            ]
        )

        # 4. Final Consolidation
        temp_cols = ["_is_trees", "_is_shrubs", "_is_vines", "_is_grasses_sedges", "_is_ferns", "_is_forbs"]

        df_final = df_working.with_columns(
            plant_categories=pl.concat_list([pl.col(c) for c in temp_cols if c in df_working.columns])
            .list.drop_nulls()
            .list.unique()
        ).with_columns(
            plant_categories=pl.when(pl.col("plant_categories").list.len() == 0)
            .then(pl.lit(["Other"]))
            .otherwise(pl.col("plant_categories"))
        )

        return df_final.drop(temp_cols + ["_strict_search", "_fuzzy_search"])
