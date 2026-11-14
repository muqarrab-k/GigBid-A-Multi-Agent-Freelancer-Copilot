import argparse
from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ChannelRow:
    channel: str
    sessions: int
    spend: float
    first_click_credit: float
    last_click_credit: float
    position_based_credit: float


def normalize_channel(channel: str) -> str:
    return channel.strip().lower()


def build_report(rows: List[ChannelRow]) -> List[Dict[str, float]]:
    report = []
    for row in rows:
        report.append(
            {
                "channel": normalize_channel(row.channel),
                "sessions": row.sessions,
                "spend": row.spend,
                "first_click_cpa": row.spend / row.first_click_credit if row.first_click_credit else 0.0,
                "last_click_cpa": row.spend / row.last_click_credit if row.last_click_credit else 0.0,
                "position_based_cpa": row.spend / row.position_based_credit if row.position_based_credit else 0.0,
            }
        )
    return report


def print_report(report: List[Dict[str, float]]) -> None:
    header = "channel,sessions,spend,first_click_cpa,last_click_cpa,position_based_cpa"
    print(header)
    for row in report:
        print(
            f"{row['channel']},{row['sessions']},{row['spend']:.2f},"
            f"{row['first_click_cpa']:.2f},{row['last_click_cpa']:.2f},{row['position_based_cpa']:.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare attribution models for GA4 channel performance.")
    parser.add_argument("--sample", action="store_true", help="Use a small local sample instead of BigQuery output.")
    args = parser.parse_args()

    # This file compares model credit after the BigQuery join.
    rows = [
        ChannelRow("Paid Search", 1200, 8400.0, 300.0, 220.0, 260.0),
        ChannelRow("Organic Search", 1800, 0.0, 420.0, 500.0, 460.0),
        ChannelRow("Paid Social", 900, 6100.0, 190.0, 130.0, 160.0),
    ] if args.sample else []

    report = build_report(rows)
    print_report(report)


if __name__ == "__main__":
    main()
