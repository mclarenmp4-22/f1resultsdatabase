import logging
import re
import math
import cv2
import numpy as np
from ollama import chat
import json
import os
import shutil
import pytesseract
headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.7922.138 Safari/537.36"
        )
}
def imread_from_url(url):
    #GetImage.ashx hotlink-protects on Referer: without it the site answers 404 with an
    #HTML error page rather than the image. That page still decodes to None instead of
    #raising, so the explicit check below is what stops a silent 404 from being written
    #into the database as a corrupt SVG.
    response = fetch_url(url, extra_headers={'Referer': 'https://www.statsf1.com/'})
    image_bytes = response.content

    img = decode_layout_image(image_bytes, url, response.headers.get('content-type'))
    return img, image_bytes


# Every layout map statsf1 serves is 920px wide. When the site is rate limiting
# it answers GetImage.ashx with a 24x16 placeholder that decodes perfectly well,
# and one run stored six layouts traced off exactly that: an SVG with no track
# in it. Anything narrower than this is not a map.
MIN_LAYOUT_IMAGE_WIDTH = 400


def decode_layout_image(image_bytes, source, content_type=None):
    """Decode map bytes to BGR, refusing anything that is not a real map."""
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(
            f"Could not decode an image from {source} "
            f"(content-type {content_type!r}, {len(image_bytes)} bytes)"
        )
    if img.shape[1] < MIN_LAYOUT_IMAGE_WIDTH:
        raise RuntimeError(
            f"{source} decoded to a {img.shape[1]}x{img.shape[0]} image, which is a "
            f"placeholder rather than a layout map (statsf1 is probably rate limiting)"
        )
    return img

import html
import unicodedata
from pathlib import Path
from PIL import Image


def gimp_contrast(pil_gray, contrast=1.0, pivot=200):
    """Replicate GIMP's Brightness-Contrast slider on a greyscale image.

    GIMP pivots around a fixed value and applies slope = tan((contrast + 1) * pi/4).
    At contrast = 1.0 (max) that slope is infinite, i.e. a hard step at the pivot.
    PIL's ImageEnhance.Contrast pivots on the *image mean* instead, which on these
    aerial-photo circuit maps (mean ~84) saturates the trees and buildings to white
    long before the track does. The pivot has to sit in the gap between the photo
    (below ~160) and the white track/text overlay (240-255), hence the 200 default,
    the same cut the SVG mask uses.
    """
    contrast = min(max(contrast, -1.0), 1.0)
    if contrast >= 1.0:
        return pil_gray.point(lambda p: 255 if p > pivot else 0)
    slope = math.tan((contrast + 1.0) * math.pi / 4.0)
    return pil_gray.point(lambda p: max(0, min(255, int((p - pivot) * slope + pivot))))


def scale_box_to_pixels(qwen_box, actual_width, actual_height):
    xmin, ymin, xmax, ymax = qwen_box

    # Convert from 0-1000 system to real fractional percentages
    pixel_xmin = int((xmin / 1000.0) * actual_width)
    pixel_ymin = int((ymin / 1000.0) * actual_height)
    pixel_xmax = int((xmax / 1000.0) * actual_width)
    pixel_ymax = int((ymax / 1000.0) * actual_height)

    # Return standard bounding box format
    return (pixel_xmin, pixel_ymin, pixel_xmax, pixel_ymax)


# Direction detection tuning. TANGENTIALITY is |sin(theta)| between the arrow and
# the radius drawn out to it: an arrow pointing straight at (or straight away
# from) the centroid says nothing about which way round the lap the cars go, and
# on a concave layout the centroid can sit close enough to the track for that to
# actually happen. MIN_RADIUS_FRACTION throws out an arrow sitting almost on top
# of the centroid, where the radius is too short for its direction to be anything
# but box-jitter. A reading that fails either test is dropped rather than guessed
# at - the column is better left NULL than filled with a coin flip.
MIN_TANGENTIALITY = 0.05
MIN_RADIUS_FRACTION = 0.05


# Hand-set directions, keyed by the layout id in the map's own URL - the
# "piste.xxx" of /images/GetImage.ashx?id=piste.xxx - so an entry names exactly
# one map and cannot drift onto another version of the same circuit.
#
# The table is applied wherever it has an entry, not only where the detector
# gave up, so an entry here is the final word on that map. It used to carry
# twenty-odd layouts the centroid reading got wrong or could not read; the
# outline reading (tangent_direction) settles every one of those off the map
# itself, and they were taken out once it had been checked against all 171
# layouts. What is left is the one map that has no single direction.
#
# statsf1's own "Direction" field is not the source for these. It is per circuit
# rather than per layout, so it reports the modern direction for a circuit that
# changed - Kyalami raced clockwise on the layout here and anticlockwise today -
# and it is outright wrong on at least Interlagos, which it calls Clockwise. The
# values below were read off the maps.
DIRECTION_OVERRIDES = {
    # Suzuka crosses over itself, so it is neither direction and it is not
    # "Both" either - "Both" means the same loop was raced each way round on
    # different occasions, while a figure of eight is one lap that turns both
    # ways every time. Wikipedia's list of Formula One circuits calls it "Part
    # clockwise and part anti-clockwise (figure of eight)"; the column stores
    # the short form. The arrow detector reads its arrow correctly and would
    # report a direction, which is why this is an override rather than a
    # detection problem.
    "piste.suzuka1": "Figure of eight",
    "piste.suzuka2": "Figure of eight",
}


# Wikipedia's list of Formula One circuits carries the one thing statsf1's own
# Direction field does not: a direction tagged with the years it applied. Two
# circuits use it, and they use it differently.
#
#   Kyalami       "Clockwise (1967-1985)" / "Anti-clockwise (1992-1993)"
#   Buenos Aires  "Clockwise" / "Anti-clockwise (1954)"
#
# So a range may be attached to every entry, or only to the exception, with the
# untagged entry meaning "every other year". Both shapes are read the same way
# here: an entry with years applies to those years, an entry without is the
# default for anything the tagged entries do not claim.
#
# Matched against the years a layout was actually raced - which CircuitLayouts
# already stores in GrandPrixDates - this settles direction per layout rather
# than per circuit. Kyalami's two layouts fall either side of the split and come
# out clockwise and anticlockwise respectively, which is exactly what the maps
# show and what statsf1's single per-circuit field could never express. Buenos
# Aires' first layout ran 1953-1960 and so contains 1954: it raced both ways
# round, which is the "Both" its two drawn arrows already say.
WIKI_DIRECTION_ERAS = {
    "piste.kyalami1": (("Clockwise", (1967, 1985)),
                       ("Anticlockwise", (1992, 1993))),
    "piste.kyalami2": (("Clockwise", (1967, 1985)),
                       ("Anticlockwise", (1992, 1993))),
    "piste.buenosaires1": (("Clockwise", None),
                           ("Anticlockwise", (1954, 1954))),
    "piste.buenosaires2": (("Clockwise", None),
                           ("Anticlockwise", (1954, 1954))),
    "piste.buenosaires3": (("Clockwise", None),
                           ("Anticlockwise", (1954, 1954))),
    "piste.buenosaires4": (("Clockwise", None),
                           ("Anticlockwise", (1954, 1954))),
}


def direction_for_years(eras, years):
    """Fold a circuit's era table and a layout's racing years into one answer.

    Every year the layout raced is charged to whichever era claims it, falling
    back to the untagged entry for years no range covers. One direction across
    all of them is that direction; two is "Both", by the same reasoning
    resolve_circuit_direction uses - a layout raced each way round on different
    occasions is genuinely both, and that is a fact about the layout rather than
    an uncertainty about the reading.

    Returns None when the years say nothing, leaving the caller on the arrows.
    """
    if not eras or not years:
        return None
    default = next((d for d, span in eras if span is None), None)
    found = set()
    for year in years:
        hit = next((d for d, span in eras
                    if span is not None and span[0] <= year <= span[1]), None)
        if hit is None:
            hit = default
        if hit is not None:
            found.add(hit)
    if not found:
        return None
    return "Both" if len(found) > 1 else found.pop()


def direction_for_year(eras, year, fallback=None):
    """The direction a single race ran, given its circuit's era table.

    direction_for_years answers for a layout, which is why Buenos Aires' first
    one comes back "Both" - it really was raced both ways. That is the truthful
    answer at the layout's grain and a useless one at a race's: the 1954
    Argentine Grand Prix ran anticlockwise and the other six on that layout ran
    clockwise, and "Both" cannot say which was which.

    So this resolves one year instead of folding a set. `fallback` is what a year
    no era claims falls back to - the layout's own direction, so a circuit with
    no era table still gives every one of its races an answer.
    """
    if year is None:
        return fallback
    if eras:
        for direction, span in eras:
            if span is not None and span[0] <= year <= span[1]:
                return direction
        default = next((d for d, span in eras if span is None), None)
        if default is not None:
            return default
    return fallback


def years_from_dates(grand_prix_dates):
    """Years out of the date list CircuitLayouts stores for a layout.

    The column holds statsf1's sort keys as JSON - "19540117" and the like - so
    the year is the leading four digits. Anything that does not parse is skipped
    rather than guessed at; a layout whose dates are unreadable simply falls
    through to the arrows.
    """
    if not grand_prix_dates:
        return []
    if isinstance(grand_prix_dates, str):
        try:
            grand_prix_dates = json.loads(grand_prix_dates)
        except (ValueError, TypeError):
            return []
    years = []
    for entry in grand_prix_dates:
        match = re.match(r'\s*(\d{4})', str(entry))
        if match:
            years.append(int(match.group(1)))
    return years


def layout_id(image_path):
    """The 'piste.xxx' id out of a statsf1 map URL, or None if it is not one.

    Used as the key into DIRECTION_OVERRIDES. Falls back to None rather than
    guessing, so a URL in some other shape simply gets no override.
    """
    match = re.search(r'id=(piste\.[A-Za-z0-9_-]+)', image_path)
    return match.group(1) if match else None


def track_centroid(contours, image_shape):
    """Area centroid of the region the track encloses.

    The contours come out of RETR_EXTERNAL on the white mask, so filling one
    gives the infield rather than the stroke itself, and the moments of that
    fill are the centre of the circuit. Anything under a fifth of the largest
    contour is dropped first: a loop broken into pieces by the flag line still
    contributes all of its pieces, but a stray white blob that got past the area
    filter cannot drag the centre off the track.
    """
    if not contours:
        return None
    areas = [cv2.contourArea(c) for c in contours]
    largest = max(areas)
    if largest <= 0:
        return None
    kept = [c for c, a in zip(contours, areas) if a >= 0.2 * largest]

    mask = np.zeros(image_shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, kept, -1, 255, -1)
    moments = cv2.moments(mask, binaryImage=True)
    if moments["m00"] == 0:
        return None
    return (moments["m10"] / moments["m00"], moments["m01"] / moments["m00"])


def arrow_direction(base, tip, centroid, scale):
    """Which way round the lap a single arrow points.

    Two vectors: a = tip - base, the direction of travel, and r = arrow - centroid,
    the radius out to where the arrow sits. A 2D cross product has only a z
    component, and the sign of r x a is the handedness of the turn the car is
    making about the centre. Image axes run y downwards, which mirrors the plane,
    so the textbook "positive is anticlockwise" inverts: positive here is
    clockwise on screen, which is clockwise on the map.

    |z| / (|r||a|) is the sine of the angle between the two, i.e. how tangential
    the arrow is, and it says whether the reading means anything at all: it falls
    away to nothing as the arrow swings round to point at the centroid, where the
    sign ends up decided by noise.
    """
    ax, ay = tip[0] - base[0], tip[1] - base[1]
    mid_x, mid_y = (base[0] + tip[0]) / 2.0, (base[1] + tip[1]) / 2.0
    rx, ry = mid_x - centroid[0], mid_y - centroid[1]

    arrow_length = math.hypot(ax, ay)
    radius = math.hypot(rx, ry)
    if arrow_length == 0 or radius == 0:
        return None

    cross = rx * ay - ry * ax
    if cross == 0:
        return None
    tangentiality = abs(cross) / (arrow_length * radius)

    return {
        "direction": "Clockwise" if cross > 0 else "Anticlockwise",
        "tangentiality": tangentiality,
        "usable": (tangentiality >= MIN_TANGENTIALITY
                   and radius >= MIN_RADIUS_FRACTION * scale),
    }


def resolve_circuit_direction(readings):
    """Fold the per-arrow readings into the single value the column stores.

    statsf1 only ever draws a second arrow to say the layout was raced the other
    way round, so two real arrows always oppose one another and the set of
    directions is the whole answer: one arrow gives its own direction, two give
    "Both".

    That invariant doubles as the check on the detector. Two readings that come
    out the same way cannot both be real arrows - it is a second red object that
    got through the shape gates, or one arrow whose two halves were read as two -
    so an agreeing pair collapses back to the one direction instead of being
    counted as two.
    """
    directions = {r["direction"] for r in readings if r and r["usable"]}
    if not directions:
        return None
    if len(directions) == 2:
        return "Both"
    return directions.pop()


# How big the drawn glyph is, which is not read off the image. The arrow statsf1
# draws is sized for its own map, and those range from a few hundred pixels wide
# to well over a thousand, so its measured extent would carry that scatter
# straight into the SVG. Only the axis and the bearing are taken from the
# detected arrow; the length is fixed here as a fraction of the image, so every
# circuit comes out with the same arrow on it.
ARROW_LENGTH_FRACTION = 0.030
MIN_ARROW_LENGTH = 16.0
ARROW_HEAD_FRACTION = 0.38


# Arrow detection. statsf1 draws the direction arrow as flat vector red, over a
# black background on the drawn maps and over an aerial photograph on the rest,
# and nothing else on either kind of map is that colour: the reds in the
# photography - rooftops, gravel traps, cars - are dulled by the exposure and
# never lead green and blue by this margin. Measured across 41 layouts covering
# every map style on the site, the whole image carries 150-250 pixels this red
# and all but a handful of them are the arrow.
#
# This reads the ORIGINAL image, not the saturated second-pass copy. The second
# pass exists to make the arrow legible to a small VLM and does it by driving
# every channel to a corner of the RGB cube, which promotes those dull rooftop
# reds to exactly the same pure red as the arrow and manufactures the noise the
# gate below is meant to reject. Off the original the confusion never arises.
ARROW_RED_MIN = 120          # floor on the red channel itself
ARROW_RED_DOMINANCE = 50     # how far red has to lead both green and blue
# The colour gate above still lets a red rooftop through on an aerial map -
# Baku's turn-20 building, the La Caixa grandstand at Barcelona - because a
# roof in sunlight does lead green and blue by 50. What it never does is reach
# the arrow's flat vector red: across all 157 maps the arrow's 90th-percentile
# red is 233 or more, the rooftops' 161 or less. This is the gate between.
ARROW_MIN_RED_P90 = 200
ARROW_MIN_AREA_FRACTION = 2e-5
ARROW_MIN_LENGTH_FRACTION = 0.02
ARROW_MIN_ELONGATION = 1.6
# Confidence is the head-vs-tail asymmetry as a fraction of the arrow's length,
# so it is the margin by which the glyph is decided to point the way it does.
# The 41 measured layouts run from 0.08 to 0.31; a shape with no head at all
# sits near zero, which is what this rejects.
ARROW_MIN_CONFIDENCE = 0.02
# statsf1 draws a second arrow to say the layout was raced both ways round, and
# it does NOT draw it to match the first: Buenos Aires ran the other way once,
# and its second arrow is drawn about half the size of the main one. So size is
# exactly the wrong thing to test a second arrow on - gating on it throws away
# the real "Both" cases, which is the one answer no other layout can produce.
#
# What actually turns up falsely in the second slot is a red corner-number label
# beside the track - Barcelona's "10 La Caixa". Text has no arrowhead, so it has
# no head-to-tail asymmetry: Barcelona's scores 0.022 against the real arrow's
# 0.223, a tenfold gap, while Buenos Aires' genuine small arrow scores 0.267 and
# clears its larger partner. Confidence separates arrow from text where size
# cannot, so confidence is the only ratio applied.
SECOND_ARROW_CONFIDENCE_RATIO = 0.35
ARROW_MAX_TRACK_DISTANCE_FRACTION = 0.05


def arrow_red_mask(bgr):
    """Pixels that are the arrow's flat vector red rather than photographed red.

    Absolute redness alone picks up half a rooftop, so the test is relative as
    well: red has to clear a floor AND lead the other two channels by a wide
    margin, which a printed vector red does by 200 or more and a sunlit tile roof
    does not do at all.
    """
    b, g, r = cv2.split(bgr.astype(np.int16))
    return ((r > ARROW_RED_MIN)
            & (r - g > ARROW_RED_DOMINANCE)
            & (r - b > ARROW_RED_DOMINANCE)).astype(np.uint8)


def _principal_axis(sel):
    """Pixel coordinates of a mask, their centroid, and the direction they lie
    along. The sign of the axis is arbitrary - which end is the point is decided
    by _head_end, not here."""
    ys, xs = np.nonzero(sel)
    pts = np.stack([xs, ys], 1).astype(np.float64)
    mean = pts.mean(0)
    axis = np.linalg.svd(pts - mean, full_matrices=False)[2][0]
    return pts, mean, axis


def _glue_axis_fragments(seed_label, labels, stats, centroids, diagonal):
    """Re-attach the pieces JPEG ringing breaks an arrow into.

    These maps are saved as JPEG, and the white track line frequently crosses the
    arrow's shaft; between them they can drop a pixel or two of the shaft below
    the colour gate, leaving the head as one component and the rest of the shaft
    as another. Measured on Silverstone and Hockenheim, reading the head on its
    own reverses the answer: a triangle alone is widest at its back, so the head
    test points it at its own tail.

    Dilating the mask to close those gaps is not the fix. The gap needs two or
    three pixels to close, and by two pixels an aerial map's rooftops have merged
    into the arrow as well - measured on Adelaide, where that is enough to drag
    the centroid off the glyph and destroy the reading. So the merge is made
    selective rather than larger: start from the biggest red component, which is
    always the head, and absorb only fragments lying along the head's own axis -
    which a severed shaft does and a rooftop, off to one side, does not.
    """
    sel = (labels == seed_label)
    pts, mean, axis = _principal_axis(sel)
    along_seed = (pts - mean) @ axis
    seed_length = along_seed.max() - along_seed.min()
    normal = np.array([-axis[1], axis[0]])
    # Reach is set off the seed rather than the image: a severed shaft is a
    # continuation of the head, so it lies within about the head's own length of
    # it, plus a small floor for the smallest maps.
    reach = seed_length * 0.9 + 0.012 * diagonal
    corridor = max(3.0, 0.1 * seed_length)

    for i in range(1, stats.shape[0]):
        if i == seed_label or stats[i, cv2.CC_STAT_AREA] < 3:
            continue
        offset = np.asarray(centroids[i]) - mean
        if abs(offset @ axis) < reach and abs(offset @ normal) < corridor:
            sel |= (labels == i)
    return sel


