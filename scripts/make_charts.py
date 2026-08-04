#!/usr/bin/env python3
"""Generate the README hero image into assets/."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib  # noqa: E402
matplotlib.use("Agg")

from failure_lab.charts import collapse_by_accuracy_fig, mitigation_fig  # noqa: E402


def main() -> None:
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    collapse_by_accuracy_fig().savefig(assets / "collapse_curves.png",
                                       facecolor="#fcfcfb", bbox_inches="tight")
    mitigation_fig().savefig(assets / "mitigations.png",
                             facecolor="#fcfcfb", bbox_inches="tight")
    print(f"wrote {assets / 'collapse_curves.png'}")
    print(f"wrote {assets / 'mitigations.png'}")


if __name__ == "__main__":
    main()
