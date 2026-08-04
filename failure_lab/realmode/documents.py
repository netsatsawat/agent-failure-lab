"""Synthetic expense-report generator with exact ground truth.

Documents are rendered in deliberately varied (but unambiguous) formats so
extraction is non-trivial. Every quantity the agent must produce is derivable
from the ground truth, which makes automatic failure classification possible.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

RATES = {"THB": 0.028, "USD": 1.0, "EUR": 1.08}
CATEGORIES = ("meals", "lodging", "transport", "supplies", "other")

_TEMPLATES = {
    "meals": ["Team dinner at riverside restaurant", "Client lunch meeting",
              "Hotel breakfast buffet", "Working dinner with vendor"],
    "lodging": ["Hotel room - 2 nights", "Serviced apartment stay",
                "Airport hotel - 1 night"],
    "transport": ["Taxi from airport", "Grab ride to client office",
                  "BTS Skytrain day passes", "Airport rail link tickets"],
    "supplies": ["HDMI adapter and cables", "Printed presentation decks",
                 "Whiteboard markers and notepads"],
    "other": ["Conference entry badge", "Visa processing fee",
              "Baggage fee for equipment"],
}

_EMPLOYEES = ["Anna Kowalski", "Ben Tanaka", "Chai Srisuwan", "Dara Lim",
              "Elena Petrova", "Farid Rahman"]

# Normalized description -> true category, for classifying items that are not
# in a document's ground truth (e.g. a VOIDED line the agent wrongly extracted).
TEMPLATE_CATEGORIES = {t.strip().lower(): cat
                       for cat, ts in _TEMPLATES.items() for t in ts}

_CURRENCY_STYLE = {
    "THB": ["THB {amt}", "{amt} THB", "฿{amt}"],
    "USD": ["USD {amt}", "${amt}", "{amt} USD"],
    "EUR": ["EUR {amt}", "€{amt}", "{amt} EUR"],
}


@dataclass
class Item:
    description: str
    amount: float
    currency: str
    category: str

    @property
    def amount_usd(self) -> float:
        return round(self.amount * RATES[self.currency], 2)


@dataclass
class GroundTruth:
    doc_id: int
    employee: str
    start: date
    end: date
    items: list = field(default_factory=list)

    @property
    def currencies_needing_rates(self) -> set:
        return {i.currency for i in self.items if i.currency != "USD"}

    @property
    def category_totals(self) -> dict:
        totals: dict = {}
        for i in self.items:
            totals[i.category] = round(totals.get(i.category, 0) + i.amount_usd, 2)
        return totals

    @property
    def grand_total(self) -> float:
        return round(sum(i.amount_usd for i in self.items), 2)

    @property
    def flags(self) -> dict:
        return {
            "total_exceeds_2000": self.grand_total > 2000,
            "any_single_item_over_500": any(i.amount_usd > 500 for i in self.items),
            "trip_longer_than_7_days": (self.end - self.start).days > 7,
        }

    @property
    def true_flag_names(self) -> list:
        return sorted(k for k, v in self.flags.items() if v)


def make_ground_truth(doc_id: int, rng: random.Random) -> GroundTruth:
    employee = rng.choice(_EMPLOYEES)
    start = date(2026, rng.randint(1, 6), rng.randint(1, 25))
    end = start + timedelta(days=rng.randint(2, 9))
    n_items = rng.randint(5, 7)
    items, used = [], set()
    cats = list(CATEGORIES)
    rng.shuffle(cats)
    for k in range(n_items):
        cat = cats[k % len(cats)]
        choices = [t for t in _TEMPLATES[cat] if t not in used] or _TEMPLATES[cat]
        desc = rng.choice(choices)
        used.add(desc)
        currency = rng.choice(list(RATES))
        base = {"meals": (18, 160), "lodging": (90, 420), "transport": (6, 60),
                "supplies": (8, 90), "other": (15, 350)}[cat]
        amount = round(rng.uniform(*base), 2)
        if currency == "THB":
            amount = round(amount / RATES["THB"] / 10) * 10.0
        items.append(Item(desc, amount, currency, cat))
    return GroundTruth(doc_id, employee, start, end, items)


def render_document(gt: GroundTruth, rng: random.Random,
                    hard: bool = False) -> str:
    """Render the ground truth as a document.

    ``hard=True`` adds realistic adversity WITHOUT changing the ground truth:
    scan-noise lines, shuffled items, a VOIDED line that must be excluded,
    and a printed "Total claimed" that is deliberately wrong — an agent that
    copies the shortcut instead of computing gets caught by classification.
    """
    date_styles = [
        lambda d: d.isoformat(),
        lambda d: d.strftime("%d %b %Y"),
        lambda d: d.strftime("%B %d, %Y"),
    ]
    ds = rng.choice(date_styles)
    lines = [
        "EXPENSE REIMBURSEMENT REQUEST",
        f"Submitted by: {gt.employee}",
        f"Trip period: {ds(gt.start)} to {ds(gt.end)}",
        "",
        "Expenses claimed:",
    ]
    item_lines = []
    for i in gt.items:
        amt = f"{i.amount:,.2f}" if rng.random() < 0.5 else f"{i.amount:.2f}"
        style = rng.choice(_CURRENCY_STYLE[i.currency])
        leader = rng.choice([" .... ", "  ...... ", "   -   "]) if hard else " .... "
        item_lines.append(f"  - {i.description}{leader}{style.format(amt=amt)}")
    if hard:
        rng.shuffle(item_lines)
        # The VOIDED description must not collide with a real item — evaluation
        # keys items by description, so a duplicate would make the trap ambiguous.
        gt_descs = {i.description for i in gt.items}
        candidates = sorted(t for ts in _TEMPLATES.values() for t in ts
                            if t not in gt_descs)
        void_desc = rng.choice(candidates)
        void_amt = round(rng.uniform(20, 300), 2)
        pos = rng.randint(0, len(item_lines))
        item_lines.insert(pos, f"  - {void_desc} .... USD {void_amt:.2f}   "
                               f"[VOIDED - do not reimburse]")
    lines += item_lines
    if hard:
        wrong_total = round(gt.grand_total * rng.uniform(1.04, 1.18) + 7, 2)
        lines += ["", f"Total claimed (pre-checked): USD {wrong_total:,.2f} "
                      "-- pending finance validation, do not rely on this figure"]
        noise_at = rng.randint(1, 3)
        lines.insert(noise_at, f"[scanned p.1/1 - fax id 66-2-{rng.randint(100,999)}"
                               f"-{rng.randint(1000,9999)} - quality LOW]")
    lines += ["", "Please process according to company travel policy.",
              f"Reference: TRIP-{gt.doc_id:04d}"]
    return "\n".join(lines)
