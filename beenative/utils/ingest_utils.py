import polars as pl
from rich.console import Console
import re


LICENSE_DB = {
    "CC-BY-NC-SA": ("CC BY-NC-SA 4.0", "https://creativecommons.org/licenses/by-nc-sa/4.0/"),
    "CC-BY-NC-ND": ("CC BY-NC-ND 4.0", "https://creativecommons.org/licenses/by-nc-nd/4.0/"),
    "CC-BY-NC": ("CC BY-NC 4.0", "https://creativecommons.org/licenses/by-nc/4.0/"),
    "CC-BY-SA": ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
    "CC-BY": ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
    "CC0": ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
    "PUBLIC-DOMAIN": ("Public Domain", "https://creativecommons.org/publicdomain/mark/1.0/"),
    "PD-MARK": ("Public Domain", "https://creativecommons.org/publicdomain/mark/1.0/"),
}

# Base mapping for CC types
CC_BASE_DATA = {
    "CC-BY-NC-SA": "by-nc-sa",
    "CC-BY-NC-ND": "by-nc-nd",
    "CC-BY-NC": "by-nc",
    "CC-BY-SA": "by-sa",
    "CC-BY": "by",
    "CC0": "zero",
    "PUBLIC-DOMAIN": "mark",
}

# Standardized Name mapping
CC_NAMES = {
    "by-nc-sa": "CC BY-NC-SA",
    "by-nc-nd": "CC BY-NC-ND",
    "by-nc": "CC BY-NC",
    "by-sa": "CC BY-SA",
    "by": "CC BY",
    "zero": "CC0",
    "mark": "Public Domain",
}

logged_unknown_licenses = set()


def normalize_image_data(img_data, verbose=True):
    """
    Standardizes messy image metadata into a clean TASL format.
    Returns a dict with guaranteed keys: 'title', 'author', 'source_url', 'license_text', 'license_url'.
    """
    raw_lic = img_data.get("license") or ""
    raw_lic_url = img_data.get("license_url")

    clean_lic_name = raw_lic
    clean_lic_url = raw_lic_url
    is_standard = False

    # Normalize for matching: "CC BY-NC 2.0" -> "CC-BY-NC-2.0"
    norm_lic = raw_lic.upper().replace(" ", "-").replace("_", "-")

    # 1. Find the Base CC Type
    for key, slug in CC_BASE_DATA.items():
        if key in norm_lic:
            is_standard = True

            # 2. Try to extract a version number (e.g., 2.0 or 4.0)
            version_match = re.search(r"(\d\.?\d?)", raw_lic)
            version = version_match.group(1) if version_match else "4.0"

            # 3. Construct official Name and URL
            clean_lic_name = f"{CC_NAMES[slug]} {version}"

            # CC0 and Public Domain have different URL structures
            if slug == "zero":
                clean_lic_url = "https://creativecommons.org/publicdomain/zero/1.0/"
                clean_lic_name = "CC0 1.0"
            elif slug == "mark":
                clean_lic_url = "https://creativecommons.org/publicdomain/mark/1.0/"
                clean_lic_name = "Public Domain Mark 1.0"
            else:
                clean_lic_url = f"https://creativecommons.org/licenses/{slug}/{version}/"

            break

    # 4. Audit Log for truly unknown licenses
    if raw_lic and not is_standard:
        if raw_lic not in logged_unknown_licenses:
            if verbose:
                print(f"⚠️ [LICENSE AUDIT] Unknown/Messy License Found: '{raw_lic}'")
            logged_unknown_licenses.add(raw_lic)

    img_data.update(
        {
            "title": img_data.get("caption") or "Photo",
            "author": (img_data.get("copyright") or "Unknown").replace("©", "").strip(),
            "source_url": img_data.get("source_url") or img_data.get("original_url"),
            "license_text": clean_lic_name,
            "license_url": raw_lic_url or clean_lic_url,  # Prioritize provided URL
            "is_standard": is_standard,
        }
    )
    return img_data


def normalize_names(df):
    return df.with_columns(pl.col("scientific_name").str.strip_chars().str.to_lowercase())


def sanitize_column_names(df: pl.DataFrame) -> pl.DataFrame:
    """Converts all column names to lower_snake_case and removes special chars."""
    new_names = []
    for col in df.columns:
        # 1. Lowercase
        name = col.lower()
        # 2. Replace spaces, slashes, parens, and hyphens with underscores
        name = re.sub(r"[^a-z0-9_]", "_", name)
        # 3. Collapse multiple underscores into one and trim
        name = re.sub(r"_+", "_", name).strip("_")
        new_names.append(name)

    return df.rename(dict(zip(df.columns, new_names)))


def check_merge_quality(df):
    console = Console()
    console.print("[bold yellow]Missing Values Per Source:[/bold yellow]")

    # Calculate null counts for each column
    null_counts = df.null_count()
    console.print(null_counts)

    # Show a random sample of 5 rows
    if len(df) > 5:
        console.print("[bold blue]Random Sample:[/bold blue]")
        console.print(df.sample(5))


def debug_df(df, title="Data Sample"):
    console = Console()

    # Convert Polars head to a pandas-style dict for Rich to render easily
    # Or just use Polars' built-in formatting which Rich handles well
    console.rule(f"[bold magenta]{title}[/bold magenta]")

    # Print shape and schema info
    console.print(f"Shape: {df.shape}")

    # Use rich to print the polars output (it will auto-format)
    console.print(df.head(5))
    console.rule()
