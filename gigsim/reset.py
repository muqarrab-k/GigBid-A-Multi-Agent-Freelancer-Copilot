import argparse

from gigsim.seeding import reset
from gigsim.settings import load_settings
from gigsim.store import Store


def main() -> None:
    """Reset the local database without the server."""
    parser = argparse.ArgumentParser(description="Reset the GigSim database")
    parser.add_argument("--scenario", choices=["live", "dev"], default=None)
    parser.add_argument("--seed", type=int, default=None)
    args = parser.parse_args()
    settings = load_settings()
    print(reset(Store(settings.path(settings.storage)), settings, args.scenario, args.seed))


if __name__ == "__main__":
    main()
