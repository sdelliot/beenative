from .db import DatabaseSettings


class Settings(DatabaseSettings):
    project_name: str = "beenative"
    debug: bool = False
    crawl_dir: str = "beenative/crawls"
    download_maps_dir: str = "beenative/maps"

    vascular_nc_base_url: str = "https://auth1.dpr.ncparks.gov/flora/"
    vascular_nc_target_url: str = f"{vascular_nc_base_url}species_account.php"
    prairie_moon_base_url: str = "https://qfh40u.a.searchspring.io/api/search/search.json"
    ncsu_plant_toolbox_base_url: str = "https://plants.ces.ncsu.edu/"
    ncsu_plant_toolbox_plants_url: str = f"{ncsu_plant_toolbox_base_url}plants/"

    ncbg_base_url: str = "https://fsus.ncbg.unc.edu/"
    ncbg_target_url: str = f"{ncbg_base_url}main.php"

    requests_headers: dict = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Upgrade-Insecure-Requests": "1",
    }
    vascular_nc_headers: dict = requests_headers | {"Content-Type": "application/x-www-form-urlencoded"}
    prairie_moon_headers: dict = requests_headers | {
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
    }
