# beenative

An application to provide information about native plants.

## CLI

```bash
beenative --help
```

## Developer Documentation

Comprehensive developer documentation is available in [`docs/dev/`](./docs/dev/) covering testing, configuration, deployment, and all project features.

### Quick Start for Developers

```bash
# Install development environment
make install

# Start services with Docker
docker compose up -d

# Run tests
make tests

# Auto-fix formatting
make chores
```

See the [developer documentation](./docs/dev/README.md) for complete guides and reference.


# TODO List:

## Necessary

* Data Validation Script: A script to flag plants with missing Vascular data
  * Both spanish moss and virginia creeper are categorized as "Trees" - this is wrong

* scutellaria ovata var. bracteata - missing data from vascular. it seems like if there isn't a description than maybe the images also don't work?

* Github actions to publish code

## Nice to Have
* Refactoring and code cleaning for open source publication
* Export database as a CSV for "advanced" users.
* autocomplete for plant names?
* Name propegates to all pages of the PDF
* Pre-process getting image sizes of all thumbnail images to save on web requests
* When searching, if in description, give a snippet of that with the term(s) highlighted

* Full-Text Search (FTS5): For even faster and more "fuzzy" searches (handling typos like "Conflower" instead of "Coneflower"), look into SQLite’s FTS5 virtual tables for the description columns.

* Idea Add a secret gesture (like triple-tapping the logo) or a button in settings that opens a Scrollable Dialog containing the last 100 lines of the log file.
* provide a "Share Log" function that uses the native iOS share sheet to email the log file to yourself

* Full-Text Search (FTS5): For even faster and more "fuzzy" searches (handling typos like "Conflower" instead of "Coneflower"), look into SQLite’s FTS5 virtual tables for the description columns.

## Optional (need input)
* Photo gallery add more sources?
* Favorites/Shortlist: A heart icon to save specific plants to a local "My Garden" list that persists between sessions. This might be a seperate application...
* Fix the bottom links so that users don't ahve to scroll to get to them?
* Adding backend flags for specific garden goals: "Pollinator Friendly," "Erosion Control," or "Rain Garden."

Image Integration: As you mentioned, adding the image_url logic back in. This will require an "Image Cache" strategy so the app doesn't re-download the same flower photo every time it appears in search results.

Offline Mode: Since you’re using SQLite, the data is already local. Ensure the app handles "No Internet" states gracefully by hiding external NCSU links when offline.

Advanced Export: Allow users to "Favorite" plants and export that list as a CSV or PDF "Planting Plan."



Deploying an application with a local database requires a shift from a "developer mindset" (manually editing files) to an "automation mindset." Since your database contains 3,350 verified records, you aren't just deploying code; you're deploying a data-heavy environment.

Here is how the deployment and migration plan looks for different platforms.