def _head_end(sel):
    """Which end of the arrow is the point, and how clearly.

    The shape is a solid triangular head on a hairline shaft, so the head is both
    the heavy end and the thick end, and each of those is a vote:

      mass      - the pixel centroid is pulled off the midpoint of the extent
                  towards the head;
      thickness - binning the pixels along the axis and weighting each bin by the
                  square of its width lands the result inside the head.

    Neither reads the extreme pixel at either end, which matters because the very
    point of the arrow is a single pixel: a test that asked which end is wider at
    its outermost point would answer with the apex and get it backwards. The two
    are summed rather than required to agree, so that a stubby arrow - where the
    mass test alone is nearly balanced - still resolves on thickness. Across the
    41 measured layouts they agree every time.
    """
    pts, mean, axis = _principal_axis(sel)
    centred = pts - mean
    along = centred @ axis
    across = centred @ np.array([-axis[1], axis[0]])
    low, high = along.min(), along.max()
    length = high - low
    midpoint = (low + high) / 2.0          # the centroid is at along = 0

    mass_vote = -midpoint

    bins = max(6, int(length / 2))
    index = np.clip(((along - low) / max(length, 1e-9) * bins).astype(int), 0, bins - 1)
    widths = np.bincount(index, minlength=bins).astype(np.float64)
    bin_centres = low + (np.arange(bins) + 0.5) * length / bins
    weights = widths ** 2
    thickness_vote = float(
        (weights * bin_centres).sum() / max(weights.sum(), 1e-9)) - midpoint

    head_at_high = (mass_vote + thickness_vote) > 0
    confidence = (abs(mass_vote) + abs(thickness_vote)) / max(length, 1e-9)

    tip = mean + axis * (high if head_at_high else low)
    base = mean + axis * (low if head_at_high else high)
    return tip, base, length, across.max() - across.min(), confidence


def _shaft_hint(white_labels, white_stats, sel, base, tip):
    """Which end of the red head the shaft is on, read off the arrow's outline.

    Every arrow is drawn with a white outline round head and shaft alike, and
    on a few maps (Monaco's early layouts) the shaft itself carries no red at
    all - it is a hairline drawn white-black-white, like the flag's leader -
    so the red detector sees the head triangle alone, and a triangle alone is
    heaviest at its back. The outline settles it: its pixels lie round the
    whole arrow, so their centroid sits off the head's centroid towards the
    shaft, and the point is the other way. Returns (tip, base) or None where
    the outline says nothing (merged into the track, or no offset to speak
    of), in which case the caller keeps the head's own vote.
    """
    ys, xs = np.nonzero(sel)
    x1, y1, x2, y2 = xs.min() - 6, ys.min() - 6, xs.max() + 6, ys.max() + 6
    outline = np.zeros(sel.shape, dtype=bool)
    for i in range(1, white_stats.shape[0]):
        if white_stats[i, cv2.CC_STAT_AREA] > TEXT_MAX_GLYPH_AREA:
            continue
        left, top = white_stats[i, cv2.CC_STAT_LEFT], white_stats[i, cv2.CC_STAT_TOP]
        right, bottom = left + white_stats[i, cv2.CC_STAT_WIDTH], top + white_stats[i, cv2.CC_STAT_HEIGHT]
        if left < x2 and right > x1 and top < y2 and bottom > y1:
            outline |= (white_labels == i)
    if outline.sum() < 10:
        return None
    oy, ox = np.nonzero(outline)
    head = np.array([xs.mean(), ys.mean()])
    axis = np.array([tip[0] - base[0], tip[1] - base[1]], dtype=np.float64)
    length = np.linalg.norm(axis)
    if length == 0:
        return None
    axis /= length
    offset = float((np.array([ox.mean(), oy.mean()]) - head) @ axis)
    if abs(offset) < 0.2 * length:
        return None
    # The shaft lies towards the outline's centroid; the point is the other end.
    return (base, tip) if offset > 0 else (tip, base)


def detect_arrows(bgr, track_mask=None, max_arrows=2, white_mask=None):
    """Every direction arrow on the map, as (base, tip, bbox) in pixels.

    Replaces asking a 4b VLM for a tip box and a base box per arrow. The model
    was dependable about where the arrow sits and not about which of the two
    boxes was the point, and getting that backwards reverses both the glyph drawn
    on the SVG and the direction the column records. Colour and shape settle it
    outright: there is only one flat-red elongated object on a statsf1 circuit
    map, and its head is measurably the heavy, thick end of it.

    Largest arrow first, so a layout raced both ways round keeps the two it is
    drawn with and everything else keeps the one.
    """
    height, width = bgr.shape[:2]
    diagonal = max(height, width)
    min_area = max(20, ARROW_MIN_AREA_FRACTION * height * width)

    # Distance from every pixel to the nearest track pixel, so a candidate can be
    # asked how far it sits from the circuit it is supposed to be drawn on.
    track_distance = None
    if track_mask is not None:
        track_distance = cv2.distanceTransform(
            cv2.bitwise_not(track_mask), cv2.DIST_L2, 5)

    mask = arrow_red_mask(bgr)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    white_labels = white_stats = None
    if white_mask is not None:
        _, white_labels, white_stats, _ = cv2.connectedComponentsWithStats(white_mask, 8)

    claimed = np.zeros(mask.shape, dtype=bool)
    arrows = []
    for label in sorted(range(1, count), key=lambda i: -stats[i, cv2.CC_STAT_AREA]):
        if len(arrows) >= max_arrows:
            break
        if stats[label, cv2.CC_STAT_AREA] < min_area or claimed[labels == label].any():
            continue
        sel = _glue_axis_fragments(label, labels, stats, centroids, diagonal) & ~claimed
        if sel.sum() < min_area:
            continue
        if np.percentile(bgr[sel][:, 2], 90) < ARROW_MIN_RED_P90:
            continue
        tip, base, length, thickness, confidence = _head_end(sel)
        if (length < ARROW_MIN_LENGTH_FRACTION * diagonal
                or length / max(thickness, 1e-6) < ARROW_MIN_ELONGATION
                or confidence < ARROW_MIN_CONFIDENCE):
            continue
        if white_labels is not None:
            hint = _shaft_hint(white_labels, white_stats, sel, base, tip)
            if hint is not None:
                tip, base = hint
        if track_distance is not None:
            mx = int(min(max((base[0] + tip[0]) / 2.0, 0), width - 1))
            my = int(min(max((base[1] + tip[1]) / 2.0, 0), height - 1))
            if track_distance[my, mx] > ARROW_MAX_TRACK_DISTANCE_FRACTION * diagonal:
                continue
        claimed |= sel
        ys, xs = np.nonzero(sel)
        box = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        arrows.append((tuple(base), tuple(tip), box, length, confidence))

    # A second arrow has to look like the first one to be believed - see the note
    # on SECOND_ARROW_CONFIDENCE_RATIO.
    if len(arrows) == 2 and arrows[1][4] < SECOND_ARROW_CONFIDENCE_RATIO * arrows[0][4]:
        del arrows[1]
    return [(base, tip, box) for base, tip, box, _, _ in arrows]


def arrow_endpoints(base, tip, length):
    """A fixed-length arrow on the axis a detected one lies along.

    The detector measures the arrow's real extent, but that extent is whatever
    statsf1 happened to draw at whatever scale the map was rendered, so it is
    normalised away here: the midpoint between base and tip is where the glyph
    belongs, base -> tip is the way it faces, and it is then laid out to `length`
    about that midpoint. Every circuit gets the same arrow and only its placement
    and bearing come from the image.

    Returns None when the two points coincide, leaving no axis to point along.
    """
    ux, uy = tip[0] - base[0], tip[1] - base[1]
    axis = math.hypot(ux, uy)
    if axis == 0:
        return None
    ux, uy = ux / axis, uy / axis

    mid_x = (base[0] + tip[0]) / 2.0
    mid_y = (base[1] + tip[1]) / 2.0
    half = length / 2.0
    return ((mid_x - ux * half, mid_y - uy * half),
            (mid_x + ux * half, mid_y + uy * half))


def arrow_svg(base, tip, offset_x, offset_y, head_length=9.0, stroke_width=3.0,
              colour="#E10600"):
    """One arrow glyph rebuilt from the two boxes the detector returns for it.

    The head is written out as a triangle instead of a <marker> so the output
    stays a flat list of shapes like everything else in the file, and so it
    survives renderers that drop marker definitions. The shaft stops at the neck
    of the head so the stroke cannot poke out through the point. The offsets are
    the same padding shift the track and the labels already carry.
    """
    ax, ay = tip[0] - base[0], tip[1] - base[1]
    length = math.hypot(ax, ay)
    if length == 0:
        return []

    ux, uy = ax / length, ay / length
    nx, ny = -uy, ux                      # unit normal, for the two back corners
    # Backstop for the head against the shaft it is being put on: a head sized
    # independently of a short arrow eats the whole of it and leaves the shaft a
    # dot behind the point. Callers that size the head off the arrow stay well
    # under this, so it only bites on a length that came from somewhere else.
    head_length = min(head_length, length * 0.6)
    half_width = head_length * 0.45

    tail = (base[0] + offset_x, base[1] + offset_y)
    point = (tip[0] + offset_x, tip[1] + offset_y)
    neck = (point[0] - ux * head_length, point[1] - uy * head_length)
    left = (neck[0] + nx * half_width, neck[1] + ny * half_width)
    right = (neck[0] - nx * half_width, neck[1] - ny * half_width)

    return [
        f'<line x1="{tail[0]:.1f}" y1="{tail[1]:.1f}" '
        f'x2="{neck[0]:.1f}" y2="{neck[1]:.1f}" '
        f'stroke="{colour}" stroke-width="{stroke_width}" stroke-linecap="round" />',
        f'<polygon points="{point[0]:.1f},{point[1]:.1f} '
        f'{left[0]:.1f},{left[1]:.1f} {right[0]:.1f},{right[1]:.1f}" fill="{colour}" />',
    ]


RESAMPLE_STEP = 1.0


def _densify(pts, step=RESAMPLE_STEP):
    """Resample a closed contour to roughly uniform `step` spacing.

    findContours with CHAIN_APPROX_SIMPLE collapses a straight run to its two
    endpoints, which breaks both of the things the tangent needs. Snapping to the
    nearest *vertex* on a long straight can land tens of pixels down the road
    from the nearest actual point on it, and a walk counted in vertices covers a
    handful of pixels round a corner and half a straight on a straight. Filling
    the runs back in at a fixed spacing makes index distance and arclength the
    same thing again.
    """
    closed = np.vstack([pts, pts[:1]])
    seg = np.diff(closed, axis=0)
    seg_len = np.hypot(seg[:, 0], seg[:, 1])
    total = float(seg_len.sum())
    if total < step * 4:
        return pts
    cumulative = np.concatenate([[0.0], np.cumsum(seg_len)])
    targets = np.arange(0.0, total, step)
    return np.column_stack([
        np.interp(targets, cumulative, closed[:, 0]),
        np.interp(targets, cumulative, closed[:, 1]),
    ])


