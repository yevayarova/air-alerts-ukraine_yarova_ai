from air_alerts.config import INTERIM_DIR, RAW_DIR
from air_alerts.data_sources import inspect_dataset

dataset_dir = RAW_DIR / "ukrainian-air-raid-sirens-dataset"

df = inspect_dataset(dataset_dir)
print(df)

INTERIM_DIR.mkdir(parents=True, exist_ok=True)
output_path = INTERIM_DIR / "raw_file_inventory.csv"
df.write_csv(output_path)

print(f"Saved: {output_path}")
