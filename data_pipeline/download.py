import os
from pathlib import Path

from data_pipeline.common import Source, load_sources, table_files

KAGGLE_DIR = Path(os.getenv("KAGGLE_CONFIG_DIR", Path.home() / ".kaggle"))


def has_credentials() -> bool:
    if os.getenv("KAGGLE_USERNAME") and os.getenv("KAGGLE_KEY"):
        return True
    if os.getenv("KAGGLE_API_TOKEN"):
        return True
    return (KAGGLE_DIR / "kaggle.json").is_file() or (KAGGLE_DIR / "access_token").is_file()


def download(source: Source) -> None:
    from kaggle.api.kaggle_api_extended import KaggleApi

    api = KaggleApi()
    api.authenticate()
    source.folder.mkdir(parents=True, exist_ok=True)
    print(f"downloading {source.name} ({source.slug})")
    api.dataset_download_files(source.slug, path=str(source.folder), unzip=True, quiet=True)


def main() -> list[str]:
    """Fetch missing datasets, return names still missing."""
    sources = load_sources()
    missing = [s for s in sources if not table_files(s)]
    if missing and has_credentials():
        for source in missing:
            download(source)
        missing = [s for s in sources if not table_files(s)]

    for source in sources:
        files = table_files(source)
        state = f"{len(files)} file(s)" if files else "MISSING"
        print(f"  {source.name:<20} {state}")

    if missing:
        print("\nmissing datasets, place them manually:")
        for source in missing:
            print(f"  {source.folder}  <-  {source.url}")
        if not has_credentials():
            print("no Kaggle credentials (~/.kaggle/kaggle.json or KAGGLE_USERNAME/KAGGLE_KEY)")
    return [s.name for s in missing]


if __name__ == "__main__":
    main()