def _local_tangent(point, contours, span):
    """Direction of travel of the track at the outline point nearest `point`.

    The flag's leader line only says where the start/finish line is, never which
    way it lies, and a bar drawn at a fixed angle would cut the track lengthwise
    as often as across it. The angle has to come off the circuit itself: the
    nearest point on the resampled outline is found first, then the outline is
    walked `span` pixels of arclength in each direction and the chord between the
    two ends taken as the tangent. A chord over a span rather than the step to
    the next point, because at 1px spacing consecutive points only ever differ by
    the staircase of the traced edge.

    Returns (nearest_point, unit_tangent) or None if there is nothing to trace.
    """
    best = None
    for cnt in contours:
        pts = cnt.reshape(-1, 2).astype(np.float64)
        if len(pts) < 3:
            continue
        pts = _densify(pts)
        d = np.hypot(pts[:, 0] - point[0], pts[:, 1] - point[1])
        i = int(np.argmin(d))
        if best is None or d[i] < best[0]:
            best = (float(d[i]), pts, i)
    if best is None:
        return None

    _, pts, i = best
    n = len(pts)
    step = max(1, min(int(round(span / RESAMPLE_STEP)), (n - 1) // 2))
    back, forward = pts[(i - step) % n], pts[(i + step) % n]

    tx, ty = forward[0] - back[0], forward[1] - back[1]
    length = math.hypot(tx, ty)
    if length == 0:
        return None
    return (pts[i][0], pts[i][1]), (tx / length, ty / length)


# ---------------------------------------------------------------------------
# The white mask and the track band.
#
# statsf1 does not draw the track as a solid white stroke. On every map it is a
# grey band (about 130 on the grey scale, 9-11px wide) fenced by two 1px white
# edge lines, so thresholding at 200 keeps only those two hairlines - Zolder's
# whole circuit is 12,000 white pixels. Anything that needs the track as an
# area - the direction reading, the start/finish bar's width, the distance an
# arrow is allowed to sit from the circuit - works on a *band* instead: the
# mask closed with a kernel wider than the gap between the two edge lines,
# which fills the band back in without touching anything else. The band is
# never drawn; the SVG traces the edge lines, as it always has.
WHITE_THRESHOLD = 200
BAND_CLOSE_KERNEL = 15
MIN_TRACK_COMPONENT_AREA = 3000


def white_mask_of(gray):
    return ((gray > WHITE_THRESHOLD).astype(np.uint8)) * 255


def track_band(white_mask):
    """Solid track area: the white edge lines closed across the grey band.

    Only components at least MIN_TRACK_COMPONENT_AREA survive. A corner name
    closes into a blob of a few hundred pixels and the smallest circuit band
    measured is 24,000, so the gap is wide.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (BAND_CLOSE_KERNEL, BAND_CLOSE_KERNEL))
    closed = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(closed, 8)
    band = np.zeros_like(white_mask)
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] >= MIN_TRACK_COMPONENT_AREA:
            band[labels == i] = 255
    return band


def erase_box(mask, box, margin=0):
    x1, y1, x2, y2 = box
    cv2.rectangle(mask, (x1 - margin, y1 - margin), (x2 - 1 + margin, y2 - 1 + margin), 0, -1)


def erase_components_in_box(mask, box, margin=0, touching_max_area=None):
    """Wipe the white blobs that lie wholly inside `box` (grown by `margin`).

    A plain rectangle erase is the wrong tool next to the track: an arrow or a
    corner name drawn against the circuit has the track's edge line running
    through its box, and cutting the rectangle out severs the loop - which is
    what turned East London, Reims and Mosport anticlockwise. The edge lines
    are thousands of pixels long and never fit inside a label's box, so
    erasing only the components the box contains can take the glyphs and
    leave the track whole.

    With `touching_max_area` set, a blob no bigger than that which merely
    overlaps the box goes too. The arrow's white outline needs this: the red
    detector sees the solid head and misses the hairline shaft, so the
    outline runs on past the box it was given - and left standing, that stub
    closes into the band and puts a false edge right beside the arrow.
    """
    x1, y1, x2, y2 = box[0] - margin, box[1] - margin, box[2] + margin, box[3] + margin
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    for i in range(1, count):
        left, top = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP]
        right, bottom = left + stats[i, cv2.CC_STAT_WIDTH], top + stats[i, cv2.CC_STAT_HEIGHT]
        inside = left >= x1 and top >= y1 and right <= x2 and bottom <= y2
        overlaps = left < x2 and right > x1 and top < y2 and bottom > y1
        small = touching_max_area is not None and stats[i, cv2.CC_STAT_AREA] <= touching_max_area
        if inside or (overlaps and small):
            mask[labels == i] = 0


def erase_watermark(mask):
    """Drop the www.statsf1.com watermark down the right edge of every map.

    Only components lying wholly inside the strip go: the strip is narrower
    than any circuit, so the track can never be one of them even where it runs
    to the edge of the image (Baku).
    """
    height, width = mask.shape
    erase_components_in_box(mask, (width - WATERMARK_MARGIN, 0, width, height))


# ---------------------------------------------------------------------------
# The chequered flag.
#
# statsf1 draws one flag glyph, pixel for pixel the same on every map: a 30x22
# bordered chequer block. So it is found by template matching rather than by
# asking a model for a box. assets/flag_template.png is that block, cut from
# the Zolder map. Measured over all 157 cached maps the match scores at least
# 0.75 (Hockenheim and Brands Hatch, where the flag sits against the left edge
# of the image) and 0.99 elsewhere, while the best match anywhere that is NOT
# the flag scores 0.61. The image is padded by a template's width first so a
# flag cut off by the image edge still matches.
FLAG_TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "assets" / "flag_template.png"
FLAG_MATCH_THRESHOLD = 0.68
_flag_template = None


def flag_template():
    global _flag_template
    if _flag_template is None:
        _flag_template = cv2.imread(str(FLAG_TEMPLATE_PATH), cv2.IMREAD_GRAYSCALE)
        if _flag_template is None:
            raise FileNotFoundError(f"Chequered flag template missing: {FLAG_TEMPLATE_PATH}")
    return _flag_template


def find_chequered_flag(gray):
    """(score, (x1, y1, x2, y2)) of the flag glyph; the box is exclusive at x2, y2."""
    template = flag_template()
    th, tw = template.shape
    padded = cv2.copyMakeBorder(gray, th, th, tw, tw, cv2.BORDER_CONSTANT, value=0)
    result = cv2.matchTemplate(padded, template, cv2.TM_CCOEFF_NORMED)
    _, score, _, (x, y) = cv2.minMaxLoc(result)
    x, y = x - tw, y - th
    return float(score), (x, y, x + tw, y + th)


# ---------------------------------------------------------------------------
# The leader line and the start/finish point.
#
# The line joining the flag to the track is always drawn the same way: a 45
# degree diagonal, three pixels wide - white, black, white - whose black centre
# starts ON the corner pixel of the flag box and runs straight into the track's
# white edge line. That makes the start/finish point a pixel-exact reading:
# walk the diagonal out of each corner, and the corner where the walk finds
# dark centre pixels flanked by white ones is the leader; the first bright
# pixel the walk reaches is where the leader meets the track. On 151 of the
# 157 maps that signature is at least two pixels long; the other six (the
# Hockenheim and Brands Hatch maps) have the flag jammed against the track and
# the walk reaches the edge line within a few pixels regardless.
LEADER_MAX_LENGTH = 60
LEADER_DARK = 90
LEADER_BRIGHT = 180
LEADER_MIN_SIGNATURE = 2
LEADER_GLUED_REACH = 8
_CORNERS = (("tl", (0, 0), (-1, -1)), ("tr", (1, 0), (1, -1)),
            ("bl", (0, 1), (-1, 1)), ("br", (1, 1), (1, 1)))


def find_start_finish_touch(gray, flag_box):
    """Where the flag's leader line meets the track.

    Returns {"corner": (x, y), "direction": (dx, dy), "touch": (x, y),
    "signature": n, "glued": bool} or None if no corner's diagonal reaches
    anything bright within LEADER_MAX_LENGTH.
    """
    height, width = gray.shape
    x1, y1, x2, y2 = flag_box
    candidates = []
    for _, (cx_sel, cy_sel), (dx, dy) in _CORNERS:
        cx = x2 - 1 if cx_sel else x1
        cy = y2 - 1 if cy_sel else y1
        signature, touch = 0, None
        for t in range(0, LEADER_MAX_LENGTH):
            x, y = cx + dx * t, cy + dy * t
            if not (0 <= x < width and 0 <= y < height):
                break
            value = int(gray[y, x])
            if t > 0 and value > WHITE_THRESHOLD:
                touch = (x, y)
                break
            fx, fy, gx, gy = x + dx, y, x, y + dy
            if (value < LEADER_DARK and 0 <= fx < width and 0 <= gy < height
                    and gray[fy, fx] > LEADER_BRIGHT and gray[gy, gx] > LEADER_BRIGHT):
                signature += 1
        if touch is not None:
            reach = abs(touch[0] - cx)
            candidates.append((signature, -reach, (cx, cy), (dx, dy), touch))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    signature, neg_reach, corner, direction, touch = candidates[0]
    glued = signature < LEADER_MIN_SIGNATURE
    if glued and -neg_reach > LEADER_GLUED_REACH:
        return None
    return {"corner": corner, "direction": direction, "touch": touch,
            "signature": signature, "glued": glued}


def erase_flag_and_leader(mask, flag_box, leader):
    """Take the flag glyph and its leader out of the white mask before tracing.

    The leader is erased up to two pixels short of the touch point so the
    track's own edge line is not notched where the bar will be drawn.
    """
    if leader is not None:
        (cx, cy), (dx, dy), (tx, ty) = leader["corner"], leader["direction"], leader["touch"]
        length = abs(tx - cx)
        if length > 2:
            end = (cx + dx * (length - 2), cy + dy * (length - 2))
            cv2.line(mask, (cx, cy), end, 0, 5)
    # With the leader gone the glyph is a handful of small components inside
    # its own box, so they can be taken without touching the track - a plain
    # rectangle with a margin cut 25px out of Monaco's pit straight. The exact
    # box is then cleared as well, for a flag drawn hard against the track
    # whose border shares a component with the edge line.
    erase_components_in_box(mask, flag_box, margin=2)
    erase_box(mask, flag_box, margin=0)


# ---------------------------------------------------------------------------
# Corner names and turn numbers: their glyphs, found on the mask so they can be
# erased before the track is traced. What the labels say, and where they are
# drawn, comes from the OCR model further down - these boxes are not read.
#
# Every label on a statsf1 map is white text of one size, so its glyphs are
# the small white components - a few pixels to a few hundred, under 22px tall
# - that the track's edge lines (thousands of pixels long) and the flag are
# not. Gluing the glyphs of a line together horizontally gives one box per
# line of text. The watermark down the right edge is dropped by position; the
# arrow's white outline and the flag are dropped by the boxes passed in.
TEXT_MAX_GLYPH_AREA = 600
TEXT_GLYPH_MIN_HEIGHT = 3
TEXT_GLYPH_MAX_HEIGHT = 22
TEXT_GLYPH_MAX_WIDTH = 40
TEXT_LINE_MIN_WIDTH = 6
TEXT_LINE_MIN_HEIGHT = 6
TEXT_LINE_MAX_HEIGHT = 26
TEXT_GLUE_KERNEL = (3, 9)
WATERMARK_MARGIN = 25


def find_text_lines(white_mask, exclude_boxes=()):
    """Boxes (x, y, w, h) of every line of text, in reading order, and the glyph mask.

    A label printed against the track - Monaco's "Portier" - has letters
    touching the edge line, and those letters are one component with the whole
    circuit, so they are lost here and the label comes out short. Freeing them
    was tried both ways (cutting the band's outline out of the mask, and
    cutting the pixels beside the grey fill) and both did more harm than good,
    eating labels the closing had bulged round.
    """
    height, width = white_mask.shape
    work = white_mask.copy()
    for box in exclude_boxes:
        erase_box(work, box, margin=3)
    work[:, max(0, width - WATERMARK_MARGIN):] = 0

    count, labels, stats, _ = cv2.connectedComponentsWithStats(work, 8)
    glyphs = np.zeros_like(work)
    for i in range(1, count):
        area, w, h = stats[i, cv2.CC_STAT_AREA], stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if (area <= TEXT_MAX_GLYPH_AREA and TEXT_GLYPH_MIN_HEIGHT <= h <= TEXT_GLYPH_MAX_HEIGHT
                and w <= TEXT_GLYPH_MAX_WIDTH):
            glyphs[labels == i] = 255

    glued = cv2.dilate(glyphs, np.ones(TEXT_GLUE_KERNEL, np.uint8))
    count, labels, stats, _ = cv2.connectedComponentsWithStats(glued, 8)
    boxes = []
    for i in range(1, count):
        x, y, w, h = (stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP],
                      stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT])
        # the dilation grew the box by the kernel's reach on each side
        x, w = x + TEXT_GLUE_KERNEL[1] // 2, w - (TEXT_GLUE_KERNEL[1] // 2) * 2
        y, h = y + TEXT_GLUE_KERNEL[0] // 2, h - (TEXT_GLUE_KERNEL[0] // 2) * 2
        if w >= TEXT_LINE_MIN_WIDTH and TEXT_LINE_MIN_HEIGHT <= h <= TEXT_LINE_MAX_HEIGHT:
            boxes.append((int(x), int(y), int(w), int(h)))
    boxes.sort(key=lambda b: (b[1] // 8, b[0]))
    return boxes, glyphs


# ---------------------------------------------------------------------------
# Corner names and turn numbers: what they say and where, read off the whole
# map by a VLM.
#
# The map is preprocessed first (see preprocess_for_ocr) so none of the aerial
# photo underneath survives into what the model sees. qwen3-vl:4b reads it; if
# that fails it is retried with a repeat penalty, and if that fails too
# minicpm, which is less accurate but copes with far more context, gets it.
OCR_MODELS = ("qwen3-vl:4b", "openbmb/minicpm-v4.6:1b")
OCR_INPUT_PATH = "vlm_inference_ready.png"

SYSTEM_PROMPT_OCR = """
    You are a strict OCR engine, specialising in Formula One circuit maps.
    You will be given an image of a Formula One circuit. This image will contain text or numbers (corner names and turn numbers).
    For each text item found, transcribe it verbatim and locate its exact 2D bounding box normalized to a 0-1000 coordinate grid system. Ignore all symbols such as the chequered flag or the arrow. Only text.
    Do not use an internal monologue or thinking process. Output the raw JSON text block directly without wrapped tags. Do not include blank characters or newlines in the output.
    Do not repeat the same text in the output. Only output the text once with its bounding box.

    Formatting Rules:
    You MUST output your entire response as a single, valid JSON array of objects. Do not include conversational text or markdown code wraps. Follow this exact schema:
    [
    {"text": "Senna Chicane", "box_2d": [x_min, y_min, x_max, y_max]},
    {"text": "3", "box_2d": [x_min, y_min, x_max, y_max]},
        ...
    ]
    If there is no text in the image, return an empty JSON array: []
    """
SYSTEM_PROMPT_OCR_FALLBACK = """
    You are a strict OCR engine, specialising in Formula One circuit maps.
    You will be given an image of a Formula One circuit containing text or numbers (corner names and turn numbers).
    For each text item found, transcribe it verbatim and locate its exact 2D bounding box normalized to a 0-1000 coordinate grid system. Ignore all symbols such as the chequered flag or the arrow. Only text.
    Do not try to perform OCR on the arrow or chequered flag. Only text or numbers.

    Do not use an internal monologue or thinking process. Output the raw JSON text block directly.
    You MUST output your entire response as a single, valid JSON array of objects following the required schema.

    Formatting Rules:
    - The 'box_2d' array MUST contain exactly 4 integers ordered exactly as: [xmin, ymin, xmax, ymax].
    - Do not output native XML tags like <box>. Instead, map those integer bins directly into the JSON array.
    - If there is no text in the image, return an empty JSON array: []

    Example output structure:
    [
    {"text": "Senna Chicane", "box_2d": [120, 340, 250, 410]},
    {"text": "3", "box_2d": [500, 200, 550, 250]}
    ]
    """

OCR_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "text": {"type": "string"},
            "box_2d": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 4,
                "maxItems": 4
            }
        },
        "required": ["text", "box_2d"],
        "additionalProperties": False
    }
}


def preprocess_for_ocr(bgr):
    """The image the OCR model reads. The SVG mask is never touched by this.

    GIMP-max-contrast pass: hard cut at native resolution first, so none of the
    aerial photo underneath can survive into the upscale, then enlarge and
    re-binarise to strip the grey LANCZOS ringing off the stroke edges.
    """
    orig_h, orig_w = bgr.shape[:2]
    pil_img = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    pil_img_for_vlm = pil_img.convert("L")
    pil_img_for_vlm = gimp_contrast(pil_img_for_vlm, contrast=1.0, pivot=200)
    pil_img_for_vlm = pil_img_for_vlm.resize(
        (orig_w * 5, orig_h * 5), Image.Resampling.LANCZOS
    )
    pil_img_for_vlm = pil_img_for_vlm.point(lambda p: 255 if p > 127 else 0)

    # Close the hairline gaps the hard threshold leaves in thin glyph strokes.
    vlm_arr = np.asarray(pil_img_for_vlm, dtype=np.uint8)
    vlm_arr = cv2.morphologyEx(vlm_arr, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    return Image.fromarray(vlm_arr)


def ocr_labels(bgr):
    """[{"text": ..., "box_2d": [xmin, ymin, xmax, ymax]}, ...] read off the whole map.

    Boxes are on the model's 0-1000 grid; scale_box_to_pixels turns them into
    pixels of the original image.
    """
    temp_vlm_input = OCR_INPUT_PATH
    preprocess_for_ocr(bgr).save(temp_vlm_input)
    try:
        response_p1 = chat(
            model='qwen3-vl:4b',
            messages=[{
                'role': 'user',
                'content': SYSTEM_PROMPT_OCR,
                'images': [temp_vlm_input]
            }],
            format=OCR_SCHEMA,
            think = False,
            options={
                'temperature': 0.0,
                'top_k': 1,
                'top_p': 1.0,
                'num_ctx': 5800,
            }
        )

        labels = json.loads(response_p1['message'].get('thinking') or response_p1['message'].get('content')) #for some reason, the response comes in the thinking field for me.
        chat(model="qwen3-vl:4b", messages=[], keep_alive=0)
    except Exception as e:
        chat(model="qwen3-vl:4b", messages=[], keep_alive=0) #unload the model to free up memory
        print("Primary OCR failed: %s", e)
        try:
            #try qwen with a repeat penalty
            response_p1 = chat(
                model='qwen3-vl:4b',
                messages=[{
                    'role': 'user',
                    'content': SYSTEM_PROMPT_OCR,
                    'images': [temp_vlm_input]
                }],
                format=OCR_SCHEMA,
                think = False,
                options={
                    'temperature': 0.0,
                    'top_k': 1,
                    'top_p': 1.0,
                    'num_ctx': 5800,
                    'repeat_penalty': 1.2,    # this is to make sure that it doesn't get stuck repeating the same token over and over again, which can happen with smaller models.
                    'repeat_last_n': 64        # Looks back 64 tokens
                }
            )

            labels = json.loads(response_p1['message'].get('thinking') or response_p1['message'].get('content'))
            chat(model="qwen3-vl:4b", messages=[], keep_alive=0)
        except Exception as e2:
            #try a smaller model if qwen fails, because qwen is very large and can run out of memory if there is too much context. the smaller model is less accurate, but it can handle more context.
            chat(model="qwen3-vl:4b", messages=[], keep_alive=0) #unload the model to free up memory
            print("Secondary OCR failed: %s", e2)
            response_p1 = chat(
                model='openbmb/minicpm-v4.6:1b',
                messages=[{
                    'role': 'user',
                    'content': SYSTEM_PROMPT_OCR_FALLBACK,
                    'images': [temp_vlm_input]
                }],
                format=OCR_SCHEMA,
                think = False,
                options={
                    'temperature': 0.0,
                    'top_k': 1,
                    'top_p': 1.0,
                    'num_ctx': 16384, #more context here because this is a smaller model and if the previous model fails for lack of context, this one will be able to process it.
                    'repeat_penalty': 1.2,    # this is to make sure that it doesn't get stuck repeating the same token over and over again, which can happen with smaller models.
                    'repeat_last_n': 64        # Looks back 64 tokens

                }
            )
            labels = json.loads(response_p1['message'].get('thinking') or response_p1['message'].get('content'))
            chat(model="openbmb/minicpm-v4.6:1b", messages=[], keep_alive=0) #unload the model to free up memory
    finally:
        if os.path.exists(temp_vlm_input):
            os.remove(temp_vlm_input)
    return labels


# ---------------------------------------------------------------------------
# Three first readings of the labels, and the arbiters where they disagree.
#
# PaddleOCR-VL-1.6 is an OCR model rather than a general VLM, so it fails
# differently from qwen: it misreads the odd character and merges a turn
# number into the name beside it ("Grand6"), but it does not invent text and
# its boxes are exact 4-corner boxes, rotated text included. docTR is neither
# a VLM nor a language model at all, a text detector and a line recogniser,
# with its own exact corners. The three readings are grouped by position and
# compared. Where every reader that found a label agrees, and at least two
# did, it is taken. Where two agree and the third reads something else, the
# two stand unless two sure plain OCRs back the third. Anything else - no two
# agree, or only one reader found the label - is cut out of the preprocessed
# map, straightened, and read cold by Tesseract, EasyOCR, TrOCR and minicpm
# (see resolve_label). A reading they back is taken; anything else keeps
# Paddle's reading (docTR's, then qwen's, if Paddle found nothing) and is
# marked for review, except a label only docTR found, which is dropped. A
# region with no white in it at all is text no reader should have found and
# is dropped.
#
# Paddle runs through transformers, not paddlepaddle, which has no Python
# 3.14 build. It was measured on Monaco and Adelaide before being wired in:
# on the raw photo it missed every steeply rotated label, on the gimp_contrast
# image at 2x it found all 40.
PADDLE_MODEL = "PaddlePaddle/PaddleOCR-VL-1.6"
PADDLE_UPSCALE = 2
PADDLE_MAX_PIXELS = 2048 * 28 * 28      # the model card's setting for spotting
PADDLE_MAX_NEW_TOKENS = 1536
# docTR is a third first reader, and the only one that is not a VLM: a
# DBNet detector finds each line, rotated ones included, and PARSeq reads it.
# It was measured on Monaco and Barcelona before being wired in: the inverted
# contrast image at 2x read the most turn numbers of the raw photo, the
# contrast image and its inverse at 1x and 2x. Words it is under half sure of
# are single letters read off bits of track.
DOCTR_DET_ARCH = "db_resnet50"
DOCTR_RECO_ARCH = "parseq"
DOCTR_UPSCALE = 2
DOCTR_MIN_WORD_CONFIDENCE = 0.5
SOURCE_NAMES = {"paddle": "Paddle", "doctr": "docTR", "qwen": "qwen"}
# The crop is read by four arbiters, Tesseract, EasyOCR, TrOCR and minicpm.
# Tesseract, EasyOCR and TrOCR are plain text recognisers: they read the
# straightened crop as printed text and say how sure they are. TrOCR is a
# transformer, but one trained only to transcribe a line of print, not to
# answer questions about an image, so it does not fail the way the VLMs do;
# it is also the only one of the three with a language model behind it, so it
# reads a name through a broken glyph where Tesseract and EasyOCR, which read
# character by character, do not - and fails by writing a likelier word. minicpm is
# a general VLM like qwen and tends to fail the way qwen does - it answered
# "#000000" for a lone "3" - so on its own it cannot outvote a plain OCR.
# Tesseract runs on the CPU. The Windows build is UB Mannheim's; the Latin
# script model (every accented name on the maps) is tessdata_best's
# script/Latin.traineddata, kept in assets/tessdata. EasyOCR is also kept on
# CPU: the crops are tiny, and leaving its torch model on the GPU would fight
# qwen/Paddle/Ollama for VRAM, and so is TrOCR. TrOCR is the large printed
# model: accuracy matters more here than the second or so per crop it costs.
ARBITER_MODEL = "openbmb/minicpm-v4.6:1b"
TROCR_MODEL = "microsoft/trocr-large-printed"
TROCR_MAX_NEW_TOKENS = 32
# A run of inked rows under this share of the tallest one is an accent or a
# speck, not a line of its own (see text_line_crops).
TROCR_MIN_LINE_SHARE = 0.35
# The printed TrOCR models were fine-tuned on receipts: they write every word
# in capitals and tack on a receipt's " :" or "*". The punctuation is dropped
# in trocr_reading; the case cannot be recovered, so TrOCR's reading only
# ever backs a candidate or another arbiter's spelling (see _pick_label).
UNCASED_ARBITERS = {"TrOCR"}
ARBITER_CROP_PATH = "vlm_arbiter_crop.png"
TESSERACT_CMD = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR = Path(__file__).resolve().parent.parent / "assets" / "tessdata"
TESSERACT_LANG = "Latin"
# OCR word confidences are normalised to 0-100 and a reading counts by its
# least sure word. Agreeing with qwen or Paddle needs less than standing in
# for both of them as a near-miss.
ARBITER_MIN_CONFIDENCE = 50
ARBITER_REPLACE_CONFIDENCE = 80
ARBITER_CROP_PAD = 4
ARBITER_CROP_SCALE = 4
# Share of white pixels a crop needs before it is worth asking about. A real
# label is several percent white even in a generous crop; empty tarmac or
# photo after the hard contrast cut is black.
ARBITER_MIN_INK = 0.01
LABEL_LINK_PAD = 2
NUMBER_MATCH_DISTANCE = 20.0
# Below these the label is treated as level: a turn number's box is nearly
# square, and reading its long edge as the text direction would stand it on
# its side.
STRAIGHTEN_MIN_ANGLE = 8.0
STRAIGHTEN_MAX_ASPECT = 0.6

_LOC_TOKEN = re.compile(r"<\|LOC_(\d+)\|>")
_TRAILING_NUMBER = re.compile(r"^(.*[^\W\d_])\s*(\d{1,2})$")
# A letter straight after the digits, so "130R" is left whole.
_LEADING_NUMBER = re.compile(r"^(\d{1,2})\s*([^\W\d_].*)$")
_paddle = None
_easyocr = None
_trocr = None
_doctr = None
# What TrOCR puts round a word that is not part of it: "-CAIXA", "GRAND*******".
_TROCR_EDGE_JUNK = ":;*<>_-~.,|"


class _PaddleLoadNoise(logging.Filter):
    """Drops two warnings transformers 5 raises about its own Paddle support.

    The hub config keeps mrope_section under a "default" rope, which the rope
    validator does not know but the model reads; and transformers' own
    PaddleOCRVLProcessor still sets the deprecated image_processor_class.
    Neither can be fixed from here.
    """

    def filter(self, record):
        message = record.getMessage()
        return not ("Unrecognized keys in `rope_parameters`" in message and "mrope_section" in message
                    or "PaddleOCRVLProcessor` defines `image_processor_class" in message)


def _paddle_model():
    """Paddle loaded once per process and moved onto the GPU for each map.

    It is parked on the CPU between maps rather than kept on the GPU: the
    card is 6 GB and qwen3-vl needs most of it straight afterwards.
    """
    global _paddle
    import torch
    from transformers import AutoConfig, AutoModelForImageTextToText, AutoProcessor
    if _paddle is None:
        for name in ("transformers.modeling_rope_utils", "transformers.processing_utils"):
            logging.getLogger(name).addFilter(_PaddleLoadNoise())
        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.float16 if device == "cuda" else torch.float32
        # The checkpoint's lm_head is not a copy of the embeddings and its
        # config says so, but transformers' pre-v5 compatibility shim flips
        # tie_word_embeddings back on while parsing the flat config.
        config = AutoConfig.from_pretrained(PADDLE_MODEL)
        config.tie_word_embeddings = False
        model = AutoModelForImageTextToText.from_pretrained(
            PADDLE_MODEL, config=config, dtype=dtype, attn_implementation="sdpa").eval()
        processor = AutoProcessor.from_pretrained(PADDLE_MODEL)
        _paddle = {"model": model, "processor": processor, "device": device, "dtype": dtype}
    _paddle["model"].to(_paddle["device"])
    return _paddle


def _park_paddle():
    if _paddle is None:
        return
    import torch
    _paddle["model"].to("cpu")
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def _label(text, points, source):
    points = np.asarray(points, dtype=np.float32).reshape(4, 2)
    box = (float(points[:, 0].min()), float(points[:, 1].min()),
           float(points[:, 0].max()), float(points[:, 1].max()))
    return {"text": text.strip(), "points": points, "box": box, "source": source}


def paddle_labels(bgr):
    """Paddle's spotting output as labels with pixel corners in the original image."""
    import torch
    orig_h, orig_w = bgr.shape[:2]
    image = gimp_contrast(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)).convert("L"),
                          contrast=1.0, pivot=200).convert("RGB")
    image = image.resize((orig_w * PADDLE_UPSCALE, orig_h * PADDLE_UPSCALE), Image.Resampling.LANCZOS)

    paddle = _paddle_model()
    processor = paddle["processor"]
    try:
        messages = [{"role": "user", "content": [{"type": "image", "image": image},
                                                 {"type": "text", "text": "Spotting:"}]}]
        # The model card reads processor.image_processor.min_pixels, which
        # transformers 5 moved into size["shortest_edge"].
        inputs = processor.apply_chat_template(
            messages, add_generation_prompt=True, tokenize=True, return_dict=True, return_tensors="pt",
            processor_kwargs={"images_kwargs": {
                "size": {"shortest_edge": processor.image_processor.size["shortest_edge"],
                         "longest_edge": PADDLE_MAX_PIXELS}}},
        ).to(paddle["model"].device)
        inputs["pixel_values"] = inputs["pixel_values"].to(paddle["dtype"])
        # use_cache has to be forced: the model's generation_config ships with
        # it off, which re-runs the whole image for every token - 8.7s a token
        with torch.inference_mode():
            output = paddle["model"].generate(**inputs, max_new_tokens=PADDLE_MAX_NEW_TOKENS,
                                              do_sample=False, use_cache=True)
    finally:
        _park_paddle()

    generated = output[0][inputs["input_ids"].shape[-1]:]
    if len(generated) >= PADDLE_MAX_NEW_TOKENS:
        print(f"  Paddle hit its {PADDLE_MAX_NEW_TOKENS}-token limit; labels past that point are missing.")
    raw = processor.decode(generated, skip_special_tokens=False)

    labels = []
    for line in raw.split("\n"):
        locs = [int(v) for v in _LOC_TOKEN.findall(line)]
        text = _LOC_TOKEN.sub("", line).replace("</s>", "").strip()
        if not text:
            continue
        if len(locs) != 8:
            print(f"  Paddle returned {ascii(text)} with {len(locs)} coordinates instead of 8; skipped.")
            continue
        # Corners come clockwise from top-left on a 0-1000 grid over the image.
        points = [(locs[i] * orig_w / 1000.0, locs[i + 1] * orig_h / 1000.0) for i in range(0, 8, 2)]
        labels.append(_label(text, points, "paddle"))
    return labels


