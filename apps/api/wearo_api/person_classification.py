from __future__ import annotations

from typing import Literal

PersonCategory = Literal["unknown", "girl", "woman"]
AgeRange = Literal[
    "unknown",
    "under_10",
    "10_19",
    "20_29",
    "30_39",
    "40_49",
    "50_59",
    "60_plus",
]

AGE_RANGES: frozenset[str] = frozenset(
    {"unknown", "under_10", "10_19", "20_29", "30_39", "40_49", "50_59", "60_plus"}
)

PERSON_CATEGORY_RANK: dict[PersonCategory, int] = {
    "unknown": 0,
    "girl": 1,
    "woman": 2,
}


def promoted_person_category(stored: PersonCategory, observed: PersonCategory) -> PersonCategory:
    """Promote an observed presentation category without ever downgrading it."""
    return observed if PERSON_CATEGORY_RANK[observed] > PERSON_CATEGORY_RANK[stored] else stored


def age_range_for_estimate(estimated_age: int) -> AgeRange:
    """Map a valid visual age estimate to its stable analytics band."""
    if estimated_age < 10:
        return "under_10"
    if estimated_age < 20:
        return "10_19"
    if estimated_age < 30:
        return "20_29"
    if estimated_age < 40:
        return "30_39"
    if estimated_age < 50:
        return "40_49"
    if estimated_age < 60:
        return "50_59"
    return "60_plus"
