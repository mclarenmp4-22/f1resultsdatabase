import re
import urllib.request
import math
import cv2
import numpy as np
from ollama import chat
import json
import os
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

    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(
            f"Could not decode an image from {url} "
            f"(content-type {response.headers.get('content-type')!r}, {len(image_bytes)} bytes)"
        )
    return img, image_bytes

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

GEGL_LUMA = (0.22248840, 0.71690369, 0.06060791)


def _srgb_to_linear(a):
    """0-1 gamma-encoded sRGB -> linear light."""
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(a):
    """Inverse of _srgb_to_linear. Clipped first: saturation can push a channel
    negative, and a fractional power of a negative is NaN."""
    a = np.clip(a, 0.0, 1.0)
    return np.where(a <= 0.0031308, a * 12.92, 1.055 * np.power(a, 1.0 / 2.4) - 0.055)


def gimp_saturation(pil_rgb, scale=2.0, linear_light=False):
    """Replicate GIMP 3.x's Colors > Saturation (gegl:saturation) on an RGB image.

    GEGL interpolates each channel away from the pixel's own luminance:
        out = luma + (in - luma) * scale
    so greys stay exactly grey at any scale and only genuinely coloured pixels
    move. That is the whole point for the second pass: it drags the red arrow
    away from the aerial photo without touching the white track or the flag.

    The Interpolation Color Space dropdown decides which values that runs on.
    linear_light=False matches "Native" on a normal 8-bit gamma image (GIMP 3's
    default precision), which is what the screenshots show. Set it True if the
    image was opened at a linear precision instead - the arrow survives either
    way, the aerial photo just fades differently.
    """
    arr = np.asarray(pil_rgb.convert("RGB"), dtype=np.float32) / 255.0
    if linear_light:
        arr = _srgb_to_linear(arr)

    r, g, b = GEGL_LUMA
    luma = arr[:, :, 0] * r + arr[:, :, 1] * g + arr[:, :, 2] * b
    out = luma[:, :, None] + (arr - luma[:, :, None]) * scale

    if linear_light:
        out = _linear_to_srgb(out)
    # Round rather than truncate: the luma weights sum to 1.0 so a grey pixel is
    # its own luma and must come back bit-identical, but the /255 -> *255 round
    # trip lands on 199.99999 and truncation would drop it under the pivot.
    return Image.fromarray(np.clip(np.rint(out * 255.0), 0, 255).astype(np.uint8), mode="RGB")


def gimp_contrast_rgb(pil_rgb, contrast=1.0, pivot=200):
    """RGB counterpart of gimp_contrast(), same curve applied per channel.

    gimp_contrast() takes an "L" image and the second pass has to keep colour
    (the arrow is red, the start/finish flag is black-and-white), so the same
    tan-slope curve runs on R, G and B independently around the same pivot.
    At contrast = 1.0 every channel becomes a hard step, so each pixel lands on
    one of the eight corners of the RGB cube - white track, black photo, red
    arrow - which is what the max-contrast GIMP result looks like.
    """
    contrast = min(max(contrast, -1.0), 1.0)
    arr = np.asarray(pil_rgb.convert("RGB"), dtype=np.float32)
    if contrast >= 1.0:
        out = np.where(arr > pivot, 255.0, 0.0)
    else:
        slope = math.tan((contrast + 1.0) * math.pi / 4.0)
        out = (arr - pivot) * slope + pivot
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), mode="RGB")