def _doctr_model():
    """docTR loaded once per process and, like Paddle, on the GPU only while it reads a map."""
    global _doctr
    import torch
    if _doctr is None:
        from doctr.models import ocr_predictor
        _doctr = {"model": ocr_predictor(det_arch=DOCTR_DET_ARCH, reco_arch=DOCTR_RECO_ARCH, pretrained=True,
                                         assume_straight_pages=False, export_as_straight_boxes=False,
                                         detect_orientation=False, straighten_pages=False).eval(),
                  "device": "cuda" if torch.cuda.is_available() else "cpu", "torch": torch}
    _doctr["model"].to(_doctr["device"])
    return _doctr


def doctr_labels(bgr):
    """docTR's lines as labels with pixel corners in the original image."""
    orig_h, orig_w = bgr.shape[:2]
    gray = np.asarray(gimp_contrast(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)),
                                    contrast=1.0, pivot=200), dtype=np.uint8)
    # Dark print on a light page, as docTR was trained on.
    image = np.stack([255 - gray] * 3, axis=-1)
    image = cv2.resize(image, (orig_w * DOCTR_UPSCALE, orig_h * DOCTR_UPSCALE), interpolation=cv2.INTER_LANCZOS4)
    doctr = _doctr_model()
    try:
        with doctr["torch"].inference_mode():
            page = doctr["model"]([image]).pages[0]
    finally:
        doctr["model"].to("cpu")
        if doctr["device"] == "cuda":
            doctr["torch"].cuda.empty_cache()

    labels = []
    for block in page.blocks:
        for line in block.lines:
            words = [w.value for w in line.words if w.confidence >= DOCTR_MIN_WORD_CONFIDENCE]
            if not words:
                continue
            # Relative corners, clockwise from top-left; a straight line comes
            # back as two corners.
            corners = np.asarray(line.geometry, dtype=np.float32).reshape(-1, 2)
            if len(corners) == 2:
                (x1, y1), (x2, y2) = corners
                corners = np.array([(x1, y1), (x2, y1), (x2, y2), (x1, y2)], dtype=np.float32)
            points = [(float(x) * orig_w, float(y) * orig_h) for x, y in corners[:4]]
            labels.append(_label(" ".join(words), points, "doctr"))
    return labels


def qwen_labels(bgr):
    orig_h, orig_w = bgr.shape[:2]
    labels = []
    for label in ocr_labels(bgr):
        x1, y1, x2, y2 = scale_box_to_pixels(label["box_2d"], orig_w, orig_h)
        labels.append(_label(str(label["text"]), [(x1, y1), (x2, y1), (x2, y2), (x1, y2)], "qwen"))
    return labels


