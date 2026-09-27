import polars as pl
import base64


def verify_first_map(file_path="native_plants.parquet"):
    # Load the data
    df = pl.read_parquet(file_path)

    # Filter for non-null maps and get the first value
    subset = df.filter(pl.col("map_image_base64").is_not_null())

    if subset.is_empty():
        print("❌ No map data found in file. Did you run with --render-maps?")
        return

    # Extract the first item from the 'map_image_base64' column
    img_str = subset.select("map_image_base64")[0, 0]

    # Decode and save
    img_bytes = base64.b64decode(img_str)
    with open("verification_map.png", "wb") as f:
        f.write(img_bytes)

    print("✅ Success! Map saved to verification_map.png")


if __name__ == "__main__":
    verify_first_map()
