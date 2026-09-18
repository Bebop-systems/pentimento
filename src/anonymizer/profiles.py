"""Internally-consistent camera identities.

Every field in a profile has to agree with every other. A body paired with
a lens it never shipped with is exactly the contradiction the linter exists
to catch, so the source data must not contain any.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CameraProfile:
    key: str
    label: str
    make: str
    model: str
    lens_model: str
    lens_make: str
    focal_length: str
    f_number: str
    software: str


PROFILES: dict[str, CameraProfile] = {
    p.key: p for p in [
        CameraProfile(
            "iphone-15-pro", "Apple iPhone 15 Pro (iOS 17.5.1)",
            "Apple", "iPhone 15 Pro",
            "iPhone 15 Pro back triple camera 6.765mm f/1.78", "Apple",
            "6.765", "1.78", "17.5.1",
        ),
        CameraProfile(
            "iphone-13", "Apple iPhone 13 (iOS 16.6)",
            "Apple", "iPhone 13",
            "iPhone 13 back dual wide camera 5.1mm f/1.6", "Apple",
            "5.1", "1.6", "16.6",
        ),
        CameraProfile(
            "pixel-8", "Google Pixel 8",
            "Google", "Pixel 8",
            "Pixel 8 back camera 6.9mm f/1.68", "Google",
            "6.9", "1.68", "HDR+ 1.0.640190411zd",
        ),
        CameraProfile(
            "galaxy-s23", "Samsung Galaxy S23",
            "samsung", "SM-S911B",
            "Galaxy S23 Rear Camera", "samsung",
            "5.4", "1.8", "S911BXXU3BWL1",
        ),
    ]
}