def normalise_text(text):
    """What two readings are compared on: no accents, case, spacing or punctuation."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if c.isalnum() and not unicodedata.combining(c)).casefold()


def _is_watermark(text):
    lowered = text.lower()
    return "statsf1" in lowered or "http" in lowered or ".com" in lowered


def split_attached_number(label):
    """"Grand6" -> "Grand" and "6"; "7Wirth" -> "7" and "Wirth".

    A turn number printed beside a name is a label of its own, and Paddle
    sometimes reads the two as one, with the number on either side (Monaco's
    "Grand6", Barcelona's "7 Würth"). Left joined, the name can never agree
    with qwen's. Each part's share of the box is estimated from its share of
    the characters, which is close enough to crop it.
    """
    trailing = _TRAILING_NUMBER.match(label["text"])
    leading = _LEADING_NUMBER.match(label["text"])
    if trailing:
        first, second = trailing.group(1).strip(), trailing.group(2)
    elif leading:
        first, second = leading.group(1), leading.group(2).strip()
    else:
        return [label]
    split = len(first) / float(len(first) + len(second))
    tl, tr, br, bl = label["points"]
    top, bottom = tl + (tr - tl) * split, bl + (br - bl) * split
    return [_label(first, [tl, top, bottom, bl], label["source"]),
            _label(second, [top, tr, br, bottom], label["source"])]


def _centre(box):
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _boxes_touch(a, b, pad):
    return a[0] - pad <= b[2] and b[0] - pad <= a[2] and a[1] - pad <= b[3] and b[1] - pad <= a[3]


def _union_box(labels):
    return (min(l["box"][0] for l in labels), min(l["box"][1] for l in labels),
            max(l["box"][2] for l in labels), max(l["box"][3] for l in labels))


def reading_order_text(labels):
    """Join the lines of a name top to bottom, left to right within a line."""
    lines = []
    for label in sorted(labels, key=lambda l: _centre(l["box"])[1]):
        cy = _centre(label["box"])[1]
        height = label["box"][3] - label["box"][1]
        if lines and abs(cy - lines[-1]["cy"]) < 0.5 * min(height, lines[-1]["height"]):
            lines[-1]["labels"].append(label)
        else:
            lines.append({"cy": cy, "height": height, "labels": [label]})
    return " ".join(l["text"] for line in lines
                    for l in sorted(line["labels"], key=lambda l: l["box"][0]))


def group_names(labels):
    """Clusters of name labels, from either model, that touch one another.

    statsf1 sets a long name on two lines and the models do not agree on
    whether that is one label or two - Paddle returns "S de la" and
    "Piscine", qwen "S de la Piscine" - so names are compared a cluster at a
    time rather than a label at a time.
    """
    parent = list(range(len(labels)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            if _boxes_touch(labels[i]["box"], labels[j]["box"], LABEL_LINK_PAD):
                parent[root(j)] = root(i)
    groups = {}
    for i, label in enumerate(labels):
        groups.setdefault(root(i), []).append(label)
    return list(groups.values())


def match_numbers(by_source, sources):
    """Turn numbers from each reader matched by position: [{source: [label] or []}].

    Each reader's numbers are matched in turn to the nearest cluster so far
    within NUMBER_MATCH_DISTANCE that has none of that reader's yet, nearest
    pair first; any left over start clusters of their own.
    """
    clusters = []
    for labels, source in zip(by_source, sources):
        pairs = sorted((math.dist(_centre(c["centre"]), _centre(l["box"])), ci, li)
                       for ci, c in enumerate(clusters) for li, l in enumerate(labels))
        used_c, used_l = set(), set()
        for distance, ci, li in pairs:
            if distance > NUMBER_MATCH_DISTANCE:
                break
            if ci in used_c or li in used_l:
                continue
            used_c.add(ci)
            used_l.add(li)
            clusters[ci][source] = [labels[li]]
        clusters += [{"centre": l["box"], source: [l]} for li, l in enumerate(labels) if li not in used_l]
    return [{s: c.get(s, []) for s in sources} for c in clusters]


def label_crop(binary, points):
    """The region of the preprocessed map under `points`, turned level and enlarged."""
    points = np.asarray(points, dtype=np.float32).reshape(-1, 2)
    rect = cv2.minAreaRect(points)
    (cx, cy), _, _ = rect
    corners = cv2.boxPoints(rect)
    edges = [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    start, end = max(edges, key=lambda e: float(np.hypot(*(e[1] - e[0]))))
    length = float(np.hypot(*(end - start)))
    thickness = min(float(np.hypot(*(e[1] - e[0]))) for e in edges)
    angle = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
    if angle > 90:
        angle -= 180
    elif angle <= -90:
        angle += 180

    height, width = binary.shape
    if abs(angle) >= STRAIGHTEN_MIN_ANGLE and thickness < STRAIGHTEN_MAX_ASPECT * length:
        # Positive angles in getRotationMatrix2D turn the picture anticlockwise,
        # which in y-down coordinates takes a direction at `angle` back to 0.
        matrix = cv2.getRotationMatrix2D((float(cx), float(cy)), angle, 1.0)
        level = cv2.warpAffine(binary, matrix, (width, height), flags=cv2.INTER_LINEAR, borderValue=0)
        x1, x2 = cx - length / 2.0, cx + length / 2.0
        y1, y2 = cy - thickness / 2.0, cy + thickness / 2.0
    else:
        level = binary
        x1, y1 = points[:, 0].min(), points[:, 1].min()
        x2, y2 = points[:, 0].max(), points[:, 1].max()

    x1, y1 = max(0, int(x1) - ARBITER_CROP_PAD), max(0, int(y1) - ARBITER_CROP_PAD)
    x2, y2 = min(width, int(math.ceil(x2)) + ARBITER_CROP_PAD), min(height, int(math.ceil(y2)) + ARBITER_CROP_PAD)
    return level[y1:y2, x1:x2]


def arbiter_crop(binary, points):
    """The label under `points`, level, enlarged and framed in black; None if it has no white in it."""
    crop = label_crop(binary, points)
    if crop.size == 0 or float(np.count_nonzero(crop > 127)) / crop.size < ARBITER_MIN_INK:
        return None
    image = Image.fromarray(crop)
    image = image.resize((image.width * ARBITER_CROP_SCALE, image.height * ARBITER_CROP_SCALE),
                         Image.Resampling.LANCZOS)
    canvas = Image.new("L", (image.width + 20, image.height + 20), 0)
    canvas.paste(image, (10, 10))
    return canvas


def minicpm_reading(canvas):
    """What minicpm reads in the crop: "" for no text, None if it failed."""
    canvas.save(ARBITER_CROP_PATH)
    try:
        response = chat(
            model=ARBITER_MODEL,
            messages=[{"role": "user",
                       "content": ("The image shows white text on a black background, cut from a Formula One "
                                   "circuit map. Transcribe it exactly as written. If there is no text, return "
                                   "an empty string."),
                       "images": [ARBITER_CROP_PATH]}],
            format={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
            think=False,
            options={"temperature": 0.0, "top_k": 1, "top_p": 1.0, "num_ctx": 4096},
        )
        message = response["message"]
        return str(json.loads(message.get("content") or message.get("thinking"))["text"]).strip()
    except Exception as e:
        print(f"  minicpm could not read a crop: {e}")
        return None
    finally:
        if os.path.exists(ARBITER_CROP_PATH):
            os.remove(ARBITER_CROP_PATH)


def tesseract_reading(canvas, digits=False):
    """(text, confidence) from Tesseract for the crop: ("", 0) for no text, (None, 0) if it failed.

    `digits` reads the crop as a turn number: one word, digits only.
    """
    # Tesseract is trained on dark text on a light page.
    canvas = Image.fromarray(255 - np.asarray(canvas))
    # A name is read as a block, which takes the two lines statsf1 sets a long
    # name on; a turn number as a single word.
    config = "--psm 8 -c tessedit_char_whitelist=0123456789" if digits else "--psm 6"
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
    # The tessdata path has spaces and a comma in it, which pytesseract's
    # config string does not quote on Windows; the environment variable does.
    os.environ["TESSDATA_PREFIX"] = str(TESSDATA_DIR)
    try:
        data = pytesseract.image_to_data(canvas, lang=TESSERACT_LANG, config=config,
                                         output_type=pytesseract.Output.DICT)
    except (pytesseract.TesseractError, pytesseract.TesseractNotFoundError, OSError) as e:
        print(f"  Tesseract could not read a crop: {e}")
        return None, 0.0
    lines = {}
    for i, word in enumerate(data["text"]):
        if word.strip() and float(data["conf"][i]) >= 0:
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append((word.strip(), float(data["conf"][i])))
    if not lines:
        return "", 0.0
    # The padded crop can take in a bit of track, which comes back as a line
    # of its own with no word Tesseract is sure of - Pescara's "Spoltore" (89)
    # under a corner of track read as "r" (43). A line like that is dropped,
    # unless it is all there is.
    lines = list(lines.values())
    kept = [line for line in lines if max(c for _, c in line) >= ARBITER_MIN_CONFIDENCE] or lines
    text = " ".join(word for line in kept for word, _ in line)
    return text, min(c for line in kept for _, c in line)


def _easyocr_reader():
    global _easyocr
    if _easyocr is None:
        import easyocr
        _easyocr = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _easyocr


def _ordered_easyocr_text(words):
    lines = []
    for word in sorted(words, key=lambda w: _centre(w["box"])[1]):
        cy = _centre(word["box"])[1]
        height = word["box"][3] - word["box"][1]
        if lines and abs(cy - lines[-1]["cy"]) < 0.5 * min(height, lines[-1]["height"]):
            lines[-1]["words"].append(word)
        else:
            lines.append({"cy": cy, "height": height, "words": [word]})
    return " ".join(w["text"] for line in lines
                    for w in sorted(line["words"], key=lambda item: item["box"][0]))


def _easyocr_result_text(results):
    words = []
    for points, text, confidence in results:
        text = str(text).strip()
        if not text:
            continue
        points = np.asarray(points, dtype=np.float32).reshape(4, 2)
        box = (float(points[:, 0].min()), float(points[:, 1].min()),
               float(points[:, 0].max()), float(points[:, 1].max()))
        words.append({"text": text, "box": box, "confidence": float(confidence) * 100.0})
    if not words:
        return "", 0.0
    return _ordered_easyocr_text(words), min(w["confidence"] for w in words)


def easyocr_reading(canvas, digits=False):
    """(text, confidence) from EasyOCR for the crop: ("", 0) for no text, (None, 0) if it failed."""
    try:
        reader = _easyocr_reader()
        kwargs = {"detail": 1, "paragraph": False, "decoder": "greedy"}
        if digits:
            kwargs["allowlist"] = "0123456789"
        results = reader.readtext(np.asarray(canvas), **kwargs)
    except Exception as e:
        print(f"  EasyOCR could not read a crop: {e}")
        return None, 0.0
    return _easyocr_result_text(results)


def _trocr_model():
    """TrOCR loaded once per process, on the CPU for the same reason as EasyOCR.

    The processor is put together by hand: transformers 5's AutoTokenizer
    cannot build the checkpoint's fast tokenizer, but its RobertaTokenizer
    files load as they are.
    """
    global _trocr
    if _trocr is None:
        import torch
        from transformers import RobertaTokenizer, TrOCRProcessor, ViTImageProcessor, VisionEncoderDecoderModel
        processor = TrOCRProcessor(image_processor=ViTImageProcessor.from_pretrained(TROCR_MODEL),
                                   tokenizer=RobertaTokenizer.from_pretrained(TROCR_MODEL))
        model = VisionEncoderDecoderModel.from_pretrained(TROCR_MODEL).eval()
        # The sinusoidal position table is a plain attribute, not a weight, so
        # transformers 5's meta-device load leaves it empty; with None the
        # module builds it on its first call.
        for module in model.decoder.modules():
            if type(module).__name__ == "TrOCRSinusoidalPositionalEmbedding":
                module.weights = None
        tokenizer = processor.tokenizer
        digit_ids = [i for i in range(len(tokenizer))
                     if tokenizer.convert_ids_to_tokens(i).lstrip("Ġ").isdigit()]
        _trocr = {"model": model, "processor": processor, "torch": torch,
                  "digit_ids": digit_ids + [model.generation_config.eos_token_id or tokenizer.eos_token_id]}
    return _trocr


def text_line_crops(canvas):
    """The crop cut into its lines of text, top to bottom, by the black rows between them.

    TrOCR reads one line at a time; statsf1 sets a long name on two.
    """
    arr = np.asarray(canvas)
    inked = np.count_nonzero(arr > 127, axis=1) > 0
    runs, start = [], None
    for y, on in enumerate(list(inked) + [False]):
        if on and start is None:
            start = y
        elif not on and start is not None:
            runs.append([start, y])
            start = None
    # A run much shorter than the tallest is an accent or a speck of track, and
    # belongs to the line it is nearest.
    tallest = max((b - a for a, b in runs), default=0)
    lines = []
    for run in runs:
        if lines and (run[1] - run[0] < TROCR_MIN_LINE_SHARE * tallest
                      or lines[-1][1] - lines[-1][0] < TROCR_MIN_LINE_SHARE * tallest):
            lines[-1][1] = run[1]
        else:
            lines.append(run)
    pad = 10
    return [canvas.crop((0, max(0, a - pad), canvas.width, min(canvas.height, b + pad))) for a, b in lines]


def trocr_reading(canvas, digits=False):
    """(text, confidence) from TrOCR for the crop: ("", 0) for no text, (None, 0) if it failed.

    TrOCR always writes something, so its confidence matters more than the
    others': a word counts by the probability of all its tokens together.
    """
    try:
        trocr = _trocr_model()
        torch, model, processor = trocr["torch"], trocr["model"], trocr["processor"]
        tokenizer = processor.tokenizer
        words = []
        for line in text_line_crops(canvas):
            # Trained on dark print on a light page, like Tesseract.
            image = Image.fromarray(255 - np.asarray(line)).convert("RGB")
            pixels = processor(images=image, return_tensors="pt").pixel_values
            kwargs = {"max_new_tokens": TROCR_MAX_NEW_TOKENS, "num_beams": 1, "do_sample": False,
                      "output_scores": True, "return_dict_in_generate": True}
            if digits:
                kwargs["prefix_allowed_tokens_fn"] = lambda batch, ids: trocr["digit_ids"]
            with torch.inference_mode():
                out = model.generate(pixels, **kwargs)
            tokens = out.sequences[0, -len(out.scores):].tolist()
            for token, scores in zip(tokens, out.scores):
                if token in tokenizer.all_special_ids:
                    continue
                piece = tokenizer.convert_ids_to_tokens(token)
                probability = float(torch.softmax(scores[0].float(), dim=-1)[token])
                if piece.startswith("Ġ") or not words:
                    words.append({"tokens": [token], "probability": probability})
                else:
                    words[-1]["tokens"].append(token)
                    words[-1]["probability"] *= probability
    except Exception as e:
        print(f"  TrOCR could not read a crop: {e}")
        return None, 0.0
    words = [(tokenizer.decode(w["tokens"]).strip(), w["probability"] * 100.0) for w in words]
    words = [(text.strip(_TROCR_EDGE_JUNK), confidence) for text, confidence in words]
    words = [(text, confidence) for text, confidence in words if any(c.isalnum() for c in text)]
    if not words:
        return "", 0.0
    return " ".join(text for text, _ in words), min(confidence for _, confidence in words)


# Every label on a statsf1 map is white glyphs, and find_text_lines already
# knows which white pixels are glyphs rather than track, flag or arrow. A
# label a model reports where there are none - qwen's "Senna Chicane" and "3"
# on maps with no text at all, lifted from its own prompt - is dropped before
# it can be matched with anything. The glyph mask is used rather than the line
# boxes because the line filter throws out anything under 6px wide, which is a
# lone "1". Boxes are padded because qwen's are loose.
#
# Only qwen's readings get the glyph test. A turn number printed against the
# track's edge line is one white component with the whole circuit, so it is
# not in the glyph mask at all - Barcelona's "1", Monaco's "7" and Singapore's
# "1" were all dropped that way while Paddle had read them correctly. Paddle
# has not invented a label on any map tested, so its readings only have to
# have some white under them.
LABEL_GLYPH_PAD = 3
LABEL_MIN_GLYPH_PIXELS = 8
# When the readings differ, an arbiter's is taken if it is this close to every
# other one: it reads a straightened crop of the label alone,
# and where the other two are near-misses of it (Pescara: "Spoldore",
# "Spotore", "Spoltore") it has been the right one. Anything further off -
# "#000000" for a lone "3" - is noise, and Paddle's reading stands.
#
# The allowance shrinks with length, one edit per four characters: a single
# character is within two edits of any other, which is how Barcelona's "1"
# became minicpm's "L". A turn number is never replaced by letters or the
# other way round.
ARBITER_MAX_EDIT_DISTANCE = 2
ARBITER_CHARS_PER_EDIT = 4


def edit_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def close_reading(read, candidate):
    """Whether an arbiter's reading is a near-miss of `candidate` rather than something else."""
    a, b = normalise_text(read), normalise_text(candidate)
    if not a or not b or a.isdigit() != b.isdigit():
        return False
    allowed = min(ARBITER_MAX_EDIT_DISTANCE, len(b) // ARBITER_CHARS_PER_EDIT)
    return edit_distance(a, b) <= allowed


def _is_accented(c):
    return c.isalpha() and ord(c) > 127


def accent_variant(accented, other):
    """Whether `other` is `accented` with only its accented letters misread.

    Each accented letter may come back as up to two other characters or as
    none - Tesseract reads Barcelona's "Würth" as "Wiirth", Paddle as "Wirth" -
    while every other letter must be the same. Case, spacing and punctuation
    are ignored.
    """
    if not any(_is_accented(c) for c in accented) or any(_is_accented(c) for c in other):
        return False
    pattern = "".join(r"[^\W_]{0,2}" if _is_accented(c) else re.escape(c)
                      for c in accented.casefold() if c.isalnum())
    return re.fullmatch(pattern, "".join(c for c in other.casefold() if c.isalnum())) is not None


def resolve_label(candidates, readings, minicpm):
    """(text, review) for a label no two first readers agreed on.

    `candidates` are Paddle's, docTR's and qwen's readings, in that order,
    for those that found the label. `readings`
    are the plain OCRs' (name, text, confidence), most trusted first:
    Tesseract, EasyOCR, TrOCR. They count only at ARBITER_MIN_CONFIDENCE, and
    minicpm, which fails the way qwen does, never outvotes them. Settled, in
    this order:
    - A plain OCR matches a candidate and no other arbiter backs another one.
    - Two arbiters match the same candidate.
    - No plain OCR has a sure reading and minicpm matches a candidate.
    - Two arbiters read the same near-miss of every candidate.
    Anything else goes to review with, in this order, the most trusted plain
    OCR's match, a very sure plain-OCR near-miss, minicpm's match, a minicpm
    near-miss, or the first candidate.

    Whichever is picked, an arbiter's reading that is the same name with its
    accents kept takes its place, as where qwen and Paddle agree.
    """
    plain = [{"name": name, "text": text, "confidence": confidence}
             for name, text, confidence in readings if text and confidence >= ARBITER_MIN_CONFIDENCE]
    text, review = _pick_label(candidates, plain, minicpm)
    for read in [arbiter["text"] for arbiter in plain] + [minicpm]:
        if read and accent_variant(read, text):
            return read, review
    return text, review


def _pick_label(candidates, plain, minicpm):
    """resolve_label's choice before accents; `plain` is the sure plain-OCR readings."""
    def matching(read):
        return next((t for t in candidates if read and normalise_text(t) == normalise_text(read)), None)

    def near_every_candidate(read):
        return bool(read) and any(c.isalnum() for c in read) and all(close_reading(read, t) for t in candidates)

    by_plain = [(arbiter, matching(arbiter["text"])) for arbiter in plain]
    by_minicpm = matching(minicpm)
    for arbiter, match in by_plain:
        if match is not None and by_minicpm in (None, match) \
                and all(other in (None, match) for other_plain, other in by_plain if other_plain is not arbiter):
            return match, False

    arbiter_matches = [match for _, match in by_plain if match is not None]
    if by_minicpm is not None:
        arbiter_matches.append(by_minicpm)
    for candidate in candidates:
        if sum(match == candidate for match in arbiter_matches) >= 2:
            return candidate, False

    if not plain and by_minicpm is not None:
        return by_minicpm, False

    # An uncased arbiter's reading can back a near-miss but is never written
    # out itself: two readings that agree give the cased one's spelling.
    near_reads = [arbiter for arbiter in plain if near_every_candidate(arbiter["text"])]
    if near_every_candidate(minicpm):
        near_reads.append({"name": "minicpm", "text": minicpm})
    seen = {}
    for arbiter in near_reads:
        normalised = normalise_text(arbiter["text"])
        if normalised in seen:
            pair = (seen[normalised], arbiter)
            return next(a for a in pair if a["name"] not in UNCASED_ARBITERS)["text"], False
        seen[normalised] = arbiter

    for _, match in by_plain:
        if match is not None:
            return match, True
    for arbiter in plain:
        if arbiter["name"] not in UNCASED_ARBITERS and arbiter["confidence"] >= ARBITER_REPLACE_CONFIDENCE \
                and near_every_candidate(arbiter["text"]):
            return arbiter["text"], True
    if by_minicpm is not None:
        return by_minicpm, True
    if near_every_candidate(minicpm):
        return minicpm, True
    return candidates[0], True


def pixels_under(mask, box):
    height, width = mask.shape
    x1, y1 = max(0, int(box[0]) - LABEL_GLYPH_PAD), max(0, int(box[1]) - LABEL_GLYPH_PAD)
    x2 = min(width, int(math.ceil(box[2])) + LABEL_GLYPH_PAD)
    y2 = min(height, int(math.ceil(box[3])) + LABEL_GLYPH_PAD)
    if x2 <= x1 or y2 <= y1:
        return 0
    return int(np.count_nonzero(mask[y1:y2, x1:x2]))


def read_map_labels(bgr, pid, glyph_mask=None, white_mask=None):
    """[{"text", "box", "review", "alt"}] for one map, cross-checked as described above.

    `glyph_mask` is find_text_lines' glyph mask for the map, which qwen's
    readings are checked against; `white_mask` the white mask it was taken
    from, which Paddle's and docTR's are. Without them no label is checked
    against the pixels.
    """
    readers = {"paddle": paddle_labels, "doctr": doctr_labels, "qwen": qwen_labels}
    found = {}
    for source, read in readers.items():
        try:
            found[source] = read(bgr)
        except Exception as e:
            print(f"  WARNING: {pid}: {SOURCE_NAMES[source]} failed ({e}); the other readers go unchecked by it.")
            found[source] = []

    names, numbers = {s: [] for s in readers}, {s: [] for s in readers}
    no_text = 0
    for label in [l for labels in found.values() for l in labels]:
        for part in split_attached_number(label):
            if _is_watermark(part["text"]) or not any(c.isalnum() for c in part["text"]):
                continue
            mask = glyph_mask if part["source"] == "qwen" else white_mask
            if mask is not None and pixels_under(mask, part["box"]) < LABEL_MIN_GLYPH_PIXELS:
                print(f"  {pid}: {SOURCE_NAMES[part['source']]} read {ascii(part['text'])} at "
                      f"{tuple(int(v) for v in part['box'])}, where the map has no text - dropped.")
                no_text += 1
                continue
            kind = numbers if part["text"].isdigit() else names
            kind[part["source"]].append(part)

    clusters = [{s: [l for l in g if l["source"] == s] for s in readers}
                for g in group_names([l for s in readers for l in names[s]])]
    clusters += match_numbers([numbers[s] for s in readers], list(readers))

    binary = np.asarray(gimp_contrast(Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)),
                                      contrast=1.0, pivot=200), dtype=np.uint8)
    results = []
    counts = {"agreed": 0, "majority": 0, "overturned": 0, "settled": 0, "confirmed": 0, "review": 0,
              "dropped": 0, "unconfirmed": 0}
    minicpm_used = False
    for cluster in clusters:
        # Paddle's order, then docTR's, then qwen's: the first two read exact
        # corners that follow rotated text, qwen a loose upright box.
        texts = {s: reading_order_text(cluster[s]) for s in readers if cluster[s]}
        box = _union_box([l for s in readers for l in cluster[s]])
        points = np.concatenate([l["points"] for l in next(cluster[s] for s in readers if cluster[s])])
        votes = {}
        for source, text in texts.items():
            votes.setdefault(normalise_text(text), []).append(source)
        majority = max(votes.values(), key=len)
        # Same words from every reader that found the label, and at least two
        # of them; keep whichever kept its accents.
        if len(votes) == 1 and len(majority) >= 2:
            text = max((texts[s] for s in majority), key=lambda t: sum(ord(c) > 127 for c in t))
            results.append({"text": text, "box": box, "review": False, "alt": ""})
            counts["agreed"] += 1
            continue

        candidates = list(texts.values())
        canvas = arbiter_crop(binary, points)
        if canvas is None:
            print(f"  {pid}: {ascii(candidates)} sits on a blank region of the map - dropped.")
            counts["dropped"] += 1
            continue
        digits = all(t.isdigit() for t in candidates)
        readings = [("Tesseract", *tesseract_reading(canvas, digits=digits)),
                    ("EasyOCR", *easyocr_reading(canvas, digits=digits)),
                    ("TrOCR", *trocr_reading(canvas, digits=digits))]
        minicpm = minicpm_reading(canvas)
        minicpm_used = True

        if len(majority) >= 2:
            # Two first readers agree and the third reads something else. The
            # two stand unless two sure plain OCRs both read the dissent.
            winner = max((s for s in majority), key=lambda s: sum(ord(c) > 127 for c in texts[s]))
            text, review = texts[winner], False
            dissent = [texts[s] for s in texts if s not in majority]
            backing = [t for _, t, c in readings
                       if t and c >= ARBITER_MIN_CONFIDENCE and normalise_text(t) == normalise_text(dissent[0])]
            if len(backing) >= 2:
                text, review = dissent[0], True
                counts["overturned"] += 1
                print(f"  {pid}: {ascii(texts[winner])} from two readers, but two arbiters read "
                      f"{ascii(dissent[0])} - kept for review.")
            else:
                counts["majority"] += 1
        else:
            text, review = resolve_label(candidates, readings, minicpm)
            if review and list(texts) == ["doctr"]:
                # docTR alone reads odd letters off bits of track ("a", "g");
                # a label nothing else found and no arbiter backs is dropped.
                print(f"  {pid}: only docTR read {ascii(texts['doctr'])} and no arbiter backs it - dropped.")
                counts["unconfirmed"] += 1
                continue
            if not review:
                counts["settled" if len(candidates) >= 2 else "confirmed"] += 1
            else:
                print(f"  {pid}: label {ascii(text)} unresolved ("
                      + "".join(f"{SOURCE_NAMES[s]} {ascii(texts.get(s))}, " for s in readers)
                      + "".join(f"{name} {ascii(t)} at {c:.0f}, " for name, t, c in readings)
                      + f"minicpm {ascii(minicpm)}) - kept for review.")
                counts["review"] += 1
        # The alternatives are the other candidates, plus, for a label left
        # for review, whatever else the arbiters read.
        alts = []
        for t in list(texts.values()) + ([t for _, t, _ in readings] + [minicpm] if review else []):
            if t and normalise_text(t) != normalise_text(text)                     and all(normalise_text(t) != normalise_text(a) for a in alts):
                alts.append(t)
        results.append({"text": text, "box": box, "review": review, "alt": " / ".join(alts)})

    if minicpm_used:
        chat(model=ARBITER_MODEL, messages=[], keep_alive=0)
    print(f"  {pid}: {len(results)} labels - {counts['agreed']} agreed, {counts['majority']} taken two readers "
          f"to one ({counts['overturned']} overturned for review), {counts['settled']} settled by the arbiters, "
          f"{counts['confirmed']} single readings confirmed, {counts['review']} for review, "
          f"{counts['dropped']} dropped as blank, {counts['unconfirmed']} unconfirmed docTR readings dropped, "
          f"{no_text} readings dropped for having no text under them.")
    return results


