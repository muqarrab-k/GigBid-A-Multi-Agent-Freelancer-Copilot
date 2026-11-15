"""Write the bid graph diagram from code."""

from agent.config import ROOT
from agent.graphs.bid_graph import build_bid_graph

OUT = ROOT / "docs" / "images" / "bid_graph.mmd"


def main() -> None:
    OUT.write_text(build_bid_graph().get_graph().draw_mermaid())
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
