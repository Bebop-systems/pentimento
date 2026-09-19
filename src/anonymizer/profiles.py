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
    CameraProfile(
        "canon-r5", "Canon EOS R5",
        "Canon", "Canon EOS R5",
        "RF24-70mm F2.8 L IS USM", "Canon",
        "50", "2.8", "Firmware Version 1.8.1",
        filename_pattern="IMG_{n:04}{ext}",
        note="Canon writes IMG_ for sRGB and _MG_ for Adobe RGB, because "
             "DCF allows only four characters and the underscore had to go "
             "somewhere.",
    ),
    CameraProfile(
        "nikon-z6ii", "Nikon Z 6II",
        "NIKON CORPORATION", "NIKON Z 6_2",
        "NIKKOR Z 24-70mm f/4 S", "NIKON",
        "35", "4.0", "Ver.01.40",
        filename_pattern="DSC_{n:04}{ext}",
        note="The model really is written 'NIKON Z 6_2' in the file: the "
             "roman numerals would not survive ASCII, so Nikon used an "
             "underscore.",
    ),
    CameraProfile(
        "sony-a7iv", "Sony a7 IV",
        "SONY", "ILCE-7M4",
        "FE 24-105mm F4 G OSS", "SONY",
        "50", "4.0", "ILCE-7M4 v2.00",
        filename_pattern="DSC{n:05}{ext}",
        note="Sony names the body ILCE-7M4 internally: Interchangeable Lens "
             "Camera, E-mount. Nothing in the file says 'a7 IV' at all.",
    ),
    CameraProfile(
        "fuji-x100v", "Fujifilm X100V",
        "FUJIFILM", "X100V",
        "23mm f/2", "FUJIFILM",
        "23", "2.0", "Digital Camera X100V Ver1.10",
        filename_pattern="DSCF{n:04}{ext}",
        note="A fixed 23mm lens, which is 35mm once the APS-C crop is "
             "applied. The DSCF prefix has outlived the FinePix line it "
             "was named for.",
    ),
    CameraProfile(
        "gopro-hero12", "GoPro HERO12 Black",
        "GoPro", "HERO12 Black",
        "GoPro HERO12 Black Lens", "GoPro",
        "2.92", "2.5", "H23.01.02.32.00",
        filename_pattern="GOPR{n:04}{ext}",
        note="An action camera's metadata usually carries far more than a "
             "phone's: GoPro embeds a telemetry track with GPS, "
             "accelerometer and gyroscope samples many times a second.",
    ),
    CameraProfile(
        "dji-mavic3", "DJI Mavic 3",
        "DJI", "FC4170",
        "DJI Mavic 3 24mm f/2.8", "Hasselblad",
        "12.29", "2.8", "01.00.0400",
        filename_pattern="DJI_{n:04}{ext}",
        note="Drone files carry absolute altitude and often the operator's "
             "home point, which is usually where the drone took off from "
             "and frequently a garden.",
    ),
    CameraProfile(
        "epson-scan", "Epson Perfection V600 (scan)",
        "SEIKO EPSON CORP.", "Perfection V600",
        "Flatbed CCD, 6400 dpi", "SEIKO EPSON CORP.",
        "50", "8.0", "Epson Scan 3.9.9.4",
        filename_pattern="img{n:03}{ext}",
        note="A scan of a print has no capture date of its own, so the "
             "timestamp is when it was scanned, not when the photograph "
             "was taken. That gap is itself informative.",
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
        "daguerreotype", "Giroux Daguerreotype (1839)",
        "Daguerre & Giroux", "Giroux Daguerreotype",
        "Chevalier Achromat 15in f/16", "Charles Chevalier",
        "381", "16", "Iodine, mercury, hot salt water",
        filename_pattern="PLATE_{n:03}{ext}",
        novelty=True,
        note="The first camera sold to the public, in 1839, with a genuine "
             "f/16 Chevalier lens. Exposures ran ten to fifteen minutes, "
             "which is why nobody in an early photograph is smiling.",
    ),
    CameraProfile(
        "quickcam", "Connectix QuickCam (1994)",
        "Connectix", "QuickCam",
        "Fixed focus f/2.0, 320x240 greyscale", "Connectix",
        "4", "2.0", "QuickMovie 1.0",
        filename_pattern="CAM{n:05}{ext}",
        novelty=True,
        note="The first consumer webcam: a grey golf ball producing 320x240 "
             "in sixteen shades of grey, over a serial port. It cost $100 "
             "in 1994 and was genuinely astonishing.",
    ),
    CameraProfile(
        "trailcam", "Bushnell Trophy Cam (night)",
        "Bushnell", "Trophy Cam HD",
        "Infrared Fixed Lens f/2.8, 850nm illuminator", "Bushnell",
        "4.3", "2.8", "TrophyCam 2.1",
        filename_pattern="PICT{n:04}{ext}",
        novelty=True,
        note="The camera responsible for almost every blurry cryptid "
             "photograph. Infrared triggers on heat, so it fires at "
             "anything warm and passing, including moths.",
    ),
    CameraProfile(
        "perseverance", "NASA Perseverance (Mastcam-Z)",
        "NASA/JPL-Caltech", "Mastcam-Z",
        "Mastcam-Z 26-110mm f/7-f/9.5", "Malin Space Science Systems",
        "110", "9.5", "FSW 4.1",
        filename_pattern="ZL{n:04}_MSTCMZ{ext}",
        novelty=True,
        note="A real zoom lens on Mars, f/7 to f/9.5. Every frame it takes "
             "is public domain, which makes it the least private camera "
             "ever built.",
    ),
    CameraProfile(
        "voyager", "Voyager 1 (ISS-NA, 1977)",
        "NASA", "Voyager 1 ISS-NA",
        "1500mm f/8.5 Cassegrain vidicon", "Jet Propulsion Laboratory",
        "1500", "8.5", "CCS 6.0",
        filename_pattern="C{n:07}{ext}",
        novelty=True,
        note="A 1500mm f/8.5 vidicon tube, not a sensor, running on about "
             "70 kilobytes of memory. It took the Pale Blue Dot and is now "
             "the most distant camera from Earth.",
    ),
    CameraProfile(
        "etch-a-sketch", "Ohio Art Etch A Sketch",
        "Ohio Art", "Etch A Sketch",
        "Aluminium powder and a stylus, f/2 knobs", "Ohio Art",
        "2", "2.0", "Shake To Erase v1960",
        filename_pattern="ETCH_{n:03}{ext}",
        novelty=True,
        note="Aluminium powder clinging to the inside of the glass, scraped "
             "away by a stylus on two axes. Erasing really does work by "
             "shaking the powder back into suspension.",
    ),
    CameraProfile(
        "pinhole-camera-obscura", "Camera Obscura (a darkened room)",
        "Natural Philosophy", "Camera Obscura",
        "Aperture in a shutter, f/64", "A Wall",
        "500", "64", "Observation, by eye",
        filename_pattern="OBSCURA_{n:03}{ext}",
        novelty=True,
        note="Described by Mozi in China around 400 BC and by Ibn al-Haytham "
             "in 1021. It is the oldest camera there is and it cannot "
             "record anything at all.",
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