def unload_ocr_models():
    global _paddle, _easyocr, _trocr, _doctr
    for model in OCR_MODELS:
        chat(model=model, messages=[], keep_alive=0)
    if _paddle is not None:
        _paddle = None
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    _easyocr = None
    _trocr = None
    _doctr = None


# ---------------------------------------------------------------------------
# Direction, read against the track itself.
#
# The centroid reading (arrow_direction above) fails whenever the arrow sits on
# a straight that runs past the centre of the layout - Jacarepagua's pit
# straight, Miami's, Baku's - because the cross product of two nearly parallel
# vectors has no reliable sign. This reading needs no centre: it finds the
# nearest point of the band's outline to the arrow and asks whether the arrow
# runs with or against the outline's traversal. OpenCV traverses an outer
# contour one way round and a hole's contour the other, so a hole's answer is
# flipped, and for a simple closed loop every hole is circled the same way as
# the outside, which makes the two agree. The last step - mapping the outer
# contour's oriented area onto Clockwise/Anticlockwise - is fixed empirically:
# checked against the arrow on all 157 maps, it agrees everywhere the reading
# is usable except Jacarepagua, where it is right and the old reading was not.
TANGENT_MAX_DISTANCE_FRACTION = 0.03
MIN_TANGENT_DISTANCE = 5.0        # an arrow drawn on top of the band has no side
TANGENT_HALF_SPAN = 15
MIN_TANGENT_ALIGNMENT = 0.3
RING_CLOSED_RATIO = 1.3
RING_INTACT_FRACTION = 0.8        # of the untouched mask's enclosed area