def preprocess_second_pass(pil_rgb, saturation=2.0, contrast=1.0, pivot=200,
                           linear_light=False):
    """Saturation x2 then max contrast - the GIMP recipe for the arrow /
    start-finish pass. Takes and returns a PIL RGB image; intended for
    pil_img_p2, the copy the first pass already sets aside untouched."""
    boosted = gimp_saturation(pil_rgb, scale=saturation, linear_light=linear_light)
    return gimp_contrast_rgb(boosted, contrast=contrast, pivot=pivot)


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
# Two things put a layout here, and they are not the same thing:
#
#   - the arrow is unreadable against the centroid. Miami's arrow points almost
#     straight at the centre of its own layout (tangentiality 0.013), so the
#     cross product is the residue of two nearly equal products and its sign is
#     noise. That is what the tangentiality gate is for, and the gate is right
#     to drop it; the entry here is what fills the hole afterwards.
#   - the arrow reads cleanly and the reading is wrong anyway. Dallas resolves
#     at 0.367, nowhere near the gate, and still comes out backwards: the arrow
#     sits due east of the centroid pointing west, which is the same radial
#     degeneracy showing up as a middling number rather than a small one. No
#     threshold catches this, which is why the table is applied wherever it has
#     an entry rather than only where the detector gave up.
#
# statsf1's own "Direction" field is not the source for these. It is per circuit
# rather than per layout, so it reports the modern direction for a circuit that
# changed - Kyalami raced clockwise on the layout here and anticlockwise today -
# and it is outright wrong on at least Interlagos, which it calls Clockwise. The
# values below were read off the maps.
DIRECTION_OVERRIDES = {
    # Unreadable against the centroid: the arrow points so nearly at (or away
    # from) the centre of its own layout that the cross product is the residue
    # of two nearly equal products and its sign is noise. Tangentiality in
    # brackets - the gate at MIN_TANGENTIALITY drops all of these.
    "piste.baku1": "Anticlockwise",         # 0.010
    "piste.miami1": "Anticlockwise",        # 0.013
    "piste.yasmarina1": "Anticlockwise",    # 0.015
    "piste.newdelhi1": "Clockwise",         # 0.027, Buddh
    "piste.kualalumpur": "Clockwise",       # 0.210, Sepang
    "piste.lecastellet1": "Clockwise",      # 0.752

    # Read cleanly and came out backwards anyway. Same radial degeneracy, but
    # presenting as a middling tangentiality rather than a small one, so no
    # threshold separates them from the readings that are right - which is why
    # this table is consulted wherever it has an entry rather than only where
    # the detector gave up.
    "piste.dallas": "Anticlockwise",        # 0.367
    "piste.sebring": "Clockwise",           # 0.766

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
    "piste.spa2": "Clockwise",              # 0.266
    "piste.spa3": "Clockwise",              # 0.266
    "piste.spa4": "Clockwise",              # 0.267
    "piste.jerez1": "Clockwise",            # 0.251
    "piste.jerez2": "Clockwise",            # 0.052
    "piste.phoenix2": "Anticlockwise",      # 0.082
    "piste.zandvoort3": "Clockwise",
    "piste.zandvoort4": "Clockwise",
    "piste.zandvoort5": "Clockwise",
    "piste.zolder1": "Clockwise",
    "piste.zolder2": "Clockwise",
    "piste.zeltweg": "Clockwise",
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


def box_centre(qwen_box, actual_width, actual_height):
    """Centre of a 0-1000 normalised box, in pixels of the original image."""
    x_min, y_min, x_max, y_max = scale_box_to_pixels(qwen_box, actual_width, actual_height)
    return ((x_min + x_max) / 2.0, (y_min + y_max) / 2.0)


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


def detect_arrows(bgr, track_mask=None, max_arrows=2):
    """Every direction arrow on the map, as (base, tip) pixel pairs.

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
        tip, base, length, thickness, confidence = _head_end(sel)
        if (length < ARROW_MIN_LENGTH_FRACTION * diagonal
                or length / max(thickness, 1e-6) < ARROW_MIN_ELONGATION
                or confidence < ARROW_MIN_CONFIDENCE):
            continue
        if track_distance is not None:
            mx = int(min(max((base[0] + tip[0]) / 2.0, 0), width - 1))
            my = int(min(max((base[1] + tip[1]) / 2.0, 0), height - 1))
            if track_distance[my, mx] > ARROW_MAX_TRACK_DISTANCE_FRACTION * diagonal:
                continue
        claimed |= sel
        arrows.append((tuple(base), tuple(tip), int(sel.sum()), length, confidence))

    # A second arrow has to look like the first one to be believed - see the note
    # on SECOND_ARROW_AREA_RATIO.
    if len(arrows) == 2 and arrows[1][4] < SECOND_ARROW_CONFIDENCE_RATIO * arrows[0][4]:
        del arrows[1]
    return [(base, tip) for base, tip, _, _, _ in arrows]


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


# Flag erasure safety. The flag box comes from the model, and one drawn a few
# pixels too generously runs into the track. A partial bite is harmless - it
# thins the stroke, the outline stays closed - but a box reaching all the way
# across severs the circuit, and what gets traced is no longer a loop. That shows
# up as a collapse in the area the largest external contour encloses: an intact
# ring encloses the whole infield, while a severed one has its contour snake in
# through the gap and back around the inside, so it encloses only the stroke
# material. Measured on a 10px stroke, biting nine pixels of it leaves the ratio
# at 0.996 and the tenth drops it to 0.24 - a step with a 4x gap either side of
# it, so the threshold needs no tuning and anything from 0.3 to 0.95 behaves the
# same. The retreat is deliberately small: an overlap this check can see is at
# most a stroke wide, and the measured case cleared in three pixels.
# The bar is drawn in its own colour rather than the track's white. Drawn white
# it is invisible: it sits on top of a white stroke, and the only thing marking
# the spot is then the label. The overhang is what makes it read as crossing the
# track rather than being part of it, so it is sized off the image instead of the
# stroke - a few pixels either side of a 9px stroke disappears at a glance.
START_FINISH_COLOUR = "#FFD200"
START_FINISH_OVERHANG_FRACTION = 0.010
MIN_START_FINISH_OVERHANG = 7.0

LOOP_INTACT_RATIO = 0.5
FLAG_RETREAT_STEP = 2
FLAG_RETREAT_LIMIT = 16


def _largest_external_area(mask):
    """Area enclosed by the biggest external contour - the loop-intact measure."""
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    return max((cv2.contourArea(c) for c in contours), default=0.0)


# How far past the box edge the remnant sweep looks, and how big a component it
# is still willing to call flag. The margin covers a box that under-covers the
# glyph - the leftover is contiguous with the erased area, so it starts at the
# box edge - plus some slack for a box displaced outright. The area cap is what
# keeps the sweep honest on maps where the source image draws the circuit broken
# at the flag line: those pieces are each a large share of the track, while a
# flag remnant is never more than a glyph, so anything near a tenth of the
# largest component is track and stays.
FLAG_SWEEP_AREA_RATIO = 0.1


def _sweep_flag_remnants(mask, box_px):
    """Delete detached leftovers of the flag the box erase failed to cover.

    The box erase can only remove what the box contains, and a box the model
    draws too small leaves the rest of the glyph standing - severed from the
    track by the erase, so it gets traced as a stray blob right next to the
    start/finish bar. Those leftovers have a signature the box does not need to
    be accurate for: a small connected component that is not the circuit,
    sitting in or against the box. Everything matching it goes; the largest
    component is never touched, so this cannot sever anything.

    Returns the number of components removed. Modifies `mask` in place.
    """
    x1, y1, x2, y2 = box_px
    margin = max(10.0, 0.5 * max(x2 - x1, y2 - y1))
    gx1, gy1, gx2, gy2 = x1 - margin, y1 - margin, x2 + margin, y2 + margin

    num, comp_map, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if num <= 2:
        return 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    largest = 1 + int(np.argmax(areas))
    cap = FLAG_SWEEP_AREA_RATIO * float(stats[largest, cv2.CC_STAT_AREA])

    removed = 0
    for i in range(1, num):
        if i == largest or stats[i, cv2.CC_STAT_AREA] >= cap:
            continue
        bx, by, bw, bh = stats[i, cv2.CC_STAT_LEFT], stats[i, cv2.CC_STAT_TOP],                          stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
        if bx <= gx2 and bx + bw >= gx1 and by <= gy2 and by + bh >= gy1:
            mask[comp_map == i] = 0
            removed += 1
    return removed


def erase_chequered_flag(white_mask, flag_box, flag_line_box, orig_w, orig_h):
    """Cut the flag out of the mask, but never at the cost of cutting the circuit.

    Erases the box, checks the circuit came through it still a loop, and if it
    did not, gives ground two pixels at a time until it did. The touch box aims
    the retreat where there is one: it is the one part of the picture guaranteed
    to be track, so the edges facing it are the ones doing the cutting. Without
    it there is nothing to aim by and the box simply shrinks from every side.

    If no amount of retreating leaves the loop intact the flag is left where it
    is. A stray rectangle in the output is a far smaller problem than a circuit
    with a hole in it, and unlike the hole it is obvious on sight.

    Returns (mask, retreat) - a new mask, and the pixels of ground given up, or
    None if the flag had to be left alone.
    """
    x1, y1, x2, y2 = scale_box_to_pixels(flag_box, orig_w, orig_h)
    baseline = _largest_external_area(white_mask)

    touch = box_centre(flag_line_box, orig_w, orig_h) if flag_line_box else None
    if touch is None:
        left = right = top = bottom = 1
    else:
        # A box that has run into the track has the touch point inside it, so
        # which side is nearest is what identifies the edge that did the cutting.
        # Giving ground on any other only costs flag coverage for nothing.
        gaps = (("left", touch[0] - x1), ("right", x2 - touch[0]),
                ("top", touch[1] - y1), ("bottom", y2 - touch[1]))
        nearest = min(gaps, key=lambda g: abs(g[1]))[0]
        left, right = int(nearest == "left"), int(nearest == "right")
        top, bottom = int(nearest == "top"), int(nearest == "bottom")

    for retreat in range(0, FLAG_RETREAT_LIMIT + 1, FLAG_RETREAT_STEP):
        ax1, ay1 = x1 + left * retreat, y1 + top * retreat
        ax2, ay2 = x2 - right * retreat, y2 - bottom * retreat
        if ax2 - ax1 < 2 or ay2 - ay1 < 2:
            break
        trial = white_mask.copy()
        cv2.rectangle(trial, (ax1, ay1), (ax2, ay2), 0, -1)
        if baseline <= 0 or _largest_external_area(trial) >= LOOP_INTACT_RATIO * baseline:
            _sweep_flag_remnants(trial, (x1, y1, x2, y2))
            return trial, retreat

    # Even with the box unusable, a flag the erase has to leave alone may still
    # be a separate component the sweep can take whole.
    trial = white_mask.copy()
    _sweep_flag_remnants(trial, (x1, y1, x2, y2))
    return trial, None


# Start/finish bar geometry. TANGENT_SPAN is the arclength walked out along the
# traced outline either side of the touch point before the chord between the two
# is taken as the local direction of travel. The short end of that is set by how
# much of the flag's leader line the detector's box fails to cover: whatever is
# left behind is a spur welded to the outline right where the tangent is being
# measured, and the walk has to reach well past it to out-vote it. Measured on a
# 6px leftover, the error runs 41 degrees at a span of 6, 19 at 10, and settles
# around 4-5 from 20 upwards. The long end is set by corner radius, and is much
# more forgiving than it looks - the chord across a symmetric apex still points
# the right way - with an 18px hairpin still inside a degree at a span of 40. 20
# sits in the flat part of both. CROSS_SCAN caps how far the re-centring scan
# travels across the stroke, so a scan that starts on the wrong pixel gives up
# instead of wandering into the next straight over.
TANGENT_SPAN_FRACTION = 0.025
MIN_TANGENT_SPAN = 18.0
CROSS_SCAN_FRACTION = 0.05


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


def start_finish_svg(flag_line_box, flag_box, track_mask, contours, centroid,
                     orig_w, orig_h, offset_x, offset_y,
                     colour=START_FINISH_COLOUR, stroke_width=3.0):
    """The start/finish bar and its label, drawn across the track at the flag.

    The touch point the detector returns lands on the *edge* of the stroke - it
    is where the leader line runs into the track, not where the racing line
    crosses - so a bar centred on it would sit half off the track. The distance
    transform fixes that: scanning perpendicular to the tangent, the value rises
    to a maximum on the ridge running down the middle of the stroke and falls
    back to zero at the far edge, which gives the centre to draw about and, in
    the same number, the half-width to draw out to. The scan stops the moment it
    leaves white so it can only ever measure the one stroke it started on.

    The label goes on the side the flag was on, which is by construction the
    outside of the track at that point, so it cannot land in the infield on top
    of a corner name.
    """
    scale = max(orig_w, orig_h)
    span = max(MIN_TANGENT_SPAN, TANGENT_SPAN_FRACTION * scale)
    touch = box_centre(flag_line_box, orig_w, orig_h)

    tangent = _local_tangent(touch, contours, span)
    if tangent is None:
        return []
    (qx, qy), (tx, ty) = tangent
    nx, ny = -ty, tx                      # perpendicular to the direction of travel

    dist = cv2.distanceTransform(track_mask, cv2.DIST_L2, 5)
    img_h, img_w = track_mask.shape[:2]
    max_scan = max(12.0, CROSS_SCAN_FRACTION * scale)

    def scan(sign):
        """Walk across the stroke, returning (offset, value) at the widest point."""
        best_t, best_d, t = 0.0, 0.0, 0.0
        while t <= max_scan:
            xi = int(round(qx + sign * nx * t))
            yi = int(round(qy + sign * ny * t))
            if not (0 <= xi < img_w and 0 <= yi < img_h):
                break
            d = float(dist[yi, xi])
            if d <= 0.0 and t > 1.0:
                break
            if d > best_d:
                best_d, best_t = d, t
            t += 0.5
        return best_t, best_d

    (t_pos, d_pos), (t_neg, d_neg) = scan(1), scan(-1)
    sign, offset, half_width = (1, t_pos, d_pos) if d_pos >= d_neg else (-1, t_neg, d_neg)
    if half_width <= 0.0:
        # Nothing white under the touch point - the box missed the track, and a
        # bar drawn off a guessed width would be worse than no bar at all.
        return []

    cx = qx + sign * nx * offset
    cy = qy + sign * ny * offset
    overhang = max(MIN_START_FINISH_OVERHANG, START_FINISH_OVERHANG_FRACTION * scale)
    reach = half_width + overhang          # overhang, so the bar reads as crossing

    x1 = cx - nx * reach + offset_x
    y1 = cy - ny * reach + offset_y
    x2 = cx + nx * reach + offset_x
    y2 = cy + ny * reach + offset_y

    # Which end of the bar points away from the track: the flag's own side if it
    # was found, otherwise simply away from the centre of the circuit.
    if flag_box:
        away = box_centre(flag_box, orig_w, orig_h)
    elif centroid is not None:
        away = (2 * cx - centroid[0], 2 * cy - centroid[1])
    else:
        away = None
    label_sign = 1.0
    if away is not None and (nx * (away[0] - cx) + ny * (away[1] - cy)) < 0:
        label_sign = -1.0

    label_gap = reach + 11.0
    label_x = cx + label_sign * nx * label_gap + offset_x
    label_y = cy + label_sign * ny * label_gap + offset_y

    return [
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
        f'stroke="{colour}" stroke-width="{stroke_width}" stroke-linecap="butt" />',
        f'<g fill="{colour}" font-family="sans-serif" font-size="9" font-weight="bold" '
        'paint-order="stroke fill" stroke="#111111" stroke-width="3px" stroke-linejoin="round">'
        f'<text x="{label_x:.1f}" y="{label_y + 3.0:.1f}" text-anchor="middle">'
        'START/FINISH</text></g>',
    ]


def generate_track_svg(image_path, grand_prix_dates=None):
    SYSTEM_PROMPT_OCR="""
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
    SYSTEM_PROMPT_OBJECT_DETECTION = """
    You are a deterministic, strict engine given the task of finding bounding boxes for specific parts of Formula One circuit maps.
    You will be given an image of a Formula One circuit. This image will contain certain elements of the circuit, which you must locate and return as bounding boxes in a normalized 0-1000 coordinate grid system.
    You will need to find the following elements in the image:
    - The chequered flag: This is a black-and white chequered flag that indicates the start/finish line of the circuit.
      You will need to find a) the bounding box encompassing the ENTIRE chequered flag region, from the line that extends from the flag and touches the track, to the end of the flag. Do not include any of the track in the bounding box, only the flag itself. 
      and b) the bounding box for the small region where the line from the chequered flag touches the track. The small region that connects the chequered flag to the track is what you will have to return.
    For each item found, return the exact 2D bounding box as you see it, in the format [xmin, ymin, xmax, ymax]. Ignore any text or numbers and do not attempt to transcribe them. Only return bounding boxes for the specified elements, and do not try to check its position in relation with any other element in the image.
    Do not use an internal monologue or thinking process. Output the raw JSON text block directly without wrapped tags. Do not include blank characters or newlines in the output.
    Do not repeat the same text in the output. Only output the text once with its bounding box.

    Formatting Rules:
    You MUST output your entire response as a single, valid JSON object. Do not include conversational text or markdown code wraps. Follow this exact schema:
    {
        "chequered_flag": [x_min, y_min, x_max, y_max],
        "chequered_flag_line": [x_min, y_min, x_max, y_max]
    }
    """   
    SYSTEM_PROMPT_OBJECT_DETECTION_FALLBACK = """
    You are a deterministic, strict engine given the task of finding bounding boxes for specific parts of Formula One circuit maps.
    You will be given an image of a Formula One circuit. This image will contain certain elements of the circuit, which you must locate and return as bounding boxes in a normalized 0-1000 coordinate grid system.
    You will need to find the following elements in the image:
    - The chequered flag: This is a black-and white chequered flag that indicates the start/finish line of the circuit.
      You will need to find a) the bounding box encompassing the ENTIRE chequered flag region, from the line that extends from the flag and touches the track, to the end of the flag. Do not include any of the track in the bounding box, only the flag itself. 
      and b) the bounding box for the small region where the line from the chequered flag touches the track. The small region that connects the chequered flag to the track is what you will have to return.
    For each item found, return the exact 2D bounding box as you see it, in the format [xmin, ymin, xmax, ymax]. Ignore any text or numbers and do not attempt to transcribe them. Only return bounding boxes for the specified elements, and do not try to check its position in relation with any other element in the image.
    Do not use an internal monologue or thinking process. Output the raw JSON text block directly without wrapped tags. Do not include blank characters or newlines in the output.
    Do not repeat the same text in the output. Only output the text once with its bounding box.

    Formatting Rules:
    You MUST output your entire response as a single, valid JSON object. Do not include conversational text or markdown code wraps. Follow this exact schema:
    {
        "chequered_flag": [x_min, y_min, x_max, y_max],
        "chequered_flag_line": [x_min, y_min, x_max, y_max]
    }
    - The bounding box MUST contain exactly 4 integers ordered exactly as: [xmin, ymin, xmax, ymax].
    - Do not output native XML tags like <box>. Instead, map those integer bins directly into the values of the JSON object.
    """       
    OBJECT_DETECTION_SCHEMA = {
        "type": "object",
        "properties": {
            "chequered_flag": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 4,
                "maxItems": 4,
            },
            "chequered_flag_line": {
                "type": "array",
                "items": {"type": "integer"},
                "minItems": 4,
                "maxItems": 4,
            },
        },
        "required": [
            "chequered_flag",
            "chequered_flag_line",
        ],
        "additionalProperties": False,
    }
    if image_path == "https://www.statsf1.com/images/GetImage.ashx?id=piste.avus":
        #this was so hard, so i hardcoded it.
        return """
            <svg width="1020" height="500" viewBox="0 0 1020 454" xmlns="http://www.w3.org/2000/svg" style="background: #111;" xmlns:c2pa="http://c2pa.org/manifest"><metadata><c2pa:manifest>AAAWgmp1bWIAAAAeanVtZGMycGEAEQAQgAAAqgA4m3EDYzJwYQAAABZcanVtYgAAAEdqdW1kYzJtYQARABCAAACqADibcQN1cm46YzJwYTo1MzIwOGIwZC01NzE1LTQwODItYmU3Zi1jOTQ1N2Y5YjdhMmYAAAADl2p1bWIAAAApanVtZGMyYXMAEQAQgAAAqgA4m3EDYzJwYS5hc3NlcnRpb25zAAAAALxqdW1iAAAARGp1bWRjYm9yABEAEIAAAKoAOJtxE2MycGEuaW5ncmVkaWVudC52MwAAAAAYYzJzaGe0Ica2QXmMWrzjSIwWi30AAABwY2JvcqNpZGM6Zm9ybWF0bWltYWdlL3N2Zyt4bWxqaW5zdGFuY2VJRHgseG1wOmlpZDpkYzgzN2EyNy00YWEzLTRkYTYtOWIwOS0xOWRhMzg0MjZjZGVscmVsYXRpb25zaGlwaHBhcmVudE9mAAAB4mp1bWIAAABBanVtZGNib3IAEQAQgAAAqgA4m3ETYzJwYS5hY3Rpb25zLnYyAAAAABhjMnNoc6mYB4Z6lX6eksLDLvcSAgAAAZljYm9yomdhY3Rpb25zgqJmYWN0aW9ua2MycGEub3BlbmVkanBhcmFtZXRlcnOha2luZ3JlZGllbnRzgaJjdXJseC1zZWxmI2p1bWJmPWMycGEuYXNzZXJ0aW9ucy9jMnBhLmluZ3JlZGllbnQudjNkaGFzaFggedgXgm02XZnxtAgtnbNQOqQrXj166mfmZzevLHLRds2kZmFjdGlvbngdY29tLmFudGhyb3BpYy5jbGF1ZGUucHJvdmlkZWRqcGFyYW1ldGVyc6F4H2NvbS5hbnRocm9waWMub3JpZ2luLWNvbmZpZGVuY2VndW5rbm93bmtkZXNjcmlwdGlvbnhmQ2xhdWRlIHByb3ZpZGVkIHRoaXMgZmlsZSBhdCB0aGUgcmVxdWVzdCBvZiBhIHVzZXIgYW5kIG1heSBoYXZlIGNyZWF0ZWQgb3IgbW9kaWZpZWQgdGhlIGZpbGUgY29udGVudHMubXNvZnR3YXJlQWdlbnShZG5hbWVmQ2xhdWRlcmFsbEFjdGlvbnNJbmNsdWRlZPUAAADIanVtYgAAAEBqdW1kY2JvcgARABCAAACqADibcRNjMnBhLmhhc2guZGF0YQAAAAAYYzJzaMZUTFdYQ3R15pRqU2ABCxMAAACAY2JvcqVjYWxnZnNoYTI1NmNwYWRNAAAAAAAAAAAAAAAAAGRoYXNoWCCb9sw9WKhkk5Z+CDPHK+9c1/zMxFYlv/fVUBPtwGQolmRuYW1lbmp1bWJmIG1hbmlmZXN0amV4Y2x1c2lvbnOBomVzdGFydBiyZmxlbmd0aBkeBAAAAj5qdW1iAAAAJ2p1bWRjMmNsABEAEIAAAKoAOJtxA2MycGEuY2xhaW0udjIAAAACD2Nib3KlY2FsZ2ZzaGEyNTZpc2lnbmF0dXJleE1zZWxmI2p1bWJmPS9jMnBhL3VybjpjMnBhOjUzMjA4YjBkLTU3MTUtNDA4Mi1iZTdmLWM5NDU3ZjliN2EyZi9jMnBhLnNpZ25hdHVyZWppbnN0YW5jZUlEeCx4bXA6aWlkOjE0MmU4MzAwLWRiZDUtNGZmOC04MjMwLTcyMjA3ZTNmODE5MHJjcmVhdGVkX2Fzc2VydGlvbnODomN1cmx4LXNlbGYjanVtYmY9YzJwYS5hc3NlcnRpb25zL2MycGEuaW5ncmVkaWVudC52M2RoYXNoWCB52BeCbTZdmfG0CC2ds1A6pCtePXrqZ+ZnN68sctF2zaJjdXJseCpzZWxmI2p1bWJmPWMycGEuYXNzZXJ0aW9ucy9jMnBhLmFjdGlvbnMudjJkaGFzaFgggcfH2Wk4HNkAB+040HtLXTkgtQjc9OZIItx+cSyBCsCiY3VybHgpc2VsZiNqdW1iZj1jMnBhLmFzc2VydGlvbnMvYzJwYS5oYXNoLmRhdGFkaGFzaFggtFYRme5NH0f/gzxX9k/CSBus/yrC1PHGAKswuEfr3NN0Y2xhaW1fZ2VuZXJhdG9yX2luZm+jZG5hbWVvQW50aHJvcGljIEZpbGVzZ3ZlcnNpb25lMS4wLjBrc3BlY1ZlcnNpb25lMi40LjAAABA4anVtYgAAAChqdW1kYzJjcwARABCAAACqADibcQNjMnBhLnNpZ25hdHVyZQAAABAIY2JvctKEWQISogEmGCFZAgowggIGMIIBjaADAgECAhRA5aAK7sI50L64g/oGQgU9Z1UTADAKBggqhkjOPQQDAzBJMRcwFQYDVQQKEw5BbnRocm9waWMsIFBCQzEuMCwGA1UEAxMlQW50aHJvcGljIENvbnRlbnQgQ3JlZGVudGlhbHMgUm9vdCBDQTAeFw0yNjA4MDcxODQzNTZaFw0yODA4MDYxOTQzNTZaMEQxFzAVBgNVBAoTDkFudGhyb3BpYywgUEJDMSkwJwYDVQQDEyBBbnRocm9waWMgQ2xhdWRlIENvbnRlbnQgU2lnbmluZzBZMBMGByqGSM49AgEGCCqGSM49AwEHA0IABJh6CmvLUBgFFNU0vUKlOVtE6djd17L5SuwX0LemFisBM3dkd/3cyjxFA3Qo5S46fX0/ihY0VZ7mfb9KF703t5OjWDBWMA4GA1UdDwEB/wQEAwIHgDAVBgNVHSUEDjAMBgorBgEEAYPoXgIBMAwGA1UdEwEB/wQCMAAwHwYDVR0jBBgwFoAUzlHiBIFOZFsj+OPEz5o+nMHXXMIwCgYIKoZIzj0EAwMDZwAwZAIwMXMdFJ4BetLLVY7ORuE9noqbbAZOZn/aArXyTwFAZfKrPzxF2vPoJNf1+UCdg1XGAjBwX1zd9WGqYkqmL5SFqw1QySjr1zJfpJM9+1rdDwSPLMOPOjKuiXjoU/pUUeG9RwmhY3BhZFkNngAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAPZYQGId/E+0nF99Au0tbu326NQ4FXIIBXim0KWcG1B+d036Ay928DxKCkjCUKJ2BXS1Ksy1hvXDzh4RnfhZQGHhq7o=</c2pa:manifest></metadata>
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
            </svg>
        """, "Anticlockwise"
    for i in range(4):
        img, _ = imread_from_url(image_path)

        if img is not None:
            break

        if i == 3:
            raise ValueError(f"Failed to read image from URL: {image_path}")


    orig_h, orig_w = img.shape[:2]
    h = orig_h + 50
    w = orig_w + 100
    svg_elements = []
    # 1. Track outline (white / grey)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, white_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb_img)
    pil_img_p2 = pil_img.copy() #this is for the second pass, for the arrow and the start/finish line
    #leaving it here and continuing after the first pass is done...

    # Keep the original SVG mask untouched. This is a separate VLM/OCR image only.
    # GIMP-max-contrast pass: hard cut at native resolution first, so none of the
    # aerial photo underneath can survive into the upscale, then enlarge and
    # re-binarise to strip the grey LANCZOS ringing off the stroke edges.
    pil_img_for_vlm = pil_img.convert("L")
    pil_img_for_vlm = gimp_contrast(pil_img_for_vlm, contrast=1.0, pivot=200)
    pil_img_for_vlm = pil_img_for_vlm.resize(
        (orig_w * 5, orig_h * 5), Image.Resampling.LANCZOS
    )
    pil_img_for_vlm = pil_img_for_vlm.point(lambda p: 255 if p > 127 else 0)

    # Close the hairline gaps the hard threshold leaves in thin glyph strokes.
    vlm_arr = np.asarray(pil_img_for_vlm, dtype=np.uint8)
    vlm_arr = cv2.morphologyEx(vlm_arr, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    pil_img_for_vlm = Image.fromarray(vlm_arr)

    temp_vlm_input = "vlm_inference_ready.png"
    pil_img_for_vlm.save(temp_vlm_input)
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
    


    svg_content = (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'xmlns="http://www.w3.org/2000/svg" style="background: #111;">\n'
    )
    # Text style grouping with drop shadow borders for visibility
    svg_elements.append(
        '<g fill="#FFFFFF" font-family="sans-serif" font-size="12" font-weight="bold" '
        '   paint-order="stroke fill" stroke="#111111" stroke-width="3px" stroke-linejoin="round">'
    )        
    for label in labels:
        text = label["text"]
        if "statsf1" in text.lower() or "https://" in text.lower() or "http://" in text.lower() or ".com" in text.lower():
            continue
        x_min, y_min, x_max, y_max = scale_box_to_pixels(label["box_2d"], orig_w, orig_h)

        raw_center_x = int((x_min + x_max) / 2)
        raw_center_y = int((y_min + y_max) / 2)

        shifted_x = raw_center_x + 50
        shifted_y = raw_center_y + 25
        
        # 4. Inject into SVG elements array
        svg_elements.append(
            f'  <text x="{shifted_x}" y="{shifted_y + 4}" text-anchor="middle">{text}</text>'
        )
        
    svg_elements.append('</g>')    
    # ... continuing with second pass now
    pil_img_p2 = preprocess_second_pass(pil_img_p2)
    temp_vlm_input = "vlm_p2_inference_ready.png"
    pil_img_p2.save(temp_vlm_input) 
    try:
        response_p2 = chat(  
            model='qwen3-vl:4b',  
            messages=[{
                'role': 'user',
                'content': SYSTEM_PROMPT_OBJECT_DETECTION,
                'images': [temp_vlm_input]
            }],
            format=OBJECT_DETECTION_SCHEMA, 
            think = False,
            options={
                'temperature': 0.0,  
                'top_k': 1,          
                'top_p': 1.0,
                'num_ctx': 5800,    
            }
        )
        
        labels = json.loads(response_p2['message'].get('thinking') or response_p2['message'].get('content')) #for some reason, the response comes in the thinking field for me.
        chat(model="qwen3-vl:4b", messages=[], keep_alive=0)
    except Exception as e:
        chat(model="qwen3-vl:4b", messages=[], keep_alive=0) #unload the model to free up memory
        print("Primary OCR failed: %s", e)
        try:
            #try qwen with a repeat penalty
            response_p2 = chat(  
                model='qwen3-vl:4b',  
                messages=[{
                    'role': 'user',
                    'content': SYSTEM_PROMPT_OBJECT_DETECTION,
                    'images': [temp_vlm_input]
                }],
                format=OBJECT_DETECTION_SCHEMA, 
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
            
            labels = json.loads(response_p2['message'].get('thinking') or response_p2['message'].get('content'))    
            chat(model="qwen3-vl:4b", messages=[], keep_alive=0)      
        except Exception as e2:
            #try a smaller model if qwen fails, because qwen is very large and can run out of memory if there is too much context. the smaller model is less accurate, but it can handle more context.
            chat(model="qwen3-vl:4b", messages=[], keep_alive=0) #unload the model to free up memory
            print("Secondary OCR failed: %s", e2)
            response_p2 = chat(  
                model='openbmb/minicpm-v4.6:1b',  
                messages=[{
                    'role': 'user',
                    'content': SYSTEM_PROMPT_OBJECT_DETECTION_FALLBACK,
                    'images': [temp_vlm_input]
                }],
                format=OBJECT_DETECTION_SCHEMA, 
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
            labels = json.loads(response_p2['message'].get('thinking') or response_p2['message'].get('content'))    
            chat(model="openbmb/minicpm-v4.6:1b", messages=[], keep_alive=0) #unload the model to free up memory

    # The chequered flag is drawn in the same white as the track, so the tracer
    # cannot tell the two apart: left in, the glyph and its leader line come out
    # as a stray rectangle stuck to the circuit. The second pass has just located
    # it, so cut it out of the mask here - before anything is traced - rather
    # than trying to filter the resulting contour back out afterwards. Only the
    # flag's own box is cut, never the touch box: the touch box is where the
    # leader line runs into the track, so its pixels are track, and cutting it
    # would notch the circuit open at exactly the point the bar is drawn on.
    flag_box = labels.get("chequered_flag") if isinstance(labels, dict) else None
    flag_line_box = labels.get("chequered_flag_line") if isinstance(labels, dict) else None
    if flag_box:
        white_mask, retreat = erase_chequered_flag(
            white_mask, flag_box, flag_line_box, orig_w, orig_h
        )
        if retreat is None:
            print("Chequered flag box overlaps the track everywhere it was tried; "
                  "left in place rather than severing the circuit.")
        elif retreat:
            print(f"Chequered flag box pulled back {retreat}px to keep the circuit closed.")

    kernel = np.ones((3, 3), np.uint8)
    white_mask_processed = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel)
    
    temp_contours, _ = cv2.findContours(white_mask_processed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    track_only_mask = np.zeros_like(white_mask)
    valid_track_contours = []
    
    for c in temp_contours:
        area = cv2.contourArea(c)
        if area > 1000:
             valid_track_contours.append(c)
             cv2.drawContours(track_only_mask, [c], -1, 255, -1)
             
    has_giant_contour = any(cv2.contourArea(c) > (h*w*0.1) for c in valid_track_contours)

    if has_giant_contour: 
       erosion_kernel = np.ones((3,3), np.uint8)
       track_mask_for_fb = cv2.erode(track_only_mask, erosion_kernel, iterations=1)
    else:
       track_mask_for_fb = track_only_mask

    inverted_track_mask = cv2.bitwise_not(track_mask_for_fb)
    dist_transform = cv2.distanceTransform(inverted_track_mask, cv2.DIST_L2, 5)

    white_contours, _ = cv2.findContours(track_mask_for_fb, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    box_regions = []
    for cnt in white_contours:
        area = cv2.contourArea(cnt)
        x, y, w_box, h_box = cv2.boundingRect(cnt)
        bbox_area = w_box * h_box
        
        if bbox_area < 20 or bbox_area > 1000 or min(w_box, h_box) < 5:
            continue
        
        fill_ratio = area / bbox_area if bbox_area > 0 else 0
        if min(w_box, h_box) > 0:
            aspect_ratio = max(w_box, h_box) / min(w_box, h_box)
            roi = white_mask[max(0, y):min(gray.shape[0], y+h_box), max(0, x):min(gray.shape[1], x+w_box)]
            white_pixel_ratio = np.sum(roi == 255) / (w_box * h_box) if roi.size > 0 else 0
            
            perimeter = cv2.arcLength(cnt, True)
            expected_perimeter = 2 * (w_box + h_box)
            perimeter_ratio = perimeter / expected_perimeter if expected_perimeter > 0 else 0
            
            if (1.2 <= aspect_ratio <= 1.4 and fill_ratio > 0.7 and white_pixel_ratio > 0.8 and 0.8 <= perimeter_ratio <= 1.2):
                box_regions.append((x, y, x+w_box, y+h_box))
    
    track_mask = white_mask.copy()
    for x1, y1, x2, y2 in box_regions:
        cv2.rectangle(track_mask, (x1, y1), (x2, y2), 0, -1)
    
    contours, _ = cv2.findContours(track_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    track_contours = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 50:
            track_contours.append(cnt)

    # Tracing now happens after the second pass, so the track is the last thing
    # built rather than the first. It still has to be the first thing *drawn* -
    # the corner names sit on top of it - so it is collected separately and put
    # back at the head of the list instead of appended.
    track_elements = []
    if track_contours:
        track_elements.append('<g fill="none" stroke="white" stroke-width="4">')
        for cnt in track_contours:
            if cv2.contourArea(cnt) < 100:
                continue
            epsilon = 0.8
            approx = cv2.approxPolyDP(cnt, epsilon, True)
            points = " ".join([f"{int(p[0][0]) + 50},{int(p[0][1]) + 25}" for p in approx])
            track_elements.append(f'<polyline points="{points}" />')
        track_elements.append('</g>')

    # Arrows are measured off the original image rather than asked of the second
    # pass: the detector reads the head off the glyph's own shape, so it cannot
    # do what the model kept doing and hand back the tail as the point. Each one
    # is redrawn at a common size, and the circuit direction is read off the same
    # two points against the centre of the track.
    OFFSET_X, OFFSET_Y = 50, 25
    scale = max(orig_w, orig_h)
    centroid = track_centroid(valid_track_contours, img.shape)
    arrow_length = max(MIN_ARROW_LENGTH, ARROW_LENGTH_FRACTION * scale)
    # The traced circuit, as a mask, so a red blob far from it - a rooftop in the
    # corner of an aerial photo - cannot be mistaken for an arrow.
    arrow_track_mask = np.zeros(img.shape[:2], dtype=np.uint8)
    cv2.drawContours(arrow_track_mask, valid_track_contours, -1, 255, -1)
    readings = []
    for base, tip in detect_arrows(img, track_mask=arrow_track_mask):
        ends = arrow_endpoints(base, tip, arrow_length)
        if ends is None:
            continue
        base, tip = ends
        svg_elements.extend(arrow_svg(
            base, tip, OFFSET_X, OFFSET_Y,
            head_length=arrow_length * ARROW_HEAD_FRACTION))
        if centroid is not None:
            readings.append(arrow_direction(base, tip, centroid, scale))
    direction = resolve_circuit_direction(readings)

    # The hand-set table wins wherever it has an entry. It is not a fallback for
    # the NULL case alone: the reading it most needs to correct, Dallas, is one
    # the detector resolves confidently and gets backwards, so consulting the
    # table only when the detector gave up would leave exactly that class of
    # error in place.
    # The years a layout raced settle it outright where Wikipedia records a
    # direction per era, so that is consulted before the hand-set table: it is
    # derived from data the caller already has rather than maintained by hand,
    # and it is the only thing that can tell two layouts of one circuit apart.
    pid = layout_id(image_path)
    from_era = direction_for_years(WIKI_DIRECTION_ERAS.get(pid),
                                   years_from_dates(grand_prix_dates))
    if from_era is not None:
        if direction is not None and direction != from_era:
            print(f"  TrackDirection: detector read {direction}, corrected to "
                  f"{from_era} from the years {pid} was raced.")
        direction = from_era

    override = DIRECTION_OVERRIDES.get(pid)
    if override is not None:
        if direction is not None and direction != override:
            print(f"  TrackDirection: detector read {direction}, overridden to "
                  f"{override} by DIRECTION_OVERRIDES.")
        direction = override

    if direction is None:
        print(f"  WARNING: TrackDirection could NOT be determined for "
              f"{layout_id(image_path) or image_path} - storing NULL. "
              f"{len(readings)} arrow reading(s), none usable. "
              f"Add an entry to DIRECTION_OVERRIDES to fill it.")

    # The bar goes in with the track rather than after it: it belongs under the
    # corner names, and it is traced off the same contours, so it is only
    # meaningful next to them.
    if flag_line_box:
        track_elements.extend(
            start_finish_svg(flag_line_box, flag_box, track_mask,
                             valid_track_contours, centroid,
                             orig_w, orig_h, OFFSET_X, OFFSET_Y)
        )

    svg_elements = track_elements + svg_elements

    for element in svg_elements:
        svg_content += f"  {element}\n"
    svg_content += '</svg>'

    if os.path.exists("vlm_inference_ready.png"):
        os.remove("vlm_inference_ready.png")    
    if os.path.exists("vlm_p2_inference_ready.png"):
        os.remove("vlm_p2_inference_ready.png")
    return svg_content, direction

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


def parse_circuit_metadata(soup):
    circuittype_items = soup.find('div', class_='circuittype').find_all('li')
    official_circuit_name = None
    raw_track_type = None
    for item in circuittype_items:
        if "track" in clean_circuittype_bullet(item).lower():
            raw_track_type = clean_circuittype_bullet(item)
            if not circuittype_items[0] == item:
                official_circuit_name = clean_circuittype_bullet(circuittype_items[0])
            break
    official_circuit_name = clean_circuittype_bullet(circuittype_items[0])
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
    c = 73
    for tr in trs[1:-1][73:]:
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
        official_circuit_name, track_type = parse_circuit_metadata(soup)
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