1. The Strategy: Seeds vs. Migrations
When deploying to a new system (like a user's phone or a fresh Windows install), you face a "Cold Start" problem: the database file (`beenative.db`) won't exist yet.

The Seed (Initial Data): You should bundle a "Master" version of your SQLite database within your application package. When the app first runs, it checks if a local database exists in the user's "App Data" folder. If not, it copies the Master file there.

The Migrations (Schema Changes): As you add features (like a favorites table), Alembic runs scripts to update that local file without deleting the user's existing data.

3. The "Production Ready" Plan
To handle this effectively, you should implement these three steps:

B. The Startup Check
In your main() function in app.py, add a check that runs before the UI loads:

```Python

async def main(page: ft.Page):
    # 1. Ensure DB exists and is upgraded
    await ensure_database_ready() 
    
    # 2. Load UI
    # ...
```
C. Formalizing Alembic
Instead of manually running Alembic in the terminal, you can trigger migrations programmatically within the Python code using the alembic API. This ensures that every time a user opens your app, it automatically checks if the "JsonList" columns are correctly set up.

Next Step
To get this started, would you like me to help you write a "Database Manager" utility class? This class would handle finding the file path, running migrations, and initializing the connection so that app.py doesn't have to worry about the "plumbing."



"https://img.grid.ws" or https://commons.wikimedia.org/wiki/File:No-Image-Placeholder.svg


```python
    # def create_plant_card(plant):
    #     # Access attributes directly from the SQLAlchemy object
    #     display_name = plant.pm_common_name or plant.scientific_name
    #     sci_name = plant.scientific_name

    #     # Image handling - check model attribute
    #     image_src = plant.pm_image_url or "https://img.grid.ws" or https://commons.wikimedia.org/wiki/File:No-Image-Placeholder.svg

    #     # Sunlight Icons - 'plant.sunlight' is already a list
    #     sun_icons = []
    #     if plant.sunlight:
    #         if any("Full Sun" in s for s in plant.sunlight):
    #             sun_icons.append(ft.Icon(ft.Icons.WB_SUNNY, color=ft.Colors.ORANGE_400, size=16))
    #         if any("Part" in s for s in plant.sunlight):
    #             sun_icons.append(ft.Icon(ft.CupertinoIcons.SUN_MAX, color=ft.Colors.BLUE_GREY_400, size=16))
    #         if any("Shade" in s for s in plant.sunlight):
    #             sun_icons.append(ft.Icon(ft.Icons.NIGHTLIGHT_ROUND, color=ft.Colors.INDIGO_400, size=16))

    #     return ft.GestureDetector(
    #         on_tap=lambda _: show_details(plant),
    #         content=ft.Card(
    #             content=ft.Container(
    #                 padding=10,
    #                 width=200,
    #                 content=ft.Column(
    #                     [
    #                         ft.Image(
    #                             src=image_src,
    #                             width=180,
    #                             height=120,
    #                             fit=ft.BoxFit.COVER,
    #                             border_radius=ft.border_radius.all(8),
    #                         ),
    #                         ft.Text(
    #                             display_name,
    #                             weight=ft.FontWeight.BOLD,
    #                             size=14,
    #                             max_lines=1,
    #                             overflow=ft.TextOverflow.ELLIPSIS,
    #                         ),
    #                         ft.Text(
    #                             sci_name,
    #                             italic=True,
    #                             size=12,
    #                             color=ft.Colors.GREY_500,
    #                         ),
    #                         ft.Row(sun_icons, spacing=5),
    #                         # Plant Categories (JSON list)
    #                         ft.Text(
    #                             ", ".join(plant.plant_categories[:2]) if plant.plant_categories else "",
    #                             size=10,
    #                             color=ft.Colors.GREEN_700,
    #                         ),
    #                     ],
    #                     spacing=5,
    #                 ),
    #             )
    #         ),
    #     )

    # async def run_search(e=None):
    #     results_col.controls.clear()
    #     results_col.controls.append(ft.ProgressBar())
    #     page.update()
    #     results_col.controls.clear()

    #     async with get_session() as session:
    #     # We pass the query and unpack the state dictionary into the engine
    #     df = await asyncio.to_thread(db.search_plants, query=search_input.value, **state)

    #     if df.is_empty():
    #         results_col.controls.append(
    #             ft.Container(
    #                 content=ft.Text("No plants match your search/filters", size=18, color=ft.Colors.GREY_500),
    #                 padding=20,
    #                 alignment=ft.Alignment.CENTER
    #             )
    #         )
    #     else:
    #         for row in df.to_dicts():
    #             try:
    #                 # Attempt to parse common names
    #                 name = row.get("vasc_common_name_primary")
    #                 display_name = name if name else row["scientific_name"]

    #                 categories = row.get("plant_categories", [])
    #                 plant_icon = get_plant_icon(categories)

    #                 results_col.controls.append(
    #                     ft.ListTile(
    #                         leading=ft.Icon(plant_icon, color=ft.Colors.GREEN_400),
    #                         title=ft.Text(display_name),
    #                         subtitle=ft.Text(row["scientific_name"], italic=True),
    #                         on_click=lambda _, r=row: asyncio.create_task(show_details(r))
    #                     )
    #                 )
    #             except Exception as e:
    #                 print(f"Error rendering row: {e}")
    #     page.update()
```



BeeNative Data Integration & Processing GuideThe BeeNative application aggregates and normalizes native plant data specifically for North Carolina. To provide users with comprehensive details ranging from basic taxonomy to specific growing conditions, the application runs a multi-stage data ingestion pipeline.1. Primary Data SourcesThe application relies on four primary sources to construct its database:Vascular Plants of North Carolina: Acts as the foundational "ground truth" for identifying native species. It provides scientific names, primary common names, map distribution images, and specific botanical account details.NC Extension Gardener Plant Toolbox (NCSU): Supplies detailed horticultural data. This includes phonetic spellings, HTML-formatted descriptions, cultivars, physical attributes, and image galleries complete with licensing metadata.Prairie Moon Nursery: Acts as the primary source for seed and propagation data. It provides wildlife value indicators, bloom colors, bloom times, specific height markers, and environmental needs like sun and moisture exposure.Flora of the Southeastern United States (NCBG): Supplements the database with high-resolution imagery and permanent reference links. It extracts thumbnail URLs, original high-resolution image links, copyright attributions, and license details.2. Plant Selection ProcessNot all plants listed in the crawled databases make it into the final application. The selection process ensures strict adherence to native NC species:The system uses the Vascular Plants of North Carolina database to identify native species.The crawler evaluates the background color of table rows on the source website to filter out non-native plants.The crawler explicitly excludes colors that indicate "Exotic" (#ffbb99), "Uncertain" (#ffe699), "Not Valid" (#ffff99), and "Not in NC" (#eeccff).During the final database preparation, any plant that does not have a matching Vascular NC ID is permanently removed from the dataset.3. Data Consolidation and Field MappingBecause the application ingests data from four distinct sources, many fields overlap or use different terminology. The system uses specific consolidation algorithms to map these into clean, unified columns.Common NamesThe system aggregates names from Vascular NC, Prairie Moon, and NCSU.It strips out conversational "junk words" like "Most", "Some", and "Reference".It parses out quotation marks and isolates valid hyphenated names into a single, deduplicated list.Plant Categories (Woody vs. Herbaceous)The system categorizes plants using strict NCSU tags and fuzzy keyword searches across descriptions.Plants are grouped into "Woody" categories (Trees, Shrubs, Vines) or "Herbaceous" categories (Grasses & Sedges, Ferns, Forbs).An absolute override prevents any plant identified as a Tree, Shrub, or Vine from being simultaneously categorized as a "Forb", even if another source tags it as a perennial.Sunlight RequirementsNCSU sunlight strings (e.g., "Full sun", "Deep shade") and Prairie Moon strings (e.g., "Partial", "Shade") are mapped to a standard dictionary.The final output creates a unified list column containing standardized values: "Full Sun", "Partial Shade", "Dappled Sunlight", or "Deep Shade".Moisture & DrainageNCSU drainage descriptions are converted to standardized moisture levels.For example, "Frequent Standing Water" maps to "Wet", while "Occasionally Dry" maps to "Medium-Dry".These are combined with Prairie Moon's existing moisture tags into a single list of categories.Bloom Time ValidationThe system combines textual bloom times from Prairie Moon, NCSU, and Vascular NC.It utilizes a precision algorithm to extract exact months and date ranges (e.g., "May to Jul" or "spring").The output is a weighted JSON dictionary that tracks how many times a specific month is confirmed across the different sources.Dimensions (Height and Width)Raw textual dimensions from Prairie Moon and NCSU are extracted and standardized.The algorithm converts various formats (e.g., "ft.", "inches", "'") into decimal feet.It determines unified minimum and maximum heights, prioritizing Prairie Moon height data when conflicts occur.The final outputs are clean, formatted strings (e.g., "2.0–4.5 ft") alongside the raw float values.Wildlife Value & ResistancesThe system checks boolean flags from Prairie Moon indicating if a plant is advantageous for bees, birds, or deer.It merges these flags with textual "Attracts" and "Resistance To" columns from NCSU.The output yields two clean lists: wildlife_attracts and plant_resistances.Flower ColorsThe system consolidates raw color descriptions from Prairie Moon and NCSU into a single searchable string.It searches this string against a strict color map of 10 primary colors (Yellow, White, Red, Blue, Purple, Orange, Pink, Green, Brown, Grey).Synonyms like "crimson" or "burgundy" are automatically mapped to the parent "Red" category.4. Application CLI CommandsThe data is processed sequentially using the bundled command-line interface.CommandDescriptioninitializeCrawls all four sources based on the local vascular plant list and downloads raw HTML/JSON files.processParses the downloaded raw files into structured Polars DataFrames and merges them into a single parquet file.prep_dbExecutes the field mapping algorithms (deduplication, sunlight extraction, categorization) and saves the final normalized output to the SQLite database.migrateHandles database schema updates using Alembic.



# BeeNative: North Carolina’s Native Plant Guide

Welcome to BeeNative! Our goal is to provide you with accurate, useful, and quick-glance information about plants native to North Carolina to enable with education of native plants for gardeners and native plant nurseries. This application is designed for NC residents who want a quick guide to understanding key gardening information about a plant. 

We make no such attempt to replace the high-quality field-botany plant identification guides provided by [UNC Chapel Hill Herbarium's FloraQuest](https://ncbg.unc.edu/research/unc-herbarium/flora-apps/). Rather, we carefully gather and combine details from trusted botanical sources and provide a simplified lookup for gardeners and NC plant nurseries. We are deeply grateful to the incredible resources of our data sources and recommend users interested in learning more about a particular plant to visit the cited sources.

This guide explains exactly where our data comes from, how we decide which plants are included, and the exact rules we use to organize everything so it's easy for you to understand.

---

## 1. App Features & Displayed Information

The BeeNative app is designed for speed and ease of use. Whether you are at a nursery or in your backyard, these features help you find the right plant:

* **Smart Search:** Instantly find plants by their Common Name or Scientific Name.
* **Condition Filters:** Tap to narrow your list by **Bloom Color**, **Sunlight**, or **Moisture** needs.
* **Native Range Maps:** View official county-level maps showing exactly where each plant naturally grows in North Carolina.
* **Wildlife Impact:** Look for "Quick Glance" icons that show if a plant supports bees, birds, or butterflies.
* **PDF Catalog Creator:** Select a group of plants to generate a professional PDF guide—perfect for creating a custom shopping list to take to your local nursery.
* **Botanical Confidence:** Every plant includes a phonetic pronunciation (e.g., *“uh-SKLEE-pee-us”*) so you can master the names used by professionals.

---

# About the BeeNative Database

Welcome to the most comprehensive guide to North Carolina’s native plants. 

Building a reliable database for native plants is a bit like putting together a massive jigsaw puzzle. Different experts have different pieces of the puzzle: one knows the scientific names, another knows how to grow them in a garden, and another knows which bees love them. 

**BeeNative** acts as the "Master Librarian." We have built custom tools that visit four of the most prestigious botanical institutions in the Southeast, collect their specialized knowledge, and organize it into one easy-to-use application.

---


### How We Keep It Simple
Botanical data is often messy. One website might say a plant likes "wet feet," while another says it needs "frequent flooding." 

Our system uses **Smart Mapping**. We have programmed "translation rules" that read thousands of lines of text and simplify them into standard categories. When you filter for a "Yellow" flower that likes "Partial Shade," our app has already done the hard work of checking every source to make sure that plant fits your criteria.

### Our Promise of Quality
* **Verified Native:** If a plant isn't officially listed as native to NC by the state's top botanists, it doesn't make it into our app.
* **Cleaned Names:** We remove confusing codes and technical "junk" so you only see the names people actually use.
* **Unified Measurements:** Whether a source uses inches, feet, or symbols, we convert everything into a single format so you can easily compare the size of two different plants.

---