def enclosed_area(band):
    """Area inside the band's largest outer contour - the whole infield for a closed ring."""
    contours, _ = cv2.findContours(band, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return max((cv2.contourArea(c) for c in contours), default=0.0)


def band_geometry(band, reference_area=None):
    """Densified outlines of the band with their nesting, plus the outer orientation.

    `reference_area` is the enclosed area of the band traced off the untouched
    mask; if cleaning the mask has cost more than a fifth of it, the ring was
    severed somewhere and the reading is marked unusable.
    """
    contours, hierarchy = cv2.findContours(band, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None
    hierarchy = hierarchy[0]
    outlines = []
    outer_sign = 0.0
    largest = 0.0
    for i, contour in enumerate(contours):
        area = cv2.contourArea(contour)
        if area < 50:
            continue
        is_outer = hierarchy[i][3] == -1
        if is_outer and area > largest:
            largest = area
            outer_sign = float(np.sign(cv2.contourArea(contour, oriented=True)))
        outlines.append((_densify(contour.reshape(-1, 2).astype(np.float64)), is_outer))
    if outer_sign == 0.0:
        return None
    # A closed ring's outer contour encloses the whole infield, many times the
    # band's own area; a severed ring's snakes back along the inside edge and
    # encloses little more than the band itself. The inside edge of a severed
    # ring is traversed the wrong way round, so the reading below cannot be
    # trusted on one - the flag is carried out so the caller can say so.
    band_area = float(np.count_nonzero(band))
    closed = largest >= RING_CLOSED_RATIO * band_area
    if reference_area:
        closed = closed and largest >= RING_INTACT_FRACTION * reference_area
    return {"outlines": outlines, "outer_sign": outer_sign, "closed": closed}


def tangent_direction(geometry, base, tip, scale):
    """Which way round the lap an arrow points, read against the outline beside it."""
    if geometry is None:
        return None
    mid = np.array([(base[0] + tip[0]) / 2.0, (base[1] + tip[1]) / 2.0])
    axis = np.array([tip[0] - base[0], tip[1] - base[1]], dtype=np.float64)
    if np.linalg.norm(axis) == 0:
        return None
    axis /= np.linalg.norm(axis)
    best = None
    for pts, is_outer in geometry["outlines"]:
        d = np.hypot(pts[:, 0] - mid[0], pts[:, 1] - mid[1])
        i = int(np.argmin(d))
        if best is None or d[i] < best[0]:
            best = (float(d[i]), pts, i, is_outer)
    distance, pts, i, is_outer = best
    n = len(pts)
    k = min(TANGENT_HALF_SPAN, (n - 1) // 2)
    tangent = pts[(i + k) % n] - pts[(i - k) % n]
    if np.linalg.norm(tangent) == 0:
        return None
    tangent /= np.linalg.norm(tangent)
    alignment = float(tangent @ axis)
    along = alignment * (1.0 if is_outer else -1.0)
    lap = geometry["outer_sign"] if along > 0 else -geometry["outer_sign"]
    return {"direction": "Clockwise" if lap > 0 else "Anticlockwise",
            "alignment": alignment,
            "distance": distance,
            "usable": (geometry["closed"]
                       and abs(alignment) >= MIN_TANGENT_ALIGNMENT
                       and MIN_TANGENT_DISTANCE <= distance <= TANGENT_MAX_DISTANCE_FRACTION * scale)}


# ---------------------------------------------------------------------------
# The start/finish bar, drawn across the band through the touch point.
#
# The bar is drawn in its own colour rather than the track's white. Drawn white
# it is invisible: it sits on top of a white stroke, and the only thing marking
# the spot is then the label. The overhang is what makes it read as crossing the
# track rather than being part of it, so it is sized off the image instead of the
# stroke - a few pixels either side of a 9px stroke disappears at a glance.
START_FINISH_COLOUR = "#FFD200"
START_FINISH_OVERHANG_FRACTION = 0.010
MIN_START_FINISH_OVERHANG = 7.0
TANGENT_SPAN_FRACTION = 0.025
MIN_TANGENT_SPAN = 18.0
CROSS_SCAN_FRACTION = 0.05


def start_finish_svg(touch, band, geometry, flag_box, orig_w, orig_h, offset_x, offset_y,
                     colour=START_FINISH_COLOUR, stroke_width=3.0):
    """The start/finish bar and its label, drawn across the band at the touch point.

    The touch point is on the track's edge line, exactly where the flag's
    leader meets it. The bar goes through that point: it lies along the
    normal to the outline there (the tangent comes off the band's densified
    outline, walked `span` pixels either side so the leader's stump cannot
    tilt it) and runs from an overhang on the flag's side, across the band,
    to an overhang on the far side. The band's width is read off it directly
    by walking the normal until the band ends, so the bar crosses the whole
    stroke and nothing more.
    """
    scale = max(orig_w, orig_h)
    span = max(MIN_TANGENT_SPAN, TANGENT_SPAN_FRACTION * scale)
    contours = [pts.reshape(-1, 1, 2).astype(np.int32) for pts, _ in geometry["outlines"]]
    tangent = _local_tangent(touch, contours, span)
    if tangent is None:
        return []
    _, (tx, ty) = tangent
    nx, ny = -ty, tx

    # Point the normal into the band: whichever way from the touch point is
    # white three pixels on is the way across.
    def is_band(x, y):
        xi, yi = int(round(x)), int(round(y))
        return 0 <= xi < orig_w and 0 <= yi < orig_h and band[yi, xi] > 0

    qx, qy = float(touch[0]), float(touch[1])
    if not is_band(qx + nx * 3, qy + ny * 3) and is_band(qx - nx * 3, qy - ny * 3):
        nx, ny = -nx, -ny

    max_scan = max(12.0, CROSS_SCAN_FRACTION * scale)
    width, t = 0.0, 1.0
    while t <= max_scan and is_band(qx + nx * t, qy + ny * t):
        width = t
        t += 0.5
    if width <= 0.0:
        return []

    overhang = max(MIN_START_FINISH_OVERHANG, START_FINISH_OVERHANG_FRACTION * scale)
    x1 = qx - nx * overhang + offset_x
    y1 = qy - ny * overhang + offset_y
    x2 = qx + nx * (width + overhang) + offset_x
    y2 = qy + ny * (width + overhang) + offset_y

    # The label goes on the flag's side of the track.
    fx, fy = (flag_box[0] + flag_box[2]) / 2.0, (flag_box[1] + flag_box[3]) / 2.0
    on_near_side = (nx * (fx - qx) + ny * (fy - qy)) < 0
    gap = 11.0
    if on_near_side:
        label_x, label_y = qx - nx * (overhang + gap) + offset_x, qy - ny * (overhang + gap) + offset_y
    else:
        label_x, label_y = qx + nx * (width + overhang + gap) + offset_x, qy + ny * (width + overhang + gap) + offset_y

    return [
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{colour}" stroke-width="{stroke_width}" stroke-linecap="butt" />',
        f'<g fill="{colour}" font-family="sans-serif" font-size="9" font-weight="bold" '
        'paint-order="stroke fill" stroke="#111111" stroke-width="3px" stroke-linejoin="round">'
        f'<text x="{label_x:.1f}" y="{label_y + 3.0:.1f}" text-anchor="middle">'
        'START/FINISH</text></g>',
    ]


AVUS_SVG = """<svg width="1020" height="500" viewBox="0 0 1020 454" xmlns="http://www.w3.org/2000/svg" style="background: #111;">
<polyline points="766,32 770,36 769,37 768,37 767,38 766,38 765,39 764,39 763,40 761,40 760,41 759,41 758,42 757,42 756,43 754,43 753,44 752,44 751,45 750,45 749,46 748,46 747,47 745,47 744,48 743,48 742,49 741,49 740,50 739,50 738,51 736,51 735,52 734,52 733,53 732,53 731,54 729,54 728,55 727,55 726,56 725,56 724,57 722,57 721,58 720,58 719,59 718,59 717,60 716,60 715,61 713,61 712,62 711,62 710,63 709,63 708,64 707,64 706,65 704,65 703,66 702,66 701,67 699,67 698,68 697,68 696,69 695,69 694,70 693,70 692,71 690,71 689,72 688,72 687,73 686,73 685,74 683,74 682,75 681,75 680,76 679,76 678,77 677,77 676,78 674,78 673,79 672,79 671,80 670,80 669,81 667,81 666,82 665,82 664,83 663,83 662,84 660,84 659,85 658,85 657,86 656,86 655,87 654,87 653,88 651,88 650,89 649,89 648,90 647,90 646,91 644,91 643,92 642,92 641,93 640,93 639,94 637,94 636,95 635,95 634,96 633,96 632,97 631,97 630,98 628,98 627,99 626,99 625,100 624,100 623,101 621,101 620,102 619,102 618,103 616,103 615,104 614,104 613,105 612,105 611,106 610,106 609,107 607,107 606,108 605,108 604,109 603,109 602,110 601,110 600,111 598,111 597,112 596,112 595,113 594,113 593,114 591,114 590,115 589,115 588,116 587,116 586,117 584,117 583,118 582,118 581,119 580,119 579,120 578,120 577,121 575,121 574,122 573,122 572,123 570,123 568,125 566,125 565,126 564,126 563,127 561,127 560,128 559,128 558,129 557,129 556,130 554,130 553,131 552,131 551,132 550,132 549,133 548,133 547,134 546,134 545,135 543,135 542,136 540,136 539,137 538,137 537,138 536,138 535,139 534,139 533,140 531,140 530,141 529,141 528,142 527,142 526,143 525,143 524,144 522,144 521,145 520,145 519,146 518,146 517,147 515,147 514,148 513,148 512,149 511,149 510,150 509,150 508,151 506,151 505,152 504,152 503,153 502,153 501,154 499,154 498,155 497,155 496,156 495,156 494,157 492,157 491,158 490,158 489,159 488,159 487,160 486,160 485,161 483,161 482,162 481,162 480,163 479,163 478,164 476,164 475,165 474,165 473,166 472,166 471,167 469,167 468,168 467,168 466,169 465,169 464,170 463,170 462,171 460,171 459,172 458,172 457,173 456,173 455,174 454,174 453,175 451,175 450,176 449,176 448,177 447,177 446,178 444,178 443,179 442,179 441,180 440,180 439,181 438,181 437,182 435,182 434,183 433,183 432,184 431,184 430,185 429,185 428,186 426,186 425,187 424,187 423,188 422,188 421,189 419,189 418,190 417,190 416,191 415,191 414,192 413,192 412,193 410,193 409,194 408,194 407,195 406,195 405,196 404,196 403,197 402,197 401,198 399,198 398,199 397,199 396,200 395,200 394,201 392,201 391,202 390,202 389,203 388,203 387,204 385,204 384,205 383,205 382,206 381,206 380,207 379,207 378,208 377,208 376,209 374,209 373,210 372,210 371,211 369,211 368,212 367,212 366,213 365,213 364,214 363,214 362,215 361,215 360,216 358,216 357,217 356,217 355,218 354,218 353,219 351,219 350,220 349,220 348,221 347,221 346,222 345,222 344,223 342,223 341,224 340,224 339,225 338,225 337,226 335,226 334,227 333,227 332,228 331,228 330,229 329,229 328,230 327,230 326,231 324,231 323,232 322,232 321,233 320,233 319,234 318,234 317,235 315,235 314,236 313,236 312,237 311,237 310,238 308,238 307,239 306,239 305,240 304,240 303,241 302,241 301,242 299,242 298,243 297,243 296,244 295,244 294,245 293,245 292,246 290,246 289,247 288,247 287,248 286,248 285,249 284,249 283,250 281,250 280,251 279,251 278,252 277,252 276,253 275,253 274,254 272,254 271,255 270,255 269,256 268,256 267,257 266,257 265,258 263,258 262,259 261,259 260,260 259,260 258,261 256,261 255,262 254,262 253,263 252,263 251,264 250,264 249,265 247,265 246,266 245,266 244,267 243,267 242,268 241,268 240,269 238,269 237,270 236,270 235,271 234,271 233,272 231,272 230,273 229,273 228,274 227,274 226,275 225,275 224,276 223,276 222,277 220,277 219,278 218,278 217,279 216,279 215,280 214,280 213,281 212,281 211,282 210,282 209,283 208,283 207,284 206,284 205,285 204,285 203,286 202,286 201,287 200,287 199,288 198,288 197,289 196,289 195,290 194,290 193,291 192,291 191,292 189,292 188,293 187,293 186,294 185,294 184,295 183,295 182,296 181,296 180,297 179,297 178,298 177,298 176,299 175,299 174,300 173,300 172,301 171,301 170,302 169,302 168,303 167,303 166,304 165,304 164,305 163,305 162,306 161,306 160,307 159,307 158,308 157,308 156,309 154,309 153,310 152,310 151,311 150,311 149,312 148,312 147,313 146,313 145,314 144,314 143,315 142,315 141,316 140,316 139,317 138,317 137,318 136,318 135,319 134,319 133,320 132,320 131,321 130,321 129,322 128,322 127,323 126,323 125,324 123,324 122,325 121,325 120,326 119,326 118,327 117,327 116,328 115,328 114,329 113,329 112,330 111,330 110,331 109,331 108,332 107,332 106,333 105,333 104,334 103,334 102,335 101,335 100,336 99,336 98,337 97,337 96,338 95,338 94,339 93,339 92,340 91,340 90,341 89,341 88,342 87,342 86,343 84,343 83,344 82,344 81,345 80,345 79,346 78,346 77,347 76,347 75,348 74,348 73,349 72,349 71,350 70,350 69,351 68,351 67,352 66,352 65,353 64,353 63,354 62,354 61,355 60,355 59,356 58,356 57,357 55,357 54,358 53,358 52,359 50,359 49,360 47,360 46,361 44,361 43,362 41,362 40,363 37,363 36,364 34,364 33,365 32,365 31,366 29,366 28,367 26,367 24,369 23,369 22,370 21,370 19,372 19,373 18,374 18,381 19,382 19,383 20,384 20,385 21,385 22,386 24,386 25,387 38,387 39,386 42,386 43,385 44,385 45,384 46,384 47,383 48,383 49,382 50,382 51,381 52,381 53,380 54,380 55,379 56,379 57,378 58,378 59,377 60,377 61,376 62,376 63,375 65,375 66,374 67,374 68,373 69,373 70,372 71,372 72,371 73,371 74,370 75,370 76,369 77,369 78,368 79,368 80,367 81,367 82,366 83,366 84,365 85,365 86,364 87,364 88,363 89,363 90,362 91,362 92,361 93,361 94,360 95,360 96,359 97,359 98,358 99,358 100,357 101,357 102,356 103,356 104,355 106,355 107,354 108,354 109,353 110,353 111,352 112,352 113,351 114,351 115,350 116,350 117,349 118,349 119,348 120,348 121,347 122,347 123,346 124,346 125,345 126,345 127,344 128,344 129,343 130,343 131,342 132,342 133,341 134,341 135,340 136,340 137,339 138,339 139,338 140,338 141,337 142,337 143,336 144,336 145,335 147,335 148,334 149,334 150,333 151,333 152,332 153,332 154,331 155,331 156,330 157,330 158,329 159,329 160,328 161,328 162,327 163,327 164,326 165,326 166,325 167,325 168,324 169,324 170,323 171,323 172,322 173,322 174,321 175,321 176,320 177,320 178,319 179,319 180,318 181,318 182,317 184,317 186,315 188,315 189,314 190,314 191,313 192,313 193,312 194,312 195,311 196,311 197,310 198,310 199,309 200,309 201,308 202,308 203,307 204,307 205,306 206,306 207,305 208,305 209,304 210,304 211,303 212,303 213,302 214,302 215,301 216,301 217,300 218,300 219,299 220,299 221,298 222,298 223,297 224,297 225,296 226,296 227,295 228,295 229,294 230,294 231,293 233,293 234,292 235,292 236,291 237,291 238,290 239,290 240,289 242,289 243,288 244,288 245,287 246,287 247,286 249,286 250,285 251,285 252,284 253,284 254,283 255,283 256,282 258,282 259,281 260,281 261,280 262,280 263,279 264,279 265,278 267,278 268,277 269,277 270,276 271,276 272,275 274,275 275,274 276,274 277,273 278,273 279,272 280,272 281,271 283,271 284,270 285,270 286,269 287,269 288,268 290,268 291,267 292,267 293,266 294,266 295,265 297,265 298,264 299,264 300,263 301,263 302,262 304,262 305,261 306,261 307,260 308,260 309,259 310,259 311,258 313,258 314,257 315,257 316,256 317,256 318,255 320,255 321,254 322,254 323,253 324,253 325,252 327,252 328,251 329,251 330,250 331,250 332,249 333,249 334,248 336,248 337,247 338,247 339,246 340,246 341,245 343,245 344,244 345,244 346,243 347,243 348,242 349,242 350,241 352,241 353,240 354,240 355,239 356,239 357,238 358,238 359,237 361,237 362,236 363,236 364,235 366,235 367,234 368,234 369,233 370,233 371,232 372,232 373,231 375,231 376,230 377,230 378,229 379,229 380,228 381,228 382,227 384,227 385,226 386,226 387,225 388,225 389,224 391,224 392,223 393,223 394,222 395,222 396,221 397,221 398,220 400,220 401,219 402,219 403,218 404,218 405,217 406,217 407,216 409,216 410,215 411,215 412,214 413,214 414,213 416,213 417,212 418,212 419,211 420,211 421,210 423,210 424,209 425,209 426,208 427,208 428,207 429,207 430,206 432,206 433,205 434,205 435,204 436,204 437,203 439,203 440,202 441,202 442,201 443,201 444,200 445,200 446,199 448,199 449,198 450,198 451,197 452,197 453,196 455,196 456,195 457,195 458,194 459,194 460,193 462,193 463,192 464,192 465,191 466,191 467,190 468,190 469,189 471,189 472,188 473,188 474,187 475,187 476,186 477,186 478,185 480,185 481,184 482,184 483,183 484,183 485,182 487,182 488,181 489,181 490,180 491,180 492,179 494,179 495,178 496,178 497,177 498,177 499,176 500,176 501,175 503,175 504,174 505,174 506,173 507,173 508,172 510,172 511,171 512,171 513,170 515,170 516,169 517,169 518,168 519,168 520,167 521,167 522,166 524,166 525,165 526,165 527,164 529,164 530,163 531,163 532,162 533,162 534,161 536,161 537,160 538,160 539,159 540,159 541,158 543,158 544,157 545,157 546,156 547,156 548,155 550,155 551,154 552,154 553,153 554,153 555,152 556,152 557,151 558,151 559,150 561,150 562,149 563,149 564,148 566,148 567,147 568,147 569,146 570,146 571,145 572,145 573,144 575,144 576,143 577,143 578,142 579,142 580,141 582,141 583,140 584,140 585,139 586,139 587,138 588,138 589,137 591,137 592,136 593,136 594,135 595,135 596,134 597,134 598,133 600,133 601,132 602,132 603,131 605,131 606,130 607,130 608,129 609,129 610,128 611,128 612,127 614,127 615,126 616,126 617,125 618,125 619,124 621,124 622,123 623,123 624,122 625,122 626,121 628,121 629,120 630,120 631,119 632,119 633,118 635,118 636,117 637,117 638,116 639,116 640,115 642,115 643,114 644,114 645,113 646,113 647,112 648,112 649,111 651,111 652,110 653,110 654,109 655,109 656,108 658,108 659,107 660,107 661,106 662,106 663,105 665,105 666,104 667,104 668,103 669,103 670,102 672,102 673,101 674,101 675,100 676,100 677,99 678,99 679,98 681,98 682,97 683,97 684,96 686,96 687,95 688,95 689,94 690,94 691,93 692,93 693,92 694,92 695,91 697,91 698,90 699,90 700,89 701,89 702,88 704,88 705,87 706,87 707,86 709,86 710,85 711,85 712,84 713,84 714,83 715,83 716,82 718,82 719,81 720,81 721,80 722,80 723,79 725,79 726,78 727,78 728,77 729,77 730,76 732,76 733,75 734,75 735,74 736,74 737,73 739,73 740,72 741,72 742,71 743,71 744,70 745,70 746,69 748,69 749,68 750,68 751,67 752,67 753,66 755,66 756,65 757,65 758,64 759,64 760,63 761,63 762,62 764,62 765,61 766,61 767,60 769,60 770,59 771,59 772,58 773,58 774,57 775,57 776,56 779,56 780,55 783,55 784,54 787,54 788,53 791,53 792,52 797,52 798,53 799,52 804,52 805,53 809,53 810,54 814,54 815,55 818,55 819,56 821,56 822,57 824,57 825,58 828,58 829,59 831,59 832,60 834,60 835,61 837,61 838,62 840,62 841,63 843,63 844,64 847,64 848,65 850,65 851,66 855,66 856,67 869,67 870,66 872,66 875,63 876,63 878,61 878,60 879,59 879,58 881,56 881,53 882,52 882,40 881,39 881,38 880,37 880,36 879,35 879,34 878,33 878,32 872,26 871,26 868,23 867,23 866,22 864,22 863,21 860,21 859,20 833,20 832,21 826,21 825,22 820,22 819,23 814,23 813,24 810,24 809,25 806,25 805,26 803,26 802,27 798,27 797,28 795,28 794,29 792,29 791,30 788,30 787,31 785,31 784,32 783,32 782,33 780,33 779,34 776,34 775,35 773,35 772,36" fill="none" stroke="white" stroke-width="9" stroke-linejoin="round" stroke-linecap="round"></polyline>
<polyline points="766,32 770,36 769,37 768,37 767,38 766,38 765,39 764,39 763,40 761,40 760,41 759,41 758,42 757,42 756,43 754,43 753,44 752,44 751,45 750,45 749,46 748,46 747,47 745,47 744,48 743,48 742,49 741,49 740,50 739,50 738,51 736,51 735,52 734,52 733,53 732,53 731,54 729,54 728,55 727,55 726,56 725,56 724,57 722,57 721,58 720,58 719,59 718,59 717,60 716,60 715,61 713,61 712,62 711,62 710,63 709,63 708,64 707,64 706,65 704,65 703,66 702,66 701,67 699,67 698,68 697,68 696,69 695,69 694,70 693,70 692,71 690,71 689,72 688,72 687,73 686,73 685,74 683,74 682,75 681,75 680,76 679,76 678,77 677,77 676,78 674,78 673,79 672,79 671,80 670,80 669,81 667,81 666,82 665,82 664,83 663,83 662,84 660,84 659,85 658,85 657,86 656,86 655,87 654,87 653,88 651,88 650,89 649,89 648,90 647,90 646,91 644,91 643,92 642,92 641,93 640,93 639,94 637,94 636,95 635,95 634,96 633,96 632,97 631,97 630,98 628,98 627,99 626,99 625,100 624,100 623,101 621,101 620,102 619,102 618,103 616,103 615,104 614,104 613,105 612,105 611,106 610,106 609,107 607,107 606,108 605,108 604,109 603,109 602,110 601,110 600,111 598,111 597,112 596,112 595,113 594,113 593,114 591,114 590,115 589,115 588,116 587,116 586,117 584,117 583,118 582,118 581,119 580,119 579,120 578,120 577,121 575,121 574,122 573,122 572,123 570,123 568,125 566,125 565,126 564,126 563,127 561,127 560,128 559,128 558,129 557,129 556,130 554,130 553,131 552,131 551,132 550,132 549,133 548,133 547,134 546,134 545,135 543,135 542,136 540,136 539,137 538,137 537,138 536,138 535,139 534,139 533,140 531,140 530,141 529,141 528,142 527,142 526,143 525,143 524,144 522,144 521,145 520,145 519,146 518,146 517,147 515,147 514,148 513,148 512,149 511,149 510,150 509,150 508,151 506,151 505,152 504,152 503,153 502,153 501,154 499,154 498,155 497,155 496,156 495,156 494,157 492,157 491,158 490,158 489,159 488,159 487,160 486,160 485,161 483,161 482,162 481,162 480,163 479,163 478,164 476,164 475,165 474,165 473,166 472,166 471,167 469,167 468,168 467,168 466,169 465,169 464,170 463,170 462,171 460,171 459,172 458,172 457,173 456,173 455,174 454,174 453,175 451,175 450,176 449,176 448,177 447,177 446,178 444,178 443,179 442,179 441,180 440,180 439,181 438,181 437,182 435,182 434,183 433,183 432,184 431,184 430,185 429,185 428,186 426,186 425,187 424,187 423,188 422,188 421,189 419,189 418,190 417,190 416,191 415,191 414,192 413,192 412,193 410,193 409,194 408,194 407,195 406,195 405,196 404,196 403,197 402,197 401,198 399,198 398,199 397,199 396,200 395,200 394,201 392,201 391,202 390,202 389,203 388,203 387,204 385,204 384,205 383,205 382,206 381,206 380,207 379,207 378,208 377,208 376,209 374,209 373,210 372,210 371,211 369,211 368,212 367,212 366,213 365,213 364,214 363,214 362,215 361,215 360,216 358,216 357,217 356,217 355,218 354,218 353,219 351,219 350,220 349,220 348,221 347,221 346,222 345,222 344,223 342,223 341,224 340,224 339,225 338,225 337,226 335,226 334,227 333,227 332,228 331,228 330,229 329,229 328,230 327,230 326,231 324,231 323,232 322,232 321,233 320,233 319,234 318,234 317,235 315,235 314,236 313,236 312,237 311,237 310,238 308,238 307,239 306,239 305,240 304,240 303,241 302,241 301,242 299,242 298,243 297,243 296,244 295,244 294,245 293,245 292,246 290,246 289,247 288,247 287,248 286,248 285,249 284,249 283,250 281,250 280,251 279,251 278,252 277,252 276,253 275,253 274,254 272,254 271,255 270,255 269,256 268,256 267,257 266,257 265,258 263,258 262,259 261,259 260,260 259,260 258,261 256,261 255,262 254,262 253,263 252,263 251,264 250,264 249,265 247,265 246,266 245,266 244,267 243,267 242,268 241,268 240,269 238,269 237,270 236,270 235,271 234,271 233,272 231,272 230,273 229,273 228,274 227,274 226,275 225,275 224,276 223,276 222,277 220,277 219,278 218,278 217,279 216,279 215,280 214,280 213,281 212,281 211,282 210,282 209,283 208,283 207,284 206,284 205,285 204,285 203,286 202,286 201,287 200,287 199,288 198,288 197,289 196,289 195,290 194,290 193,291 192,291 191,292 189,292 188,293 187,293 186,294 185,294 184,295 183,295 182,296 181,296 180,297 179,297 178,298 177,298 176,299 175,299 174,300 173,300 172,301 171,301 170,302 169,302 168,303 167,303 166,304 165,304 164,305 163,305 162,306 161,306 160,307 159,307 158,308 157,308 156,309 154,309 153,310 152,310 151,311 150,311 149,312 148,312 147,313 146,313 145,314 144,314 143,315 142,315 141,316 140,316 139,317 138,317 137,318 136,318 135,319 134,319 133,320 132,320 131,321 130,321 129,322 128,322 127,323 126,323 125,324 123,324 122,325 121,325 120,326 119,326 118,327 117,327 116,328 115,328 114,329 113,329 112,330 111,330 110,331 109,331 108,332 107,332 106,333 105,333 104,334 103,334 102,335 101,335 100,336 99,336 98,337 97,337 96,338 95,338 94,339 93,339 92,340 91,340 90,341 89,341 88,342 87,342 86,343 84,343 83,344 82,344 81,345 80,345 79,346 78,346 77,347 76,347 75,348 74,348 73,349 72,349 71,350 70,350 69,351 68,351 67,352 66,352 65,353 64,353 63,354 62,354 61,355 60,355 59,356 58,356 57,357 55,357 54,358 53,358 52,359 50,359 49,360 47,360 46,361 44,361 43,362 41,362 40,363 37,363 36,364 34,364 33,365 32,365 31,366 29,366 28,367 26,367 24,369 23,369 22,370 21,370 19,372 19,373 18,374 18,381 19,382 19,383 20,384 20,385 21,385 22,386 24,386 25,387 38,387 39,386 42,386 43,385 44,385 45,384 46,384 47,383 48,383 49,382 50,382 51,381 52,381 53,380 54,380 55,379 56,379 57,378 58,378 59,377 60,377 61,376 62,376 63,375 65,375 66,374 67,374 68,373 69,373 70,372 71,372 72,371 73,371 74,370 75,370 76,369 77,369 78,368 79,368 80,367 81,367 82,366 83,366 84,365 85,365 86,364 87,364 88,363 89,363 90,362 91,362 92,361 93,361 94,360 95,360 96,359 97,359 98,358 99,358 100,357 101,357 102,356 103,356 104,355 106,355 107,354 108,354 109,353 110,353 111,352 112,352 113,351 114,351 115,350 116,350 117,349 118,349 119,348 120,348 121,347 122,347 123,346 124,346 125,345 126,345 127,344 128,344 129,343 130,343 131,342 132,342 133,341 134,341 135,340 136,340 137,339 138,339 139,338 140,338 141,337 142,337 143,336 144,336 145,335 147,335 148,334 149,334 150,333 151,333 152,332 153,332 154,331 155,331 156,330 157,330 158,329 159,329 160,328 161,328 162,327 163,327 164,326 165,326 166,325 167,325 168,324 169,324 170,323 171,323 172,322 173,322 174,321 175,321 176,320 177,320 178,319 179,319 180,318 181,318 182,317 184,317 186,315 188,315 189,314 190,314 191,313 192,313 193,312 194,312 195,311 196,311 197,310 198,310 199,309 200,309 201,308 202,308 203,307 204,307 205,306 206,306 207,305 208,305 209,304 210,304 211,303 212,303 213,302 214,302 215,301 216,301 217,300 218,300 219,299 220,299 221,298 222,298 223,297 224,297 225,296 226,296 227,295 228,295 229,294 230,294 231,293 233,293 234,292 235,292 236,291 237,291 238,290 239,290 240,289 242,289 243,288 244,288 245,287 246,287 247,286 249,286 250,285 251,285 252,284 253,284 254,283 255,283 256,282 258,282 259,281 260,281 261,280 262,280 263,279 264,279 265,278 267,278 268,277 269,277 270,276 271,276 272,275 274,275 275,274 276,274 277,273 278,273 279,272 280,272 281,271 283,271 284,270 285,270 286,269 287,269 288,268 290,268 291,267 292,267 293,266 294,266 295,265 297,265 298,264 299,264 300,263 301,263 302,262 304,262 305,261 306,261 307,260 308,260 309,259 310,259 311,258 313,258 314,257 315,257 316,256 317,256 318,255 320,255 321,254 322,254 323,253 324,253 325,252 327,252 328,251 329,251 330,250 331,250 332,249 333,249 334,248 336,248 337,247 338,247 339,246 340,246 341,245 343,245 344,244 345,244 346,243 347,243 348,242 349,242 350,241 352,241 353,240 354,240 355,239 356,239 357,238 358,238 359,237 361,237 362,236 363,236 364,235 366,235 367,234 368,234 369,233 370,233 371,232 372,232 373,231 375,231 376,230 377,230 378,229 379,229 380,228 381,228 382,227 384,227 385,226 386,226 387,225 388,225 389,224 391,224 392,223 393,223 394,222 395,222 396,221 397,221 398,220 400,220 401,219 402,219 403,218 404,218 405,217 406,217 407,216 409,216 410,215 411,215 412,214 413,214 414,213 416,213 417,212 418,212 419,211 420,211 421,210 423,210 424,209 425,209 426,208 427,208 428,207 429,207 430,206 432,206 433,205 434,205 435,204 436,204 437,203 439,203 440,202 441,202 442,201 443,201 444,200 445,200 446,199 448,199 449,198 450,198 451,197 452,197 453,196 455,196 456,195 457,195 458,194 459,194 460,193 462,193 463,192 464,192 465,191 466,191 467,190 468,190 469,189 471,189 472,188 473,188 474,187 475,187 476,186 477,186 478,185 480,185 481,184 482,184 483,183 484,183 485,182 487,182 488,181 489,181 490,180 491,180 492,179 494,179 495,178 496,178 497,177 498,177 499,176 500,176 501,175 503,175 504,174 505,174 506,173 507,173 508,172 510,172 511,171 512,171 513,170 515,170 516,169 517,169 518,168 519,168 520,167 521,167 522,166 524,166 525,165 526,165 527,164 529,164 530,163 531,163 532,162 533,162 534,161 536,161 537,160 538,160 539,159 540,159 541,158 543,158 544,157 545,157 546,156 547,156 548,155 550,155 551,154 552,154 553,153 554,153 555,152 556,152 557,151 558,151 559,150 561,150 562,149 563,149 564,148 566,148 567,147 568,147 569,146 570,146 571,145 572,145 573,144 575,144 576,143 577,143 578,142 579,142 580,141 582,141 583,140 584,140 585,139 586,139 587,138 588,138 589,137 591,137 592,136 593,136 594,135 595,135 596,134 597,134 598,133 600,133 601,132 602,132 603,131 605,131 606,130 607,130 608,129 609,129 610,128 611,128 612,127 614,127 615,126 616,126 617,125 618,125 619,124 621,124 622,123 623,123 624,122 625,122 626,121 628,121 629,120 630,120 631,119 632,119 633,118 635,118 636,117 637,117 638,116 639,116 640,115 642,115 643,114 644,114 645,113 646,113 647,112 648,112 649,111 651,111 652,110 653,110 654,109 655,109 656,108 658,108 659,107 660,107 661,106 662,106 663,105 665,105 666,104 667,104 668,103 669,103 670,102 672,102 673,101 674,101 675,100 676,100 677,99 678,99 679,98 681,98 682,97 683,97 684,96 686,96 687,95 688,95 689,94 690,94 691,93 692,93 693,92 694,92 695,91 697,91 698,90 699,90 700,89 701,89 702,88 704,88 705,87 706,87 707,86 709,86 710,85 711,85 712,84 713,84 714,83 715,83 716,82 718,82 719,81 720,81 721,80 722,80 723,79 725,79 726,78 727,78 728,77 729,77 730,76 732,76 733,75 734,75 735,74 736,74 737,73 739,73 740,72 741,72 742,71 743,71 744,70 745,70 746,69 748,69 749,68 750,68 751,67 752,67 753,66 755,66 756,65 757,65 758,64 759,64 760,63 761,63 762,62 764,62 765,61 766,61 767,60 769,60 770,59 771,59 772,58 773,58 774,57 775,57 776,56 779,56 780,55 783,55 784,54 787,54 788,53 791,53 792,52 797,52 798,53 799,52 804,52 805,53 809,53 810,54 814,54 815,55 818,55 819,56 821,56 822,57 824,57 825,58 828,58 829,59 831,59 832,60 834,60 835,61 837,61 838,62 840,62 841,63 843,63 844,64 847,64 848,65 850,65 851,66 855,66 856,67 869,67 870,66 872,66 875,63 876,63 878,61 878,60 879,59 879,58 881,56 881,53 882,52 882,40 881,39 881,38 880,37 880,36 879,35 879,34 878,33 878,32 872,26 871,26 868,23 867,23 866,22 864,22 863,21 860,21 859,20 833,20 832,21 826,21 825,22 820,22 819,23 814,23 813,24 810,24 809,25 806,25 805,26 803,26 802,27 798,27 797,28 795,28 794,29 792,29 791,30 788,30 787,31 785,31 784,32 783,32 782,33 780,33 779,34 776,34 775,35 773,35 772,36" fill="none" stroke="#111111" stroke-width="5" stroke-linejoin="round" stroke-linecap="round"></polyline>
<line x1="762.7" y1="29.8" x2="775.3" y2="38.2" stroke="#FFD200" stroke-width="3.0" stroke-linecap="butt" />
<g fill="#FFD200" font-family="sans-serif" font-size="9" font-weight="bold" paint-order="stroke fill" stroke="#111111" stroke-width="3px" stroke-linejoin="round"><text x="779.0" y="19.0" text-anchor="middle">START/FINISH</text></g>
<line x1="745.7" y1="21.5" x2="734.5" y2="25.9" stroke="#E10600" stroke-width="3.0" stroke-linecap="round" />
<polygon points="727.1,28.9 733.0,22.2 736.0,29.7" fill="#E10600" />
<g fill="#FFFFFF" font-family="sans-serif" font-size="12" font-weight="bold" paint-order="stroke fill" stroke="#111111" stroke-width="3px" stroke-linejoin="round">
<text x="850" y="0">Nordschleife</text>
<text x="0" y="420">Sudkehre</text>
</g>
</svg>"""


AVUS_IMAGE_URL = "https://www.statsf1.com/images/GetImage.ashx?id=piste.avus"

SVG_OFFSET_X, SVG_OFFSET_Y = 50, 25
TRACK_CONTOUR_MIN_AREA = 100
TRACK_CONTOUR_EPSILON = 0.8


def _svg_text(text):
    return html.escape(text, quote=True)


def _opposing(first, second):
    return (first is not None and second is not None
            and first["direction"] != second["direction"])


def generate_track_svg(image_path, grand_prix_dates=None, image_bytes=None):
    """(svg, TrackDirection) for one statsf1 layout map.

    `image_path` is the map's URL and is always used to identify the layout
    (it carries the piste id the override tables key on). Pass `image_bytes`
    to read a locally cached copy of the map instead of fetching it, which is
    how a regeneration run avoids hammering statsf1.
    """
    if image_path == AVUS_IMAGE_URL:
        # The AVUS map is a pair of straights with a banked loop at each end,
        # too far from every other map's shape for the tracer; hand-drawn.
        return AVUS_SVG, "Anticlockwise"

    if image_bytes is None:
        img, _ = imread_from_url(image_path)
    else:
        img = decode_layout_image(image_bytes, image_path)

    orig_h, orig_w = img.shape[:2]
    h, w = orig_h + 2 * SVG_OFFSET_Y, orig_w + 2 * SVG_OFFSET_X
    scale = max(orig_w, orig_h)
    pid = layout_id(image_path) or image_path
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    white = white_mask_of(gray)
    erase_watermark(white)
    untouched_area = enclosed_area(track_band(white))

    # 1. The flag and its leader, cut out of the mask before anything is traced.
    flag_score, flag_box = find_chequered_flag(gray)
    flag_found = flag_score >= FLAG_MATCH_THRESHOLD
    leader = None
    if flag_found:
        leader = find_start_finish_touch(gray, flag_box)
        erase_flag_and_leader(white, flag_box, leader)
        if leader is None:
            print(f"  {pid}: chequered flag found (score {flag_score:.2f}) but no leader line "
                  f"reaches the track from it - no start/finish bar drawn.")
        elif leader["glued"]:
            print(f"  {pid}: flag sits against the track; start/finish taken at the nearest "
                  f"corner, {abs(leader['touch'][0] - leader['corner'][0])}px out.")
    else:
        print(f"  WARNING: {pid}: no chequered flag matched (best score {flag_score:.2f}) - "
              f"no start/finish bar drawn.")

    # 2. The arrows, off the original colours, gated on distance to the band.
    band = track_band(white)
    arrows = detect_arrows(img, track_mask=band, white_mask=white)
    for _, _, box in arrows:
        erase_components_in_box(white, box, margin=4,     # the arrow's white outline
                                touching_max_area=TEXT_MAX_GLYPH_AREA)

    # 3. Text: glyphs erased from the mask so they are not traced as track;
    #    the labels themselves come off the cross-checked OCR.
    exclude = [box for _, _, box in arrows]
    if flag_found:
        exclude.append(flag_box)
    text_boxes, glyph_mask = find_text_lines(white, exclude)
    white_with_text = white.copy()
    for x, y, bw, bh in text_boxes:
        erase_components_in_box(white, (x, y, x + bw, y + bh), margin=2)
    labels = read_map_labels(img, pid, glyph_mask, white_with_text)

    # 4. Geometry off the cleaned mask.
    band = track_band(white)
    geometry = band_geometry(band, reference_area=untouched_area)
    if geometry is not None and not geometry["closed"]:
        print(f"  WARNING: {pid}: the traced track is not a closed loop; the direction "
              f"is read off the centroid instead of the outline.")
    band_contours, _ = cv2.findContours(band, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    centroid = track_centroid(list(band_contours), img.shape)

    # 5. Direction. The tangent reading is the answer; the centroid reading is
    #    kept as a cross-check and only ever printed.
    arrow_length = max(MIN_ARROW_LENGTH, ARROW_LENGTH_FRACTION * scale)
    glyphs = []
    for base, tip, _ in arrows:
        ends = arrow_endpoints(base, tip, arrow_length)
        if ends is None:
            continue
        base, tip = ends
        tangent = tangent_direction(geometry, base, tip, scale)
        radial = arrow_direction(base, tip, centroid, scale) if centroid is not None else None
        glyphs.append((base, tip, tangent, radial))
    # statsf1 only draws a second arrow to say the layout was raced the other
    # way round, so a second glyph that agrees with the first is not an arrow.
    if len(glyphs) == 2:
        first, second = glyphs[0][2], glyphs[1][2]
        if not (first and second and first["usable"] and second["usable"] and _opposing(first, second)):
            print(f"  {pid}: second red shape dropped - it does not oppose the first arrow.")
            del glyphs[1]

    tangent_readings = [t for _, _, t, _ in glyphs if t and t["usable"]]
    radial_readings = [r for _, _, _, r in glyphs if r]
    direction = resolve_circuit_direction([{"direction": t["direction"], "usable": True}
                                           for t in tangent_readings])
    radial_direction = resolve_circuit_direction(radial_readings)
    if direction is None and radial_direction is not None:
        print(f"  {pid}: tangent reading unusable, falling back to the centroid reading.")
        direction = radial_direction
    elif radial_direction is not None and radial_direction != direction:
        print(f"  {pid}: centroid reading ({radial_direction}) disagrees with the tangent "
              f"reading ({direction}); the tangent reading is kept.")

    from_era = direction_for_years(WIKI_DIRECTION_ERAS.get(pid), years_from_dates(grand_prix_dates))
    if from_era is not None:
        if direction is not None and direction != from_era:
            print(f"  TrackDirection: detector read {direction}, corrected to {from_era} "
                  f"from the years {pid} was raced.")
        direction = from_era
    override = DIRECTION_OVERRIDES.get(pid)
    if override is not None:
        if direction is not None and direction != override:
            print(f"  TrackDirection: detector read {direction}, overridden to {override} "
                  f"by DIRECTION_OVERRIDES.")
        direction = override
    if direction is None:
        print(f"  WARNING: TrackDirection could NOT be determined for {pid} - storing NULL. "
              f"{len(glyphs)} arrow(s), none readable. Add an entry to DIRECTION_OVERRIDES.")

    # 6. Draw: track first, then the bar, then arrows, then the names on top.
    elements = ['<g fill="none" stroke="white" stroke-width="4">']
    contours, _ = cv2.findContours(white, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    for cnt in contours:
        if cv2.contourArea(cnt) < TRACK_CONTOUR_MIN_AREA:
            continue
        approx = cv2.approxPolyDP(cnt, TRACK_CONTOUR_EPSILON, True)
        points = " ".join(f"{int(p[0][0]) + SVG_OFFSET_X},{int(p[0][1]) + SVG_OFFSET_Y}" for p in approx)
        elements.append(f'<polyline points="{points}" />')
    elements.append('</g>')

    if leader is not None and geometry is not None:
        elements.extend(start_finish_svg(leader["touch"], band, geometry, flag_box,
                                         orig_w, orig_h, SVG_OFFSET_X, SVG_OFFSET_Y))

    for base, tip, _, _ in glyphs:
        elements.extend(arrow_svg(base, tip, SVG_OFFSET_X, SVG_OFFSET_Y,
                                  head_length=arrow_length * ARROW_HEAD_FRACTION))

    elements.append('<g fill="#FFFFFF" font-family="sans-serif" font-size="12" font-weight="bold" '
                    'paint-order="stroke fill" stroke="#111111" stroke-width="3px" stroke-linejoin="round">')
    review = 0
    for label in labels:
        raw_center_x, raw_center_y = (int(v) for v in _centre(label["box"]))
        shifted_x = raw_center_x + SVG_OFFSET_X
        shifted_y = raw_center_y + SVG_OFFSET_Y
        flag_attr = ""
        if label["review"]:
            review += 1
            flag_attr = f' data-review="1" data-alt="{_svg_text(label["alt"])}"'
        elements.append(
            f'  <text x="{shifted_x}" y="{shifted_y + 4}" text-anchor="middle"{flag_attr}>{_svg_text(label["text"])}</text>'
        )
    elements.append('</g>')

    if leader is None:
        start_finish = "missing"
    elif leader["glued"]:
        start_finish = "glued"
    else:
        start_finish = "exact"
    tangent_text = ",".join(t["direction"] for t in tangent_readings) or "none"
    svg = (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" xmlns="http://www.w3.org/2000/svg" '
           f'style="background: #111;" data-flag-score="{flag_score:.2f}" '
           f'data-start-finish="{start_finish}" data-arrows="{len(glyphs)}" '
           f'data-direction-tangent="{tangent_text}" data-direction-centroid="{radial_direction or "none"}" '
           f'data-labels="{len(labels)}" data-labels-review="{review}">\n')
    svg += "".join(f"  {element}\n" for element in elements)
    svg += "</svg>"
    return svg, direction


import sqlite3
from bs4 import BeautifulSoup
from curl_cffi import requests
import time
import random

def parse_coordinate(value):
    match = re.search(r'-?\d+(?:\.\d+)?', str(value).strip())
    if not match:
        raise ValueError(f"Invalid coordinate: {value}")
    return float(match.group(0))

TRACK_TYPE_MAP = {
    "Occasional track": "Street Circuit",
    "Semi-permanent track": "Semi-permanent Circuit",
    "Permanent track": "Permanent Circuit",
}


def clean_circuittype_bullet(li):
    return re.sub(
        r'^(?:\u2022|\u00e2\u20ac\u00a2)\s*',
        '',
        li.get_text(" ", strip=True)
    ).strip()


def parse_circuit_metadata(soup, fallback_name=None):
    """(official circuit name, track type) off a statsf1 circuit page.

    The circuittype box lists the official name first and the track type
    after it - but only when statsf1 has an official name to give. Pescara,
    Bremgarten, Dijon, the Hungaroring and a dozen others open straight with
    "Permanent track", and taking bullet 0 blindly stored that as the name of
    twenty layouts. So bullet 0 is the name only when it is not the track-type
    bullet; otherwise `fallback_name` (the circuit's name on the circuits
    list) is used, and the run fails loudly if there is no fallback either.
    """
    circuittype_items = soup.find('div', class_='circuittype').find_all('li')
    bullets = [clean_circuittype_bullet(item) for item in circuittype_items]
    raw_track_type = next(b for b in bullets if "track" in b.lower())
    if bullets[0] == raw_track_type:
        official_circuit_name = fallback_name
    else:
        official_circuit_name = bullets[0]
    if not official_circuit_name:
        raise ValueError("Circuit page carries no official name and no fallback was given")
    official_circuit_name = re.sub(r'\s+', ' ', official_circuit_name).strip()
    return official_circuit_name, TRACK_TYPE_MAP[raw_track_type]


#This is the shared fetcher every request goes through. It returns the raw response so
#both the HTML scraping (open_url) and the track map images (imread_from_url) get the
#same Chrome TLS fingerprint, the same retry/backoff, and — most importantly — the same
#throttle. Images used to bypass all of this on plain urllib, which meant a circuit page
#with five layouts fired five unthrottled requests back to back and got the connection reset.
def fetch_url(url, retries=3, extra_headers=None):
    url = "https://" + url.replace("https://", "").replace("//", "/")
    request_headers = dict(headers)
    if extra_headers:
        request_headers.update(extra_headers)
    last_exception = None

    for attempt in range(retries):
        try:
            response = requests.get(
                url,
                headers=request_headers,
                impersonate="chrome",
                timeout=30
            )
            if (
                response.status_code == 302
                and response.headers.get("location")
                == "https://www.statsf1.com/errors/GenericErrorPage.htm"
            ):
                raise Exception(
                    "You have been IP blocked by statsf1.com. Please wait and try again later."
                )
            response.raise_for_status()
            if "statsf1.com" in url:
                time.sleep(random.uniform(4, 15))
            return response
        except Exception as e:
            last_exception = e
            print(f"Attempt {attempt + 1} failed for URL {url}: {e}")

            if attempt < retries - 1:
                time.sleep(
                    random.expovariate(1 / (5 * (2 ** attempt)))
                )
    if isinstance(last_exception, (requests.exceptions.Timeout, TimeoutError)):
        print("Timed out after all retries. Sleeping for 5 minutes...")
        time.sleep(300)
    raise RuntimeError(
        f"Failed to open URL {url} after {retries} attempts."
    ) from last_exception

def open_url(url, retries=3):
    response = fetch_url(url, retries=retries)
    global soup
    soup = BeautifulSoup(response.content, "html.parser")
    return soup

if __name__ == "__main__":
    conn = sqlite3.connect("../sessionresults.db")
    cur = conn.cursor()    
    open_url("https://www.statsf1.com/en/circuits.aspx")
    table = soup.find('table')
    trs = table.find_all('tr')
    for tr in trs[1:-1]:
        p = tr.find_all('td')[0]
        v = p.find('a')
        print ("Processing circuit: ", v.get_text(strip=True))
        print(c)
        c +=1
        twd = v['href']
        open_url(f'https://www.statsf1.com/{twd}')
        a_tag = soup.find('a', id='ctl00_CPH_Main_HL_GMaps')['href']
        coord_str = re.search(r'@([^,]+),([^,]+)', a_tag).groups()
        lat, lng = coord_str
        lat = parse_coordinate(lat)
        lng = parse_coordinate(lng)
        official_circuit_name, track_type = parse_circuit_metadata(soup, fallback_name=v.get_text(strip=True))
        circuitlayoutdivs = soup.find_all('div', class_ = 'circuitversion')
        for layoutdiv in circuitlayoutdivs:
            circuittable = layoutdiv.find('table', class_ = 'sortable circuittable').find_all('tr')
            dates = [tr.find_all('td')[0]['sorttable_customkey'] for tr in circuittable[1:-1]]                
            version = circuitlayoutdivs.index(layoutdiv) + 1
            layoutimg = layoutdiv.find('img')['src']
            circuit_text_div = layoutdiv.find('div', class_='circuitversiontxt')
            circuit_text = circuit_text_div.get_text(strip=True).replace('\n', '').replace('"', '').replace('\r', '')            
            t, track_direction = generate_track_svg(f'https://www.statsf1.com{layoutimg}', dates)
            cur.execute("UPDATE CircuitLayouts SET GrandPrixDates = ?, CircuitVersion = ?, SVG = ?, CircuitChanges = ?, TrackDirection = ?, OfficialCircuitName = ?, TrackType = ? WHERE Latitude = ? AND Longitude = ? AND CircuitVersion = ?", (json.dumps(dates), version, t, circuit_text, track_direction, official_circuit_name, track_type, lat, lng, version))
            conn.commit()
