"""Camera identities, both credible and deliberately not.

Every field in a profile has to agree with every other. A body paired with
a lens it never shipped with is exactly the contradiction the linter exists
to catch, so the source data must not contain any.

That agreement extends to the filename. `IMG_0942.HEIC` announces Apple as
plainly as the Make tag does, so each profile carries the naming convention
its camera actually uses.

Novelty profiles keep the same rule. They are absurd about *which* camera
they claim, never about internal consistency, and their numeric fields stay
real numbers so a written file still passes all four gates. The comedy
lives in the text fields; the optics stay arithmetic.
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
    filename_pattern: str
    novelty: bool = False
    note: str = ""


_CREDIBLE = [
    CameraProfile(
        "iphone-15-pro", "Apple iPhone 15 Pro (iOS 17.5.1)",
        "Apple", "iPhone 15 Pro",
        "iPhone 15 Pro back triple camera 6.765mm f/1.78", "Apple",
        "6.765", "1.78", "17.5.1",
        filename_pattern="IMG_{n:04}{ext}",
        note="IMG_0001 is not Apple's invention. Every camera since 1998 "
             "follows DCF, which demands exactly four letters and four "
             "digits so the names survive an 8.3 filesystem. It rolls over "
             "at 9999.",
    ),
    CameraProfile(
        "iphone-13", "Apple iPhone 13 (iOS 16.6)",
        "Apple", "iPhone 13",
        "iPhone 13 back dual wide camera 5.1mm f/1.6", "Apple",
        "5.1", "1.6", "16.6",
        filename_pattern="IMG_{n:04}{ext}",
        note="The iPhone 13 shipped with iOS 15, so any Software value "
             "below 15 here would be a contradiction the linter catches.",
    ),
    CameraProfile(
        "pixel-8", "Google Pixel 8",
        "Google", "Pixel 8",
        "Pixel 8 back camera 6.9mm f/1.68", "Google",
        "6.9", "1.68", "HDR+ 1.0.640190411zd",
        filename_pattern="PXL_{datetime}{ext}",
        note="Google abandoned DCF in 2020: Pixels name files by timestamp "
             "to the millisecond instead, which is why a Pixel photo called "
             "IMG_0942 reads as wrong immediately.",
    ),
    CameraProfile(
        "galaxy-s23", "Samsung Galaxy S23",
        "samsung", "SM-S911B",
        "Galaxy S23 Rear Camera", "samsung",
        "5.4", "1.8", "S911BXXU3BWL1",
        filename_pattern="{datetime}{ext}",
        note="Samsung drops the prefix entirely and uses a bare timestamp. "
             "The Make really is lowercase 'samsung' in the file, which "
             "looks like a typo and is not.",
    ),
]

_NOVELTY = [
    CameraProfile(
        "gameboy-camera", "Nintendo Game Boy Camera (1998)",
        "Nintendo", "Game Boy Camera",
        "Mitsubishi M64282FP 128x128 CMOS, fixed focus f/2.0", "Mitsubishi",
        "3.2", "2.0", "GB Camera v1.0",
        filename_pattern="GBCAM_{n:03}{ext}",
        novelty=True,
        note="All of this is real. The Game Boy Camera used a Mitsubishi "
             "M64282FP sensor: 128x128 pixels, four shades of grey, f/2.0, "
             "fixed focus. It held the Guinness record for smallest digital "
             "camera for a decade.",
    ),
    CameraProfile(
        "toaster", "Sunbeam Radiant Control T-20",
        "Sunbeam", "Radiant Control T-20",
        "Nichrome Element Array, 2-slice, f/1.1", "Sunbeam",
        "1.5", "1.1", "Bakelite Firmware 4 (Medium Brown)",
        filename_pattern="TOAST_{n:03}{ext}",
        novelty=True,
        note="A 1949 toaster that lowered the bread by itself and judged "
             "doneness by the bread's own thermal mass. It took no "
             "photographs whatsoever.",
    ),
    CameraProfile(
        "dream", "A Dream I Had Once",
        "Unreliable Narrator", "A Dream I Had Once",
        "Recollection, approximate, f/0.95", "Memory",
        "35", "0.95", "REM 4.2 (non-lucid build)",
        filename_pattern="REM_{n:03}_unverified{ext}",
        novelty=True,
        note="35mm and f/0.95 because dreams are reportedly wide, shallow "
             "and poorly lit. The timestamp will not survive scrutiny and "
             "neither will yours.",
    ),
    CameraProfile(
        "potato", "Shot On A Potato (Russet, 2003)",
        "Solanum", "Russet Burbank",
        "Single Starch Aperture, f/8", "Solanum tuberosum",
        "12", "8", "Tuber OS 0.3",
        filename_pattern="SPUD_{n:03}{ext}",
        novelty=True,
        note="The traditional answer to 'what did you take this on'. "
             "Nutritionally excellent, optically not.",
    ),
    CameraProfile(
        "pinhole", "Oatmeal Tin Pinhole (handmade)",
        "Handmade", "Oatmeal Tin Pinhole",
        "0.3mm aperture in brass shim, f/180", "Kitchen Drawer",
        "50", "180", "Darkroom, by hand",
        filename_pattern="FRAME_{n:02}{ext}",
        novelty=True,
        note="f/180 is genuinely what a pinhole works out to. Exposures run "
             "to minutes, so this claims a photograph nobody moved during.",
    ),
    CameraProfile(
        "hubble", "NASA Hubble Space Telescope (WFC3)",
        "NASA", "Hubble Space Telescope",
        "Wide Field Camera 3, 57600mm f/24", "Goddard Space Flight Center",
        "57600", "24", "WFC3 Pipeline 3.5.2",
        filename_pattern="hst_{n:05}_01_wfc3_uvis{ext}",
        novelty=True,
        note="Hubble really is a 57.6 metre focal length at f/24, and its "
             "archive really does name files like this. The claim that it "
             "was pointed at your kitchen is the implausible part.",
    ),
]

PROFILES: dict[str, CameraProfile] = {p.key: p for p in (*_CREDIBLE, *_NOVELTY)}

CREDIBLE_KEYS = tuple(p.key for p in _CREDIBLE)
NOVELTY_KEYS = tuple(p.key for p in _NOVELTY)
