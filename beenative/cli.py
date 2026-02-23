import asyncio
from collections.abc import Callable
from functools import wraps
from typing import Any
import polars as pl
import typer

from pathlib import Path
from alembic.config import Config
from alembic import command
from settings import settings

from api import BeeNativeAPI
from utils.ingest import BeeNativeDB

app = typer.Typer()


def syncify(f: Callable[..., Any]) -> Callable[..., Any]:
    """This simple decorator converts an async function into a sync function,
    allowing it to work with Typer.
    """

    @wraps(f)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.run(f(*args, **kwargs))

    return wrapper


@app.command(help=f"Display the current installed version of {settings.project_name}.")
def version() -> None:
    from . import __version__

    typer.echo(f"{settings.project_name} - {__version__}")


@app.command()
def initialize(
    vascular_source: str = typer.Argument("beenative/plant_list.html", help="The local HTML file to parse"),
    get_maps: bool = typer.Option(False, "--get-maps", help="Download map PNGs during processing"),
    ncsu_output_file: str = typer.Option(
        "beenative/ncsu_plant_data.parquet", help="Path to save NCSU Plant Toolbox data output"
    ),
    vascular_output_file: str = typer.Option("beenative/native_plants.parquet", help="Path to save NC Vascular output"),
    ncbg_output_file: str = typer.Option(
        "beenative/ncbg_plant_data.parquet", help="Path to save Flora of the Southeastern United States data output"
    ),
    delay: float = typer.Option(1.0, help="Seconds to wait between requests"),
):
    """
    Crawls the NC Parks Flora site for native plant details based on a local list.
    """
    api = BeeNativeAPI()
    try:
        api.initialize(vascular_source, delay, get_maps, vascular_output_file, ncsu_output_file, ncbg_output_file)
    except Exception as e:
        typer.secho(f"❌ Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command()
def process(
    output: str = typer.Option("beenative/merged.parquet", "--output", "-o"),
):
    """
    Parses downloaded HTML into a structured Polars DataFrame.
    Note: Using .parquet is recommended if storing Base64 images.
    """
    api = BeeNativeAPI()
    try:
        api.process_data(
            input_vasc="beenative/native_plants.parquet",
            input_ncsu="beenative/ncsu_plant_data.parquet",
            input_ncbg="beenative/ncbg_plant_data.parquet",
            output_path=output,
        )
    except Exception as exc:
        typer.secho(f"❌ Error: {exc}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from exc


@app.command()
def prep_db(
    input: str = typer.Option("beenative/merged.parquet", "--input", "-i"),
):
    """
    Parses downloaded HTML into a structured Polars DataFrame.
    Note: Using .parquet is recommended if storing Base64 images.
    """
    api = BeeNativeAPI()
    try:
        df = pl.read_parquet(input)
        df = api.deduplicate_plants(df)
        df = api.prepare_for_sqlite(df)
        df = api.remove_non_nc_plants(df)
        df = api.create_common_names(df)
        df = api.merge_wildlife(df)
        df = api.update_bloomtime(df)
        df = api.extract_sunlight_values(df)
        df = api.extract_moisture_values(df)
        df = api.extract_lifecycle(df)
        df = api.parse_dimensions(df)
        df = api.standardize_colors(df)
        df = api.categorize_plants(df)
        bdb = BeeNativeDB()
        bdb.save_dataframe(df)
    except Exception as e:
        typer.secho(f"❌ Error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1)


@app.command()
def migrate(message: str = typer.Option(None, "--message", "-m", help="Revision message")):
    """
    Handles database schema updates.
    Runs 'autogenerate' if a message is provided, otherwise upgrades to latest.
    """
    # 1. Load Alembic configuration
    project_root = Path(__file__).resolve().parent.parent
    ini_path = project_root / "alembic.ini"

    if not ini_path.exists():
        typer.secho(f"❌ Could not find alembic.ini at {ini_path}", fg=typer.colors.RED)
        raise typer.Exit(1)

    # Alembic Config expects a string path
    alembic_cfg = Config(str(ini_path))

    if message:
        typer.echo(f"✨ Generating new migration: {message}...")
        command.revision(alembic_cfg, message=message, autogenerate=True)

    typer.echo("🚀 Upgrading database to latest schema...")
    command.upgrade(alembic_cfg, "head")
    typer.secho("✅ Database is now up to date.", fg=typer.colors.GREEN)


if __name__ == "__main__":
    app()
