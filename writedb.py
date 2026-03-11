from os import link
import sqlite3
import urllib.request, urllib.parse, urllib.error
from bs4 import BeautifulSoup
import time
import re
import datetime
import json
import unicodedata
from decimal import Decimal
from collections import defaultdict, Counter
import cv2
import numpy as np
import warnings

# Suppress technical warnings
warnings.filterwarnings("ignore", category=UserWarning)

conn = sqlite3.connect('sessionresults.db')
cur = conn.cursor()
#cur.execute("PRAGMA foreign_keys = ON")

def ensure_column(table, col, coldef):
    cur.execute(f"PRAGMA table_info({table})")
    cols = {row[1] for row in cur.fetchall()}
    if col not in cols:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coldef}")

# Auto-migrate older DBs to include newer stat/update columns.
ensure_column("Seasons", "TotalGrandPrix", "INTEGER DEFAULT 0")
ensure_column("Seasons", "TotalDrivers", "INTEGER DEFAULT 0")
ensure_column("Seasons", "TotalConstructors", "INTEGER DEFAULT 0")
ensure_column("Seasons", "TotalEngines", "INTEGER DEFAULT 0")
ensure_column("Seasons", "TotalTeams", "INTEGER DEFAULT 0")
ensure_column("Seasons", "TotalEngineModels", "INTEGER DEFAULT 0")
ensure_column("Seasons", "TotalChassis", "INTEGER DEFAULT 0")
ensure_column("Seasons", "TotalNationalities", "INTEGER DEFAULT 0")
ensure_column("Seasons", "needstatsupdate", "BOOLEAN DEFAULT 0")

for _table in ["Drivers", "Constructors", "Engines", "Chassis", "EngineModels", "Tyres", "Teams", "Nationalities"]:
    ensure_column(_table, "SeasonsRaced", "INTEGER DEFAULT 0")



def normalize_name(name):
  """
  Normalizes a name for comparison by converting to lowercase and decomposing
  unicode characters. e.g., 'José' becomes 'jose'.
  """
  if not name:
    return ""
  if name.lower() == "gianmaria bruni":
    return "gimmi bruni"
  elif name.lower() == "zhou guanyu":
    return "zhou guanyu"
  # Normalizes to decomposed form, converts to lowercase, and removes accents
  return unicodedata.normalize('NFKD', name.lower()).encode('ascii', 'ignore').decode('ascii').replace('-', ' ')

#Functions:
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'} #Mimics the browser user agent to avoid being blocked by the website
#This is the open_url function that opens the url and returns the soup object

def open_url(url, retries=3):
    url = "https://" + url.replace("https://", "").replace("//", "/")
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(retries):
        try:
            html = urllib.request.urlopen(req, timeout=30).read()
            global soup
            soup = BeautifulSoup(html, 'html.parser')
            return soup
        except (Exception) as e:
        #except (urllib.error.URLError, socket.timeout, TimeoutError, Exception) as e:
            print(f"Attempt {attempt + 1} failed for URL {url}: {e}")
            time.sleep(5)  # Wait 5 seconds before retrying
    raise RuntimeError(f"Failed to open URL {url} after {retries} attempts.")

#This is the function we use to open json files. We use this when we scrape APIs
def open_json(url):
    retries = 0
    while retries < 3:
        try:
            req = urllib.request.Request(url, headers=headers)
            data = json.loads(urllib.request.urlopen(req).read())
            return data
        except Exception as e:
            retries += 1
            print(f"Failed to open url {url} due to error {e}. \n Available retries: {retries}")
            if retries == 3:
                raise RuntimeError (f"Failed to open URL {url} due to error {e} after 3 retries.")
            time.sleep(1)

#This is the function to download an image from a url and read it into a cv2 image. We use this to read the track maps when we generate the svg files for the track maps.
def imread_from_url(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Referer': 'https://www.statsf1.com/'
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        image_bytes = resp.read()

    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    return img, image_bytes

#This is the function to find the closest point on a contour to a given point. We use this to find the closest point on the track outline to the start/finish line when we generate the svg files for the track maps.
def closest_point_on_contours(contours, point):
    px, py = point
    min_dist = float("inf")
    closest = None
    closest_cnt = None
    idx = 0

    for cnt in contours:
        for i, p in enumerate(cnt):
            x, y = p[0]
            d = (x - px) ** 2 + (y - py) ** 2
            if d < min_dist:
                min_dist = d
                closest = (x, y)
                closest_cnt = cnt
                idx = i

    return closest, closest_cnt, idx

#This is the function to generate the svg file for the track map. We use this to generate the svg files for the track maps. 
# We use the track outline and the start/finish line to generate the svg file. 
# We also use the distance transform of the track mask to find the width of the track at each point, and we use this to generate a more accurate svg file.
def generate_track_svg(image_path):
    if image_path == "https://www.statsf1.com/images/GetImage.ashx?id=piste.avus":
        return """
            <svg width="1020" height="500" viewBox="0 0 1020 454" xmlns="http://www.w3.org/2000/svg" style="background: #111;">
            <polyline points="738,11 738,32 766,32 770,36 769,37 768,37 767,38 766,38 765,39 764,39 763,40 761,40 760,41 759,41 758,42 757,42 756,43 754,43 753,44 752,44 751,45 750,45 749,46 748,46 747,47 745,47 744,48 743,48 742,49 741,49 740,50 739,50 738,51 736,51 735,52 734,52 733,53 732,53 731,54 729,54 728,55 727,55 726,56 725,56 724,57 722,57 721,58 720,58 719,59 718,59 717,60 716,60 715,61 713,61 712,62 711,62 710,63 709,63 708,64 707,64 706,65 704,65 703,66 702,66 701,67 699,67 698,68 697,68 696,69 695,69 694,70 693,70 692,71 690,71 689,72 688,72 687,73 686,73 685,74 683,74 682,75 681,75 680,76 679,76 678,77 677,77 676,78 674,78 673,79 672,79 671,80 670,80 669,81 667,81 666,82 665,82 664,83 663,83 662,84 660,84 659,85 658,85 657,86 656,86 655,87 654,87 653,88 651,88 650,89 649,89 648,90 647,90 646,91 644,91 643,92 642,92 641,93 640,93 639,94 637,94 636,95 635,95 634,96 633,96 632,97 631,97 630,98 628,98 627,99 626,99 625,100 624,100 623,101 621,101 620,102 619,102 618,103 616,103 615,104 614,104 613,105 612,105 611,106 610,106 609,107 607,107 606,108 605,108 604,109 603,109 602,110 601,110 600,111 598,111 597,112 596,112 595,113 594,113 593,114 591,114 590,115 589,115 588,116 587,116 586,117 584,117 583,118 582,118 581,119 580,119 579,120 578,120 577,121 575,121 574,122 573,122 572,123 570,123 568,125 566,125 565,126 564,126 563,127 561,127 560,128 559,128 558,129 557,129 556,130 554,130 553,131 552,131 551,132 550,132 549,133 548,133 547,134 546,134 545,135 543,135 542,136 540,136 539,137 538,137 537,138 536,138 535,139 534,139 533,140 531,140 530,141 529,141 528,142 527,142 526,143 525,143 524,144 522,144 521,145 520,145 519,146 518,146 517,147 515,147 514,148 513,148 512,149 511,149 510,150 509,150 508,151 506,151 505,152 504,152 503,153 502,153 501,154 499,154 498,155 497,155 496,156 495,156 494,157 492,157 491,158 490,158 489,159 488,159 487,160 486,160 485,161 483,161 482,162 481,162 480,163 479,163 478,164 476,164 475,165 474,165 473,166 472,166 471,167 469,167 468,168 467,168 466,169 465,169 464,170 463,170 462,171 460,171 459,172 458,172 457,173 456,173 455,174 454,174 453,175 451,175 450,176 449,176 448,177 447,177 446,178 444,178 443,179 442,179 441,180 440,180 439,181 438,181 437,182 435,182 434,183 433,183 432,184 431,184 430,185 429,185 428,186 426,186 425,187 424,187 423,188 422,188 421,189 419,189 418,190 417,190 416,191 415,191 414,192 413,192 412,193 410,193 409,194 408,194 407,195 406,195 405,196 404,196 403,197 402,197 401,198 399,198 398,199 397,199 396,200 395,200 394,201 392,201 391,202 390,202 389,203 388,203 387,204 385,204 384,205 383,205 382,206 381,206 380,207 379,207 378,208 377,208 376,209 374,209 373,210 372,210 371,211 369,211 368,212 367,212 366,213 365,213 364,214 363,214 362,215 361,215 360,216 358,216 357,217 356,217 355,218 354,218 353,219 351,219 350,220 349,220 348,221 347,221 346,222 345,222 344,223 342,223 341,224 340,224 339,225 338,225 337,226 335,226 334,227 333,227 332,228 331,228 330,229 329,229 328,230 327,230 326,231 324,231 323,232 322,232 321,233 320,233 319,234 318,234 317,235 315,235 314,236 313,236 312,237 311,237 310,238 308,238 307,239 306,239 305,240 304,240 303,241 302,241 301,242 299,242 298,243 297,243 296,244 295,244 294,245 293,245 292,246 290,246 289,247 288,247 287,248 286,248 285,249 284,249 283,250 281,250 280,251 279,251 278,252 277,252 276,253 275,253 274,254 272,254 271,255 270,255 269,256 268,256 267,257 266,257 265,258 263,258 262,259 261,259 260,260 259,260 258,261 256,261 255,262 254,262 253,263 252,263 251,264 250,264 249,265 247,265 246,266 245,266 244,267 243,267 242,268 241,268 240,269 238,269 237,270 236,270 235,271 234,271 233,272 231,272 230,273 229,273 228,274 227,274 226,275 225,275 224,276 223,276 222,277 220,277 219,278 218,278 217,279 216,279 215,280 214,280 213,281 212,281 211,282 210,282 209,283 208,283 207,284 206,284 205,285 204,285 203,286 202,286 201,287 200,287 199,288 198,288 197,289 196,289 195,290 194,290 193,291 192,291 191,292 189,292 188,293 187,293 186,294 185,294 184,295 183,295 182,296 181,296 180,297 179,297 178,298 177,298 176,299 175,299 174,300 173,300 172,301 171,301 170,302 169,302 168,303 167,303 166,304 165,304 164,305 163,305 162,306 161,306 160,307 159,307 158,308 157,308 156,309 154,309 153,310 152,310 151,311 150,311 149,312 148,312 147,313 146,313 145,314 144,314 143,315 142,315 141,316 140,316 139,317 138,317 137,318 136,318 135,319 134,319 133,320 132,320 131,321 130,321 129,322 128,322 127,323 126,323 125,324 123,324 122,325 121,325 120,326 119,326 118,327 117,327 116,328 115,328 114,329 113,329 112,330 111,330 110,331 109,331 108,332 107,332 106,333 105,333 104,334 103,334 102,335 101,335 100,336 99,336 98,337 97,337 96,338 95,338 94,339 93,339 92,340 91,340 90,341 89,341 88,342 87,342 86,343 84,343 83,344 82,344 81,345 80,345 79,346 78,346 77,347 76,347 75,348 74,348 73,349 72,349 71,350 70,350 69,351 68,351 67,352 66,352 65,353 64,353 63,354 62,354 61,355 60,355 59,356 58,356 57,357 55,357 54,358 53,358 52,359 50,359 49,360 47,360 46,361 44,361 43,362 41,362 40,363 37,363 36,364 34,364 33,365 32,365 31,366 29,366 28,367 26,367 24,369 23,369 22,370 21,370 19,372 19,373 18,374 18,381 19,382 19,383 20,384 20,385 21,385 22,386 24,386 25,387 38,387 39,386 42,386 43,385 44,385 45,384 46,384 47,383 48,383 49,382 50,382 51,381 52,381 53,380 54,380 55,379 56,379 57,378 58,378 59,377 60,377 61,376 62,376 63,375 65,375 66,374 67,374 68,373 69,373 70,372 71,372 72,371 73,371 74,370 75,370 76,369 77,369 78,368 79,368 80,367 81,367 82,366 83,366 84,365 85,365 86,364 87,364 88,363 89,363 90,362 91,362 92,361 93,361 94,360 95,360 96,359 97,359 98,358 99,358 100,357 101,357 102,356 103,356 104,355 106,355 107,354 108,354 109,353 110,353 111,352 112,352 113,351 114,351 115,350 116,350 117,349 118,349 119,348 120,348 121,347 122,347 123,346 124,346 125,345 126,345 127,344 128,344 129,343 130,343 131,342 132,342 133,341 134,341 135,340 136,340 137,339 138,339 139,338 140,338 141,337 142,337 143,336 144,336 145,335 147,335 148,334 149,334 150,333 151,333 152,332 153,332 154,331 155,331 156,330 157,330 158,329 159,329 160,328 161,328 162,327 163,327 164,326 165,326 166,325 167,325 168,324 169,324 170,323 171,323 172,322 173,322 174,321 175,321 176,320 177,320 178,319 179,319 180,318 181,318 182,317 184,317 186,315 188,315 189,314 190,314 191,313 192,313 193,312 194,312 195,311 196,311 197,310 198,310 199,309 200,309 201,308 202,308 203,307 204,307 205,306 206,306 207,305 208,305 209,304 210,304 211,303 212,303 213,302 214,302 215,301 216,301 217,300 218,300 219,299 220,299 221,298 222,298 223,297 224,297 225,296 226,296 227,295 228,295 229,294 230,294 231,293 233,293 234,292 235,292 236,291 237,291 238,290 239,290 240,289 242,289 243,288 244,288 245,287 246,287 247,286 249,286 250,285 251,285 252,284 253,284 254,283 255,283 256,282 258,282 259,281 260,281 261,280 262,280 263,279 264,279 265,278 267,278 268,277 269,277 270,276 271,276 272,275 274,275 275,274 276,274 277,273 278,273 279,272 280,272 281,271 283,271 284,270 285,270 286,269 287,269 288,268 290,268 291,267 292,267 293,266 294,266 295,265 297,265 298,264 299,264 300,263 301,263 302,262 304,262 305,261 306,261 307,260 308,260 309,259 310,259 311,258 313,258 314,257 315,257 316,256 317,256 318,255 320,255 321,254 322,254 323,253 324,253 325,252 327,252 328,251 329,251 330,250 331,250 332,249 333,249 334,248 336,248 337,247 338,247 339,246 340,246 341,245 343,245 344,244 345,244 346,243 347,243 348,242 349,242 350,241 352,241 353,240 354,240 355,239 356,239 357,238 358,238 359,237 361,237 362,236 363,236 364,235 366,235 367,234 368,234 369,233 370,233 371,232 372,232 373,231 375,231 376,230 377,230 378,229 379,229 380,228 381,228 382,227 384,227 385,226 386,226 387,225 388,225 389,224 391,224 392,223 393,223 394,222 395,222 396,221 397,221 398,220 400,220 401,219 402,219 403,218 404,218 405,217 406,217 407,216 409,216 410,215 411,215 412,214 413,214 414,213 416,213 417,212 418,212 419,211 420,211 421,210 423,210 424,209 425,209 426,208 427,208 428,207 429,207 430,206 432,206 433,205 434,205 435,204 436,204 437,203 439,203 440,202 441,202 442,201 443,201 444,200 445,200 446,199 448,199 449,198 450,198 451,197 452,197 453,196 455,196 456,195 457,195 458,194 459,194 460,193 462,193 463,192 464,192 465,191 466,191 467,190 468,190 469,189 471,189 472,188 473,188 474,187 475,187 476,186 477,186 478,185 480,185 481,184 482,184 483,183 484,183 485,182 487,182 488,181 489,181 490,180 491,180 492,179 494,179 495,178 496,178 497,177 498,177 499,176 500,176 501,175 503,175 504,174 505,174 506,173 507,173 508,172 510,172 511,171 512,171 513,170 515,170 516,169 517,169 518,168 519,168 520,167 521,167 522,166 524,166 525,165 526,165 527,164 529,164 530,163 531,163 532,162 533,162 534,161 536,161 537,160 538,160 539,159 540,159 541,158 543,158 544,157 545,157 546,156 547,156 548,155 550,155 551,154 552,154 553,153 554,153 555,152 556,152 557,151 558,151 559,150 561,150 562,149 563,149 564,148 566,148 567,147 568,147 569,146 570,146 571,145 572,145 573,144 575,144 576,143 577,143 578,142 579,142 580,141 582,141 583,140 584,140 585,139 586,139 587,138 588,138 589,137 591,137 592,136 593,136 594,135 595,135 596,134 597,134 598,133 600,133 601,132 602,132 603,131 605,131 606,130 607,130 608,129 609,129 610,128 611,128 612,127 614,127 615,126 616,126 617,125 618,125 619,124 621,124 622,123 623,123 624,122 625,122 626,121 628,121 629,120 630,120 631,119 632,119 633,118 635,118 636,117 637,117 638,116 639,116 640,115 642,115 643,114 644,114 645,113 646,113 647,112 648,112 649,111 651,111 652,110 653,110 654,109 655,109 656,108 658,108 659,107 660,107 661,106 662,106 663,105 665,105 666,104 667,104 668,103 669,103 670,102 672,102 673,101 674,101 675,100 676,100 677,99 678,99 679,98 681,98 682,97 683,97 684,96 686,96 687,95 688,95 689,94 690,94 691,93 692,93 693,92 694,92 695,91 697,91 698,90 699,90 700,89 701,89 702,88 704,88 705,87 706,87 707,86 709,86 710,85 711,85 712,84 713,84 714,83 715,83 716,82 718,82 719,81 720,81 721,80 722,80 723,79 725,79 726,78 727,78 728,77 729,77 730,76 732,76 733,75 734,75 735,74 736,74 737,73 739,73 740,72 741,72 742,71 743,71 744,70 745,70 746,69 748,69 749,68 750,68 751,67 752,67 753,66 755,66 756,65 757,65 758,64 759,64 760,63 761,63 762,62 764,62 765,61 766,61 767,60 769,60 770,59 771,59 772,58 773,58 774,57 775,57 776,56 779,56 780,55 783,55 784,54 787,54 788,53 791,53 792,52 797,52 798,53 799,52 804,52 805,53 809,53 810,54 814,54 815,55 818,55 819,56 821,56 822,57 824,57 825,58 828,58 829,59 831,59 832,60 834,60 835,61 837,61 838,62 840,62 841,63 843,63 844,64 847,64 848,65 850,65 851,66 855,66 856,67 869,67 870,66 872,66 875,63 876,63 878,61 878,60 879,59 879,58 881,56 881,53 882,52 882,40 881,39 881,38 880,37 880,36 879,35 879,34 878,33 878,32 872,26 871,26 868,23 867,23 866,22 864,22 863,21 860,21 859,20 833,20 832,21 826,21 825,22 820,22 819,23 814,23 813,24 810,24 809,25 806,25 805,26 803,26 802,27 798,27 797,28 795,28 794,29 792,29 791,30 788,30 787,31 785,31 784,32 783,32 782,33 780,33 779,34 776,34 775,35 773,35 772,36 767,31 767,11" fill="none" stroke="white" stroke-width="4"></polyline>
            <polygon points="694,48 691,51 690,51 688,53 687,53 684,56 683,56 683,58 686,58 687,57 690,57 691,56 694,56 695,55 699,55 699,53 698,53 697,52 697,51 696,50 696,48" fill="#FF0000"></polygon>
            </svg>
        """
    
    img, _ = imread_from_url(image_path)
    if img is None:
        print(f"Error: Could not load image {image_path}")
        return ""

    h, w = img.shape[:2]
    h = h + 50
    w = w + 100
    svg_elements = []

    # 1. Track outline (white / grey)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, white_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
    
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

    if track_contours:
        svg_elements.append('<g fill="none" stroke="white" stroke-width="4">')
        for cnt in track_contours:
            if cv2.contourArea(cnt) < 100:
                continue
            epsilon = 0.8
            approx = cv2.approxPolyDP(cnt, epsilon, True)
            points = " ".join([f"{int(p[0][0])},{int(p[0][1])}" for p in approx])
            svg_elements.append(f'<polyline points="{points}" />')
        svg_elements.append('</g>')

    # 2. Arrow Detection
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_red1 = np.array([0, 150, 80])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([170, 150, 80])
    upper_red2 = np.array([180, 255, 255])
    
    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    red_mask = cv2.bitwise_or(mask1, mask2)
    
    kernel = np.ones((3,3), np.uint8)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)
    red_contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if not red_contours:
        lower_red_lenient1 = np.array([0, 120, 60])
        lower_red_lenient2 = np.array([170, 120, 60])
        mask_lenient = cv2.bitwise_or(
            cv2.inRange(hsv, lower_red_lenient1, upper_red1),
            cv2.inRange(hsv, lower_red_lenient2, upper_red2)
        )
        mask_lenient = cv2.morphologyEx(mask_lenient, cv2.MORPH_OPEN, kernel)
        red_contours, _ = cv2.findContours(mask_lenient, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in red_contours:
        area = cv2.contourArea(cnt)
        if area < 30: continue

        M = cv2.moments(cnt)
        if M["m00"] != 0:
            cx = int(M["m10"]/M["m00"])
            cy = int(M["m01"]/M["m00"])
            if 0 <= cy < dist_transform.shape[0] and 0 <= cx < dist_transform.shape[1]:
                if dist_transform[cy, cx] > 60:
                    continue
        
        hull = cv2.convexHull(cnt)
        hull_area = cv2.contourArea(hull)
        solidity = float(area)/hull_area if hull_area > 0 else 0
        
        epsilon = 0.04 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, epsilon, True)
        vertices = len(approx)
        
        if (0.5 < solidity < 0.95 and 3 <= vertices <= 7) or area > 50: 
             points = " ".join([f"{p[0][0]},{p[0][1]}" for p in cnt])
             svg_elements.append(f'<polygon points="{points}" fill="#FF0000" />')

    svg_content = (
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'xmlns="http://www.w3.org/2000/svg" style="background: #111;">\n'
    )
    for element in svg_elements:
        svg_content += f"  {element}\n"
    svg_content += '</svg>'
    
    return svg_content

#This function gets the birthdate and nationality of a driver from their statsf1.com page. 
def fetch_driver_info(driver_name):
    # Convert "George Russell" → "george-russell"
    slug = normalize_name(driver_name).replace(" ", "-")
    url = f"https://www.statsf1.com/en/{slug}.aspx"

    open_url(url)  # You provide this and it returns a BeautifulSoup object

    # --- Nationality ---
    nationality_tag = soup.find("a", id="ctl00_CPH_Main_HL_Pays")
    nationality = nationality_tag.text.strip() if nationality_tag else None
    # Normalise French/other localized names to English equivalents
    if nationality:
        if nationality == "Irlande":
            nationality = "Ireland"

    # --- Birthdate ---
    birthdate = None
    birth_field = soup.find("div", class_="field", string=re.compile(r"Born the"))
    if not birth_field:
        for div in soup.find_all("div", class_="field"):
            if "Born the" in div.text:
                birth_field = div
                break

    if birth_field:
        match = re.search(r"Born the ([0-9]{1,2} [a-zA-Z]+ [0-9]{4})", birth_field.text)
        if match:
            try:
                birthdate_obj = datetime.datetime.strptime(match.group(1), "%d %B %Y")
                birthdate = birthdate_obj.strftime("%Y-%m-%d")
            except ValueError:
                print(f"Date format error for {driver_name}: {match.group(1)}")

    return nationality, birthdate


#This function parses the points system from the statsf1.com seasons page.
def parse_points_system(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')

    drivers_info = {
        "scores": "All Scores",
        "pointssharedforsharedcars": False,
        "grandprix": {},
        "sprint": None
    }

    constructors_info = {
        "scores": "All Scores",
        "topscoring": False,
        "grandprix": {},
        "sprint": None
    }

    drivers_found = False
    constructors_found = False

    for section in soup.find_all('div', class_='aligncenter'):
        table = section.find('table', class_='bareme')
        if not table:
            continue

        rows = table.find_all('tr')
        full_text = section.get_text(separator=' ').lower()

        # -------- DRIVERS --------
        if not drivers_found and not constructors_found:
            drivers_found = True

            # Get all score-related lines before the table
            score_lines = []
            for elem in section.contents:
                if getattr(elem, 'name', None) == 'table':
                    break
                if isinstance(elem, str):
                    line = elem.strip()
                    if "score" in line.lower():
                        score_lines.append(line)
            drivers_info["scores"] = "\n".join(score_lines) if score_lines else "All Scores"

            if "points shared for shared drives" in full_text:
                drivers_info["pointssharedforsharedcars"] = True

            if len(rows) == 2:
                # Use header row to determine keys
                header_cells = [cell.get_text(strip=True) for cell in rows[0].find_all('td')[1:]]
                point_cells = rows[1].find_all('td')[1:]
                for header, cell in zip(header_cells, point_cells):
                    header_clean = re.sub(r'\s*\d+(st|nd|rd|th)?\.?$', '', header, flags=re.IGNORECASE)
                    value = cell.get_text(strip=True).replace("*", "")
                    # Use header as key, or map to integer if it's a position
                    if header_clean.lower().startswith('fastest'):
                        if "(* only by finishing in the top ten)" or "(* only by finishing in the top 10)" in full_text:
                            key = "Fastest Lap (only for finishing in the top 10)"
                        else:
                            key = "Fastest Lap"
                        drivers_info["grandprix"][key] = value
                    else:
                        # Try to extract the position number
                        match = re.match(r'(\d+)', header)
                        key = match.group(1) if match else header
                    drivers_info["grandprix"][key] = int(value) if value.isdigit() else 0

            if len(rows) >= 3:
                # Use header row to determine keys
                header_cells = [cell.get_text(strip=True) for cell in rows[0].find_all('td')[1:]]
                point_cells = rows[1].find_all('td')[2:]
                for header, cell in zip(header_cells, point_cells):
                    header_clean = re.sub(r'\s*\d+(st|nd|rd|th)?\.?$', '', header, flags=re.IGNORECASE)
                    value = cell.get_text(strip=True).replace("*", "")
                    # Use header as key, or map to integer if it's a position
                    if header_clean.lower().startswith('fastest'):
                        if "(* only by finishing in the top ten)" or "(* only by finishing in the top 10)" in full_text:
                            key = "Fastest Lap (only for finishing in the top 10)"
                        else:
                            key = "Fastest Lap"
                        drivers_info["grandprix"][key] = value
                    else:
                        # Try to extract the position number
                        match = re.match(r'(\d+)', header)
                        key = match.group(1) if match else header
                    drivers_info["grandprix"][key] = int(value) if value.isdigit() else 0                
                drivers_info["sprint"] = {}
                for i, cell in enumerate(rows[2].find_all('td')[2:], start=1):
                    value = cell.get_text(strip=True)
                    if value != "":
                        drivers_info["sprint"][str(i)] = int(value) if value.isdigit() else 0

        # -------- CONSTRUCTORS --------
        elif not constructors_found and drivers_found:
            constructors_found = True

            constructor_score_lines = []
            for elem in section.contents:
                if getattr(elem, 'name', None) == 'table':
                    break
                if isinstance(elem, str):
                    line = elem.strip()
                    if "score" in line.lower():
                        constructor_score_lines.append(line)
            constructors_info["scores"] = "\n".join(constructor_score_lines) if constructor_score_lines else "All Scores"

            if "point only for highest placed car" in full_text:
                constructors_info["topscoring"] = True

            if len(rows) == 2:
                # Use header row to determine keys (skip only the first column for constructors)
                header_cells = [cell.get_text(strip=True) for cell in rows[0].find_all('td')[1:]]
                point_cells = rows[1].find_all('td')[1:]
                for header, cell in zip(header_cells, point_cells):
                    header_clean = re.sub(r'\s*\d+(st|nd|rd|th)?\.?$', '', header, flags=re.IGNORECASE)
                    value = cell.get_text(strip=True).replace("*", "")
                    if header_clean.lower().startswith('fastest'):
                        if "(* only by finishing in the top ten)" or "(* only by finishing in the top 10)" in full_text:
                            key = "Fastest Lap (only for finishing in the top 10)"
                        else:
                            key = "Fastest Lap"
                        drivers_info["grandprix"][key] = value
                    else:
                        match = re.match(r'(\d+)', header)
                        key = match.group(1) if match else header
                    constructors_info["grandprix"][key] = int(value) if value.isdigit() else 0

            if len(rows) >= 3:
                # Use header row to determine keys (skip only the first column for constructors)
                header_cells = [cell.get_text(strip=True) for cell in rows[0].find_all('td')[1:]]
                point_cells = rows[1].find_all('td')[2:]
                for header, cell in zip(header_cells, point_cells):
                    header_clean = re.sub(r'\s*\d+(st|nd|rd|th)?\.?$', '', header, flags=re.IGNORECASE)
                    value = cell.get_text(strip=True).replace("*", "")
                    if header_clean.lower().startswith('fastest'):
                        if "(* only by finishing in the top ten)" or "(* only by finishing in the top 10)" in full_text:
                            key = "Fastest Lap (only for finishing in the top 10)"
                        else:
                            key = "Fastest Lap"
                        drivers_info["grandprix"][key] = value
                    else:
                        match = re.match(r'(\d+)', header)
                        key = match.group(1) if match else header
                    constructors_info["grandprix"][key] = int(value) if value.isdigit() else 0                
                constructors_info["sprint"] = {}
                for i, cell in enumerate(rows[2].find_all('td')[1:], start=1):
                    value = cell.get_text(strip=True)
                    if value != "":
                        constructors_info["sprint"][str(i)] = int(value) if value.isdigit() else 0

    # Fallback if nothing found
    if not drivers_found:
        print("Drivers' points table not found.")
        return None, None

    if not constructors_found:
        print("Constructors' points table not found.")
        return drivers_info, {}

    return drivers_info, constructors_info

def extract_regulations_notes(span):
    """
    Extracts only the textual notes from the regulations <span>, before the 'Regulations' label or <table>.
    """
    notes = []
    for element in span.contents:
        if element.name == 'br':
            continue
        if isinstance(element, str):
            stripped = element.strip()
            if stripped:
                notes.append(stripped)
        elif element.name == 'strong' and 'regulations' in element.get_text(strip=True).lower():
            break  # Stop when we hit the start of the actual 'Regulations' section
        else:
            break  # Stop at anything else unexpected (e.g., table)
    return notes if notes else None

def standardize_circuit_name_with_year(circuit, year):
    """
    Converts a circuit name to its original/standard name based on the year F1 raced there.
    Only applies name changes for the specific years the circuit actually hosted F1.
    
    Args:
        circuit (str): The circuit name
        year (int): The year F1 raced at the circuit
        
    Returns:
        str: The circuit name during that specific year
    """
    
    # AUSTRIA - Red Bull Ring / Österreichring / A1-Ring / Zeltweg
    if circuit == "Red Bull Ring":
        if 1970 <= year <= 1987:
            circuit = "Österreichring"
        elif 1997 <= year <= 2003:
            circuit = "A1-Ring"
        elif year >= 2014:
            circuit = "Red Bull Ring"
        elif year == 1964:
            circuit = "Zeltweg Airfield"
    
    # MEXICO - Autódromo Hermanos Rodríguez / Magdalena Mixhuca
    if circuit == "Autódromo Hermanos Rodríguez":
        if 1963 <= year <= 1970:
            circuit = "Autódromo Magdalena Mixhuca"
        elif year >= 1986:
            circuit = "Autódromo Hermanos Rodríguez"
    
    # CANADA - Canadian Tire Motorsport Park / Mosport Park
    elif circuit == "Canadian Tire Motorsport Park":
        if 1967 <= year <= 1977:
            circuit = "Mosport Park"
        elif year >= 2007:
            circuit = "Canadian Tire Motorsport Park"
    
    elif circuit == "Mosport Park":
        if 1967 <= year <= 1977:
            circuit = "Mosport Park"
        elif year >= 2007:
            circuit = "Canadian Tire Motorsport Park"
    
    # BRAZIL - Autódromo José Carlos Pace / Interlagos
    elif circuit == "Autódromo José Carlos Pace":
        if 1973 <= year <= 1989:
            circuit = "Autódromo de Interlagos"
        elif year >= 1990:
            circuit = "Autódromo José Carlos Pace"
    
    #BRAZIL - Autódromo Internacional Nelson Piquet/ Autódromo de Jacarepaguá
    elif circuit == "Autódromo Internacional Nelson Piquet":
        if 1978 <= year <= 1987:
            circuit = "Autódromo de Jacarepaguá"
        elif 1988 <= year:
            circuit = "Autódromo Internacional Nelson Piquet"
    
    # ITALY (IMOLA) - Autodromo Enzo e Dino Ferrari / Autodromo Dino Ferrari
    elif circuit == "Autodromo Internazionale Enzo e Dino Ferrari":
        if 1980 <= year <= 1987:
            circuit = "Autodromo Dino Ferrari"
        elif year >= 1988:
            circuit = "Autodromo Enzo e Dino Ferrari"
    
    #JAPAN - TI Circuit Aida / Okayama International Circuit
    elif circuit == "Okayama International Circuit":
        if 1994 <= year <= 1995:
            circuit = "TI Circuit Aida"
        elif year >= 2005:
            circuit = "Okayama International Circuit"
    #ARGENTINA - Autódromo Oscar y Juan Gálvez / Autódromo 17 de Octubre
    elif circuit == "Autódromo Juan y Oscar Gálvez":
        if 1952 <= year <= 1954:
            circuit = "Autódromo 17 de Octubre"
        elif 1955 <= year <= 1960:
            circuit = "Autódromo Municipal Ciudad de Buenos Aires"
        elif 1961 <= year <= 1989:
            circuit = "Autódromo Municipal del Parque Almirante Brown de la Ciudad de Buenos Aires"
        elif year >= 1995:
            circuit = "Autódromo Oscar Alfredo Gálvez"
    #FRANCE - rename
    elif circuit == "Charade Circuit":
        circuit = "Circuit de Charade"
    # CANADA (MONTREAL) - Circuit Gilles Villeneuve / Circuit Île Notre-Dame
    elif circuit == "Circuit Gilles Villeneuve":
        if year == 1978:
            circuit = "Circuit Île Notre-Dame"
        elif year >= 1982:
            circuit = "Circuit Gilles Villeneuve"
    
    elif circuit == "Circuit Île Notre-Dame":
        if year == 1978:
            circuit = "Circuit Île Notre-Dame"
        elif year >= 1982:
            circuit = "Circuit Gilles Villeneuve"
    
    # TURKEY - Istanbul Park / Istanbul Otodrom
    elif circuit == "Istanbul Park":
        if 2005 <= year <= 2011:
            circuit = "Istanbul Otodrom"
        elif 2020 <= year <= 2021:
            circuit = "Istanbul Park"
    
    # RUSSIA - Sirius Autodrom / Sochi Autodrom (F1 only raced 2014-2021)
    elif circuit == "Sirius Autodrom":
        if 2014 <= year <= 2021:
            circuit = "Sochi Autodrom"
        # Note: Sirius Autodrom is post-2024 rename, F1 never raced there
    
    elif circuit == "Sochi Autodrom":
        if 2014 <= year <= 2021:
            circuit = "Sochi Autodrom"
    
    # AZERBAIJAN - Baku City Circuit (circuit name never changed, only race name)
    # 2016: European Grand Prix
    # 2017+: Azerbaijan Grand Prix
    # Circuit name remained "Baku City Circuit" throughout
    
    return circuit

# =========================
# Driver matching utilities
# =========================

def compute_best_time_from_lapdata(lap_json):
    """
    Return the best (minimum) lap time in seconds from a TracingInsights laptimes JSON.
    Returns None if no valid times found.
    """
    times = []
    for t in lap_json.get("time", []):
        if t in (None, "None"):
            continue
        try:
            times.append(float(Decimal(str(t)).quantize(Decimal('0.001'))))
        except Exception:
            continue
    return min(times) if times else None


def generate_abbr_from_name(fullname, existing_abbrs):
    """
    Generate a deterministic, unique 3-letter abbreviation from a driver's full name.
    Disambiguates shared surnames (LEC → LEL), then given-name fallback.
    """
    parts = [p for p in fullname.split() if p]
    if not parts:
        raise ValueError("Empty name for abbreviation")

    surname = parts[-1].upper()
    given = parts[0].upper()

    # Base: first 3 letters of surname
    base = (surname + "XXX")[:3]
    if base not in existing_abbrs:
        return base

    # Replace 3rd character with later surname letters
    for i in range(2, len(surname)):
        cand = surname[:2] + surname[i]
        if cand not in existing_abbrs:
            return cand

    # Fallback: surname + given initial
    cand = (surname[:2] + given[0])[:3]
    if cand not in existing_abbrs:
        return cand

    raise ValueError(f"Unable to generate unique abbreviation for {fullname}")


def match_tracing_abbr_to_entrant(
    abbr,
    entrants,
    tracing_lap_json=None,
    f1_best_times=None,
    lap_by_lap_map=None,
    tracing_team=None,
):
    """
    Match a TracingInsights driver abbreviation to a session entrant.

    Matching priority:
    1) Existing lap_by_lap / race / sprint mapping (authoritative)
    2) Best lap time match (±0.05s)
    3) Direct entrant code comparison
    4) Deterministic abbreviation generation
    4.5) Initial + surname-prefix + team (guarded, handles 'de Vries' → DEV)
    5) Team-only (ONLY if unique, excluding already-mapped drivers)
    Otherwise → raise ValueError
    """

    abbr = abbr.upper()

    # --------------------------------
    # Track already-mapped drivers
    # --------------------------------
    already_mapped_drivers = set()
    if lap_by_lap_map:
        for v in lap_by_lap_map.values():
            already_mapped_drivers.add(normalize_name(v["driver"]))

    # -----------------
    # 1) Trusted mapping
    # -----------------
    if lap_by_lap_map and abbr in lap_by_lap_map:
        mapped_driver = normalize_name(lap_by_lap_map[abbr]["driver"])
        for e in entrants:
            if normalize_name(e.get("driver", "")) == mapped_driver:
                return e

    # -----------------
    # 2) Best lap match
    # -----------------
    tracing_best = (
        compute_best_time_from_lapdata(tracing_lap_json)
        if tracing_lap_json
        else None
    )

    if tracing_best is not None and f1_best_times:
        tol = 0.05
        time_keys = [
            k for k, t in f1_best_times.items()
            if t is not None and abs(float(t) - tracing_best) <= tol
        ]

        if len(time_keys) == 1:
            key = str(time_keys[0]).upper()
            for e in entrants:
                if (
                    str(e.get("driver", "")).upper() == key
                    or str(e.get("id", "")).upper() == key
                    or str(e.get("name", "")).upper() == key
                ):
                    return e

        if len(time_keys) > 1 and tracing_team:
            candidates = []
            for key in time_keys:
                key = str(key).upper()
                for e in entrants:
                    if (
                        (
                            str(e.get("driver", "")).upper() == key
                            or str(e.get("id", "")).upper() == key
                            or str(e.get("name", "")).upper() == key
                        )
                        and tracing_team.lower() in str(e.get("team", "")).lower()
                    ):
                        candidates.append(e)

            if len(candidates) == 1:
                return candidates[0]

            if len(candidates) > 1:
                raise ValueError(
                    f"Ambiguous best-lap match for {abbr} "
                    f"(team={tracing_team}): {[c.get('driver') for c in candidates]}"
                )

    # --------------------------------
    # 3) Direct entrant code comparison
    # --------------------------------
    for e in entrants:
        if str(e.get("driver", "")).upper() == abbr:
            return e

    # --------------------------------
    # 4) Deterministic abbreviation gen
    # --------------------------------
    entrants_sorted = sorted(
        entrants,
        key=lambda e: (e.get("name") or e.get("driver") or "").upper()
    )

    existing_abbrs = {
        str(e.get("driver")).upper()
        for e in entrants
        if isinstance(e.get("driver"), str) and len(e["driver"]) == 3
    }

    for e in entrants_sorted:
        name = e.get("name") or e.get("driver")
        cand = generate_abbr_from_name(
            str(normalize_name(name)), existing_abbrs
        )
        existing_abbrs.add(cand)
        if cand == abbr:
            return e

    # --------------------------------
    # 4.5) Initial + surname-prefix + team
    # --------------------------------
    if tracing_team:
        particles = {"de", "da", "di", "van", "von", "le", "la"}
        candidates = []

        for e in entrants:
            name = e.get("driver") or e.get("name")
            team = str(e.get("team", ""))

            if not name or tracing_team.lower() not in team.lower():
                continue

            norm = normalize_name(name)
            if norm in already_mapped_drivers:
                continue

            parts = norm.split()
            if len(parts) < 2:
                continue

            first_initial = parts[0][0]

            if parts[-2] in particles:
                last = parts[-2] + parts[-1]   # de + vries → devries
            else:
                last = parts[-1]

            last_two = last[:2]
            generated = (first_initial + last_two).upper()

            if generated == abbr:
                candidates.append(e)

        if len(candidates) == 1:
            return candidates[0]

        if len(candidates) > 1:
            raise ValueError(
                f"Ambiguous initial+surname match for {abbr} "
                f"(team={tracing_team}): {[c.get('driver') for c in candidates]}"
            )

    #TracingInsights, how do I contact you about how badly you have done the 2023 Hungarian Grand Prix? 😭
    '''
    {"drivers": [{"driver": "ARO", "team": "Red Bull Racing"}, {"driver": "BEG", "team": "Williams"}, {"driver": "OSU", "team": "AlphaTauri"}, 
    {"driver": "FOR", "team": "McLaren"}, {"driver": "FCO", "team": "Alpine"}, {"driver": "BOY", "team": "Red Bull Racing"}, 
    {"driver": "MON", "team": "Aston Martin"}, {"driver": "BRO", "team": "Ferrari"}, {"driver": "VIL", "team": "Aston Martin"}, 
    {"driver": "GRA", "team": "Haas F1 Team"}, {"driver": "COH", "team": "AlphaTauri"}, {"driver": "MAR", "team": "Williams"}, 
    {"driver": "MAN", "team": "Alfa Romeo"}, {"driver": "TBA", "team": "Haas F1 Team"}, {"driver": "SHI", "team": "Alpine"}, 
    {"driver": "HAM", "team": "Mercedes"}, {"driver": "SAI", "team": "Ferrari"}, {"driver": "RUS", "team": "Mercedes"}, 
    {"driver": "BOT", "team": "Alfa Romeo"}, {"driver": "PIA", "team": "McLaren"}]}
    '''
    if gp == "2023 Hungarian Grand Prix":
        for ent in entrants:
            if abbr == "FOR":
                if ent['driver'] == "Lando Norris":
                    return ent
            elif abbr == "BRO":
                if ent['driver'] == "Charles Leclerc":
                    return ent
            elif abbr == "MAN":
                if ent['driver'] == "Zhou Guanyu":
                    return ent
            elif abbr == "ARO":
                if ent['driver'] == "Max Verstappen":
                    return ent
            elif abbr == "BEG":
                if ent['driver'] == "Logan Sargeant":
                    return ent
            elif abbr == "BOY":
                if ent['driver'] == "Sergio Perez":
                    return ent
            elif abbr == "COH":
                if ent['driver'] == "Yuki Tsunoda":
                    return ent  
            elif abbr == "FCO":
                if ent['driver'] == "Pierre Gasly":
                    return ent    
            elif abbr == "GRA":
                if ent['driver'] == "Kevin Magnussen":
                    return ent
            elif abbr == "MAR":
                if ent['driver'] == "Alexander Albon":
                    return ent  
            elif abbr == "MON":
                if ent['driver'] == "Fernando Alonso":
                    return ent
            elif abbr == "OSU":
                if ent['driver'] == "Daniel Ricciardo":
                    return ent
            elif abbr == "SHI":
                if ent['driver'] == "Esteban Ocon":
                    return ent 
            elif abbr == "TBA":
                if ent['driver'] == "Nico Hülkenberg":
                    return ent  
            elif abbr == "VIL":
                if ent['driver'] == "Lance Stroll":
                    return ent   
        #one very easy practice session to analyse if you visit the tracinginsights site if you ask me!  
    '''
    {"drivers": [{"driver": "BAD", "team": "Red Bull Racing"}, {"driver": "GAS", "team": "Alpine"}, {"driver": "ANT", "team": "Mercedes"}, 
    {"driver": "ALO", "team": "Aston Martin"}, {"driver": "LEC", "team": "Ferrari"}, {"driver": "STR", "team": "Aston Martin"}, {"driver": "TSU", "team": "Red Bull Racing"}, 
    {"driver": "VOI", "team": "Williams"}, {"driver": "MAR", "team": "Kick Sauber"}, {"driver": "LAW", "team": "Racing Bulls"}, {"driver": "CHO", "team": "Haas F1 Team"}, 
    {"driver": "NOR", "team": "McLaren"}, {"driver": "HAM", "team": "Ferrari"}, {"driver": "CAM", "team": "Kick Sauber"}, 
    {"driver": "SAI", "team": "Williams"}, {"driver": "HAD", "team": "Racing Bulls"}, {"driver": "ARO", "team": "Alpine"}, {"driver": "RUS", "team": "Mercedes"}, 
    {"driver": "BEA", "team": "Haas F1 Team"}, {"driver": "DUN", "team": "McLaren"}]}
    '''
    if gp == "2025 Italian Grand Prix": 
        for en in entrants:
            if abbr == "BAD":
                if en['driver'] == "Max Verstappen":
                    return en #how do you even get your abbreviations? pain.      
            elif abbr == "VOI":
                if en['driver'] == "Alexander Albon":
                    return en
            elif abbr == "MAR":
                if en['driver'] == "Nico Hülkenberg":
                    return en            
            elif abbr == "CAM":
                if en['driver'] == "Gabriel Bortoleto":
                    return en            
            elif abbr == "CHO":
                if en['driver'] == "Esteban Ocon":
                    return en    
            
    # -------------------------
    # 5) Team-only (guarded!)
    # -------------------------
    if tracing_team:
        candidates = [
            e for e in entrants
            if (
                tracing_team.lower() in str(e.get("team", "")).lower()
                and normalize_name(e.get("driver", "") or e.get("name", ""))
                not in already_mapped_drivers
            )
        ]

        if len(candidates) == 1:
            return candidates[0]

        if len(candidates) > 1:
            raise ValueError(
                f"Ambiguous team-only match for {abbr} "
                f"(team={tracing_team}): {[c.get('driver') for c in candidates]}"
            )

    # -----------------
    # Final hard fail
    # -----------------
    raise ValueError(f"Could not match tracing abbreviation '{abbr}'")


def parse_regulations(html_content):
    """
    Parses the regulations for a given season from the provided HTML content.
    Groups technical regulations under their categories (e.g., 'Engine', 'Fuel').
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Find the regulations section
    regulations_section = soup.find('div', id='ctl00_CPH_Main_P_Note1', class_='yearinfo')
    if not regulations_section:
        print("Regulations section not found.")
        return None

    regulations = {}

    # Extract notes and tables
    regulations_notes = regulations_section.find('span', id='ctl00_CPH_Main_LB_Note1')
    if regulations_notes:
        notes = extract_regulations_notes(regulations_notes)
        regulations['notes'] = notes if notes else None

        # Find all tables in the span
        tables = regulations_notes.find_all('table')
        # If there are two tables, first is trophies, second is technical
        # If only one, it's technical
        tech_table = None
        if len(tables) == 2:
            # Trophies table (first)
            trophy_rows = tables[0].find_all('tr')
            for row in trophy_rows:
                cells = row.find_all('td')
                if len(cells) == 2:
                    key = cells[0].get_text(strip=True).rstrip(':')
                    value = cells[1].get_text(strip=True)
                    regulations[key] = value
            tech_table = tables[1]
        elif len(tables) == 1:
            tech_table = tables[0]

        # Parse technical regulations table
        if tech_table:
            rows = tech_table.find_all('tr')
            current_category = None
            for row in rows:
                th = row.find('th')
                if th and th.has_attr('colspan') and th['colspan'] == '2':
                    current_category = th.get_text(strip=True)
                    regulations[current_category] = {}
                else:
                    cells = row.find_all('td')
                    if len(cells) == 2:
                        key = cells[0].get_text(strip=True).rstrip(':')
                        value = cells[1].get_text(strip=True)
                        if current_category:
                            regulations[current_category][key] = value
                        else:
                            regulations[key] = value

    return regulations


def format_name_from_caps(raw_name):
    # Special case mappings for known corrections
    name_corrections = {
        "GIMMI BRUNI": "Gianmaria Bruni",
        "Gimmi Bruini": "Gianmaria Bruni",
        "Jose-Froilan Gonzalez": "José Froilán González",
        "Kimi Raikkonen": "Kimi Räikkönen",
        "Nico Hulkenberg": "Nico Hülkenberg",
        "Guanyu Zhou": "Zhou Guanyu"
    }
    
    # Check for exact matches (case-insensitive)
    for pattern, replacement in name_corrections.items():
        if raw_name.upper().replace("*", '') == pattern.upper():
            return replacement
    
    parts = raw_name.split()
    formatted = []

    for part in parts:
        # Handle apostrophes (O'Connor, d'Ambrosio, etc.)
        if "'" in part:
            subparts = part.split("'")
            formatted_subparts = []
            for i, subpart in enumerate(subparts):
                # Handle hyphens within each apostrophe-separated part
                hyphen_parts = subpart.split('-')
                formatted_hyphen_parts = []
                for hyphen_part in hyphen_parts:
                    if hyphen_part:  # Skip empty strings
                        formatted_hyphen_parts.append(format_subpart(hyphen_part))
                formatted_subparts.append('-'.join(formatted_hyphen_parts))
            part = "'".join(formatted_subparts)
        else:
            # Handle hyphenated parts (no apostrophe)
            subparts = part.split('-')
            formatted_subparts = []
            for subpart in subparts:
                if subpart:  # Skip empty strings
                    formatted_subparts.append(format_subpart(subpart))
            part = '-'.join(formatted_subparts)
        
        formatted.append(part)

    return " ".join(formatted).replace("*", '')


def format_subpart(subpart):
    """Helper function to format a single name part"""
    if not subpart:
        return subpart
    
    # Convert to lowercase first, then capitalize
    subpart = subpart.lower().capitalize()
    
    # Handle Mc/Mac prefix
    if subpart.startswith("Mc") and len(subpart) > 2:
        subpart = "Mc" + subpart[2].upper() + subpart[3:]
    elif subpart.startswith("Mac") and len(subpart) > 3:
        subpart = "Mac" + subpart[3].upper() + subpart[4:]
    
    return subpart


def parse_race_info(html_content, someelements):
    """
    Parses the race information from the given HTML content.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Initialize the race info dictionary
    race_info = {
        "race_number": None,
        "track_name": None,
        "date": None,
        "dateindatetime": someelements[1],
        "circuit_name": standardize_circuit_name_with_year(someelements[3], year),
        "laps": None,
        "circuit_distance": None,
        "weather": None,
        "notes": None
    }
    # Extract the race number
    race_number_tag = soup.find('h4')
    if race_number_tag:
        race_number_text = race_number_tag.get_text(strip=True)
        race_number = ''.join(filter(str.isdigit, race_number_text.split()[0]))
        race_info["race_number"] = int(race_number) if race_number.isdigit() else None

    # Extract the circuit name and date and lap info from GPinfo
    gpinfo_tag = soup.find('div', class_='GPinfo')
    if gpinfo_tag:
        gpinfo_text = gpinfo_tag.get_text(separator=' ', strip=True)

        # Extract circuit name (assumed to be the first word or phrase before a day/date)
        circuit_match = re.search(r'^(.*?)\s+(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),', gpinfo_text)
        if circuit_match:
            race_info["track_name"] = circuit_match.group(1).strip()
        

        # Extract date
        date_match = re.search(r'(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+\d{1,2}\s+\w+\s+\d{4}', gpinfo_text)
        if date_match:
            race_info["date"] = date_match.group(0)

        # Extract laps and circuit distance
        laps_dist_match = re.search(r'(\d+)\s+laps?\s*x\s*([\d.]+\s*km)', gpinfo_text)
        if laps_dist_match:
            race_info["laps"] = int(laps_dist_match.group(1))
            race_info["circuit_distance"] = laps_dist_match.group(2).strip()

    # Extract the weather
    weather_tag = soup.find('div', class_='GPmeteo')
    if weather_tag:
        img_tag = weather_tag.find('img')
        if img_tag:
            race_info["weather"] = img_tag.get('title', None)

    # Extract any notes
    notes_span = soup.find('span', id='ctl00_CPH_Main_LB_Commentaire')
    if notes_span:
        race_info["notes"] = notes_span.get_text(strip=True)
    else:
        race_info["notes"] = None

    return race_info


def parse_race_time(time_str):
    """Convert strings like '1hr 42m 06.304s' to total seconds (float)."""
    h = m = s = 0.0

    # Normalize variants like "1hr" to "1h"
    time_str = time_str.replace("hr", "h").replace("min", "m")

    match_h = re.search(r"(\d+)\s*h", time_str)
    match_m = re.search(r"(\d+)\s*m", time_str)
    match_s = re.search(r"([\d.]+)\s*s", time_str)

    if match_h:
        h = int(match_h.group(1))
    if match_m:
        m = int(match_m.group(1))
    if match_s:
        s = float(match_s.group(1))

    return float(Decimal(str(h * 3600 + m * 60 + s)).quantize(Decimal('0.001')))

def tts(t):
    parts = t.strip().split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return float(Decimal(str(int(hours) * 3600 + int(minutes) * 60 + float(seconds))).quantize(Decimal('0.001')))
    elif len(parts) == 2:
        minutes, seconds = parts
        return float(Decimal(str(int(minutes) * 60 + float(seconds))).quantize(Decimal('0.001')))
    elif len(parts) == 1:
        return float(Decimal(str(float(parts[0]))).quantize(Decimal('0.001'))) if parts[0].replace('.', '', 1).isdigit() else None
    else:
        return None


def parse_penalties(soup, is_sprint=False):
    penalties = []

    # Penalties during the race
    race_penalty_table = soup.find('table', id='ctl00_CPH_Main_GV_PenaltyP', class_='datatable')
    if race_penalty_table:
        rows = race_penalty_table.find('tbody').find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) == 3:
                penalties.append({
                    "driver": format_name_from_caps(cells[0].get_text(strip=True)),
                    "penalty": cells[1].get_text(strip=True),
                    "reason": cells[2].get_text(strip=True),
                    "type": "during_the_race",
                    "is_sprint": is_sprint
                })

    # Penalties after the race
    after_race_penalty_table = soup.find('table', id='ctl00_CPH_Main_GV_PenaltyA', class_='datatable')
    if after_race_penalty_table:
        rows = after_race_penalty_table.find('tbody').find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) == 4:
                penalties.append({
                    "driver": format_name_from_caps(cells[0].get_text(strip=True)),
                    "penalty": cells[1].get_text(strip=True),
                    "reason": cells[2].get_text(strip=True),
                    "lost_position": int(cells[3].get_text(strip=True)) if cells[3].get_text(strip=True).isdigit() else None,
                    "type": "added_after_chequered_flag",
                    "is_sprint": is_sprint
                })

    return penalties


def parse_statsf1_grid(soup, entrants, prefix="", return_metadata=False):
    """
    Extracts grid data (either main or sprint) and adds to entrants list.
    Prefix should be "" for main race, or "sprint" for sprint grid.
    """

    grid_field = f"{prefix}starting_grid_position"
    penalty_field = f"{prefix}gridpenalty"
    penalty_reason_field = f"{prefix}gridpenalty_reason"

    # 1. Grid positions
    grid_table = soup.find('table', id='ctl00_CPH_Main_TBL_Grille', class_='GPgrid')
    if grid_table:
        grid_divs = grid_table.find_all('div', id=lambda x: x and x.startswith('Grd'))
    # --- EXTRA METADATA ---
    pole_side = None
    grid_formation = None

    if grid_divs:
        # ---- GRID FORMATION ----
        rows = []

        for tr in grid_table.find_all("tr"):
            row_positions = []

            for div in tr.find_all("div", id=lambda x: x and x.startswith("Grd")):
                raw_text = div.get_text(strip=True)
                match = re.match(r"(\d+)\.", raw_text)
                if not match:
                    continue

                row_positions.append(int(match.group(1)))

            if row_positions:
                rows.append(row_positions)

        grid_formation = "-".join(str(len(r)) for r in rows)


        # ---- POLE SIDE ----
        first_row = rows[0] if rows else []

        if first_row:
            first_row_divs = [
                div for div in grid_divs
                if int(re.match(r'(\d+)\.', div.get_text(strip=True)).group(1)) in first_row
            ]

            if first_row_divs:
                if first_row_divs[0].get_text(strip=True).startswith("1."):
                    pole_side = "Left"
                else:
                    pole_side = "Right"
        if return_metadata:
            return pole_side, grid_formation
        for div in grid_divs:
            raw_text = div.get_text(strip=True)
            match = re.match(r'(\d+)\.', raw_text)
            if not match:
                continue
            grid_position = int(match.group(1))
            anchor = div.find('a')
            if anchor and 'title' in anchor.attrs:
                driver_name = anchor['title'].strip()
                for entrant in entrants:
                    if normalize_name(entrant['driver']) in normalize_name(format_name_from_caps(driver_name)):
                        entrant[grid_field] = grid_position
                        break

    # 2. Pit lane starters (from JavaScript)
    pitlane_script = soup.find('script', string=re.compile(r'var pitlane *= *\[.*?\];'))
    if pitlane_script:
        match = re.search(r'var pitlane *= *\[(.*?)\];', pitlane_script.string)
        if match:
            pitlane_ids = [int(i.strip()) for i in match.group(1).split(',') if i.strip().isdigit()]
            for pit_id in pitlane_ids:
                div = soup.find('div', id=f'Grd{pit_id}')
                if div:
                    anchor = div.find('a')
                    if anchor and 'title' in anchor.attrs:
                        driver_name = anchor['title'].strip()
                        for entrant in entrants:
                            if normalize_name(entrant['driver']) in normalize_name(format_name_from_caps(driver_name)):
                                entrant[grid_field] = None  # pit lane start
                                break

    # 3. Penalties table (if present)
    penalty_table = soup.find('table', id='ctl00_CPH_Main_GV_PenaltyG', class_='datatable')
    if penalty_table:
        rows = penalty_table.find('tbody').find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            if len(cells) == 3:
                driver_info = cells[0].get_text(strip=True)
                penalty = cells[1].get_text(strip=True)
                reason = cells[2].get_text(strip=True)
                driver_name = driver_info.split('(')[0].strip()
                for entrant in entrants:
                    if normalize_name(entrant['driver']) in normalize_name(format_name_from_caps(driver_name)):
                        entrant[penalty_field] = penalty
                        entrant[penalty_reason_field] = reason
                        if 'Start from pit lane' in penalty:
                            entrant[grid_field] = None
                        break


def fetch_race_report(gp):
    title = gp.replace(" ", "_")
    encoded = urllib.parse.quote(title)
    url = f"https://en.wikipedia.org/api/rest_v1/page/html/{encoded}"
    retries = 0
    while retries < 3:
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "F1DB/1.0"}
            )
        except Exception as e:
            print(f"Error creating request for {title}: {e}")
            retries += 1
        else:
            break
    #raise error if request creation failed after retries
    if retries == 3:
        raise ValueError(f"Failed to create request for {title} after multiple attempts")

    try:
        with urllib.request.urlopen(req) as response:
            html = response.read().decode("utf-8")
    except Exception as e:
        raise ValueError(f"Failed to fetch {title}: {e}")

    soup = BeautifulSoup(html, "html.parser")

    # 1. FIX SPACING: Inject spaces around inline tags so words don't merge
    for tag in soup.find_all(["a", "span", "b", "i"]):
        tag.insert_before(" ")
        tag.insert_after(" ")

    # 2. REMOVE CITATIONS: Remove all <sup> tags (the [1], [2] markers)
    for ref in soup.find_all("sup"):
        ref.decompose()


    temp_output = []

    # 3. SCRAPE: Iterate through the entire body for headers and paragraphs
    # Removing the "Section 0" filter allows us to see the whole article
    for elem in soup.find_all(["h2", "h3", "h4", "p"]):
        
        # Skip content inside tables, infoboxes, or references
        if elem.find_parent(["table", "aside", "cite", "footer"]):
            continue

        if elem.name.startswith("h"):
            header_text = elem.get_text(strip=True)
            
            level = "##" if elem.name == "h2" else "###"
            temp_output.append({"type": "header", "content": f"\n{level} {header_text}\n"})
        
        elif elem.name == "p":
            # Clean up extra whitespace from the space-injection step
            text = " ".join(elem.get_text().split())
            if text:
                temp_output.append({"type": "para", "content": text + "\n"})

    # 4. FILTER EMPTY HEADERS: Only keep a header if text follows it
    final_content = []
    for i, item in enumerate(temp_output):
        if item["type"] == "header":
            has_text_below = False
            for next_item in temp_output[i+1:]:
                if next_item["type"] == "para":
                    has_text_below = True
                    break
                if next_item["type"] == "header" and next_item["content"].startswith("\n## "):
                    # Stop looking if we hit a new major H2 section
                    break
            if has_text_below:
                final_content.append(item["content"])
        else:
            final_content.append(item["content"])

    content = "\n".join(final_content).strip()
    
    # Final cleanup of double spaces
    content = re.sub(r' +', ' ', content)

    if not content:
        raise ValueError(f"No usable content extracted for {title}")

    return content

def tts_to_normal(tts):
    if tts is None:
        return None
    # change 60.429 to 1:00.429
    minutes = int(tts / 60)
    seconds = float(Decimal(str(tts % 60)).quantize(Decimal('0.001')))
    return f"{minutes}:{seconds:06.3f}"

def assign_qualifying_positions_by_session(entrants, session_num):
    """
    Sorts entrants by qualifying session time and assigns positions.
    session_num: 1, 2, or 3 for qualifying1, qualifying2, qualifying3
    """
    time_key = f'qualifying{session_num}timeinseconds'
    position_key = f'qualifying{session_num}position'
    
    # Filter entrants with valid times in this session
    valid_entrants = [(i, ent) for i, ent in enumerate(entrants) 
                     if ent.get(time_key) is not None]
    
    # Sort by time (ascending - fastest first)
    valid_entrants.sort(key=lambda x: x[1][time_key])
    
    # Assign positions
    for position, (original_idx, ent) in enumerate(valid_entrants, start=1):
        entrants[original_idx][position_key] = position


def assign_sprint_qualifying_positions_by_session(entrants, session_num):
    """
    Sorts entrants by sprint qualifying session time and assigns positions.
    session_num: 1, 2, or 3 for sprint_qualifying1, sprint_qualifying2, sprint_qualifying3
    """
    time_key = f'sprint_qualifying{session_num}timeinseconds'
    position_key = f'sprint_qualifying{session_num}position'
    
    # Filter entrants with valid times in this session
    valid_entrants = [(i, ent) for i, ent in enumerate(entrants) 
                     if ent.get(time_key) is not None]
    
    # Sort by time (ascending - fastest first)
    valid_entrants.sort(key=lambda x: x[1][time_key])
    
    # Assign positions
    for position, (original_idx, ent) in enumerate(valid_entrants, start=1):
        entrants[original_idx][position_key] = position


def parse_race_results(links):
    parseprequalifyingflag = False
    """
    Parses the race results from the given links.
    """
    entrants = []
    abbreviations = {
        "ab": "Did not finish",
        "dsq": "Disqualified",
        "nc": "Not classified",
        "exc": "Excluded",
        "np": "Did not start",
        "f": "Withdrew",
        "nq": "Did not qualify",
        "tf": "Formation lap",
        "npq": "Did not pre-qualify",
        "t": "Substitute, third driver"
    }

    """    
    qualifying = []
    starting_grid = []
    race_results = []
    fastest_laps = []
    lap_by_lap = []"""
    sprintweekend = False
    for link in links:
        if link['href'].endswith('engages.aspx'):
            open_url(f"https://www.statsf1.com{link['href']}")
            table = soup.find('table', class_ = 'sortable')
            # Parse the table rows
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 8:  # Ensure there are enough columns
                    entrant = {
                        "number": int(cells[0].get_text(strip=True)),
                        "driver": format_name_from_caps(cells[1].get_text(strip=True)),
                        "team": cells[2].get_text(strip=True),
                        "constructor": cells[3].get_text(strip=True),
                        "chassis": cells[4].get_text(strip=True),
                        "engine": cells[5].get_text(strip=True),
                        "enginemodel": cells[6].get_text(strip=True),
                        "tyre": cells[7].get_text(strip=True),
                        "substituteorthirddriver": True if cells[1].get_text(strip=True).endswith('*') else False
                    }
                    if entrant['team'] == 'Privé':
                        entrant['team'] = 'Privateer'
                    entrants.append(entrant)
                    #print (entrants)
                    
        elif link['href'].endswith('/qualification.aspx'):
            open_url(f"https://www.statsf1.com{link['href']}")
            table = soup.find('table', class_ = 'datatable')
            # Parse the table rows
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 8:
                    for entrant in entrants:
                        #again normalise the diacritics to compare
                        if normalize_name(entrant['driver']) == normalize_name(format_name_from_caps(cells[1].get_text(strip=True))):
                            x = entrants.index(entrant)
                            #We are going to cross the values now.
                            entrant['qualifyingposition'] = int(cells[0].get_text(strip=True))
                            entrant['qualifyingtime'] = cells[4].get_text(strip=True).replace("'", ":")
                            entrant['qualifyinggap'] = cells[5].get_text(strip=True)
                            entrant['qualifyingtimeinseconds'] = tts(cells[4].get_text(strip=True).replace("'", ":"))
                            entrant['qualifyinggapseconds'] = tts(cells[5].get_text(strip=True))
                            entrants[x] = entrant                         
                            break  # Exit the loop once the entrant is found
        elif link['href'].endswith('/grille.aspx'):
            open_url(f"https://www.statsf1.com{link['href']}")
            parse_statsf1_grid(soup, entrants, prefix="")
        elif link['href'].endswith('/sprint.aspx?grille'):
            open_url(f"https://www.statsf1.com{link['href']}")
            parse_statsf1_grid(soup, entrants, prefix="sprint")
        elif link['href'].endswith('/meilleur-tour.aspx'):
            open_url(f"https://www.statsf1.com{link['href']}")
            table = soup.find('table', class_ = 'datatable')
            # Parse the table rows
            if table: #This line exists because the 2021 Belgian Grand Prix exists, even though it should not exist.
                rows = table.find('tbody').find_all('tr')
            else:
                break
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 8:
                    for entrant in entrants:
                        if normalize_name(entrant['driver']) == normalize_name(format_name_from_caps(cells[1].get_text(strip=True))):
                            x = entrants.index(entrant)
                            #We are going to cross the values now.
                            entrant['fastestlap'] = int(cells[0].get_text(strip=True)) if cells[0].get_text(strip=True).isdigit() else None
                            entrant['fastestlapinseconds'] = tts(cells[4].get_text(strip=True).replace("'", ":"))
                            entrant['fastestlapgapinseconds'] = tts(cells[5].get_text(strip=True))
                            entrant['fastestlap_time'] = cells[4].get_text(strip=True).replace("'", ":")
                            entrant['fastestlap_gap'] = cells[5].get_text(strip=True)
                            entrant['fastestlap_lap'] = int(cells[6].get_text(strip=True)) if cells[6].get_text(strip=True).isdigit() else None
                            entrants[x] = entrant 
                            break  # Exit the loop once the entrant is found
        elif link['href'].endswith('/sprint.aspx?mt'):
            open_url(f"https://www.statsf1.com{link['href']}")
            table = soup.find('table', class_ = 'datatable')
            # Parse the table rows
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) >= 8:
                    for entrant in entrants:
                        if normalize_name(entrant['driver']) == normalize_name(format_name_from_caps(cells[1].get_text(strip=True))):
                            x = entrants.index(entrant)
                            #We are going to cross the values now.
                            entrant['sprintfastestlap'] = int(cells[0].get_text(strip=True))
                            entrant['sprintfastestlapinseconds'] = tts(cells[4].get_text(strip=True).replace("'", ":"))
                            entrant['sprintfastestlapgapinseconds'] = tts(cells[5].get_text(strip=True))
                            entrant['sprintfastestlap_time'] = cells[4].get_text(strip=True).replace("'", ":")
                            entrant['sprintfastestlap_gap'] = cells[5].get_text(strip=True)
                            entrant['sprintfastestlap_lap'] = int(cells[6].get_text(strip=True))
                            entrants[x] = entrant  
                            break  # Exit the loop once the entrant is found                        
        elif link['href'].endswith('/qualifying/2'):
                entrant['qualifying2laps'] = None
                open_url(f"https://formula1.com{link['href']}")
                table = soup.find('table', class_ = 'Table-module_table__cKsW2')
                rows = table.find('tbody').find_all('tr')
                first_qualifying_time = None
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) == 5:
                        for entrant in entrants:
                            if entrant['number'] == int(cells[1].get_text(strip=True)) and not entrant['substituteorthirddriver']:
                                x = entrants.index(entrant)
                                entrant['qualifying2position'] = int(cells[0].get_text(strip=True))
                                entrant['qualifying2time'] = cells[4].get_text(strip=True)
                                t = tts(cells[4].get_text(strip=True))
                                entrant['qualifying2timeinseconds'] = float(Decimal(str(t)).quantize(Decimal('0.001'))) if t else None
                                entrant['qualifying2gap'] = float((Decimal(str(tts(first_qualifying_time))) - Decimal(str(t))).quantize(Decimal('0.001'))) if first_qualifying_time and t else None
                                entrant['qualifying2laps'] = None
                                entrants[x] = entrant
                                first_qualifying_time = cells[4].get_text(strip=True)
                                break
                    elif len(cells) == 6:
                        for entrant in entrants:
                            if entrant['number'] == int(cells[1].get_text(strip=True)) and not entrant['substituteorthirddriver']:
                                x = entrants.index(entrant)
                                entrant['qualifying2position'] = int(cells[0].get_text(strip=True)) if cells[0].text.strip().isdigit() else None
                                entrant['qualifying2time'] = cells[4].get_text(strip=True)
                                t = tts(cells[4].get_text(strip=True))
                                entrant['qualifying2timeinseconds'] = float(Decimal(str(t)).quantize(Decimal('0.001'))) if t else None
                                entrant['qualifying2gap'] = float((Decimal(str(tts(first_qualifying_time))) - Decimal(str(t))).quantize(Decimal('0.001'))) if first_qualifying_time and t else None
                                entrant['qualifying2laps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                                entrants[x] = entrant
                                first_qualifying_time = cells[4].get_text(strip=True)
                                break
        elif link['href'].endswith('/qualifying/1'):
            open_url(f"https://formula1.com{link['href']}")
            table = soup.find('table', class_ = 'Table-module_table__cKsW2')
            rows = table.find('tbody').find_all('tr')
            first_qualifying_time = None
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 5:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)) and not entrant['substituteorthirddriver']:
                            x = entrants.index(entrant)
                            entrant['qualifying1position'] = int(cells[0].get_text(strip=True))
                            entrant['qualifying1time'] = cells[4].get_text(strip=True)
                            t = tts(cells[4].get_text(strip=True))
                            entrant['qualifying1timeinseconds'] = float(Decimal(str(t)).quantize(Decimal('0.001'))) if t else None
                            entrant['qualifying1gap'] = float((Decimal(str(tts(first_qualifying_time))) - Decimal(str(t))).quantize(Decimal('0.001'))) if first_qualifying_time and t else None
                            entrants[x] = entrant
                            if entrant['qualifying1position'] == 1:
                                first_qualifying_time = cells[4].get_text(strip=True)
                            break
                elif len(cells) == 6:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)) and not entrant['substituteorthirddriver']:
                            x = entrants.index(entrant)
                            entrant['qualifying1position'] = int(cells[0].get_text(strip=True))
                            entrant['qualifying1time'] = cells[4].get_text(strip=True)
                            t = tts(cells[4].get_text(strip=True))
                            entrant['qualifying1timeinseconds'] = float(Decimal(str(t)).quantize(Decimal('0.001'))) if t else None
                            entrant['qualifying1gap'] = float((Decimal(str(tts(first_qualifying_time))) - Decimal(str(t))).quantize(Decimal('0.001'))) if first_qualifying_time and t else None
                            entrant['qualifying1laps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrants[x] = entrant
                            if entrant['qualifying1position'] == 1:
                                first_qualifying_time = cells[4].get_text(strip=True)
                            break                         
        elif link['href'].endswith('/qualifying/0'):
                open_url(f"https://formula1.com{link['href']}")
                table = soup.find('table', class_ = 'Table-module_table__cKsW2')          #soup.find('table', class_ = 'f1-table f1-table-with-data w-full')
                rows = table.find('tbody').find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) == 6:  
                        for entrant in entrants:
                            if entrant['number'] == int(cells[1].get_text(strip=True)) and not entrant['substituteorthirddriver']:
                                x = entrants.index(entrant)
                                entrant['qualifyinglaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                                entrants[x] = entrant
                                break 
        elif link['href'].endswith('/qualifying'):
            open_url(f"https://formula1.com{link['href']}")
            table = soup.find('table', class_ = 'Table-module_table__cKsW2')
            rows = table.find('tbody').find_all('tr')
            fastest_q1 = None
            fastest_q2 = None
            fastest_q3 = None
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 6:  #1996-2003 qualifying format
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)) and not entrant['substituteorthirddriver']:
                            x = entrants.index(entrant)
                            entrant['qualifyinglaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrants[x] = entrant
                            break
                elif len(cells) == 8: #current qualifying format
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)) and not entrant['substituteorthirddriver']:
                            x = entrants.index(entrant)
                            t1 = tts(cells[4].get_text(strip=True))
                            t2 = tts(cells[5].get_text(strip=True))
                            t3 = tts(cells[6].get_text(strip=True))
                            entrant['qualifying1time'] = cells[4].get_text(strip=True)
                            entrant['qualifying2time'] = cells[5].get_text(strip=True)
                            entrant['qualifying3time'] = cells[6].get_text(strip=True)
                            entrant['qualifying1timeinseconds'] = float(Decimal(str(t1)).quantize(Decimal('0.001'))) if t1 else None
                            entrant['qualifying2timeinseconds'] = float(Decimal(str(t2)).quantize(Decimal('0.001'))) if t2 else None
                            entrant['qualifying3timeinseconds'] = float(Decimal(str(t3)).quantize(Decimal('0.001'))) if t3 else None
                            # Track fastest times (leaders)
                            if t1 and (fastest_q1 is None or t1 < fastest_q1):
                                fastest_q1 = t1
                            if t2 and (fastest_q2 is None or t2 < fastest_q2):
                                fastest_q2 = t2
                            if t3 and (fastest_q3 is None or t3 < fastest_q3):
                                fastest_q3 = t3
                            entrant['qualifyinglaps'] = int(cells[7].get_text(strip=True)) if cells[7].get_text(strip=True).isdigit() else None
                            entrants[x] = entrant
                            break
            # Second pass: calculate gaps from leader
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 8:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)) and not entrant['substituteorthirddriver']:
                            x = entrants.index(entrant)
                            t1 = tts(cells[4].get_text(strip=True))
                            t2 = tts(cells[5].get_text(strip=True))
                            t3 = tts(cells[6].get_text(strip=True))
                            entrant['qualifying1gap'] = float((Decimal(str(t1)) - Decimal(str(fastest_q1))).quantize(Decimal('0.001'))) if t1 and fastest_q1 else None
                            entrant['qualifying2gap'] = float((Decimal(str(t2)) - Decimal(str(fastest_q2))).quantize(Decimal('0.001'))) if t2 and fastest_q2 else None
                            entrant['qualifying3gap'] = float((Decimal(str(t3)) - Decimal(str(fastest_q3))).quantize(Decimal('0.001'))) if t3 and fastest_q3 else None
                            entrants[x] = entrant
                            break
            # Third pass: assign positions based on timeinseconds
            assign_qualifying_positions_by_session(entrants, 1)
            assign_qualifying_positions_by_session(entrants, 2)
            assign_qualifying_positions_by_session(entrants, 3)

        elif link['href'].endswith('/sprint-qualifying'):
            open_url(f"https://formula1.com{link['href']}")
            table = soup.find('table', class_ = 'Table-module_table__cKsW2')
            rows = table.find('tbody').find_all('tr')
            fastest_q1 = None
            fastest_q2 = None
            fastest_q3 = None
            fastest_sq = None
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 8:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)) and not entrant['substituteorthirddriver']:
                            x = entrants.index(entrant)
                            t1 = tts(cells[4].get_text(strip=True))
                            t2 = tts(cells[5].get_text(strip=True))
                            t3 = tts(cells[6].get_text(strip=True))
                            entrant['sprint_qualifyingposition'] = int(cells[0].get_text(strip=True)) if cells[0].get_text(strip=True).isdigit() else None
                            entrant['sprint_qualifying1time'] = cells[4].get_text(strip=True)
                            entrant['sprint_qualifying2time'] = cells[5].get_text(strip=True)
                            entrant['sprint_qualifying3time'] = cells[6].get_text(strip=True)
                            entrant['sprint_qualifying1timeinseconds'] = float(Decimal(str(t1)).quantize(Decimal('0.001'))) if t1 else None
                            entrant['sprint_qualifying2timeinseconds'] = float(Decimal(str(t2)).quantize(Decimal('0.001'))) if t2 else None
                            entrant['sprint_qualifying3timeinseconds'] = float(Decimal(str(t3)).quantize(Decimal('0.001'))) if t3 else None
                            if t1 and (fastest_q1 is None or t1 < fastest_q1):
                                fastest_q1 = t1
                            if t2 and (fastest_q2 is None or t2 < fastest_q2):
                                fastest_q2 = t2
                            if t3 and (fastest_q3 is None or t3 < fastest_q3):
                                fastest_q3 = t3
                            if entrant['sprint_qualifying3time']:
                                entrant['sprint_qualifyingtime'] = entrant['sprint_qualifying3time']
                            elif entrant['sprint_qualifying2time']:
                                entrant['sprint_qualifyingtime'] = entrant['sprint_qualifying2time']
                            elif entrant['sprint_qualifying1time']:
                                entrant['sprint_qualifyingtime'] = entrant['sprint_qualifying1time']
                            t_sq = tts(entrant['sprint_qualifyingtime']) if entrant.get('sprint_qualifyingtime') else None
                            entrant['sprint_qualifyingtimeinseconds'] = float(Decimal(str(t_sq)).quantize(Decimal('0.001'))) if t_sq else None
                            if t_sq and (fastest_sq is None or t_sq < fastest_sq):
                                fastest_sq = t_sq
                            entrant['sprint_qualifyinglaps'] = int(cells[7].get_text(strip=True)) if cells[7].get_text(strip=True).isdigit() else None
                            entrants[x] = entrant
                            break
            # Second pass: calculate gaps from leader
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 8:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)) and not entrant['substituteorthirddriver']:
                            x = entrants.index(entrant)
                            t1 = tts(cells[4].get_text(strip=True))
                            t2 = tts(cells[5].get_text(strip=True))
                            t3 = tts(cells[6].get_text(strip=True))
                            t_sq = tts(entrant.get('sprint_qualifyingtime')) if entrant.get('sprint_qualifyingtime') else None
                            entrant['sprint_qualifying1gap'] = float((Decimal(str(t1)) - Decimal(str(fastest_q1))).quantize(Decimal('0.001'))) if t1 and fastest_q1 else None
                            entrant['sprint_qualifying2gap'] = float((Decimal(str(t2)) - Decimal(str(fastest_q2))).quantize(Decimal('0.001'))) if t2 and fastest_q2 else None
                            entrant['sprint_qualifying3gap'] = float((Decimal(str(t3)) - Decimal(str(fastest_q3))).quantize(Decimal('0.001'))) if t3 and fastest_q3 else None
                            entrant['sprint_qualifyinggap'] = float((Decimal(str(t_sq)) - Decimal(str(fastest_sq))).quantize(Decimal('0.001'))) if t_sq and fastest_sq else None
                            entrants[x] = entrant
                            break
            # Third pass: assign positions based on timeinseconds
            assign_sprint_qualifying_positions_by_session(entrants, 1)
            assign_sprint_qualifying_positions_by_session(entrants, 2)
            assign_sprint_qualifying_positions_by_session(entrants, 3)                     
        elif link['href'].endswith('/practice/0'):
            open_url(f"https://formula1.com{link['href']}")
            table = soup.find('table', class_='Table-module_table__cKsW2')
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')

                if len(cells) == 6:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)) and not entrant['substituteorthirddriver']:
                            x = entrants.index(entrant)
                            entrant['warmupposition'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else None
                            entrant['warmuptime'] = cells[4].get_text(strip=True) if entrant['warmupposition'] == 1 else tts_to_normal(
                                leadertime + tts(cells[4].get_text(strip=True).replace('+', '').replace('s', '')) if cells[4].get_text(strip=True) else None
                            )
                            entrant['warmupgap'] = gap
                            entrant['warmuptimeinseconds'] = tts(entrant['warmuptime']) if entrant['warmuptime'] is not None else None
                            if entrant['warmupposition'] == 1:
                                leadertime = entrant['warmuptimeinseconds']
                            entrant['warmuplaps'] = int(cells[5].get_text(strip=True)) 
                            entrants[x] = entrant
                            break

                elif len(cells) == 7:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)) and not entrant['substituteorthirddriver']:
                            x = entrants.index(entrant)
                            entrant['warmupposition'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else None
                            entrant['warmuptime'] = cells[4].get_text(strip=True) if entrant['warmupposition'] == 1 else tts_to_normal(
                                leadertime + tts(cells[4].get_text(strip=True).replace('+', '').replace('s', ''))
                            )
                            entrant['warmupgap'] = gap
                            entrant['warmuptimeinseconds'] = tts(entrant['warmuptime'])
                            if entrant['warmupposition'] == 1:
                                leadertime = entrant['warmuptimeinseconds']
                            entrant['warmuplaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrants[x] = entrant
                            break
                elif len(cells) == 5:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)) and not entrant['substituteorthirddriver']:
                            x = entrants.index(entrant)
                            entrant['warmupposition'] = int(cells[0].get_text(strip=True))
                            entrant['warmuptime'] = cells[4].get_text(strip=True) if entrant['warmupposition'] == 1 else tts_to_normal(
                                leadertime + tts(cells[4].get_text(strip=True).replace('+', '').replace('s', '')) if cells[4].get_text(strip=True) else None
                            )
                            entrant['warmupgap'] = cells[4].get_text(strip=True)
                            entrant['warmuptimeinseconds'] = tts(entrant['warmuptime']) if entrant['warmuptime'] is not None else None
                            if entrant['warmupposition'] == 1:
                                leadertime = entrant['warmuptimeinseconds']
                            entrants[x] = entrant
                            break

        elif link['href'].endswith('/practice/1'):
            open_url(f"https://formula1.com{link['href']}")
            table = soup.find('table', class_='Table-module_table__cKsW2')
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 6:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice1position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else None
                            entrant['practice1time'] = cells[4].get_text(strip=True) if entrant['practice1position'] == 1 else tts_to_normal(
                                leadertime + tts(cells[4].get_text(strip=True).replace('+', '').replace('s', '')) if cells[4].get_text(strip=True) else None
                            )
                            entrant['practice1gap'] = gap
                            entrant['practice1timeinseconds'] = tts(entrant['practice1time']) if entrant['practice1time'] is not None else None
                            if entrant['practice1position'] == 1:
                                leadertime = entrant['practice1timeinseconds']
                            entrant['practice1laps'] = int(cells[5].get_text(strip=True))
                            entrants[x] = entrant
                            break

                elif len(cells) == 7:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice1position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else None
                            entrant['practice1time'] = cells[4].get_text(strip=True) if entrant['practice1position'] == 1 else tts_to_normal(
                                leadertime + tts(cells[4].get_text(strip=True).replace('+', '').replace('s', ''))
                            )
                            entrant['practice1gap'] = gap
                            entrant['practice1timeinseconds'] = tts(entrant['practice1time'])
                            if entrant['practice1position'] == 1:
                                leadertime = entrant['practice1timeinseconds']
                            entrant['practice1laps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrants[x] = entrant
                            break
                elif len(cells) == 5:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice1position'] = int(cells[0].get_text(strip=True))
                            entrant['practice1time'] = cells[4].get_text(strip=True) if entrant['practice1position'] == 1 else tts_to_normal(
                                leadertime + tts(cells[4].get_text(strip=True).replace('+', '').replace('s', '')) if cells[4].get_text(strip=True) else None
                            )
                            entrant['practice1gap'] = cells[4].get_text(strip=True)
                            entrant['practice1timeinseconds'] = tts(entrant['practice1time']) if entrant['practice1time'] is not None else None
                            if entrant['practice1position'] == 1:
                                leadertime = entrant['practice1timeinseconds']
                            entrants[x] = entrant
                            break

        elif link['href'].endswith('/practice/2'):
            open_url(f"https://formula1.com{link['href']}")
            table = soup.find('table', class_='Table-module_table__cKsW2')
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')

                if len(cells) == 6:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice2position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else None
                            entrant['practice2time'] = cells[4].get_text(strip=True) if entrant['practice2position'] == 1 else tts_to_normal(
                                leadertime + tts(cells[4].get_text(strip=True).replace('+', '').replace('s', '')) if cells[4].get_text(strip=True) else None
                            )
                            entrant['practice2gap'] = gap
                            entrant['practice2timeinseconds'] = tts(entrant['practice2time']) if entrant['practice2time'] is not None else None
                            if entrant['practice2position'] == 1:
                                leadertime = entrant['practice2timeinseconds']
                            entrant['practice2laps'] = int(cells[5].get_text(strip=True))
                            entrants[x] = entrant
                            break

                elif len(cells) == 7:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice2position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else None
                            entrant['practice2time'] = cells[4].get_text(strip=True) if entrant['practice2position'] == 1 else tts_to_normal(
                                leadertime + tts(cells[4].get_text(strip=True).replace('+', '').replace('s', ''))
                            )
                            entrant['practice2gap'] = gap
                            entrant['practice2timeinseconds'] = tts(entrant['practice2time'])
                            if entrant['practice2position'] == 1:
                                leadertime = entrant['practice2timeinseconds']
                            entrant['practice2laps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrants[x] = entrant
                            break
                elif len(cells) == 5:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice2position'] = int(cells[0].get_text(strip=True))
                            entrant['practice2time'] = cells[4].get_text(strip=True) if entrant['practice2position'] == 1 else tts_to_normal(
                                leadertime + tts(cells[4].get_text(strip=True).replace('+', '').replace('s', '')) if cells[4].get_text(strip=True) else None
                            )
                            entrant['practice2gap'] = cells[4].get_text(strip=True)
                            entrant['practice2timeinseconds'] = tts(entrant['practice2time']) if entrant['practice2time'] is not None else None
                            if entrant['practice2position'] == 1:
                                leadertime = entrant['practice2timeinseconds']
                            entrants[x] = entrant
                            break
        elif link['href'].endswith('/practice/3'):
            open_url(f"https://formula1.com{link['href']}")
            table = soup.find('table', class_='Table-module_table__cKsW2')
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')

                if len(cells) == 6:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice3position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else None
                            entrant['practice3time'] = cells[4].get_text(strip=True) if entrant['practice3position'] == 1 else tts_to_normal(
                                leadertime + tts(cells[4].get_text(strip=True).replace('+', '').replace('s', '')) if cells[4].get_text(strip=True) else None
                            )
                            entrant['practice3gap'] = gap
                            entrant['practice3timeinseconds'] = tts(entrant['practice3time']) if entrant['practice3time'] is not None else None
                            if entrant['practice3position'] == 1:
                                leadertime = entrant['practice3timeinseconds']
                            entrant['practice3laps'] = int(cells[5].get_text(strip=True))
                            entrants[x] = entrant
                            break

                elif len(cells) == 7:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice3position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else None
                            entrant['practice3time'] = cells[4].get_text(strip=True) if entrant['practice3position'] == 1 else tts_to_normal(
                                leadertime + tts(cells[4].get_text(strip=True).replace('+', '').replace('s', ''))
                            )
                            entrant['practice3gap'] = gap
                            entrant['practice3timeinseconds'] = tts(entrant['practice3time'])
                            if entrant['practice3position'] == 1:
                                leadertime = entrant['practice3timeinseconds']
                            entrant['practice3laps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrants[x] = entrant
                            break

        elif link['href'].endswith('/practice/4'):
            open_url(f"https://formula1.com{link['href']}")
            table = soup.find('table', class_='Table-module_table__cKsW2')
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')

                if len(cells) == 6:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice4position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else None
                            entrant['practice4time'] = cells[4].get_text(strip=True) if entrant['practice4position'] == 1 else tts_to_normal(
                                leadertime + tts(cells[4].get_text(strip=True).replace('+', '').replace('s', '')) if cells[4].get_text(strip=True) else None
                            )
                            entrant['practice4gap'] = gap
                            entrant['practice4timeinseconds'] = tts(entrant['practice4time']) if entrant['practice4time'] is not None else None
                            if entrant['practice4position'] == 1:
                                leadertime = entrant['practice4timeinseconds']
                            entrant['practice4laps'] = int(cells[5].get_text(strip=True))
                            entrants[x] = entrant
                            break

                elif len(cells) == 7:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice4position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else None
                            entrant['practice4time'] = cells[4].get_text(strip=True) if entrant['practice4position'] == 1 else tts_to_normal(
                                leadertime + tts(cells[4].get_text(strip=True).replace('+', '').replace('s', ''))
                            )
                            entrant['practice4gap'] = gap
                            entrant['practice4timeinseconds'] = tts(entrant['practice4time'])
                            if entrant['practice4position'] == 1:
                                leadertime = entrant['practice4timeinseconds']
                            entrant['practice4laps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrants[x] = entrant
                            break
        elif link['href'].endswith('/sprint.aspx'):
            TIME_REGEX = re.compile(
                r'(\d+h\s*)?(\d+m\s*)?(\d+(?:\.\d+)?s|\d+:\d{2}(?::\d{2}(?:\.\d+)?)?)'
            )            
            sprintweekend = True 
            open_url(f"https://www.statsf1.com{link['href']}")
            sprintpenalties = parse_penalties(soup, is_sprint=True)
            table = soup.find('table', class_ = 'datatable')
            #You need to do shared cars and avoid exceptions when the sprint position is "ab" or something
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                for entrant in entrants:
                    if  normalize_name(entrant['driver'].lower()) in normalize_name(cells[1].get_text(strip=True).lower()):
                        x = entrants.index(entrant)
                        # Process the main car entry
                        if cells[0].get_text(strip=True) in ['ab', 'nc', 'np', 'nq', 'npq', 'dsq', 'exc', 'f', 'tf', 't']:
                            entrant['sprintposition'] = None
                            entrant['sprintlaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrant['sprinttime'] = cells[5].get_text(strip=True) + f" ({abbreviations[cells[0].get_text(strip=True)]})"
                            entrant['sprintstatus'] = abbreviations[cells[0].get_text(strip=True)]
                            entrant['sprintgap'] = cells[6].get_text(strip=True).split('(')[1].replace(')', '') if '(' in cells[6].get_text(strip=True) and cells[6].get_text(strip=True).split('(')[1].replace(')', '').strip().endswith('s')  else None
                            entrant['sprintgapinseconds'] = parse_race_time(entrant['sprintgap'].replace("+", "")) if entrant['sprintgap'] else None
                            raw = cells[6].get_text(strip=True)
                            m = TIME_REGEX.search(raw)
                            if m:
                                entrant['sprinttime'] = m.group(0).strip().replace("h ", ":").replace("m ", ":") if m.group(0).strip() else None
                                entrant['sprintstatusreason'] = raw[:m.start()].strip() or None
                            else:
                                entrant['sprinttime'] = None
                                entrant['sprintstatusreason'] = raw.strip() or None                                  
                            entrant['sprintpoints'] = 0
                        else:
                            entrant['sprintposition'] = int(cells[0].get_text(strip=True))
                            entrant['sprintlaps'] = int(cells[4].get_text(strip=True))
                            entrant['sprinttime'] = cells[5].get_text(strip=True).split('(')[0].replace("'", ":") if '(' in cells[5].get_text(strip=True) else cells[5].get_text(strip=True)
                            entrant['sprinttimeinseconds'] = tts(entrant['sprinttime'])
                            entrant['sprintgap'] = cells[5].get_text(strip=True).split('(')[1].replace(')', '') if '(' in cells[5].get_text(strip=True) and cells[5].get_text(strip=True).split('(')[1].replace(')', '' ).strip().endswith('s')  else None
                            entrant['sprintgapinseconds'] = parse_race_time(entrant['sprintgap'].replace("+", "")) if entrant['sprintgap'] else None
                            raw = cells[6].get_text(strip=True)
                            m = TIME_REGEX.search(raw)
                            if m:
                                entrant['sprinttime'] = m.group(0).strip().replace("h ", ":").replace("m ", ":") if m.group(0).strip() else None
                                entrant['sprintstatusreason'] = raw[:m.start()].strip() or None
                            else:
                                entrant['sprinttime'] = None
                                entrant['sprintstatusreason'] = raw.strip() or None  
                            entrant['sprintstatus'] = 'Classified'                            
                            entrant['sprintpoints'] = float(cells[7].get_text(strip=True)) if cells[7].get_text(strip=True).replace('.', '', 1).isdigit() else None
                        # Parse penalties during and after the race
                        entrants[x] = entrant
                        break                                                                                                         
        elif link['href'].endswith('/classement.aspx'):
            TIME_REGEX = re.compile(
                r'(\d+h\s*)?(\d+m\s*)?(\d+(?:\.\d+)?s|\d+:\d{2}(?::\d{2}(?:\.\d+)?)?)'
            )            
            #print(entrants[19])
            open_url(f"https://www.statsf1.com{link['href']}")
            table = soup.find('table', class_ = 'datatable')
            penalties = parse_penalties(soup, is_sprint=False)
            if sprintweekend == True:
                for penalty in sprintpenalties:
                    penalties.append(penalty)
            #You need to do shared cars and avoid exceptions when the race position is "ab" or something
            rows = table.find('tbody').find_all('tr')
            main_car = None  # Keep track of the main car for shared cars
            for row in rows:
                #print (row)
                cells = row.find_all('td')
                if len(cells) >= 8:
                    if not cells[1].get_text(strip=True).isdigit() and cells[2].get_text(strip=True) == '':
                        #print("")
                        #print (row)
                        continue  # Skip this row if the "No" column is blank or invalid                    
                    # Check if the row represents a shared car
                    if cells[0].get_text(strip=True) == '&':  # Shared car entry
                        #print("DEBUG: Shared car detected.")
                        #print("DEBUG: Current main car before processing shared car:", main_car)                        
                        if main_car:
                            for entrant in entrants:
                                if normalize_name(entrant['driver'].lower()) in normalize_name(cells[2].get_text(strip=True).lower()) and entrant['number'] == main_car['number']:
                                    # Create a new entry for the shared car
                                    entrant['raceposition'] = main_car["raceposition"]
                                    entrant['racelaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                                    entrant['racetime'] = cells[6].get_text(strip=True)
                                    entrant['racepoints'] = float(cells[7].get_text(strip=True)) if cells[7].get_text(strip=True).replace('.', '', 1).isdigit() else None
                                    if cells[0].get_text(strip=True) in ['ab', 'nc', 'np', 'nq', 'npq', 'dsq', 'exc', 'f', 'tf', 't']:
                                        if cells[0].get_text(strip=True) == 'npq':
                                            parseprequalifyingflag = True                                         
                                        entrant['raceposition'] = None
                                        entrant['racelaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                                        entrant['racetime'] = cells[6].get_text(strip=True) 
                                        entrant['racestatus'] = main_car['racestatus']
                                        entrant['racegap'] = cells[6].get_text(strip=True).split('(')[1].replace(')', '') if '(' in cells[6].get_text(strip=True) and cells[6].get_text(strip=True).split('(')[1].replace(')', '').strip().endswith('s')  else None
                                        raw = cells[6].get_text(strip=True)
                                        m = TIME_REGEX.search(raw)
                                        if m:
                                            entrant['racetime'] = m.group(0).strip().replace("h ", ":").replace("m ", ":") if m.group(0).strip() else None
                                            entrant['racestatusreason'] = raw[:m.start()].strip() or None
                                        else:
                                            entrant['racetime'] = None
                                            entrant['racestatusreason'] = raw.strip() or None                            
                                        entrant['racepoints'] = 0  
                                    elif main_car['raceposition'] is None:
                                        entrant['raceposition'] = None
                                        entrant['raceposition'] = None
                                        entrant['racelaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                                        entrant['racetime'] = cells[6].get_text(strip=True)
                                        entrant['racestatus'] = main_car['racestatus'] if main_car.get('racestatus') else abbreviations[cells[0].get_text(strip=True)]
                                        entrant['racegap'] = cells[6].get_text(strip=True).split('(')[1].replace(')', '') if '(' in cells[6].get_text(strip=True) and cells[6].get_text(strip=True).split('(')[1].replace(')', '').strip().endswith('s')  else None
                                        raw = cells[6].get_text(strip=True)
                                        m = TIME_REGEX.search(raw)
                                        if m:
                                            entrant['racetime'] = m.group(0).strip().replace("h ", ":").replace("m ", ":") if m.group(0).strip() else None
                                            entrant['racestatusreason'] = raw[:m.start()].strip() or None
                                        else:
                                            entrant['racetime'] = None
                                            entrant['racestatusreason'] = raw.strip() or None   
                                        entrant['racepoints'] = 0  
                                    if entrant["racetime"] is not None:
                                        entrant["racetime"] = entrant["racetime"].split('(')[0] if '(' in entrant["racetime"] else entrant["racetime"]
                                        entrant['racetimeinseconds'] = parse_race_time(entrant['racetime'])
                                        entrant['racegap'] = cells[6].get_text(strip=True).split('(')[1].replace(')', '') if '(' in cells[6].get_text(strip=True) and cells[6].get_text(strip=True).split('(')[1].replace(')', '').strip().endswith('s')  else None
                                        entrant['racegapinseconds'] = parse_race_time(entrant['racegap'].replace("+", "")) if entrant['racegap'] else None
                                        raw = cells[6].get_text(strip=True)
                                        m = TIME_REGEX.search(raw)
                                        if m:
                                            entrant['racetime'] = m.group(0).strip().replace("h ", ":").replace("m ", ":") if m.group(0).strip() else None
                                            entrant['racestatusreason'] = raw[:m.start()].strip() or None
                                        else:
                                            entrant['racetime'] = None
                                            entrant['racestatusreason'] = raw.strip() or None  
                                        entrant['racestatus'] = 'Classified'                                          
                                    # Append the shared car entry to the race results
                                    #print ("Main car: ", main_car)
                                    #print ("Shared car: ",  entrant)
                                    #entrants[x] = entrant
                                    break
                                elif normalize_name(entrant['driver'].lower()) in normalize_name(cells[2].get_text(strip=True).lower()) and entrant['number'] != main_car['number']:
                                    shared_car = {
                                        "driver": entrant['driver'],
                                        "team": main_car["team"],
                                        "constructor": main_car["constructor"],
                                        "raceposition": main_car["raceposition"],
                                        "number": main_car["number"],
                                        "chassis": main_car["chassis"],
                                        "engine": main_car["engine"],
                                        "enginemodel": main_car['enginemodel'],
                                        "tyre": main_car['tyre'],
                                        "raceposition": main_car["raceposition"],
                                        "racelaps": int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None,
                                        "racepoints": float(cells[7].get_text(strip=True)) if cells[7].get_text(strip=True).replace('.', '', 1).isdigit() else None,
                                        "racetime": cells[6].get_text(strip=True)
                                    }
                                    if cells[0].get_text(strip=True) in ['ab', 'nc', 'np', 'nq', 'npq', 'dsq', 'exc', 'f', 'tf', 't']:
                                        if cells[0].get_text(strip=True) == 'npq':
                                            parseprequalifyingflag = True                                        
                                        shared_car['raceposition'] = None
                                        shared_car['racelaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                                        shared_car['racetime'] = cells[6].get_text(strip=True) 
                                        shared_car['racestatus'] = main_car['racestatus']
                                        shared_car['racegap'] = cells[6].get_text(strip=True).split('(')[1].replace(')', '') if '(' in cells[6].get_text(strip=True) and cells[6].get_text(strip=True).split('(')[1].replace(')', '').strip().endswith('s')  else None
                                        raw = cells[6].get_text(strip=True)
                                        m = TIME_REGEX.search(raw)
                                        if m:
                                            shared_car['racetime'] = m.group(0).strip().replace("h ", ":").replace("m ", ":") if m.group(0).strip() else None
                                            shared_car['racestatusreason'] = raw[:m.start()].strip() or None
                                        else:
                                            shared_car['racetime'] = None
                                            shared_car['racestatusreason'] = raw.strip() or None                                              
                                        shared_car['racepoints'] = None
                                    elif main_car['raceposition'] is None:
                                        shared_car['raceposition'] = None
                                        shared_car['racelaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                                        shared_car['racetime'] = cells[6].get_text(strip=True) 
                                        shared_car['racestatus'] = main_car['racestatus'] 
                                        shared_car['racegap'] = cells[6].get_text(strip=True).split('(')[1].replace(')', '') if '(' in cells[6].get_text(strip=True) and cells[6].get_text(strip=True).split('(')[1].replace(')', '').strip().endswith('s')  else None
                                        raw = cells[6].get_text(strip=True)
                                        m = TIME_REGEX.search(raw)
                                        if m:
                                            shared_car['racetime'] = m.group(0).strip().replace("h ", ":").replace("m ", ":") if m.group(0).strip() else None
                                            shared_car['racestatusreason'] = raw[:m.start()].strip() or None
                                        else:
                                            shared_car['racetime'] = None
                                            shared_car['racestatusreason'] = raw.strip() or None                                              
                                        shared_car['racepoints'] = None                                        
                                    if shared_car["racetime"] is not None:
                                        shared_car["racetime"] = shared_car["racetime"].split('(')[0] if '(' in shared_car["racetime"] else shared_car["racetime"]
                                        shared_car['racetimeinseconds'] = parse_race_time(shared_car['racetime'])
                                        shared_car['racegap'] = cells[6].get_text(strip=True).split('(')[1].replace(')', '') if '(' in cells[6].get_text(strip=True) and cells[6].get_text(strip=True).split('(')[1].replace(')', '').strip().endswith('s')  else None
                                        shared_car['racegapinseconds'] = parse_race_time(shared_car['racegap'].replace("+", "")) if shared_car['racegap'] else None
                                        raw = cells[6].get_text(strip=True)
                                        m = TIME_REGEX.search(raw)
                                        if m:
                                            shared_car['racetime'] = m.group(0).strip().replace("h ", ":").replace("m ", ":") if m.group(0).strip() else None
                                            shared_car['racestatusreason'] = raw[:m.start()].strip() or None
                                        else:
                                            shared_car['racetime'] = None
                                            shared_car['racestatusreason'] = raw.strip() or None  
                                        shared_car['racestatus'] = 'Classified'                                        
                                    entrants.append(shared_car)
                                    break
                    else:  # Main car entry
                        for entrant in entrants:
                            if entrant['number'] == int(cells[1].get_text(strip=True)) and normalize_name(entrant['driver'].lower()) in normalize_name(cells[2].get_text(strip=True).lower()):
                                # Process the main car entry
                                if cells[0].get_text(strip=True) in ['ab', 'nc', 'np', 'nq', 'npq', 'dsq', 'exc', 'f', 'tf', 't']:
                                    if cells[0].get_text(strip=True) == 'npq':
                                        parseprequalifyingflag = True                                     
                                    entrant['raceposition'] = None
                                    entrant['racelaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                                    entrant['racetime'] = cells[6].get_text(strip=True) + f" ({abbreviations[cells[0].get_text(strip=True)]})"
                                    entrant['racestatus'] = abbreviations[cells[0].get_text(strip=True)]
                                    entrant['racegap'] = cells[6].get_text(strip=True).split('(')[1].replace(')', '') if '(' in cells[6].get_text(strip=True) and cells[6].get_text(strip=True).split('(')[1].replace(')', '').strip().endswith('s')  else None
                                    raw = cells[6].get_text(strip=True)
                                    m = TIME_REGEX.search(raw)
                                    if m:
                                        entrant['racetime'] = m.group(0).strip().replace("h ", ":").replace("m ", ":") if m.group(0).strip() else None
                                        entrant['racestatusreason'] = raw[:m.start()].strip() or None
                                    else:
                                        entrant['racetime'] = None
                                        entrant['racestatusreason'] = raw.strip() or None                                          
                                    entrant['racepoints'] = 0
                                else:
                                    entrant['raceposition'] = int(cells[0].get_text(strip=True))
                                    entrant['racelaps'] = int(cells[5].get_text(strip=True))
                                    entrant['racetime'] = cells[6].get_text(strip=True).split('(')[0] if '(' in cells[6].get_text(strip=True) else cells[6].get_text(strip=True)
                                    entrant['racetimeinseconds'] = parse_race_time(entrant['racetime'])
                                    entrant['racegap'] = cells[6].get_text(strip=True).split('(')[1].replace(')', '') if '(' in cells[6].get_text(strip=True) and cells[6].get_text(strip=True).split('(')[1].replace(')', '').strip().endswith('s')  else None
                                    entrant['racegapinseconds'] = parse_race_time(entrant['racegap'].replace("+", "")) if entrant['racegap'] else None
                                    entrant['racepoints'] = float(cells[7].get_text(strip=True)) if cells[7].get_text(strip=True).replace('.', '', 1).isdigit() else None
                                    raw = cells[6].get_text(strip=True)
                                    m = TIME_REGEX.search(raw)
                                    if m:
                                        entrant['racetime'] = m.group(0).strip().replace("h ", ":").replace("m ", ":") if m.group(0).strip() else None
                                        entrant['racestatusreason'] = raw[:m.start()].strip() or None
                                    else:
                                        entrant['racetime'] = None
                                        entrant['racestatusreason'] = raw.strip() or None  
                                    entrant['racestatus'] = 'Classified'                                                              
                                main_car = entrant  # Update the main car reference                                   
                                break  # Exit the loop once the entrant is found
                else:
                    raise ValueError(f"Unexpected number of cells in row: {len(cells)}. Expected at least 8 cells.")
        elif link['href'].startswith('https://motorsportstats.com') and link['href'].endswith('_race'):
            b = open_json(link['href'])
            for driver in b['details']:
                for entrant in entrants:
                    if int(driver['carNumber']) == entrant['number'] and not entrant['substituteorthirddriver']:
                        if entrant['racetime'] is None:
                            timestewer = driver['time']
                            timestr = int(timestewer)
                            h = timestr // (3600000)
                            m = (timestr % 3600000) // 60000
                            s = (timestr % 60000) / 1000
                            if timestr == 0:
                                entrant['racetime'] = None
                                entrant['racetimeinseconds'] = None
                                break
                            entrant['racetime'] = f"{h:02d}:{m:02d}.{s:03.0f}s"
                            entrant['racetimeinseconds'] = float(Decimal(str(timestr / 1000)).quantize(Decimal('0.001')))
                        if entrant['racegap'] is None:
                            gapstewer = driver['gap']['timeToLead']   
                            gapstr = int(gapstewer)
                            h = gapstr // (3600000)
                            m = (gapstr % 3600000) // 60000
                            s = (gapstr % 60000) / 1000
                            if gapstr != 0:
                                entrant['racegap'] = f"{h:02d}:{m:02d}.{s:03.0f}s"
                                entrant['racegapinseconds'] = float(Decimal(str(gapstr / 1000)).quantize(Decimal('0.001')))
        elif link['href'].startswith('https://motorsportstats.com') and link['href'].endswith('_sprint'):
            b = open_json(link['href'])
            for driver in b['details']:
                for entrant in entrants:
                    if int(driver['carNumber']) == entrant['number'] and not entrant['substituteorthirddriver']:
                        if entrant['sprinttime'] is None:
                            timestewer = driver['time']
                            timestr = int(timestewer)
                            h = timestr // (3600000)
                            m = (timestr % 3600000) // 60000
                            s = (timestr % 60000) / 1000
                            entrant['sprinttime'] = f"{h:02d}:{m:02d}.{s:03.0f}s"
                            entrant['sprinttimeinseconds'] = float(Decimal(str(timestr / 1000)).quantize(Decimal('0.001')))  
                        if entrant['sprintgap'] is None:
                            gapstewer = driver['gap']['timeToLead']   
                            gapstr = int(gapstewer)
                            h = gapstr // (3600000)
                            m = (gapstr % 3600000) // 60000
                            s = (gapstr % 60000) / 1000
                            if gapstr != 0:
                                entrant['sprintgap'] = f"{h:02d}:{m:02d}.{s:03.0f}s"
                                entrant['sprintgapinseconds'] = float(Decimal(str(gapstr / 1000)).quantize(Decimal('0.001')))
        elif link['href'].startswith('https://motorsportstats.com') and (link['href'].endswith ('qualifying-1') or link['href'].endswith('1st-qualifying')):
            b = open_json(link['href'])
            for driver in b['details']:
                for entrant in entrants:
                    if int(driver['carNumber']) == entrant['number'] and not entrant['substituteorthirddriver']:
                        if year < 1958:
                            if not normalize_name(driver['drivers'][0]['name'].lower()) == normalize_name(entrant['driver'].lower()):
                                continue #because of shared cars.
                        if entrant.get('qualifying1position') is None:
                            entrant['qualifying1position'] = driver['finishPosition']
                        if entrant.get('qualifying1time') is None and driver.get('time') is not None:
                            entrant['qualifying1timeinseconds'] = float(Decimal(str(driver['time'] / 1000)).quantize(Decimal('0.001')))
                            entrant['qualifying1time'] = tts_to_normal(entrant['qualifying1timeinseconds'])
                        q1_gap_to_lead = (driver.get('gap') or {}).get('timeToLead')
                        if entrant.get('qualifying1gap') is None and driver['finishPosition'] != 1 and q1_gap_to_lead is not None:
                            entrant['qualifying1gap'] = float(Decimal(str(q1_gap_to_lead / 1000)).quantize(Decimal('0.001')))
                        if year > 2011 and entrant.get('qualifying1laps') is None:
                            entrant['qualifying1laps'] = driver['laps']
        elif link['href'].startswith('https://motorsportstats.com') and (link['href'].endswith ('qualifying-2') or link['href'].endswith('2nd-qualifying')):
            b = open_json(link['href'])
            for driver in b['details']:
                for entrant in entrants:
                    if gp == "1956 Italian Grand Prix" and driver['carNumber'] == '?':
                        driver['carNumber'] == '12'
                        if entrant['driver'].lower() != "joao rezende dos santos":
                            continue #because of shared cars. 
                    if int(driver['carNumber']) == entrant['number'] and not entrant['substituteorthirddriver']:
                        if year < 1958:
                            if not normalize_name(driver['drivers'][0]['name'].lower()) == normalize_name(entrant['driver'].lower()):
                                continue #because of shared cars.                        
                        if entrant.get('qualifying2position') is None:
                            entrant['qualifying2position'] = driver['finishPosition']
                        if entrant.get('qualifying2time') is None and driver.get('time') is not None:
                            entrant['qualifying2timeinseconds'] = float(Decimal(str(driver['time'] / 1000)).quantize(Decimal('0.001')))
                            entrant['qualifying2time'] = tts_to_normal(entrant['qualifying2timeinseconds'])
                        q2_gap_to_lead = (driver.get('gap') or {}).get('timeToLead')
                        if entrant.get('qualifying2gap') is None and driver['finishPosition'] != 1 and q2_gap_to_lead is not None:
                            entrant['qualifying2gap'] = float(Decimal(str(q2_gap_to_lead / 1000)).quantize(Decimal('0.001')))
                        if year > 2011 and entrant.get('qualifying2laps') is None:
                            entrant['qualifying2laps'] = driver['laps']
                        if gp == "2005 Australian Grand Prix":
                            entrant['qualifying2position'] = driver['finishPosition'] # Correcting known data issue for 2005 AUS GP Q2
        elif link['href'].startswith('https://motorsportstats.com') and (link['href'].endswith ('qualifying-3') or link['href'].endswith('3rd-qualifying')):
            if link['href'] == "https://motorsportstats.com/api/results-classification?sessionSlug=fia-formula-one-world-championship_2015_united-states-grand-prix_qualifying-3":
                continue #q3 skipped that race due to rain.
            b = open_json(link['href'])
            for driver in b['details']:
                for entrant in entrants:
                    if int(driver['carNumber']) == entrant['number'] and not entrant['substituteorthirddriver']:
                        if entrant.get('qualifying3position') is None:
                            entrant['qualifying3position'] = driver['finishPosition']
                        entrant['qualifying3gap'] = float(Decimal(str(driver['gap']['timeToLead'] / 1000)).quantize(Decimal('0.001'))) if driver['finishPosition'] != 1 else None
                        if year > 2011 and entrant.get('qualifying3laps') is None:
                            entrant['qualifying3laps'] = driver['laps']
        elif link['href'].startswith('https://motorsportstats.com') and link['href'].endswith ('1st-sprint-qualifying'):
            b = open_json(link['href'])
            for driver in b['details']:
                for entrant in entrants:
                    if int(driver['carNumber']) == entrant['number'] and not entrant['substituteorthirddriver']:
                        if entrant.get('sprintqualifying1position') is None:
                            entrant['sprintqualifying1position'] = driver['finishPosition']
                        entrant['sprintqualifying1gapseconds'] = float(Decimal(str(driver['gap']['timeToLead'] / 1000)).quantize(Decimal('0.001'))) if driver['finishPosition'] != 1 else None
                        if year > 2011 and entrant.get('sprintqualifying1laps') is None:
                            entrant['sprintqualifying1laps'] = driver['laps']
        elif link['href'].startswith('https://motorsportstats.com') and link['href'].endswith ('2nd-sprint-qualifying'):
            b = open_json(link['href'])
            for driver in b['details']:
                for entrant in entrants:
                    if int(driver['carNumber']) == entrant['number'] and not entrant['substituteorthirddriver']:
                        if entrant.get('sprintqualifying2position') is None:
                            entrant['sprintqualifying2position'] = driver['finishPosition']
                        entrant['sprintqualifying2gapseconds'] = float(Decimal(str(driver['gap']['timeToLead'] / 1000)).quantize(Decimal('0.001'))) if driver['finishPosition'] != 1 else None
                        if year > 2011 and entrant.get('sprintqualifying2laps') is None:
                            entrant['sprintqualifying2laps'] = driver['laps']
        elif link['href'].startswith('https://motorsportstats.com') and link['href'].endswith ('3rd-sprint-qualifying'):
            b = open_json(link['href'])
            for driver in b['details']:
                for entrant in entrants:
                    if int(driver['carNumber']) == entrant['number'] and not entrant['substituteorthirddriver']:
                        if entrant.get('sprintqualifying3position') is None:
                            entrant['sprintqualifying3position'] = driver['finishPosition']
                        entrant['sprintqualifying3gapseconds'] = float(Decimal(str(driver['gap']['timeToLead'] / 1000)).quantize(Decimal('0.001'))) if driver['finishPosition'] != 1 else None
                        if year > 2011 and entrant.get('sprintqualifying3laps') is None:
                            entrant['sprintqualifying3laps'] = driver['laps']
    for penalty in penalties:
        for entrant in entrants:
            if normalize_name(entrant['driver'].lower()) == normalize_name(penalty['driver'].lower()):
                key = 'sprint_penalties' if penalty['is_sprint'] else 'penalties'
                if key not in entrant:
                    entrant[key] = []
                penalty_entry = {
                    "penalty": penalty["penalty"],
                    "reason": penalty["reason"],
                    "type": penalty["type"]
                }
                if "lost_position" in penalty:
                    penalty_entry["lost_position"] = penalty["lost_position"]
                entrant[key].append(penalty_entry)
                break
    
    if parseprequalifyingflag:
        title = gp.replace(" ", "_")
        encoded = urllib.parse.quote(title)
        url = f"https://en.wikipedia.org/api/rest_v1/page/html/{encoded}"
        preq_table = None
        retries = 0
        while retries < 3:
            try:
                req = urllib.request.Request(
                    url,
                    headers={"User-Agent": "F1DB/1.0"}
                )
            except Exception as e:
                print(f"Error creating request for {title}: {e}")
                retries += 1
            else:
                break
        #raise error if request creation failed after retries
        if retries == 3:
            raise ValueError(f"Failed to create request for {title} after multiple attempts")

        try:
            with urllib.request.urlopen(req) as response:
                html = response.read().decode("utf-8")
        except Exception as e:
            raise ValueError(f"Failed to fetch {title}: {e}")

        wiki_soup = BeautifulSoup(html, "html.parser")            
        
        # Look for "Pre-qualifying" heading
        preq_heading = None
        for tag in wiki_soup.find_all(["h2", "h3", "h4"]):
            if "pre-qualifying" in tag.get_text(strip=True).lower() or "pre-qualification" in tag.get_text(strip=True).lower():
                preq_heading = tag
                # Find the next table after the heading
                preq_table = None
                for sibling in preq_heading.find_all_next():
                    if sibling.name == "table":
                        preq_table = sibling
                        break
                    # Stop if we hit another heading of same or higher level
                    if sibling.name in ["h2", "h3", "h4"] and sibling != preq_heading:
                        break
                if preq_table is not None:
                    rows = preq_table.find_all("tr")
                        
                    # Parse header to understand column layout
                    header_row = rows[0] if rows else None
                    headers_ = []
                    if header_row:
                        headers_ = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]
                    
                    # Detect column indices dynamically
                    def find_col(keywords):
                        for i, h in enumerate(headers_):
                            for kw in keywords:
                                if kw in h:
                                    return i
                        return None
                    
                    pos_idx  = find_col(["pos"])
                    no_idx   = find_col(["no", "#"])
                    drv_idx  = find_col(["driver"])
                    con_idx  = find_col(["constructor"])
                    
                    # Check for combined "Time/Gap" column first, before separate time/gap
                    timegap_idx = find_col(["time/gap"])
                    if timegap_idx is not None:
                        time_idx = timegap_idx
                        gap_idx  = None
                        combined_timegap = True
                    else:
                        combined_timegap = False
                        time_idx = find_col(["time"])
                        gap_idx  = find_col(["gap"])
                    
                    leadertime = None
                    previoustime = None

                    for row in rows[1:]:
                        cells = row.find_all(["th", "td"])
                        if not cells:
                            continue

                        def cell_text(idx):
                            if idx is not None and idx < len(cells):
                                return cells[idx].get_text(strip=True)
                            return ""

                        pos         = cell_text(pos_idx)
                        car_no      = cell_text(no_idx)
                        driver      = cell_text(drv_idx)
                        constructor = cell_text(con_idx)
                        raw_timegap = cell_text(time_idx)

                        if not driver:
                            continue

                        pos = pos.replace("—", "").strip()

                        # Image 1 style: relative time like "-1:37.0" or "+1:37.0" in a plain Time column
                        # These are not real lap times so skip time/gap calculations entirely
                        if (raw_timegap.startswith("+") or raw_timegap.startswith("-")) and ":" in raw_timegap:
                            time = raw_timegap
                            timeinseconds = None
                            gap = None
                            interval = None

                        elif combined_timegap:
                            if raw_timegap.startswith("+") or raw_timegap.startswith("-"):
                                gap_val = float(Decimal(raw_timegap.replace("+", "").replace("-", "").strip().rstrip('s')).quantize(Decimal('0.001')))
                                if leadertime is not None:
                                    timeinseconds = leadertime + gap_val
                                    time = tts_to_normal(timeinseconds)
                                else:
                                    timeinseconds = None
                                    time = None
                                gap = raw_timegap
                                interval = float(Decimal(str(timeinseconds - previoustime)).quantize(Decimal('0.001'))) if timeinseconds and previoustime else None
                            else:
                                time = raw_timegap
                                timeinseconds = tts(time) if time else None
                                gap = None
                                interval = None
                                if pos == "1" and timeinseconds:
                                    leadertime = timeinseconds

                        else:
                            time = raw_timegap
                            timeinseconds = tts(time) if time else None
                            gap = cell_text(gap_idx)
                            interval = float(Decimal(str(timeinseconds - previoustime)).quantize(Decimal('0.001'))) if timeinseconds and previoustime else None
                            if pos == "1" and timeinseconds:
                                leadertime = timeinseconds

                        if timeinseconds:
                            previoustime = timeinseconds
                        # Skip empty rows
                        if not driver:
                            continue
                        for entrant in entrants:
                            if car_no and entrant['number'] == int(car_no):
                                entrant['prequalifyingposition'] = int(pos) if pos.isdigit() else None
                                entrant['prequalifyingtime'] = time
                                entrant['prequalifyingtimeinseconds'] = timeinseconds
                                entrant['prequalifyinggap'] = gap
                                entrant['prequalifyinginterval'] = interval                                
                            elif normalize_name(entrant['driver'].lower()) in normalize_name(driver.lower()):
                                entrant['prequalifyingposition'] = int(pos) if pos.isdigit() else None
                                entrant['prequalifyingtime'] = time
                                entrant['prequalifyingtimeinseconds'] = timeinseconds
                                entrant['prequalifyinggap'] = gap
                                entrant['prequalifyinginterval'] = interval
                    break
        if preq_table is None:
            print("Pre-qualifying section not found.")
                    

    # Calculate intervals for all sessions
    def calculate_intervals(entrants_list, session_type):
        """Calculate intervals (gap to person in front) for a session."""
        # Sort by position
        if session_type == 'race':
            sorted_entrants = sorted([e for e in entrants_list if e.get('raceposition')], key=lambda x: x['raceposition'])
            gap_key = 'racegapinseconds'
            interval_key = 'raceinterval'
        elif session_type == 'sprint':
            sorted_entrants = sorted([e for e in entrants_list if e.get('sprintposition')], key=lambda x: x['sprintposition'])
            gap_key = 'sprintgapinseconds'
            interval_key = 'sprintinterval'
        elif session_type == 'qualifying':
            sorted_entrants = sorted([e for e in entrants_list if e.get('qualifyingposition')], key=lambda x: x['qualifyingposition'])
            gap_key = 'qualifyinggapseconds'
            interval_key = 'qualifyinginterval'
        elif session_type == 'sprint_qualifying':
            sorted_entrants = sorted([e for e in entrants_list if e.get('sprint_qualifyingposition')], key=lambda x: x['sprint_qualifyingposition'])
            gap_key = 'sprint_qualifyinggap'
            interval_key = 'sprint_qualifyinginterval'            
        elif session_type.startswith('sprint_qualifying'):
            qual_num = session_type.split('_')[2]
            pos_key = f'sprint_qualifying{qual_num}position'
            gap_key = f'sprint_qualifying{qual_num}gap'
            interval_key = f'sprint_qualifying{qual_num}interval'
            sorted_entrants = sorted([e for e in entrants_list if e.get(pos_key)], key=lambda x: x[pos_key])
        elif session_type.startswith('qualifying'):
            qual_num = session_type.split('_')[1]
            pos_key = f'qualifying{qual_num}position'
            gap_key = f'qualifying{qual_num}gap'
            interval_key = f'qualifying{qual_num}interval'
            sorted_entrants = sorted([e for e in entrants_list if e.get(pos_key)], key=lambda x: x[pos_key])
        elif session_type.startswith('practice'):
            prac_num = session_type.split('_')[1]
            pos_key = f'practice{prac_num}position'
            gap_key = f'practice{prac_num}timeinseconds'
            interval_key = f'practice{prac_num}interval'
            sorted_entrants = sorted([e for e in entrants_list if e.get(pos_key)], key=lambda x: x[pos_key])
        elif session_type == 'fastestlap':
            sorted_entrants = sorted([e for e in entrants_list if e.get('fastestlap')], key=lambda x: x['fastestlap'])
            gap_key = 'fastestlapgapinseconds'
            interval_key = 'fastestlapinterval'
        elif session_type == 'sprintfastestlap':
            sorted_entrants = sorted([e for e in entrants_list if e.get('sprintfastestlap')], key=lambda x: x['sprintfastestlap'])
            gap_key = 'sprintfastestlapgapinseconds'
            interval_key = 'sprintfastestlapinterval'
        else:
            return
        
        prev_gap = None
        for entrant in sorted_entrants:
            if gap_key in entrant and entrant[gap_key] is not None:
                if prev_gap is None:
                    entrant[interval_key] = None
                else:
                    interval = float(Decimal(str(entrant[gap_key] - prev_gap)).quantize(Decimal('0.001')))
                    entrant[interval_key] = interval
                prev_gap = entrant[gap_key]
            else:
                entrant[interval_key] = None
    
    # Calculate intervals for all sessions
    calculate_intervals(entrants, 'race')
    calculate_intervals(entrants, 'sprint')
    calculate_intervals(entrants, 'qualifying')
    calculate_intervals(entrants, 'qualifying_1')
    calculate_intervals(entrants, 'qualifying_2')
    calculate_intervals(entrants, 'qualifying_3')
    calculate_intervals(entrants, 'sprint_qualifying')
    calculate_intervals(entrants, 'sprint_qualifying_1')
    calculate_intervals(entrants, 'sprint_qualifying_2')
    calculate_intervals(entrants, 'sprint_qualifying_3')
    calculate_intervals(entrants, 'practice_1')
    calculate_intervals(entrants, 'practice_2')
    calculate_intervals(entrants, 'practice_3')
    calculate_intervals(entrants, 'practice_4')
    calculate_intervals(entrants, 'fastestlap')
    calculate_intervals(entrants, 'sprintfastestlap')
                    
    return entrants.copy()


def fetch_tracinginsights_pitstops(year, grandprix_name):
    """
    Fetches pit stop data from TracingInsights GitHub archive.
    Returns list of pit stop dicts or None if not found.
    """
    # Format Grand Prix name for URL (e.g., "Bahrain Grand Prix" -> "Bahrain%20Grand%20Prix")
    if year >= 2021 and grandprix_name.endswith("Mexican Grand Prix"):
        grandprix_name = grandprix_name.replace("Mexican Grand Prix", "Mexico City Grand Prix")
    gp_encoded = urllib.parse.quote(grandprix_name.replace(str(year), '').strip())
    url = f"https://raw.githubusercontent.com/TracingInsights-Archive/PitStops/main/{year}/{gp_encoded}.json"
    retries = 0
    while retries < 3:
        try:
            req = urllib.request.Request(url, headers=headers)
            response = urllib.request.urlopen(req, timeout=10)
            break
        except urllib.error.URLError as e:
            retries += 1
            if retries == 3:
                raise RuntimeError(f"Failed to open URL {url} after three attempts due to error {e}")
    data = json.loads(response.read().decode('utf-8'))
    return data



def parse_pit_stop_summary (pit_table, entrants, year=None, grandprix_name=None):
    rows = pit_table.find('tbody').find_all('tr')
    pitstops = []
    for row in rows:
        cells = row.find_all('td')
        if len(cells) == 8:
            pitstopdetails = {
                'stopnumber': cells[0].text.strip(),
                'carnumber': cells[1].text.strip(),
                'lapstopped': cells[4].text.strip(),
                'timeofday': cells[5].text.strip(),
                'durationspentinpitlane': cells[6].text.strip(),
                'timeinseconds': tts(cells[6].text.strip()) if cells[6].text.strip() else None,
                'totaltimeforthewholerace': cells[7].text.strip(),
                'totaltimeinseconds': tts(cells[7].text.strip()) if cells[7].text.strip() else None
            }
            for entrant in entrants:
                if entrant['number'] == int(pitstopdetails['carnumber']):
                    pitstopdetails['driver'] = entrant['driver']
                    pitstopdetails['constructor'] = entrant['constructor']
                    pitstops.append(pitstopdetails)
                    break
    
    # Try to enhance with TracingInsights data if available (only for years > 2018)
    if year and grandprix_name:
        try:
            year_int = int(year)
            if year_int > 2018:
                ti_data = fetch_tracinginsights_pitstops(year_int, grandprix_name)
                if ti_data:
                    
                    # Build lookup map from TI data: (lap, driver_name, team) -> pit box time
                    ti_lookup = {}
                    for ti_stop in ti_data:
                        lap = int(ti_stop.get('Lap', 0))
                        driver = ti_stop.get('Driver', '').strip()
                        team = ti_stop.get('Team', '').strip()
                        pitbox_time = ti_stop.get('Time (sec)', None)
                        
                        if lap > 0 and driver and team and pitbox_time is not None:
                            key = (lap, driver.lower(), team.lower())
                            ti_lookup[key] = pitbox_time
                    
                    # Match pit stops with TI data by exact match first, then by subparts
                    # Store pit box time separately (don't overwrite timeinseconds)
                    matched_count = 0
                    for pitstop in pitstops:
                        lap = int(pitstop.get('lapstopped', 0))
                        driver = pitstop.get('driver', '').strip()
                        constructor = pitstop.get('constructor', '').strip()
                        
                        if lap > 0 and driver and constructor:
                            driver_lower = driver.lower()
                            constructor_lower = constructor.lower()
                            
                            # Try exact match first
                            key = (lap, driver_lower, constructor_lower)
                            if key in ti_lookup:
                                pitstop['durationstoppedinpitbox'] = ti_lookup[key]
                                pitstop['durationstoppedinpitbox_text'] = f"{ti_lookup[key]:.2f}"
                                matched_count += 1
                                continue
                            
                            # Try subpart matching: find TI entries with same lap
                            driver_parts_list = driver_lower.split()
                            driver_parts_set = set(driver_parts_list)
                            constructor_parts_list = constructor_lower.split()
                            constructor_parts_set = set(constructor_parts_list)
                            
                            best_match = None
                            best_score = 0
                            
                            for (ti_lap, ti_driver, ti_team), ti_pitbox_time in ti_lookup.items():
                                if ti_lap != lap:
                                    continue
                                
                                # Check driver subpart match
                                ti_driver_parts_list = ti_driver.split()
                                ti_driver_parts_set = set(ti_driver_parts_list)
                                driver_match = False
                                if driver_parts_set & ti_driver_parts_set:  # Check for common words
                                    driver_match = True
                                elif len(driver_parts_list) > 0 and len(ti_driver_parts_list) > 0:
                                    # Check if last names match (last part of name)
                                    if driver_parts_list[-1] == ti_driver_parts_list[-1]:
                                        driver_match = True
                                
                                # Check team/constructor subpart match
                                ti_team_parts_list = ti_team.split()
                                ti_team_parts_set = set(ti_team_parts_list)
                                team_match = False
                                if constructor_parts_set & ti_team_parts_set:  # Check for common words
                                    team_match = True
                                elif len(constructor_parts_list) > 0 and len(ti_team_parts_list) > 0:
                                    # Check if one contains the other (e.g., "Red Bull" in "Red Bull Racing")
                                    constructor_str = ' '.join(constructor_parts_list)
                                    team_str = ' '.join(ti_team_parts_list)
                                    if constructor_str in team_str or team_str in constructor_str:
                                        team_match = True
                                
                                # Score: driver match = 2 points, team match = 1 point
                                score = 0
                                if driver_match:
                                    score += 2
                                if team_match:
                                    score += 1
                                
                                # Require at least driver match
                                if score > best_score and score >= 2:
                                    best_score = score
                                    best_match = ti_pitbox_time
                            
                            if best_match is not None:
                                pitstop['durationstoppedinpitbox'] = best_match
                                pitstop['durationstoppedinpitbox_text'] = f"{best_match:.2f}"
                                matched_count += 1
        except (ValueError, TypeError):
            pass  # Skip if year cannot be converted to int
    
    return pitstops.copy()

def scrape_mss_laptimes(url, entrants):
    dqedj= open_json(url)
    laps = []  
    for driver in dqedj['content']:
        for entrant in entrants:
            if int(driver['carNumber']) == entrant['number']:
                for lapdata in driver['laps']:
                    lap = {
                        'driver': entrant['driver'],
                        'lap': lapdata['lapNumber'],
                        'timeinseconds': float(Decimal(str(lapdata['lapTime'])).quantize(Decimal('0.001'))) if lapdata['lapTime'] is not None else None,
                        'time': tts_to_normal(lapdata['lapTime']) if lapdata['lapTime'] is not None else None
                    }
                    laps.append(lap)

    return laps

def readlapcharts(url):
    lapchartdata = open_json(url)['content']
    entrant_map = defaultdict(list)
    for lap_entry in lapchartdata:
        lap = lap_entry['lap']
        for car in lap_entry['cars']:
            if not car:
                continue
            position = lap_entry['cars'].index(car) + 1
            entrant_map[int(car)].append((lap, position))
    return entrant_map
            

def scrape_tracinginsights (url, type=None):
    #find the session we are in from the url, example sprint qualifying, etc. 
    
    session = re.search(r'/([^/]+)/[^/]+/laptimes\.json$', url).group(1)
    session = urllib.parse.unquote(session).lower().replace(" ","")
    if session == "race":
        session = "grandprix"
    retries = 0
    while retries < 3:
        try:
            data = urllib.request.urlopen(url).read().decode('utf-8')
            break
        except:
            retries += 1
            time.sleep(1)
            if retries == 3:
                raise RuntimeError ("Failed to open TracingInsights data")
    data = json.loads(data)
    laps = []
    for index in range(len(data['lap'])):
        lap = {}
        lap['timeinseconds'] = float(Decimal(str(data['time'][index])).quantize(Decimal('0.001'))) if data['time'][index] != 'None' else None
        lap['time'] = tts_to_normal(lap['timeinseconds']) if lap['timeinseconds'] is not None else None
        lap['compound'] = data['compound'][index] if data['compound'][index] not in ('nan', "TEST_UNKNOWN", "UNKNOWN", "None") else None
        lap['lap'] = int(data['lap'][index]) 
        lap['stint'] = data['stint'][index] if data['stint'][index] != 'None' else None
        lap['s1'] = float(Decimal(str(data['s1'][index])).quantize(Decimal('0.001'))) if data['s1'][index] != 'None' else None
        lap['s2'] = float(Decimal(str(data['s2'][index])).quantize(Decimal('0.001'))) if data['s2'][index] != 'None' else None
        lap['s3'] = float(Decimal(str(data['s3'][index])).quantize(Decimal('0.001'))) if data['s3'][index] != 'None' else None
        lap['life'] = data['life'][index] if data['life'][index] != 'None' else None
        lap['position'] = data['pos'][index] if data['pos'][index] != 'None' else None
        lap['status'] = []
        for statuschar in data['status'][index]:
            if statuschar == '1':
                lap['status'].append('Green Flag')
            elif statuschar == '2':
                lap['status'].append('Yellow Flag')
            elif statuschar == '4':
                lap['status'].append('Safety Car')
            elif statuschar == '5':
                lap['status'].append('Red Flag')
            elif statuschar == '6':
                lap['status'].append('Virtual Safety Car')
            elif statuschar == '7':
                lap['status'].append('Virtual Safety Car Ending')
        lap['status'] = json.dumps(lap['status'])
        lap['qs'] = data.get('qs')[index] if data.get('qs') else None
        laps.append(lap)
    return laps

def parse_lap_by_lap(linkhref, entrants, dataid=None, dataidrace=None, year=None, grandprix_name=None):
    open_url(linkhref)
    output = []
    global name_map
    # Find the lap-by-lap table (using class name, could refine further if needed)
    table = soup.find("table", class_="GPtpt")
    if table.text.strip() != "":
        # Step 1: Extract raw abbreviation → {raw name, number}
        raw_driver_map = {}
        header_cells = table.find("thead").find_all("td")[1:]  # skip first column
        for cell in header_cells:
            a_tag = cell.find("a")
            if a_tag and "title" in a_tag.attrs:
                abbrev = a_tag.text.strip()
                raw_name = a_tag["title"].strip()
                contents = list(cell.stripped_strings)
                number = int(contents[-1]) if contents[-1].isdigit() else None
                raw_driver_map[abbrev] = {"raw_name": raw_name, "number": number}

        # Step 2: Resolve to actual full names from entrants
        resolved_driver_map = {}
        for abbr, info in raw_driver_map.items():
            parts = info["raw_name"].lower().replace('.', ' ').split()
            if parts:
                first_initial = parts[0][0]
                last_name = parts[-1]
                for entrant in entrants:
                    full = normalize_name(entrant["driver"])
                    first_initial = normalize_name(first_initial)
                    last_name = normalize_name(last_name)
                    if full.startswith(first_initial) and full.endswith(last_name):
                        resolved_driver_map[abbr] = {
                            "driver": entrant["driver"],
                            "number": info["number"]
                        }
                        break
            
            if abbr not in resolved_driver_map:
                raise ValueError(f"Could not resolve driver abbreviation '{abbr}' to a full name in entrants.")
                resolved_driver_map[abbr] = {
                    "driver": info["raw_name"],
                    "number": info["number"]
                }
            drivers_in_session = {
                info["driver"] for info in resolved_driver_map.values()
            }

        # Step 3: Parse lap data
        lap_rows = table.find("tbody").find_all("tr", class_="lap")
        for row in lap_rows:
            lap_td = row.find("td", class_="numlap")
            lap_number = int(lap_td.text.strip())
            # Check for safety car
            safetycar = "sc" in lap_td.get("class", [])
            position_cells = row.find_all("td")[1:]  # Skip lap number
            for position, cell in enumerate(position_cells, start=1):
                code = cell.text.strip()
                if code in resolved_driver_map:
                    output.append({
                        "position": position,
                        "driver": resolved_driver_map[code]["driver"],
                        "number": resolved_driver_map[code]["number"],
                        "lap": lap_number,
                        "type": "grandprix" if linkhref.endswith('/tour-par-tour.aspx') else "sprint",
                        "safetycar": safetycar
                    })
    else:
        if gp.endswith('Indianapolis 500'):
            print("Lap by lap data not found")
            resolved_driver_map = {}
        else:
            raise ValueError("Lap by lap data not found")

    if dataid is not None:
        # https://pitwall.app/analysis/compare-lap-times?season=76&race=1148&main_driver=541&compare_driver=614&button=
        open_url(f"https://pitwall.app/analysis/compare-lap-times?season={dataid}&race={dataidrace}")
        lxc = soup.find_all('span', {'input-id': 'main_driver'})
        comparecounter = 1
        constructedurl = f"https://pitwall.app/analysis/compare-lap-times?season={dataid}&race={dataidrace}"
        if len(lxc) % 2 == 1:
            lxc.append(lxc[0])
        for x in lxc:
            if comparecounter == 1:
                constructedurl += f"&main_driver={x['data-id']}"
                comparecounter += 1
            elif comparecounter == 2:
                open_url(constructedurl + f"&compare_driver={x['data-id']}")
                comparecounter = 1
                constructedurl = f"https://pitwall.app/analysis/compare-lap-times?season={dataid}&race={dataidrace}"
                laps = soup.find_all('div', class_='lap')
                cacheddrivers = []
                for lap in laps:
                    findlapnumber = int(lap.find('div', class_='lap-number').text.strip().replace('Lap ', ''))
                    maindriver = lap.find('div', class_='main-driver')
                    if maindriver.find('div', class_ = 'time').text.strip() != '':
                        driverposition = int(re.sub(r'\D', '', maindriver.find('span', class_='label').text.strip()))
                        for entrant in output:
                            if entrant['position'] == driverposition and entrant['lap'] == findlapnumber:
                                entrant['time'] = maindriver.find('div', class_='time').text.strip()
                                entrant['time_in_seconds'] = tts(maindriver.find('div', class_='time').text.strip())
                                break
                    comparedriver = lap.find('div', class_='compare-driver')
                    if comparedriver.find('div', class_ = 'time').text.strip() != '':
                        driverposition = int(re.sub(r'\D', '', comparedriver.find('span', class_='label').text.strip()))
                        for entrant in output:
                            if entrant['position'] == driverposition and entrant['lap'] == findlapnumber:
                                entrant['time'] = comparedriver.find('div', class_='time').text.strip()
                                entrant['time_in_seconds'] = tts(comparedriver.find('div', class_='time').text.strip())
                                break   
    lap_index = {}
    for e in output:
        lap_index[(e["driver"], e["lap"])] = e

    if year is not None and grandprix_name is not None:
        retries = 0
        if int(year) >= 2018:
            while retries < 3:
                try:
                    year_int = int(year)
                    if year_int >= 2018:
                        # Try to get data from TracingInsights
                        #https://cdn.jsdelivr.net/gh/TracingInsights/2020/Sakhir%20Grand%20Prix/Qualifying/VER/laptimes.json"
                        session = "Race" if linkhref.endswith('/tour-par-tour.aspx') else "Sprint"
                        session_ = session
                        if year == 2021 and session == "Sprint":
                            session_ = "Sprint%20Qualifying"
                        #for each driver, get abbr and insert it and get times:
                        for entrant in entrants:
                            driver_fullname = entrant['driver']
                            driver_abbr = None
                            # skip drivers not in this race/sprint
                            if driver_fullname not in drivers_in_session:
                                continue  
                            #skip drivers who did not start:
                            if grandprix_name == "Mexican Grand Prix" and year >= 2020:
                                grandprix_name = "Mexico City Grand Prix"                            
                            driversintracinginsightssession = json.loads(urllib.request.urlopen(f"https://cdn.jsdelivr.net/gh/TracingInsights/{year_int}/{urllib.parse.quote(grandprix_name)}/{session_}/drivers.json").read().decode('utf-8'))          
                            for THEABBREVIATION in resolved_driver_map:
                                if normalize_name(resolved_driver_map[THEABBREVIATION]['driver'].lower()) == normalize_name(driver_fullname.lower()):
                                    driver_abbr = THEABBREVIATION
                                    break
                            if driver_abbr is None:
                                raise ValueError(f"Could not find abbreviation for driver '{driver_fullname}' in name_map.")
                            if not any(driver_abbr == driver['driver'] for driver in driversintracinginsightssession['drivers']):
                                print(f"{driver_abbr} not in session {session_}")
                                continue                            
                            ti_url = f"https://cdn.jsdelivr.net/gh/TracingInsights/{year_int}/{urllib.parse.quote(grandprix_name)}/{session_}/{driver_abbr}/laptimes.json"
                            ti_laps = scrape_tracinginsights(ti_url)
                            if session == "Race":
                                driver_name = resolved_driver_map[driver_abbr]['driver']

                                for ti_lap in ti_laps:
                                    key = (driver_name, ti_lap["lap"])
                                    entrant_entry = lap_index.get(key)
                                    if not entrant_entry:
                                        continue

                                    entrant_entry["compound"] = ti_lap["compound"]
                                    entrant_entry["stint"] = ti_lap["stint"]
                                    entrant_entry["s1"] = ti_lap["s1"]
                                    entrant_entry["s2"] = ti_lap["s2"]
                                    entrant_entry["s3"] = ti_lap["s3"]
                                    entrant_entry["life"] = ti_lap["life"]
                                    entrant_entry["status"] = json.dumps(ti_lap["status"])

                                    if entrant_entry.get("time") is None:
                                        entrant_entry["time"] = ti_lap["time"]
                                        entrant_entry["time_in_seconds"] = ti_lap["timeinseconds"]

                            elif session == "Sprint":
                                driver_name = resolved_driver_map[driver_abbr]["driver"]

                                for ti_lap in ti_laps:
                                    key = (driver_name, ti_lap["lap"])
                                    entrant_entry = lap_index.get(key)

                                    if not entrant_entry:
                                        continue

                                    # Common fields
                                    entrant_entry["compound"] = ti_lap.get("compound")
                                    entrant_entry["stint"] = ti_lap.get("stint")
                                    entrant_entry["s1"] = ti_lap.get("s1")
                                    entrant_entry["s2"] = ti_lap.get("s2")
                                    entrant_entry["s3"] = ti_lap.get("s3")
                                    entrant_entry["life"] = ti_lap.get("life")
                                    entrant_entry["status"] = json.dumps(ti_lap.get("status"))
                                    entrant_entry["time"] = ti_lap["time"]
                                    entrant_entry["time_in_seconds"] = ti_lap.get("timeinseconds")
                                
                    break  # Exit retry loop on success               
                except Exception as e:
                    print (f"Error fetching TracingInsights data for {grandprix_name} {year}, retrying... \n Error: {e}")
                    retries += 1
                    time.sleep(2)  
                    if retries == 3:
                        raise ValueError(f"Failed to fetch TracingInsights data for {grandprix_name} {year} after 3 retries.")                           
    
    return output, resolved_driver_map



def parse_in_season_progress(racelink):
    open_url(racelink)
    
    drivers_table = soup.find('div', id='ctl00_CPH_Main_DIV_ChpPilote')
    constructors_table = soup.find('div', id='ctl00_CPH_Main_DIV_ChpConstructeur')

    driversprogress = []
    constructorsprogress = []

    # Parse Drivers
    if drivers_table:
        table = drivers_table.find('table', class_='datatable')
        if table:
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 3:
                    driversprogress.append({
                        "positionatthispoint": int(cells[0].text.strip().replace('.', '')) if cells[0].text.strip().replace('.', '').isdigit() else (driversprogress[-1]["positionatthispoint"] if driversprogress else None),
                        "driver": format_name_from_caps(cells[1].text.strip()),
                        "pointsatthispoint": float(cells[2].text.strip())
                    })

    # Parse Constructors
    if constructors_table:
        table = constructors_table.find('table', class_='datatable')
        if table:
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 3:
                    links = cells[1].find_all('a')
                    constructorsprogress.append({
                        "positionatthispoint": int(cells[0].text.strip().replace('.', '')) if cells[0].text.strip().replace('.', '').isdigit() else (constructorsprogress[-1]["positionatthispoint"] if constructorsprogress else None),
                        "constructor": links[0].text.strip() if len(links) > 0 else "",
                        "engine": links[1].text.strip() if len(links) > 1 else (links[0].text.strip() if len(links) > 0 else ""),
                        "pointsatthispoint": float(cells[2].text.strip())
                    })

    return [driversprogress, constructorsprogress]

#if driver/constructor started previous race, the remaining races are in RaceByRace, and by the class of the element i extract racebyrace from, i can get the remaining sprints and races. then from last place in championship to first: next we get the points system from Seasons, get 1st for races, 1st for sprints (if exists), and 'Fastest Lap', if exists. then we add them up and see if you can go higher, if so, then don't assign position for driver ahead and yourself. if you can't go ahead, and driver behind you can't overtake, you get assigned a position. if driver did not participate last race, come back to them, and then check whether higher/lower from next race.
def parse_championship_results (year, drivermap):
    open_url(f"https://www.statsf1.com/en/{year}.aspx")
    #print (drivermap)
    output = []
    driverschampionship = []
    constructorschampionship = []
    drivers_table = soup.find('table', id = 'ctl00_CPH_Main_TBL_CHP_Drv')
    constructors_table = soup.find('table', id = 'ctl00_CPH_Main_TBL_CHP_Cst')
    driversrows = drivers_table.find_all('tr')[1:]
    headercells = drivers_table.find_all('tr')[0].find_all('td')
    cur.execute("SELECT MAX(GrandPrixID) FROM GrandPrixResults")
    latest_gp_id = cur.fetchone()[0]
    for row in driversrows:
        cells = row.find_all('td')
        if cells[0].get('colspan')== '27':
            continue
        driverindo = {
            'position': int(cells[0].text.strip().replace('.', '')) if cells[0].get_text(strip=True).replace('.', '').isdigit() else driverschampionship[-1]["position"],
            'driver': drivermap[cells[1].text.strip()]
        }
        if headercells[-1].text.strip() == 'Out of' and headercells[-2].text.strip() == 'Pts':
            driverindo['points'] = float(cells[-2].text.strip())
            driverindo['outof'] = float(cells[-1].text.strip()) if cells[-1].text.strip() != '' else driverindo['points']
            seasonprogress = {}
            for i, race in enumerate(cells[2:-2]):
                therace = headercells[1:-2][i].find('span', class_ = 'codegp')['title']
                racepoints = race.text.strip()
                if racepoints == "-":
                    racepoints = (0, None, "gp")
                elif racepoints == "":
                    racepoints = (None, None, "gp") 
                elif racepoints.startswith('(') and racepoints.endswith (')'):
                    racepoints = (float(racepoints.replace('(', '').replace(')', '').replace(',', '.')), True, "gp")       
                else:
                    racepoints = (float(racepoints.replace(',', '.')), False, "gp")                 
                seasonprogress[therace] = racepoints
        elif headercells[-1].text.strip() == 'Pts':
            driverindo['points'] = float(cells[-1].text.strip())
            driverindo['outof'] = None
            seasonprogress = {}
            for i, race in enumerate(cells[2:-1]):
                therace = headercells[1:-1][i].find('span', class_ = ['codegp', 'codesp'])['title']
                racepoints = race.text.strip()
                rtype = "gp" if headercells[1:-1][i].find('span', class_ = ['codegp', 'codesp'])['class'][0] == 'codegp' else "sp"
                if racepoints == "-":
                    racepoints = (0, None, rtype)
                elif racepoints == "":
                    racepoints =( None, None, rtype)
                elif racepoints.startswith('(') and racepoints.endswith (')'):
                    racepoints = (float(racepoints.replace('(', '').replace(')', '').replace(',', '.')), True, rtype)    
                else:
                    racepoints =(float(racepoints.replace(',', '.')), False, rtype)                 
                seasonprogress[therace] = racepoints   
        driverindo['racebyrace'] = seasonprogress     
        driverschampionship.append(driverindo)
    output.append(driverschampionship)
    if constructors_table:
        constructorsrows = constructors_table.find_all('tr')[1:]
        headercells = constructors_table.find_all('tr')[0].find_all('td')  # Get headers from first row
        for row in constructorsrows:
            cells = row.find_all('td')
            if cells[0].get('colspan') == '27':
                continue
            constructorindo = {
                'position': int(cells[0].text.strip().replace('.', '')) if cells[0].get_text(strip=True).replace('.', '').isdigit() else constructorschampionship[-1]["position"],
                'constructor': cells[1].find_all('a')[0].text.strip(),
                'engine': cells[1].find_all('a')[1].text.strip() if len(cells[1].find_all('a')) == 2 else cells[1].find_all('a')[0].text.strip()
            }
            if headercells[-1].text.strip() == 'Out of' and headercells[-2].text.strip() == 'Pts':
                constructorindo['points'] = float(cells[-2].text.strip())
                constructorindo['outof'] = float(cells[-1].text.strip()) if cells[-1].text.strip() != '' else constructorindo['points']
                seasonprogress = {}
                for i, race in enumerate(cells[2:-2]):
                    therace = headercells[1:-2][i].find('span', class_ = 'codegp')['title']
                    racepoints = race.text.strip()
                    if racepoints == "-":
                        racepoints = (0, None, "gp")
                    elif racepoints == "":
                        racepoints =(None, None, "gp")
                    elif racepoints.startswith('(') and racepoints.endswith (')'):
                        racepoints = (float(racepoints.replace('(', '').replace(')', '')), True, "gp")    
                    else:
                        racepoints =(float(racepoints.replace(',', '.')), False, "gp")                
                    seasonprogress[therace] = racepoints
            elif headercells[-1].text.strip() == 'Pts':
                constructorindo['points'] = float(cells[-1].text.strip())
                constructorindo['outof'] = None
                seasonprogress = {}
                for i, race in enumerate(cells[2:-1]):
                    therace = headercells[1:-1][i].find('span', class_ = ['codegp', 'codesp'])['title']
                    racepoints = race.text.strip()
                    rtype = "gp" if headercells[1:-1][i].find('span', class_ = ['codegp', 'codesp'])['class'][0] == 'codegp' else "sp"
                    if racepoints == "-":
                        racepoints = (0, None, rtype)
                    elif racepoints == "":
                        racepoints =( None, None, rtype)
                    elif racepoints.startswith('(') and racepoints.endswith (')'):
                        racepoints = (float(racepoints.replace('(', '').replace(')', '').replace(',', '.')), True, rtype)    
                    else:
                        racepoints =(float(racepoints.replace(',', '.')), False, rtype)                              
                    seasonprogress[therace] = racepoints   
            constructorindo['racebyrace'] = seasonprogress
            constructorschampionship.append(constructorindo)
        output.append(constructorschampionship) 
    else:
        constructorschampionship = []
        output.append(constructorschampionship)       
    return output.copy()

def get_tiebreaker_key(entrant):
    results = []

    for _, data in entrant['racebyrace'].items():
        if data[0] is not None:
            results.append(data[0])

    results.sort(reverse=True)
    return tuple(results)


def apply_mathematical_locks(standings, points_system):
    if not standings:
        return standings

    # 1. Identify Future Races / Weekends
    first_entry = standings[0]
    race_names = list(first_entry['racebyrace'].keys())
    future_gps, future_sprints = 0, 0

    for race in race_names:
        # A race is future only if NO entrant has a result yet
        if all(thing['racebyrace'][race][0] is None for thing in standings):
            if race == "Indianapolis":
                continue 
            rtype = first_entry['racebyrace'][race][2]
            if rtype == 'gp':
                future_gps += 1

            elif rtype == 'sp':
                # Sprint weekend still has a Grand Prix
                future_gps += 1
                future_sprints += 1

    # Season finished → standings already final
    if future_gps == 0 and future_sprints == 0:
        return standings

    # 2. Maximum Remaining Points (Constructor-aware)
    gp_scores = points_system.get('grandprix', {})
    gp_positions = sorted(
        [v for k, v in gp_scores.items() if k.isdigit()],
        reverse=True
    )

    max_gp = (
        gp_positions[0] +
        (gp_positions[1] if len(gp_positions) > 1 else 0) +
        gp_scores.get('Fastest Lap', 0)
    )

    sp_scores = points_system.get('sprint', {})
    sp_positions = sorted(
        [v for k, v in sp_scores.items() if k.isdigit()],
        reverse=True
    )

    max_sp = (
        sp_positions[0] +
        (sp_positions[1] if len(sp_positions) > 1 else 0) +
        sp_scores.get('Fastest Lap', 0)
    )

    total_remaining = (future_gps * max_gp) + (future_sprints * max_sp)

    # 3. Apply Mathematical Locks
    n = len(standings)

    for i in range(n):
        me = standings[i]
        locked = True  # assume locked unless proven otherwise

        # Can I catch the entry ahead?
        if i > 0:
            ahead = standings[i - 1]
            my_max = me['points'] + total_remaining

            if my_max > ahead['points']:
                locked = False
            elif my_max == ahead['points']:
                if get_tiebreaker_key(me) > get_tiebreaker_key(ahead):
                    locked = False

        # Can someone behind catch me?
        if i < n - 1:
            behind = standings[i + 1]
            if behind['points'] + total_remaining >= me['points']:
                locked = False

        if not locked:
            me['position'] = None
    return standings


def parsenotes (links):
    notes = {}
    for link in links:
        if link['href'].startswith('https://motorsportstats.com'):
            continue
        if not link['href'].startswith('/en/results/'):            
            open_url(f"https://www.statsf1.com{link['href']}")
            notesdiv = soup.find('div', id='ctl00_CPH_Main_P_Commentaire')
            if link['href'].endswith('engages.aspx'):
                notes["EntrantsNotes"] = notesdiv.text.strip() if notesdiv else ''
            elif link['href'].endswith('qualification.aspx'):
                notes["QualifyingNotes"] = notesdiv.text.strip() if notesdiv else ''
            elif link['href'].endswith('grille.aspx'):
                notes["StartingGridNotes"] = notesdiv.text.strip() if notesdiv else ''
            elif link['href'].endswith('classement.aspx'):
                notes["RaceResultNotes"] = notesdiv.text.strip() if notesdiv else ''
            elif link['href'].endswith('sprint.aspx?grille'):
                notes["SprintGridNotes"] = notesdiv.text.strip() if notesdiv else ''
            elif link['href'].endswith('sprint.aspx'):
                notes["SprintNotes"] = notesdiv.text.strip() if notesdiv else ''
    return notes.copy()

months = {
    'Jan': 1,
    'Feb': 2,
    'Mar': 3,
    'Apr': 4,
    'May': 5,
    'Jun': 6,
    'Jul': 7,
    'Aug': 8,
    'Sep': 9,
    'Oct': 10,
    'Nov': 11,
    'Dec': 12
}

# Check if there are no races in the database
#Also, check if there are are no circuit layouts in the CircuitLayouts table. 
# If there are, then we can skip the circuit scraping and just do the mapping of grand prix to circuit layout id. 
# If there are no circuit layouts, then we need to do the full scrape of circuits and circuit layouts.
cur.execute("SELECT COUNT(*) FROM CircuitLayouts")
if cur.fetchone()[0] == 0:
    cur.execute("SELECT COUNT(*) FROM GrandsPrix")
    mappings = {}
    if cur.fetchone()[0] == 0:
        open_url("https://www.statsf1.com/en/circuits.aspx")
        table = soup.find('table')
        trs = table.find_all('tr')
        for tr in trs[1:-1]:
            p = tr.find_all('td')[0]
            v = p.find('a')
            print ("Processing circuit: ", v.get_text(strip=True))
            twd = v['href']
            open_url(f'https://www.statsf1.com/{twd}')
            a_tag = soup.find('a', id='ctl00_CPH_Main_HL_GMaps')['href']
            coord_str = a_tag[a_tag.index('@') + 1 : a_tag.rindex(',')]
            lat = coord_str[:coord_str.index(',')]
            lng = coord_str[coord_str.index(',') + 1:]  
            mappings[v.get_text(strip=True)] = (lat, lng)
            circuitlayoutdivs = soup.find_all('div', class_ = 'circuitversion')
            for layoutdiv in circuitlayoutdivs:
                circuittable = layoutdiv.find('table', class_ = 'sortable circuittable').find_all('tr')
                dates = [tr.find_all('td')[0]['sorttable_customkey'] for tr in circuittable[1:-1]]                
                version = circuitlayoutdivs.index(layoutdiv) + 1
                layoutimg = layoutdiv.find('img')['src']
                circuit_text_div = layoutdiv.find('div', class_='circuitversiontxt')
                circuit_text = circuit_text_div.get_text(strip=True).replace('\n', '').replace('"', '').replace('\r', '')            
                t = generate_track_svg(f'https://www.statsf1.com{layoutimg}')
                cur.execute("INSERT INTO CircuitLayouts (Latitude, Longitude, GrandPrixDates, CircuitVersion, SVG, CircuitChanges)  VALUES (?, ?, ?, ?, ?, ?)", (lat, lng, json.dumps(dates), version, t, circuit_text))
                cur.execute("SELECT ID FROM CircuitLayouts WHERE Latitude = ? AND Longitude = ? AND CircuitVersion = ?", (lat, lng, version)) 
                circuitlayoutid = cur.fetchone()[0]
else:
    cur.execute("SELECT COUNT(*) FROM GrandsPrix")
    #if there are less than 1149 grands prix in the database, this will suffice.
    count = cur.fetchone()[0]
    if count < 1149:
        mappings = {'Adelaide': ('-34.9269993', '138.6172609'), 'Aida': ('34.9152924', '134.2207281'), 'Ain-Diab': ('33.5805298', '-7.68909'), 'Aintree': ('53.4759049', '-2.9413726'), 'Anderstorp': ('57.2639056', '13.6030116'), 'Austin': ('30.1336367', '-97.6345729'), 'AVUS': ('52.48658', '13.26549'), 'Baku': ('40.3712591', '49.8476935'), 'Barcelona': ('41.5682768', '2.2582064'), 'Brands Hatch': ('51.3555433', '0.2629122'), 'Bremgarten': ('46.9581878', '7.402719'), 'Buenos Aires': ('-34.6922845', '-58.4550501'), 'Caesars Palace': ('36.119148', '-115.1771724'), 'Clermont-Ferrand': ('45.7456087', '3.0402848'), 'Dallas': ('32.7767709', '-96.7593567'), 'Detroit': ('42.3280081', '-83.0405242'), 'Dijon-Prenois': ('47.3619752', '4.8995105'), 'Donington': ('52.8296656', '-1.3749465'), 'East London': ('-33.0491788', '27.8745906'), 'Estoril': ('38.7491677', '-9.394149'), 'Fuji': ('35.3689657', '138.9281865'), 'Hockenheim': ('49.3308527', '8.5790215'), 'Hungaroring': ('47.5817579', '19.2507484'), 'Imola': ('44.3398577', '11.7133288'), 'Indianapolis': ('39.7955151', '-86.2362663,4080a,20y'), 'Interlagos': ('-23.7032926', '-46.696961'), 'Istanbul': ('40.9552661', '29.4096963'), 'Jacarepagua': ('-22.9779874', '-43.3958898'), 'Jarama': ('40.6147065', '-3.5860519'), 'Jeddah': ('21.6380938', '39.0994433'), 'Jerez de la Frontera': ('36.7075431', '-6.0326723'), 'Kuala Lumpur': ('2.7597106', '101.7371379'), 'Kyalami': ('-25.9976867', '28.067626'), 'Las Vegas': ('36.1170295', '-115.1649455'), 'Le Castellet': ('43.2511291', '5.7894971'), 'Le Mans': ('47.951629', '0.2101078'), 'Long Beach': ('33.7640562', '-118.1887551'), 'Lusail': ('25.4904378', '51.4538568'), 'Magny-Cours': ('46.8619335', '3.1655065'), 'Melbourne': ('-37.8491401', '144.9698726'), 'Mexico City': ('19.4002574', '-99.0902792'), 'Miami': ('25.9577398', '-80.238678'), 'Monaco': ('43.7380948', '7.4260503'), 'Monsanto': ('38.7165398', '-9.2007324'), 'Mont-Tremblant': ('46.1865295', '-74.6096944'), 'Montjuïc Park': ('41.3680722', '2.1517021'), 'Montreal': ('45.50589', '-73.52411'), 'Monza': ('45.6184477', '9.2876756'), 'Mosport Park': ('44.0468166', '-78.6744209'), 'Mugello': ('43.9971945', '11.3722542'), 'New Delhi': ('28.3473368', '77.5337797'), 'Nivelles': ('50.6197164', '4.3277699'), 'Nürburgring': ('50.3292676', '6.942535'), 'Österreichring': ('47.22244', '14.7595'), 'Pedralbes': ('41.3881241', '2.1173237'), 'Pescara': ('42.4773755', '14.1548578'), 'Phoenix': ('33.44701', '-112.07681'), 'Portimão': ('37.2288843', '-8.627678'), 'Porto': ('41.1685927', '-8.6786295'), 'Reims': ('49.2583768', '3.9230837'), 'Riverside': ('33.93438', '-117.27276'), 'Rouen-les-Essarts': ('49.3333869', '1.0022022'), 'Sakhir': ('26.0303897', '50.513543'), 'Sebring': ('27.4548527', '-81.3513999'), 'Shanghai': ('31.341322', '121.21911'), 'Silverstone': ('52.07159', '-1.01615'), 'Singapore': ('1.2875346', '103.8554768'), 'Sochi': ('43.4067237', '39.9569962'), 'Spa-Francorchamps': ('50.4386283', '5.9666064'), 'Spielberg': ('47.2235862', '14.7555404'), 'Suzuka': ('34.8431556', '136.5266977'), 'Valencia': ('39.458529', '-0.330191'), 'Watkins Glen': ('42.336931', '-76.924553'), 'Yas Marina': ('24.4717208', '54.6018358'), 'Yeongam': ('34.7372903', '126.4123532'), 'Zandvoort': ('52.3878911', '4.5430609'), 'Zeltweg': ('47.200012', '14.741163'), 'Zolder': ('50.9900265', '5.254855')}    
    else:
        mappings = {}
        open_url("https://www.statsf1.com/en/circuits.aspx")
        table = soup.find('table')
        trs = table.find_all('tr')
        for tr in trs[1:-1]:
            p = tr.find_all('td')[0]
            v = p.find('a')
            print ("Processing circuit: ", v.get_text(strip=True))
            twd = v['href']
            open_url(f'https://www.statsf1.com/{twd}')
            a_tag = soup.find('a', id='ctl00_CPH_Main_HL_GMaps')['href']
            coord_str = a_tag[a_tag.index('@') + 1 : a_tag.rindex(',')]
            lat = coord_str[:coord_str.index(',')]
            lng = coord_str[coord_str.index(',') + 1:]  
            mappings[v.get_text(strip=True)] = (lat, lng)


    
conn.commit()   

def link_circuitlayout(lat, lng, date):
    yyyymmdd = date.strftime('%Y%m%d')
    cur.execute(
        "SELECT ID FROM CircuitLayouts "
        "WHERE Latitude = ? AND Longitude = ? AND GrandPrixDates LIKE ?",
        (lat, lng, f'%{yyyymmdd}%')
    )
    circuitlayoutids = cur.fetchall()
    return circuitlayoutids[0][0] if circuitlayoutids else None


cur.execute("SELECT Season FROM Seasons ORDER BY season DESC LIMIT 1")
row = cur.fetchone()
last_season = row[0] if row else 1950
index = range(1950, last_season + 1).index(last_season)  

executed = False
open_url("https://www.statsf1.com/en/saisons.aspx")
divs = soup.find('div', class_='saison')
soup = BeautifulSoup(str(divs), 'html.parser')
seasons = soup.find_all('a')
for season in seasons[index:]: 
    driverids = {}
    teamids = {}
    constructorids = {}
    chassisids = {}
    engineids = {}
    enginemodelids = {}
    tyreids = {} 
    nationalityids = {}    
    dataid = None
    name_map = {}   
    year = int(season['href'][4:8])  
    if year > datetime.date.today().year:
        continue
    #req = urllib.request.Request(f"https://gpracingstats.com/seasons/{year}-world-championship/", headers=headersfr)
    #html = urllib.request.urlopen(req).read() 
    #soup = BeautifulSoup(html, 'html.parser')
    open_url(f"https://pitwall.app/races/archive/{year}")
    tags = soup.find('table', class_= 'data-table').find('tbody').find_all('tr')  # find all links
    #now we open motorsportstats.com's data.  
    mslinks = [t['name'].replace('  ', ' ') for t in open_json(f"https://motorsportstats.com/_next/data/c2LGT9ym-c6f1pXlf9hjs/series/fia-formula-one-world-championship/calendar/{year}.json")['pageProps']['calendar']['events'] if "season test" not in t['name'].lower() and t.get('status', '').lower() != 'cancelled'] 
    #print (tags)
    gps = []
    thelist = []
    for tag in tags:
        cells = tag.find_all('td')
        if datetime.date.today() < datetime.date(year, months[cells[0].text.strip().split()[0]], int(cells[0].text.strip().split()[1])):
           break
        else:
            currentgrandprix = cells[1].find('a').text.strip()
            gps.append(currentgrandprix)
            thedate = cells[0].text.strip()
            dateindatetime = datetime.date(year, months[cells[0].text.strip().split()[0]], int(cells[0].text.strip().split()[1]))
            thecircuit = cells[2].text.strip()
            thelist.append((thedate, dateindatetime, currentgrandprix, thecircuit))
    last_grandprix = None
    if not executed:
        cur.execute("SELECT GrandPrixName, ID FROM GrandsPrix ORDER BY ID DESC LIMIT 1")
        xsqqwfejk = cur.fetchone()
        last_grandprix = xsqqwfejk[0] if xsqqwfejk else None
        last_grandprix_id = xsqqwfejk[1] if xsqqwfejk else -1
        executed = True
        if last_grandprix == gps[-1]:
            continue
    
    gpindex = gps.index(last_grandprix) + 1 if last_grandprix else 0            
    #year = 1983 #For debugging purposes, we set the year to 1983 🚫✔️
    print(year)
    if year > 1982: #We only scrape from F1.com from 1983 onwards, before that StatsF1 has more data than F1.com, from 1983, F1.com has Q1, Q2 (and drivers Q1, Q2 and Q3 times) and pit stop summary, which StatsF1 does not have
        open_url(f"https://www.formula1.com/en/results/{year}/races")
        #print ("IF EXECUTED")
        f1websiteraces = soup.find_all('a', class_ = 'flex gap-px-10 items-center')
    #Finds the scoring systems for drivers and constructors
    open_url(f"https://www.statsf1.com{season['href']}") 
    save = f"https://www.statsf1.com{season['href']}"
    driverschampionshiptable = soup.find('table', id = 'ctl00_CPH_Main_TBL_CHP_Drv')
    tablerows = driverschampionshiptable.find_all('tr')
    drivernames = []
    for row in tablerows[1:]:
        if len(row.find_all("td")) ==  1:
            continue
        cells = row.find_all("td")
        drivername = cells[1].text.strip()
        # Apply name corrections to drivernames from championship table
        if drivername == "Guanyu Zhou":
            drivername = "Zhou Guanyu"
        drivernames.append(drivername)
    points_system_drivers, points_system_constructors = parse_points_system(str(soup))
    #print(points_system_drivers, points_system_constructors)
    print ("Points System Parsed")            
        #print("Drivers' Points System:", points_system_drivers)
        #print("Constructors' Points System:", points_system_constructors)
    if year > 1995: #we have lap-by-lap data from 1996
        # https://pitwall.app/analysis/compare-lap-times?season=76&race=1148&main_driver=541&compare_driver=614&button=
        open_url("https://pitwall.app/analysis/compare-lap-times")
        seasonsan = soup.find_all("div", class_='items cols cols-4')
        seasonsan = seasonsan[0].find_all('span', class_='item') if seasonsan else []
        for season in seasonsan:
            if int(season.text.strip()) == year:
                dataid = season['data-id']
                break 
    #Finds the regulations (technical) for the season 
    open_url(save)  
    regs = soup.find_all('div', class_ = 'yearinfo')
    for reg in regs:
        regulations = parse_regulations(str(reg)) if reg else None
        #print("Regulations:", regulations)
        print ("Regulations Parsed") 
    cur.execute("""INSERT OR IGNORE INTO Seasons (Season, DriversRacesCounted, PointsSharedForSharedCars, GrandPrixPointsSystemDrivers, SprintPointsSystemDrivers,
                ConstructorsRacesCounted, PointsOnlyForTopScoringCar, GrandPrixPointsSystemConstructors, SprintPointsSystemConstructors,
                RegulationNotes, MinimumWeightofCars, EngineType, Supercharging, MaxCylinderCapacity, NumberOfCylinders, MaxRPM, NumberOfEnginesAllowedPerSeason,
                FuelType, RefuellingAllowed, MaxFuelConsumption) 
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (year, points_system_drivers['scores'], points_system_drivers['pointssharedforsharedcars'], json.dumps(points_system_drivers['grandprix']), json.dumps(points_system_drivers['sprint']),
                points_system_constructors.get('scores'), points_system_constructors.get('topscoring'), json.dumps(points_system_constructors.get('grandprix')), json.dumps(points_system_constructors.get('sprint')),
                json.dumps(regulations.get('notes')), regulations['Weight (min)'], regulations['Engine']['Type'], regulations['Engine']['Supercharging'], regulations['Engine']['Cylinder capacity (max)'], regulations['Engine']['Cylinders'], regulations['Engine']['Rpm (max)'], regulations['Engine']['Number'],
                regulations['Fuel']['Type'], regulations['Fuel']['Refuelling'], regulations['Fuel']['Consumption (max)']))  
    cur.execute("UPDATE Seasons SET needstatsupdate = 1 WHERE Season = ?", (year,))
    print ("Regulations data saved to database")      
    trigger2 = False
    #quit() #For debugging purposes, we quit after the first season  🚫✔️
    #Finds all the grands prix for the season   
    div = soup.find('div', class_ = 'gpaffiche')
    soup = BeautifulSoup(str(div), 'html.parser')
    grandsprix = soup.find_all('a')[:len(gps)] 
    for grandprix in grandsprix[gpindex:]:
        sxs = None
        gp = gps[grandsprix.index(grandprix)]   
        # Convert Mexican Grand Prix to Mexico City Grand Prix from 2021 onwards
        if year >= 2021 and gp.endswith("Mexican Grand Prix"):
            gp = gp.replace("Mexican Grand Prix", "Mexico City Grand Prix")
        print (gp)
        theneeded = thelist[grandsprix.index(grandprix)]
        #print (gps[-1])
        if gp == gps[-1]:
            #print ("happening")
            trigger2 = True         
        #break #To see whether the f1.com data will be executed now 🚫✔️
        open_url(f"https://www.statsf1.com{grandprix['href']}")
        raceinfo = soup.find('div', class_ = 'border-top')
        race_info = parse_race_info(str(raceinfo), theneeded)
        if race_info['track_name'] in mappings.keys():
            race_info['latitude'], race_info['longitude'] = mappings[race_info['track_name']]
            #If this is being updated, not reset, and this start off from the last grand prix, then we check if there are new circuit layouts for the circuit since the last grand prix, and if there are, we add them to the database.
            if race_info['race_number'] > last_grandprix_id > 1149: 
                #temporary solution. 1149 is the 2025 Abu Dhabi Grand Prix, which is the last grand prix in the database currently, 
                #so if the last grand prix id is greater than 1149, it means we are updating and not resetting, 
                # and we can check for new circuit layouts since the last grand prix.
                open_url(f"https://www.statsf1.com/en/circuit-{race_info['track_name'].replace(' ', '-').lower()}.aspx")  
                circuitlayoutdivs = soup.find_all('div', class_ = 'circuitversion')
                cur.execute ("SELECT CircuitVersion FROM CircuitLayouts WHERE Latitude = ? AND Longitude = ?", (race_info['latitude'], race_info['longitude']))
                existing_versions = cur.fetchall()
                existing_version_numbers = [v[0] for v in existing_versions]
                print(f"Processing circuit: {race_info['track_name']}, existing versions: {existing_version_numbers}")
                for layoutdiv in circuitlayoutdivs:
                    circuittable = layoutdiv.find('table', class_ = 'sortable circuittable').find_all('tr')
                    dates = [tr.find_all('td')[0]['sorttable_customkey'] for tr in circuittable[1:-1]]
                    version = circuitlayoutdivs.index(layoutdiv) + 1
                    if version not in existing_version_numbers:
                        layoutimg = layoutdiv.find('img')['src']
                        t = generate_track_svg(f'https://www.statsf1.com{layoutimg}')
                        circuit_text_div = soup.find('div', class_='circuittext')
                        circuit_text = circuit_text_div.get_text(strip=True).replace('\n', '').replace('"', '').replace('\r', '')                
                        cur.execute("INSERT INTO CircuitLayouts (Latitude, Longitude, GrandPrixDates, CircuitVersion, SVG, CircuitChanges)  VALUES (?, ?, ?, ?, ?, ?)", (lat, lng, json.dumps(dates), version, t, circuit_text))
                        cur.execute("SELECT ID FROM CircuitLayouts WHERE Latitude = ? AND Longitude = ? AND CircuitVersion = ?", (lat, lng, version)) 
                        circuitlayoutid = cur.fetchone()[0]
        else:
            open_url(f"https://www.statsf1.com/en/circuit-{race_info['track_name'].replace(' ', '-').lower()}.aspx")
            a_tag = soup.find('a', id='ctl00_CPH_Main_HL_GMaps')['href']
            coord_str = a_tag[a_tag.index('@') + 1 : a_tag.rindex(',')]
            lat = coord_str[:coord_str.index(',')]
            lng = coord_str[coord_str.index(',') + 1:]  
            mappings[race_info['track_name']] = (lat, lng)
            print(f"Processing circuit: {race_info['track_name']}")
            circuitlayoutdivs = soup.find_all('div', class_ = 'circuitversion')
            for layoutdiv in circuitlayoutdivs:
                circuittable = layoutdiv.find('table', class_ = 'sortable circuittable').find_all('tr')
                dates = [tr.find_all('td')[0]['sorttable_customkey'] for tr in circuittable[1:-1]]
                version = circuitlayoutdivs.index(layoutdiv) + 1
                layoutimg = layoutdiv.find('img')['src']
                t = generate_track_svg(f'https://www.statsf1.com{layoutimg}')
                circuit_text_div = soup.find('div', class_='circuittext')
                circuit_text = circuit_text_div.get_text(strip=True).replace('\n', '').replace('"', '').replace('\r', '')                
                cur.execute("INSERT INTO CircuitLayouts (Latitude, Longitude, GrandPrixDates, CircuitVersion, SVG, CircuitChanges)  VALUES (?, ?, ?, ?, ?, ?)", (lat, lng, json.dumps(dates), version, t, circuit_text))
                cur.execute("SELECT ID FROM CircuitLayouts WHERE Latitude = ? AND Longitude = ? AND CircuitVersion = ?", (lat, lng, version))   
                circuitlayoutid = cur.fetchone()[0]      
        #print(race_info)
        print ("Race Info Parsed")
        #print("Race Info:", race_info)        
        ##fi.write(raceinfo.prettify())
        #Finds all the links for the grand prix: race entrants, results, qualifying, fastest laps, lap by lap, etc.
        divs = soup.find('div', class_ = 'GPlink')
        soup = BeautifulSoup(str(divs), 'html.parser')
        grandprixlinks = soup.find_all('a')
        ##DONT GIVE JUST THE HREF, GIVE THE WHOLE A TAG
        trigger = False
        if any(item['href'].endswith("/sprint.aspx") for item in grandprixlinks):
            grandprixlinks.append({'href': f"{grandprix['href'].replace('.aspx', '')}/sprint.aspx?grille"})
            grandprixlinks.append({'href': f"{grandprix['href'].replace('.aspx', '')}/sprint.aspx?mt"})
            trigger = True
        for item in grandprixlinks:
            if item['href'].endswith("/grille.aspx"):
                open_url(f"https://www.statsf1.com{item['href']}")
                poleside, gridformation = parse_statsf1_grid(soup, [], prefix="", return_metadata=True)
                break
        cur.execute("INSERT OR IGNORE INTO Circuits (CircuitName, Latitude, Longitude, FirstGrandPrix, FirstGrandPrixID) VALUES (?,?,?,?,?)", (race_info['circuit_name'], race_info['latitude'], race_info['longitude'], gp, race_info['race_number']))
        cur.execute("SELECT ID FROM Circuits WHERE CircuitName = ?", (race_info['circuit_name'],))
        circuitid = cur.fetchone()[0]
        corresponding_circuit_layout = link_circuitlayout(race_info['latitude'], race_info['longitude'], race_info['dateindatetime'])
        cur.execute("""INSERT INTO GrandsPrix (ID, Season, GrandPrixName, RoundNumber, CircuitName, Date, DateInDateTime, Laps, CircuitLength, Weather, Notes, SprintWeekend, PoleSide, GridFormation, CircuitID, CircuitLayoutID)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, 
        (race_info['race_number'], year, gp, grandsprix.index(grandprix) + 1, race_info['circuit_name'], race_info['date'], race_info['dateindatetime'], race_info['laps'], race_info['circuit_distance'], race_info['weather'], race_info.get('notes'), trigger, poleside, gridformation, circuitid, corresponding_circuit_layout))   
        cur.execute("UPDATE Seasons SET needstatsupdate = 1 WHERE Season = ?", (year,))
        cur.execute('UPDATE Circuits SET LastGrandPrix = ?, LastGrandPrixID = ? WHERE CircuitName = ?', (gp, race_info['race_number'], race_info['circuit_name']))
        #add one to grandprixcount in circuits table
        cur.execute('UPDATE Circuits SET GrandPrixCount = GrandPrixCount + 1 WHERE CircuitName = ?', (race_info['circuit_name'],))
        if corresponding_circuit_layout:
            cur.execute("SELECT FirstGrandPrixID FROM CircuitLayouts WHERE ID = ?", (corresponding_circuit_layout,))
            if cur.fetchone()[0] is None:
                cur.execute("UPDATE CircuitLayouts SET FirstGrandPrix = ?, FirstGrandPrixID = ? WHERE ID = ?", (gp, race_info['race_number'], corresponding_circuit_layout))
            cur.execute("UPDATE CircuitLayouts SET LastGrandPrix = ?, LastGrandPrixID = ?, GrandPrixCount = GrandPrixCount + 1 WHERE ID = ?", (gp, race_info['race_number'], corresponding_circuit_layout))
        print ("Grand Prix info saved to database")    
        cur.execute("INSERT INTO RaceReports (ID, GrandPrixName, RaceReport) VALUES (?,?,?)", (race_info['race_number'], gp, fetch_race_report(gp))) 
        print ("Race Report saved to database")               
        if year > 1982:    
            racii = f1websiteraces[grandsprix.index(grandprix)]
            open_url (f"https://www.formula1.com/{racii['href']}".replace('/../../', ''))
            #theplacewithallthelinks = soup.find_all('div', class_ = 'relative text-nowrap')[3]
            for x in soup.find_all('div', class_ = 'relative text-nowrap'):
                if "Race Result" in x.text:
                    theplacewithallthelinks = x
                    break  
            #print (theplacewithallthelinks)
            soup = BeautifulSoup(str(theplacewithallthelinks), 'html.parser')
            f1links = soup.find_all('a', class_ = 'DropdownMenuItem-module_dropdown-menu-item__6Y3-v typography-module_body-s-semibold__O2lOH')
            for link in f1links:
                if not link['href'].endswith('/pit-stop-summary'):
                    grandprixlinks.append(link)
                else:
                    sxs = link['href'] 
                    #print(sxs) 
        msgrandprix = unicodedata.normalize('NFKD', mslinks[grandsprix.index(grandprix)].replace(' ', '-').lower().replace("'", '-')).encode('ascii', 'ignore').decode('ascii')
        info = open_json(f"https://motorsportstats.com/_next/data/c2LGT9ym-c6f1pXlf9hjs/results/fia-formula-one-world-championship/{year}/{msgrandprix}/info.json")['pageProps']['sessions']
        ix = 1
        dest = []
        lapchartstoberead = []
        for s in info:
            ix += 1
            tde = {
                'name': s['session'].get('shortname') or s['session']['name'],
                'openurl': s['session']['slug'],
                'sessionnumber': ix,
                'wassessioncancelled': s['cancelled'],
                'starttimetimestamputc': s['startTimeUtc'],
                'endtimetimestamputc': s['endTimeUtc'],
                'starttimetimestamp': s['startTime'],
                'endtimetimestamp': s['endTime'],  
                'precisestarttime': s['preciseStartTime'],
                'startdtutc': datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(seconds=s['startTimeUtc']) if s['startTimeUtc'] else None,
                'enddtutc': datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc) + datetime.timedelta(seconds=s['endTimeUtc']) if s['endTimeUtc'] else None,
                'startdt': datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=s['startTime']) if s['startTime'] else None,
                'enddt': datetime.datetime(1970, 1, 1) + datetime.timedelta(seconds=s['endTime']) if s['endTime'] else None,  
            }
            cur.execute("""INSERT INTO Sessions (GrandPrix, SessionName, SessionNumber, WasSessionCancelled, StartTimeTimestampUTC, EndTimeTimestampUTC, StartTimeTimestamp, 
                        EndTimeTimestamp, IfPreciseStartTime, StartTimeinDatetimeUTC, EndTimeinDatetimeUTC, StartTimeinDatetime, EndTimeinDatetime, GrandPrixID)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", 
                        (gp, tde['name'], tde['sessionnumber'], tde['wassessioncancelled'], tde['starttimetimestamputc'], tde['endtimetimestamputc'], tde['starttimetimestamp'], 
                        tde['endtimetimestamp'], tde['precisestarttime'], tde['startdtutc'], tde['enddtutc'], tde['startdt'], tde['enddt'], race_info['race_number'])) 
            openurl = tde['openurl']
            if 'sprint' in openurl:
                sopenurl = openurl
            
            if not tde['wassessioncancelled']:
                if 'qualifying' in openurl:
                    grandprixlinks.append({'href': f'https://motorsportstats.com/api/results-classification?sessionSlug={openurl}'}) #remember to parse sprint qualifying also
                elif 'sprint' in openurl:
                    grandprixlinks.append({'href': f'https://motorsportstats.com/api/results-classification?sessionSlug={openurl}'})
                if 'practice' in openurl and (1076 < race_info['race_number'] < 1080 or race_info['race_number'] > 1106):
                    dest.append(f'https://motorsportstats.com/api/result-statistics?sessionSlug={openurl}&sessionFact=LapTime&size=100000')
                if 'qualifying' in openurl and (1076 < race_info['race_number'] < 1080 or race_info['race_number'] > 1106):
                    dest.append(f'https://motorsportstats.com/api/result-statistics?sessionSlug={openurl}&sessionFact=LapTime&size=100000')
                if 'sprint-qualifying' in openurl and (1076 < race_info['race_number'] < 1080 or race_info['race_number'] > 1106):
                    dest.append(f'https://motorsportstats.com/api/result-statistics?sessionSlug={openurl}&sessionFact=LapTime&size=100000')
                if 'sprint' in openurl and race_info['race_number'] > 1106:
                    dest.append(f'https://motorsportstats.com/api/result-statistics?sessionSlug={openurl}&sessionFact=LapTime&size=100000')
                if 'sprint-qualifying' in openurl or ('race' not in openurl and 'sprint' not in openurl):
                    lapchartstoberead.append(f'https://motorsportstats.com/api/result-statistics?sessionSlug={openurl}&sessionFact=LapChart&size=100000')
        if race_info['race_number'] > 344: #only after 1981 argentine grand prix
            grandprixlinks.append({'href': f"https://motorsportstats.com/api/results-classification?sessionSlug=fia-formula-one-world-championship_{year}_{msgrandprix}_race"})

        if year > 1995: #we have lap-by-lap data from 1996
            open_url(f"https://pitwall.app/analysis/compare-lap-times?season={dataid}")
            race_divs = soup.find("div", id='dropdown-select-race')
            if race_divs:
                races = race_divs.find_all('span', class_='item')
            else:
                races = []
            for race in races:
                if race.text.strip() == gp:
                    dataidforrace = race['data-id']
                    break  
        else:
            dataidforrace = None   
        resultnotes = parsenotes(grandprixlinks)
        for key, value in resultnotes.items():
            cur.execute(f"UPDATE GrandsPrix SET {key} = ? WHERE GrandPrixName = ?", (value, gp))   
        results = parse_race_results(grandprixlinks)
        # Apply name corrections to results
        name_corrections_results = {
            "Guanyu Zhou": "Zhou Guanyu"
        }
        for result in results:
            if result['driver'] in name_corrections_results:
                result['driver'] = name_corrections_results[result['driver']]
        print ("Results Parsed")
        entrant_keys = [
            "grandprix" ,"number", "driver", "nationality", "nationalityid", "team", "constructor", "chassis", "engine", "enginemodel", "tyre",
            "substituteorthirddriver", "qualifyingposition", "qualifyingtime", "qualifyinggap",
            "qualifyingtimeinseconds", "qualifyinggapseconds", "qualifyinginterval", "prequalifyingposition",
            "prequalifyingtime", "prequalifyinggap", "prequalifyinginterval", "prequalifyingtimeinseconds", "starting_grid_position",
            "gridpenalty", "gridpenalty_reason", "sprintstarting_grid_position", "sprintgridpenalty",
            "sprintgridpenalty_reason", "fastestlap", "fastestlapinseconds", "fastestlapgapinseconds",
            "fastestlapinterval", "fastestlap_time", "fastestlap_gap", "fastestlap_lap", "sprintfastestlap",
            "sprintfastestlapinseconds", "sprintfastestlapgapinseconds", "sprintfastestlapinterval", "sprintfastestlap_time",
            "sprintfastestlap_gap", "sprintfastestlap_lap", "qualifying2position", "qualifying2time",
            "qualifying2gap", "qualifying2interval", "qualifying2timeinseconds", "qualifying2laps", "qualifying1position",
            "qualifying1time", "qualifying1gap", "qualifying1interval", "qualifying1timeinseconds", "qualifying1laps",
            "qualifyinglaps", "qualifying1time", "qualifying2time", "qualifying3time",
            "qualifying1gap", "qualifying2gap", "qualifying3gap", "qualifying1interval", "qualifying2interval", "qualifying3interval",
            "qualifying1timeinseconds", "qualifying2timeinseconds", "qualifying3timeinseconds", "sprint_qualifyingposition",
            "sprint_qualifying1time", "sprint_qualifying2time", "sprint_qualifying3time",
            "sprint_qualifying1gap", "sprint_qualifying2gap", "sprint_qualifying3gap", "sprint_qualifying1interval", "sprint_qualifying2interval", "sprint_qualifying3interval",
            "sprint_qualifyinggap", "sprint_qualifyinginterval", "sprint_qualifying1timeinseconds", "sprint_qualifying2timeinseconds",
            "sprint_qualifying3timeinseconds", "sprint_qualifyinglaps", "sprint_qualifyingtime",
            "sprint_qualifyingtimeinseconds", "warmupposition", "warmuptime", "warmupgap",
            "warmuptimeinseconds", "warmuplaps", "practice1position", "practice1time", "practice1gap",
            "practice1interval", "practice1timeinseconds", "practice1laps", "practice2position", "practice2time",
            "practice2gap", "practice2interval", "practice2timeinseconds", "practice2laps", "practice3position",
            "practice3time", "practice3gap", "practice3interval", "practice3timeinseconds", "practice3laps",
            "practice4position", "practice4time", "practice4gap", "practice4interval", "practice4timeinseconds",
            "practice4laps", "sprintposition", "sprintlaps", "sprinttime", "sprintpoints", "sprintstatus", "sprintstatusreason",
            "sprinttimeinseconds", "sprintgap", "sprintgapinseconds", "sprintinterval", "raceposition", "racelaps",
            "racetime", "racepoints", "racestatus", "racestatusreason", "racetimeinseconds", "racegap", "racegapinseconds", 
            "raceinterval", "penalties", "sprint_penalties",
            "driverid", "teamid", "constructorid", "chassisid", "engineid", "enginemodelid", "tyreid", "grandprixid"
        ]
       
        for result in results:
            #print (result['driver'])
            cur.execute("SELECT ID FROM GrandsPrix WHERE GrandPrixName = ?", (gp,))
            grandprix_id = cur.fetchone()[0]            
            cur.execute("INSERT OR IGNORE INTO Teams (TeamName, FirstGrandPrix, FirstGrandPrixID) VALUES (?,?,?)", (result['team'], gp, grandprix_id))
            cur.execute("INSERT OR IGNORE INTO Constructors (ConstructorName, FirstGrandPrix, FirstGrandPrixID) VALUES (?,?,?)", (result['constructor'], gp, grandprix_id))
            cur.execute("INSERT OR IGNORE INTO Engines (EngineName, FirstGrandPrix, FirstGrandPrixID) VALUES (?,?,?)", (result['engine'], gp, grandprix_id))
            cur.execute("INSERT OR IGNORE INTO Tyres (TyreName, FirstGrandPrix, FirstGrandPrixID) VALUES (?,?,?)", (result['tyre'], gp, grandprix_id))
            cur.execute("SELECT 1 FROM drivers WHERE name = ?", (result['driver'],))
            exists = cur.fetchone()
            nationality_id = None
            if not exists:
                # If not in DB, scrape or fetch their nationality and birthdate
                #change gianmaria bruni back to gimmi bruni:
                name_corrections = {
                    "Gianmaria Bruni": "Gimmi Bruni",
                    "PATRICIO O'WARD": "Pato O'Ward",
                    "Pato O'Ward": "Patricio O'Ward",
                    "Zhou Guanyu": "Guanyu Zhou"
                }    
                b = name_corrections.get(result['driver'], result['driver'])
                driver_name_clean = b.replace('*', '').replace('æ', '-').replace("'", '-').replace('Ø', 'O').replace('ø', 'o')
                if ' ' not in driver_name_clean:
                    driver_name_for_url = f'--{driver_name_clean}'
                else:
                    driver_name_for_url = driver_name_clean
                nationality, birthdate = fetch_driver_info(driver_name_for_url)
                cur.execute("INSERT OR IGNORE INTO Nationalities (Nationality, FirstGrandPrix, FirstGrandPrixID) VALUES (?, ?, ?)", (nationality, gp, grandprix_id))
                cur.execute("SELECT ID FROM Nationalities WHERE Nationality = ?", (nationality,))
                nationality_id = cur.fetchone()[0]                      
                # Insert into drivers table
                cur.execute("""
                    INSERT INTO Drivers (name, nationality, birthdate, FirstGrandPrix, FirstGrandPrixID, NationalityID)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (result['driver'], nationality, birthdate, gp, grandprix_id, nationality_id))          
                cur.execute('UPDATE Nationalities SET DriverCount = DriverCount + 1 WHERE ID = ?', (nationality_id,))
            cur.execute("SELECT ID FROM Drivers WHERE Name = ?", (result['driver'],))
            driver_id = cur.fetchone()[0]
            #print (result['driver'], driver_id)
            cur.execute("SELECT ID FROM Teams WHERE TeamName = ?", (result['team'],))
            team_id = cur.fetchone()[0]
            cur.execute("SELECT ID FROM Constructors WHERE ConstructorName = ?", (result['constructor'],))
            constructor_id = cur.fetchone()[0]
            cur.execute("INSERT OR IGNORE INTO Chassis (ConstructorName, ChassisName, ConstructorID, FirstGrandPrix, FirstGrandPrixID) VALUES (?,?,?,?,?)", (result['constructor'], result['chassis'], constructor_id, gp, grandprix_id))          
            cur.execute("SELECT ID FROM Chassis WHERE ChassisName = ?", (result['chassis'],))
            chassis_id = cur.fetchone()[0]
            cur.execute("SELECT ID FROM Engines WHERE EngineName = ?", (result['engine'],))
            engine_id = cur.fetchone()[0]
            cur.execute("INSERT OR IGNORE INTO EngineModels (EngineMake, EngineModel, EngineMakeID, FirstGrandPrix, FirstGrandPrixID) VALUES (?,?,?,?,?)", (result['engine'], result['enginemodel'], engine_id, gp, grandprix_id))              
            cur.execute("SELECT ID FROM EngineModels WHERE EngineModel = ?", (result['enginemodel'],))
            engine_model_id = cur.fetchone()[0]
            cur.execute("SELECT ID FROM Tyres WHERE TyreName = ?", (result['tyre'],))
            tyre_id = cur.fetchone()[0]
            cur.execute("SELECT Nationality FROM Drivers WHERE Name = ?", (result['driver'],))
            nationality = cur.fetchone()[0]
            cur.execute("SELECT ID FROM Nationalities WHERE Nationality = ?", (nationality,))
            nationality_id = cur.fetchone()[0] 
            cur.execute("UPDATE Nationalities SET LastGrandPrix = ?, LastGrandPrixID = ? WHERE ID = ?", (gp, grandprix_id, nationality_id))
            cur.execute("UPDATE Nationalities SET needstatsupdate = 1 WHERE ID = ?", (nationality_id,))
            driverids[result['driver']] = driver_id
            teamids[result['team']] = team_id
            constructorids[result['constructor']] = constructor_id
            chassisids[result['chassis']] = chassis_id
            engineids[result['engine']] = engine_id
            enginemodelids[result['enginemodel']] = engine_model_id
            tyreids[result['tyre']] = tyre_id

            if nationality_id is not None:
                nationalityids[nationality] = nationality_id


            result['driverid'] = driver_id
            result['teamid'] = team_id
            result['constructorid'] = constructor_id
            result['chassisid'] = chassis_id
            result['engineid'] = engine_id
            result['enginemodelid'] = engine_model_id
            result['tyreid'] = tyre_id
            result['grandprixid'] = grandprix_id
            result['grandprix'] = gp
            result['nationality'] = nationality
            result['nationalityid'] = nationality_id

            values = [result.get(key) for key in entrant_keys]
            penalties_idx = entrant_keys.index("penalties")
            sprint_penalties_idx = entrant_keys.index("sprint_penalties")
            values[penalties_idx] = json.dumps(values[penalties_idx]) if values[penalties_idx] else None
            values[sprint_penalties_idx] = json.dumps(values[sprint_penalties_idx]) if values[sprint_penalties_idx] else None
            placeholders = ', '.join(['?'] * len(entrant_keys))
            columns = ', '.join(entrant_keys)

            cur.execute(f'''
                INSERT INTO GrandPrixResults ({columns})
                VALUES ({placeholders})
            ''', values)
            cur.execute("UPDATE Drivers SET LastGrandPrix = ?, LastGrandPrixID = ? WHERE ID = ?", (gp, grandprix_id, driver_id)) 
            cur.execute("UPDATE Teams SET LastGrandPrix = ?, LastGrandPrixID = ? WHERE ID = ?", (gp, grandprix_id, team_id))
            cur.execute("UPDATE Constructors SET LastGrandPrix = ?, LastGrandPrixID = ? WHERE ID = ?", (gp, grandprix_id, constructor_id))
            cur.execute("UPDATE Chassis SET LastGrandPrix = ?, LastGrandPrixID = ? WHERE ChassisName = ? AND ConstructorID = ?", (gp, grandprix_id, result['chassis'], constructor_id))
            cur.execute("UPDATE Engines SET LastGrandPrix = ?, LastGrandPrixID = ? WHERE ID = ?", (gp, grandprix_id, engine_id))
            cur.execute("UPDATE EngineModels SET LastGrandPrix = ?, LastGrandPrixID = ? WHERE ID = ?", (gp, grandprix_id, engine_model_id))
            cur.execute("UPDATE Tyres SET LastGrandPrix = ?, LastGrandPrixID = ? WHERE ID = ?", (gp, grandprix_id, tyre_id))
            cur.execute("UPDATE Drivers SET needstatsupdate = 1 WHERE ID = ?", (driver_id,))
            cur.execute("UPDATE Teams SET needstatsupdate = 1 WHERE ID = ?", (team_id,))
            cur.execute("UPDATE Constructors SET needstatsupdate = 1 WHERE ID = ?", (constructor_id,))
            cur.execute("UPDATE Chassis SET needstatsupdate = 1 WHERE ChassisName = ? AND ConstructorID = ?", (result['chassis'], constructor_id))
            cur.execute("UPDATE Engines SET needstatsupdate = 1 WHERE ID = ?", (engine_id,))
            cur.execute("UPDATE EngineModels SET needstatsupdate = 1 WHERE ID = ?", (engine_model_id,))
            cur.execute("UPDATE Tyres SET needstatsupdate = 1 WHERE ID = ?", (tyre_id,))
        print ("Results saved to database")   

        for drivername in drivernames:
            fulfilled = False
            while not fulfilled:
                parts = drivername.lower().replace('.', '').split()
                if len(parts) >= 2:
                    first_initial = parts[0][0]
                    first_initial = normalize_name(first_initial)
                    last_name = ' '.join(parts[1:])
                    last_name = normalize_name(last_name)
                    # Try to match in results
                    for entrant in results:
                        full = normalize_name(entrant["driver"])
                        if full.startswith(first_initial) and full.endswith(last_name):
                            name_map[drivername] = entrant['driver']
                            fulfilled = True
                            break
                    # If not found, try to match in DB
                    if not fulfilled:
                        cur.execute("SELECT Driver FROM DriversChampionship WHERE Season = ?", (year,))
                        rows = cur.fetchall()
                        for row in rows:
                            full = normalize_name(row[0])
                            if full.startswith(first_initial) and full.endswith(last_name):
                                name_map[drivername] = row[0]
                                fulfilled = True
                                break
                    # If still not found, log and break to avoid infinite loop
                    if not fulfilled:
                        fulfilled = True  # Exit loop even if not found   
        #print (results)
        for item in grandprixlinks[6:]:
            if item['href'].endswith("/tour-par-tour.aspx"):
                lapbylaps = parse_lap_by_lap(f"https://www.statsf1.com{item['href']}", results, dataid, dataidforrace, year=year, grandprix_name=gp.replace(str(year), '').strip())
                lapbylap = lapbylaps[0]
                gp_ = gp
                if year >= 2021 and gp.endswith('Mexican Grand Prix'):
                    gp_ = gp.replace('Mexican Grand Prix', 'Mexico City Grand Prix')
                if year >= 2018:
                    fp1, fp2, fp3, q1, q2, q3, sq1, sq2, sq3, s = None, None, None, None, None, None, None, None, None, None
                    if dest:
                       for laah in dest:
                            if '1st-free-practice' in laah.lower():
                               fp1 = laah
                            elif '2nd-free-practice' in laah.lower():
                                fp2 = laah
                            elif '3rd-free-practice' in laah.lower():
                                fp3 = laah
                            elif '1st-qualifying' in laah.lower():
                                q1 = laah
                            elif '2nd-qualifying' in laah.lower():
                                q2 = laah
                            elif '3rd-qualifying' in laah.lower():
                                q3 = laah
                            elif '1st-sprint-qualifying' in laah.lower():
                               sq1 = laah
                            elif '2nd-sprint-qualifying' in laah.lower():
                                sq2 = laah
                            elif '3rd-sprint-qualifying' in laah.lower():
                                sq3 = laah
                            elif 'sprint' in laah.lower() or 'sprint-qualifying' in laah.lower():
                                s = laah

                    # Practice 1
                    if any(link['href'].endswith('practice/1') for link in theplacewithallthelinks.find_all('a', class_ = 'DropdownMenuItem-module_dropdown-menu-item__6Y3-v typography-module_body-s-semibold__O2lOH')):
                        qwertyuiop = urllib.request.Request(f"https://cdn.jsdelivr.net/gh/TracingInsights/{year}/{urllib.parse.quote(gp_.replace(str(year), '').strip())}/Practice%201/drivers.json", headers=headers)
                        driverdatafortracinginsights = json.loads(urllib.request.urlopen(qwertyuiop).read())['drivers']
                        
                        # Get MSS laptimes for FP1 as fallback
                        fp1_mss_laps = {}
                        if fp1:
                            fp1_mss_data = scrape_mss_laptimes(fp1, results)
                            for lap in fp1_mss_data:
                                key = (lap['driver'], lap['lap'])
                                fp1_mss_laps[key] = lap
                        
                        # Get lap chart data for FP1 positions
                        fp1_lap_chart = {}
                        if fp1:
                            fp1_chart_data = readlapcharts(fp1.replace('&sessionFact=LapTimes', '&sessionFact=LapChart'))
                            # Convert to driver name lookup
                            for driver_num, lap_positions in fp1_chart_data.items():
                                for entrant in results:
                                    if entrant['number'] == driver_num:
                                        for lap, position in lap_positions:
                                            key = (entrant['driver'], lap)
                                            fp1_lap_chart[key] = position
                                        break
                        
                        for driver in driverdatafortracinginsights:
                            driver_abbr = driver['driver']
                            driver_team = driver['team']
                            matched_entrant = match_tracing_abbr_to_entrant(
                                abbr=driver_abbr,
                                entrants=results,
                                tracing_lap_json=driver.get("laps"),
                                f1_best_times={inst['driver']: inst.get('practice1timeinseconds') for inst in results},
                                lap_by_lap_map=lapbylaps[1],
                                tracing_team=driver_team
                            )  
                            if matched_entrant:
                                practice1data = scrape_tracinginsights(f"https://cdn.jsdelivr.net/gh/TracingInsights/{year}/{urllib.parse.quote(gp_.replace(str(year), '').strip())}/Practice%201/{driver_abbr}/laptimes.json", 'practice1')
                                for practice1lap in practice1data:
                                    # Use MSS data as fallback if TracingInsights time is None
                                    time_val = practice1lap.get('time')
                                    time_in_sec = practice1lap.get('time_in_seconds')
                                    position_val = practice1lap.get('position')
                                    
                                    mss_key = (matched_entrant['driver'], practice1lap['lap'])
                                    
                                    if time_val is None or time_in_sec is None:
                                        if mss_key in fp1_mss_laps:
                                            time_val = time_val or fp1_mss_laps[mss_key]['time']
                                            time_in_sec = time_in_sec or fp1_mss_laps[mss_key]['timeinseconds']
                                    
                                    # Use lap chart data for position if None
                                    if position_val is None:
                                        if mss_key in fp1_lap_chart:
                                            position_val = fp1_lap_chart[mss_key]
                                    
                                    cur.execute("""INSERT INTO LapByLap (GrandPrix, Driver, Position, Lap, Type, Time, TimeInSeconds, TyreCompound, StintNumber, Sector1Time, Sector2Time, Sector3Time, TyreAge, TrackStatus, GrandPrixID, DriverID)
                                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (gp, matched_entrant['driver'], position_val, practice1lap['lap'], 'practice1', time_val, time_in_sec, practice1lap.get('compound'), practice1lap.get('stint'), practice1lap.get('s1'), practice1lap.get('s2'), practice1lap.get('s3'), practice1lap.get('life'), practice1lap.get('status'), grandprix_id, driver_id))
                    
                    # Practice 2
                    if any(link['href'].endswith('practice/2') for link in theplacewithallthelinks.find_all('a', class_ = 'DropdownMenuItem-module_dropdown-menu-item__6Y3-v typography-module_body-s-semibold__O2lOH')):
                        asdfghjkl = urllib.request.Request(f"https://cdn.jsdelivr.net/gh/TracingInsights/{year}/{urllib.parse.quote(gp_.replace(str(year), '').strip())}/Practice%202/drivers.json", headers=headers)
                        driverdatafortracinginsights2 = json.loads(urllib.request.urlopen(asdfghjkl).read())['drivers']
                        
                        # Get MSS laptimes for FP2 as fallback
                        fp2_mss_laps = {}
                        if fp2:
                            fp2_mss_data = scrape_mss_laptimes(fp2, results)
                            for lap in fp2_mss_data:
                                key = (lap['driver'], lap['lap'])
                                fp2_mss_laps[key] = lap
                        
                        # Get lap chart data for FP2 positions
                        fp2_lap_chart = {}
                        if fp2:
                            fp2_chart_data = readlapcharts(fp2.replace('&sessionFact=LapTimes', '&sessionFact=LapChart'))
                            for driver_num, lap_positions in fp2_chart_data.items():
                                for entrant in results:
                                    if entrant['number'] == driver_num:
                                        for lap, position in lap_positions:
                                            key = (entrant['driver'], lap)
                                            fp2_lap_chart[key] = position
                                        break
                        
                        for driver in driverdatafortracinginsights2:
                            driver_abbr = driver['driver']
                            driver_team = driver['team']
                            matched_entrant = match_tracing_abbr_to_entrant(
                                abbr=driver_abbr,
                                entrants=results,
                                tracing_lap_json=driver.get("laps"),
                                f1_best_times={inst['driver']: inst.get('practice2timeinseconds') for inst in results},
                                lap_by_lap_map=lapbylaps[1],
                                tracing_team=driver_team
                            )  
                            if matched_entrant:
                                practice2data = scrape_tracinginsights(f"https://cdn.jsdelivr.net/gh/TracingInsights/{year}/{urllib.parse.quote(gp_.replace(str(year), '').strip())}/Practice%202/{driver_abbr}/laptimes.json", 'practice2')
                                for practice2lap in practice2data:
                                    # Use MSS data as fallback
                                    time_val = practice2lap.get('time')
                                    time_in_sec = practice2lap.get('time_in_seconds')
                                    position_val = practice2lap.get('position')
                                    
                                    mss_key = (matched_entrant['driver'], practice2lap['lap'])
                                    
                                    if time_val is None or time_in_sec is None:
                                        if mss_key in fp2_mss_laps:
                                            time_val = time_val or fp2_mss_laps[mss_key]['time']
                                            time_in_sec = time_in_sec or fp2_mss_laps[mss_key]['timeinseconds']
                                    
                                    # Use lap chart data for position if None
                                    if position_val is None:
                                        if mss_key in fp2_lap_chart:
                                            position_val = fp2_lap_chart[mss_key]
                                    
                                    cur.execute("""INSERT INTO LapByLap (GrandPrix, Driver, Position, Lap, Type, Time, TimeInSeconds, TyreCompound, StintNumber, Sector1Time, Sector2Time, Sector3Time, TyreAge, TrackStatus, GrandPrixID, DriverID)
                                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (gp, matched_entrant['driver'], position_val, practice2lap['lap'], 'practice2', time_val, time_in_sec, practice2lap.get('compound'), practice2lap.get('stint'), practice2lap.get('s1'), practice2lap.get('s2'), practice2lap.get('s3'), practice2lap.get('life'), practice2lap.get('status'), grandprix_id, driver_id))
                    
                    # Practice 3
                    if any(link['href'].endswith('practice/3') for link in theplacewithallthelinks.find_all('a', class_ = 'DropdownMenuItem-module_dropdown-menu-item__6Y3-v typography-module_body-s-semibold__O2lOH')):
                        zxcvbnm = urllib.request.Request(f"https://cdn.jsdelivr.net/gh/TracingInsights/{year}/{urllib.parse.quote(gp_.replace(str(year), '').strip())}/Practice%203/drivers.json", headers=headers)
                        driverdatafortracinginsights3 = json.loads(urllib.request.urlopen(zxcvbnm).read())['drivers']
                        
                        # Get MSS laptimes for FP3 as fallback
                        fp3_mss_laps = {}
                        if fp3:
                            fp3_mss_data = scrape_mss_laptimes(fp3, results)
                            for lap in fp3_mss_data:
                                key = (lap['driver'], lap['lap'])
                                fp3_mss_laps[key] = lap
                        
                        # Get lap chart data for FP3 positions
                        fp3_lap_chart = {}
                        if fp3:
                            fp3_chart_data = readlapcharts(fp3.replace('&sessionFact=LapTimes', '&sessionFact=LapChart'))
                            for driver_num, lap_positions in fp3_chart_data.items():
                                for entrant in results:
                                    if entrant['number'] == driver_num:
                                        for lap, position in lap_positions:
                                            key = (entrant['driver'], lap)
                                            fp3_lap_chart[key] = position
                                        break
                        
                        for driver in driverdatafortracinginsights3:
                            driver_abbr = driver['driver']
                            driver_team = driver['team']
                            matched_entrant = match_tracing_abbr_to_entrant(
                                abbr=driver_abbr,
                                entrants=results,
                                tracing_lap_json=driver.get("laps"),
                                f1_best_times={inst['driver']: inst.get('practice3timeinseconds') for inst in results},
                                lap_by_lap_map=lapbylaps[1],
                                tracing_team=driver_team
                            )  
                            if matched_entrant:
                                practice3data = scrape_tracinginsights(f"https://cdn.jsdelivr.net/gh/TracingInsights/{year}/{urllib.parse.quote(gp_.replace(str(year), '').strip())}/Practice%203/{driver_abbr}/laptimes.json", 'practice3')
                                for practice3lap in practice3data:
                                    # Use MSS data as fallback
                                    time_val = practice3lap.get('time')
                                    time_in_sec = practice3lap.get('time_in_seconds')
                                    position_val = practice3lap.get('position')
                                    
                                    mss_key = (matched_entrant['driver'], practice3lap['lap'])
                                    
                                    if time_val is None or time_in_sec is None:
                                        if mss_key in fp3_mss_laps:
                                            time_val = time_val or fp3_mss_laps[mss_key]['time']
                                            time_in_sec = time_in_sec or fp3_mss_laps[mss_key]['timeinseconds']
                                    
                                    # Use lap chart data for position if None
                                    if position_val is None:
                                        if mss_key in fp3_lap_chart:
                                            position_val = fp3_lap_chart[mss_key]
                                    
                                    cur.execute("""INSERT INTO LapByLap (GrandPrix, Driver, Position, Lap, Type, Time, TimeInSeconds, TyreCompound, StintNumber, Sector1Time, Sector2Time, Sector3Time, TyreAge, TrackStatus, GrandPrixID, DriverID)
                                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (gp, matched_entrant['driver'], position_val, practice3lap['lap'], 'practice3', time_val, time_in_sec, practice3lap.get('compound'), practice3lap.get('stint'), practice3lap.get('s1'), practice3lap.get('s2'), practice3lap.get('s3'), practice3lap.get('life'), practice3lap.get('status'), grandprix_id, driver_id))
                    
                    # Sprint Qualifying
                    if any(link['href'].endswith('sprint-qualifying') for link in theplacewithallthelinks.find_all('a', class_ = 'DropdownMenuItem-module_dropdown-menu-item__6Y3-v typography-module_body-s-semibold__O2lOH')):
                        sessiontype = 'sprintshootout' if year == 2023 else 'sprintqualifying'
                        urlforlink = 'Sprint%20Shootout' if year == 2023 else 'Sprint%20Qualifying'
                        
                        # Get MSS laptimes for sprint qualifying (q1, q2, q3)
                        sq_mss_laps = {}
                        sq_lap_chart = {}
                        if sq1 and sq2 and sq3:
                            for session_url, segment in [(sq1, 'SQ1'), (sq2, 'SQ2'), (sq3, 'SQ3')]:
                                session_mss_data = scrape_mss_laptimes(session_url, results)
                                for lap in session_mss_data:
                                    key = (lap['driver'], lap['lap'], segment)
                                    sq_mss_laps[key] = lap
                                
                                # Get lap chart for this segment
                                chart_data = readlapcharts(session_url.replace('&sessionFact=LapTimes', '&sessionFact=LapChart'))
                                for driver_num, lap_positions in chart_data.items():
                                    for entrant in results:
                                        if entrant['number'] == driver_num:
                                            for lap, position in lap_positions:
                                                key = (entrant['driver'], lap, segment)
                                                sq_lap_chart[key] = position
                                            break
                        
                        qwertyasdf = urllib.request.Request(f"https://cdn.jsdelivr.net/gh/TracingInsights/{year}/{urllib.parse.quote(gp_.replace(str(year), '').strip())}/{urlforlink}/drivers.json", headers=headers)
                        driverdatafortracinginsights4 = json.loads(urllib.request.urlopen(qwertyasdf).read())['drivers']
                        
                        for driver in driverdatafortracinginsights4:
                            driver_abbr = driver['driver']
                            driver_team = driver['team']
                            matched_entrant = match_tracing_abbr_to_entrant(
                                abbr=driver_abbr,
                                entrants=results,
                                tracing_lap_json=driver.get("laps"),
                                f1_best_times={inst['driver']: inst.get('sprint_qualifyingtimeinseconds') for inst in results},
                                lap_by_lap_map=lapbylaps[1],
                                tracing_team=driver_team
                            )  
                            if matched_entrant:
                                sprintqualifyingdata = scrape_tracinginsights(f"https://cdn.jsdelivr.net/gh/TracingInsights/{year}/{urllib.parse.quote(gp_.replace(str(year), '').strip())}/{urlforlink}/{driver_abbr}/laptimes.json")
                                
                                # Group laps by driver to determine qs
                                driver_laps = [lap for lap in sprintqualifyingdata if lap]
                                total_laps = len(driver_laps)
                                
                                for idx, sprintqualifyinglap in enumerate(driver_laps):
                                    # Use MSS data as fallback
                                    time_val = sprintqualifyinglap.get('time')
                                    time_in_sec = sprintqualifyinglap.get('time_in_seconds')
                                    qs_val = sprintqualifyinglap.get('qs')
                                    position_val = sprintqualifyinglap.get('position')
                                    
                                    # Determine qs if None by matching lap count
                                    if qs_val is None and total_laps > 0:
                                        lap_num = sprintqualifyinglap['lap']
                                        # Try to find matching MSS lap with segment info
                                        for segment in ['SQ1', 'SQ2', 'SQ3']:
                                            mss_key = (matched_entrant['driver'], lap_num, segment)
                                            if mss_key in sq_mss_laps:
                                                qs_val = segment
                                                if time_val is None or time_in_sec is None:
                                                    time_val = time_val or sq_mss_laps[mss_key]['time']
                                                    time_in_sec = time_in_sec or sq_mss_laps[mss_key]['timeinseconds']
                                                # Use lap chart position
                                                if position_val is None and mss_key in sq_lap_chart:
                                                    position_val = sq_lap_chart[mss_key]
                                                break
                                    
                                    cur.execute("""INSERT INTO LapByLap (GrandPrix, Driver, Position, Lap, Type, Time, TimeInSeconds, TyreCompound, StintNumber, Sector1Time, Sector2Time, Sector3Time, TyreAge, TrackStatus, QualifyingSegment, GrandPrixID, DriverID)
                                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (gp, matched_entrant['driver'], position_val, sprintqualifyinglap['lap'], sessiontype, time_val, time_in_sec, sprintqualifyinglap.get('compound'), sprintqualifyinglap.get('stint'), sprintqualifyinglap.get('s1'), sprintqualifyinglap.get('s2'), sprintqualifyinglap.get('s3'), sprintqualifyinglap.get('life'), sprintqualifyinglap.get('status'), qs_val, grandprix_id, driver_id))
                    
                    # Qualifying
                    if any(link['href'].endswith('qualifying') for link in theplacewithallthelinks.find_all('a', class_ = 'DropdownMenuItem-module_dropdown-menu-item__6Y3-v typography-module_body-s-semibold__O2lOH')):
                        # Get MSS laptimes for qualifying (q1, q2, q3)
                        q_mss_laps = {}
                        q_lap_chart = {}
                        if q1 and q2 and q3:
                            for session_url, segment in [(q1, 'Q1'), (q2, 'Q2'), (q3, 'Q3')]:
                                session_mss_data = scrape_mss_laptimes(session_url, results)
                                for lap in session_mss_data:
                                    key = (lap['driver'], lap['lap'], segment)
                                    q_mss_laps[key] = lap
                                
                                # Get lap chart for this segment
                                chart_data = readlapcharts(session_url.replace('&sessionFact=LapTimes', '&sessionFact=LapChart'))
                                for driver_num, lap_positions in chart_data.items():
                                    for entrant in results:
                                        if entrant['number'] == driver_num:
                                            for lap, position in lap_positions:
                                                key = (entrant['driver'], lap, segment)
                                                q_lap_chart[key] = position
                                            break
                        
                        zxcvbnmasdf = urllib.request.Request(f"https://cdn.jsdelivr.net/gh/TracingInsights/{year}/{urllib.parse.quote(gp_.replace(str(year), '').strip())}/Qualifying/drivers.json", headers=headers)
                        driverdatafortracinginsights5 = json.loads(urllib.request.urlopen(zxcvbnmasdf).read())['drivers']
                        
                        for driver in driverdatafortracinginsights5:
                            driver_abbr = driver['driver']
                            driver_team = driver['team']
                            matched_entrant = match_tracing_abbr_to_entrant(
                                abbr=driver_abbr,
                                entrants=results,
                                tracing_lap_json=driver.get("laps"),
                                f1_best_times={inst['driver']: inst.get('qualifyingtimeinseconds') for inst in results},
                                lap_by_lap_map=lapbylaps[1],
                                tracing_team=driver_team
                            )  
                            if matched_entrant:
                                qualifyingdata = scrape_tracinginsights(f"https://cdn.jsdelivr.net/gh/TracingInsights/{year}/{urllib.parse.quote(gp_.replace(str(year), '').strip())}/Qualifying/{driver_abbr}/laptimes.json")
                                
                                # Group laps by driver to determine qs
                                driver_laps = [lap for lap in qualifyingdata if lap]
                                total_laps = len(driver_laps)
                                
                                for idx, qualifyinglap in enumerate(driver_laps):
                                    # Use MSS data as fallback
                                    time_val = qualifyinglap.get('time')
                                    time_in_sec = qualifyinglap.get('time_in_seconds')
                                    qs_val = qualifyinglap.get('qs')
                                    position_val = qualifyinglap.get('position')
                                    
                                    # Determine qs if None by matching lap count and driver
                                    if qs_val is None and total_laps > 0:
                                        lap_num = qualifyinglap['lap']
                                        # Try to find matching MSS lap with segment info
                                        for segment in ['Q1', 'Q2', 'Q3']:
                                            mss_key = (matched_entrant['driver'], lap_num, segment)
                                            if mss_key in q_mss_laps:
                                                qs_val = segment
                                                if time_val is None or time_in_sec is None:
                                                    time_val = time_val or q_mss_laps[mss_key]['time']
                                                    time_in_sec = time_in_sec or q_mss_laps[mss_key]['timeinseconds']
                                                # Use lap chart position
                                                if position_val is None and mss_key in q_lap_chart:
                                                    position_val = q_lap_chart[mss_key]
                                                break
                                    
                                    cur.execute("""INSERT INTO LapByLap (GrandPrix, Driver, Position, Lap, Type, Time, TimeInSeconds, TyreCompound, StintNumber, Sector1Time, Sector2Time, Sector3Time, TyreAge, TrackStatus, QualifyingSegment, GrandPrixID, DriverID)
                                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (gp, matched_entrant['driver'], position_val, qualifyinglap['lap'], "qualifying", time_val, time_in_sec, qualifyinglap.get('compound'), qualifyinglap.get('stint'), qualifyinglap.get('s1'), qualifyinglap.get('s2'), qualifyinglap.get('s3'), qualifyinglap.get('life'), qualifyinglap.get('status'), qs_val, grandprix_id, driver_id))
                
                if trigger == True:
                    sprintlapbylap = parse_lap_by_lap(f"https://www.statsf1.com{grandprix['href'].replace('.aspx', '')}/sprint.aspx?tpt", results, year=year, grandprix_name=gp.replace(str(year), '').strip())[0]
                    
                    # Get MSS laptimes for sprint race as fallback
                    sprint_mss_laps = {}
                    if s:  # Assuming you have a 'sprint' variable with the MSS URL
                        sprint_mss_data = scrape_mss_laptimes(s, results)
                        for lap in sprint_mss_data:
                            key = (lap['driver'], lap['lap'])
                            sprint_mss_laps[key] = lap
                    
                    for instance in sprintlapbylap:
                        driver_id = driverids[instance['driver']]
                        
                        # Use MSS data as fallback if TracingInsights/StatsF1 time is None
                        time_val = instance.get('time')
                        time_in_sec = instance.get('time_in_seconds')
                        
                        if time_val is None or time_in_sec is None:
                            mss_key = (instance['driver'], instance['lap'])
                            if mss_key in sprint_mss_laps:
                                time_val = time_val or sprint_mss_laps[mss_key]['time']
                                time_in_sec = time_in_sec or sprint_mss_laps[mss_key]['timeinseconds']
                        
                        cur.execute("""
                        INSERT INTO LapByLap (GrandPrix, Driver, Position, Lap, Type, SafetyCar, Time, TimeInSeconds, TyreCompound, StintNumber, Sector1Time, Sector2Time, Sector3Time, TyreAge, TrackStatus, GrandPrixID, DriverID)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        """,
                        (gp, instance['driver'], instance['position'], instance['lap'], instance['type'], instance['safetycar'], time_val, time_in_sec, instance.get('compound'), instance.get('stint'), instance.get('s1'), instance.get('s2'), instance.get('s3'), instance.get('life'), instance.get('status'), grandprix_id, driver_id))   
                    if "PitStop" in open_json(f"https://motorsportstats.com/api/result-statistics?{sopenurl}"):        
                        sprintpitstopsummaryjson = open_json(f"https://motorsportstats.com/api/result-statistics?sessionSlug={sopenurl}&sessionFact=PitStop&size=100000")['content'] 
                        for pitstop in sprintpitstopsummaryjson:
                            for entrant in results:
                                if entrant['number'] == int(pitstop['carNumber']):
                                    driver_name = entrant['driver']
                                    driver_id = driverids[driver_name]
                                    constructor_id = constructorids[entrant['constructor']]
                                    
                                    timeofday = pitstop['timeOfDay']
                                    lap = pitstop['lap']
                                    stopnumber = pitstop['stopNumber']
                                    duration = float(Decimal(str(pitstop['duration'] / 1000)).quantize(Decimal('0.001'))) if pitstop.get('duration') is not None else None
                                    totalduration = float(Decimal(str(pitstop['totalDuration'] / 1000)).quantize(Decimal('0.001'))) if pitstop.get('totalDuration') is not None else None
                                    cur.execute("""
                                    INSERT INTO PitStopSummary (GrandPrix, Number, Driver, Constructor, StopNumber, Lap, DurationSpentInPitLane, TimeInSeconds, TimeOfDayStopped, TotalTimeSpentInPitLane, TotalTimeinSeconds, Type, GrandPrixID, DriverID, ConstructorID)
                                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                                    """,
                                    (gp, entrant['number'], driver_name, entrant['constructor'], stopnumber, lap, duration, duration, timeofday, totalduration, totalduration, 'sprint', grandprix_id, driver_id, constructor_id))
                                    break
                #print (lapbylap)  
                #print (name_map)  
                print ("Lap by lap Parsed")
                
                for instance in lapbylap:
                    driver_id = driverids[instance['driver']]
                    cur.execute("""
                    INSERT INTO LapByLap (GrandPrix, Driver, Position, Lap, Type, SafetyCar, Time, TimeInSeconds, TyreCompound, StintNumber, Sector1Time, Sector2Time, Sector3Time, TyreAge, TrackStatus, GrandPrixID, DriverID)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (gp, instance['driver'], instance['position'], instance['lap'], instance['type'], instance['safetycar'], instance.get('time'), instance.get('time_in_seconds'), instance.get('compound'), instance.get('stint'), instance.get('s1'), instance.get('s2'), instance.get('s3'), instance.get('life'), instance.get('status'), grandprix_id, driver_id)) 
                print("Lap by lap data saved to database")    
            elif item['href'].endswith("/championnat.aspx"): 
                driversprogress, construtorsprogress = parse_in_season_progress(f"https://www.statsf1.com{item['href']}")
                #print (progress)
                print ("In season progress Parsed")
                
                for driver in driversprogress:
                    driver_id = driverids[driver['driver']]
                    cur.execute("""
                     INSERT INTO InSeasonProgressDrivers (GrandPrix, PositionAtThisPoint, Driver, PointsAtThisPoint, GrandPrixID, DriverID)
                     VALUES (?,?,?,?,?,?)
                    """, 
                    (gp, driver['positionatthispoint'], driver['driver'], driver['pointsatthispoint'], grandprix_id, driver_id))
                if construtorsprogress != []:
                    for driver in construtorsprogress:
                        constructor_id = constructorids[driver['constructor']]
                        engine_id = engineids[driver['engine']]
                        cur.execute("""
                            INSERT INTO InSeasonProgressConstructors (GrandPrix, PositionAtThisPoint, Constructor, Engine, PointsAtThisPoint, GrandPrixID, ConstructorID, EngineID)
                            VALUES (?,?,?,?,?,?,?,?)
                            """, 
                            (gp, driver['positionatthispoint'], driver['constructor'], driver['engine'], driver['pointsatthispoint'], grandprix_id, constructor_id, engine_id))
                        
                print ("In season progress data saved to database")                    
                                     
        if sxs:
            open_url(f"https://formula1.com{sxs}")
            tablex = soup.find('table', class_ = 'Table-module_table__cKsW2')          #soup.find('table', class_ = 'f1-table f1-table-with-data w-full')
            pitstopsummary = parse_pit_stop_summary(tablex, results, year=year, grandprix_name=gp) 
            print ("Pit stop summary Parsed") 
            for pitstop in pitstopsummary:
                driver_id = driverids[pitstop['driver']]
                constructor_id = constructorids[pitstop['constructor']]
                duration_stopped_in_pitbox = pitstop.get('durationstoppedinpitbox', None)
                                
                # Try to insert with DurationStoppedInPitBox column, fall back if column doesn't exist
                cur.execute("""
                INSERT INTO PitStopSummary (GrandPrix, Number, Driver, Constructor, StopNumber, Lap, DurationSpentInPitLane, TimeInSeconds, TimeOfDayStopped, TotalTimeSpentInPitLane, TotalTimeinSeconds, DurationStoppedInPitBox, type, GrandPrixID, DriverID, ConstructorID)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (gp, pitstop['carnumber'], pitstop['driver'], pitstop['constructor'], pitstop['stopnumber'], pitstop['lapstopped'], pitstop['durationspentinpitlane'], pitstop['timeinseconds'], pitstop['timeofday'], pitstop['totaltimeforthewholerace'], pitstop['totaltimeinseconds'], duration_stopped_in_pitbox, 'grandprix', grandprix_id, driver_id, constructor_id))
            #print("Pit Stop Summary:", pitstopsummary) 


        if trigger2 == True:
            driverschampionship, constructorschampionship = parse_championship_results(year, name_map)
            #check for locked:
            driverschampionship = apply_mathematical_locks(driverschampionship, points_system_drivers)
            constructorschampionship = apply_mathematical_locks(constructorschampionship, points_system_constructors)
            #print (championship)
            print ("Championship results Parsed")
            for driver in driverschampionship:
                try:
                    driver_id = driverids[driver['driver']]
                except KeyError:
                    cur.execute("SELECT ID FROM Drivers WHERE Name = ?", (driver['driver'],))
                    row = cur.fetchone()
                    if row:
                        driver_id = row[0]
                    else:
                        raise ValueError(f"Driver ID not found for {driver['driver']}")                
                cur.execute("""
                INSERT OR REPLACE INTO DriversChampionship (ID, Season, Position, Driver, Points, OutOf, RaceByRace, DriverID)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (str(year) + driver['driver'], year, driver['position'], driver['driver'], driver['points'], driver['outof'], json.dumps(driver['racebyrace']), driver_id))
            if constructorschampionship != []:
                for constructor in constructorschampionship:
                    try:
                        constructor_id = constructorids[constructor['constructor']]
                    except KeyError:
                        cur.execute("SELECT ID FROM Constructors WHERE ConstructorName = ?", (constructor['constructor'],))
                        row = cur.fetchone()
                        if row:
                            constructor_id = row[0]
                        else:
                            raise ValueError(f"Constructor ID not found for {constructor['constructor']}")                    
                    try:
                        engine_id = engineids[constructor['engine']]
                    except KeyError:
                        cur.execute("SELECT ID FROM Engines WHERE EngineName = ?", (constructor['engine'],))
                        row = cur.fetchone()
                        if row:
                            engine_id = row[0]
                        else:
                            raise ValueError(f"Engine not found in DB: {constructor['engine']}")
                    cur.execute("""
                    INSERT OR REPLACE INTO ConstructorsChampionship (ID, Season, Position, Constructor, Engine, Points, OutOf, RaceByRace, ConstructorID, EngineID)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (str(year) + constructor['constructor'] + constructor['engine'], year, constructor['position'], constructor['constructor'], constructor['engine'], constructor['points'], constructor['outof'], json.dumps(constructor['racebyrace']), constructor_id, engine_id))
            print ("Championship results saved to database")
    conn.commit()


print ("All seasons processed and saved to database. Updating subtables...")


#We update the wins, podiums, poles, fastest laps, championships and all those stats to the drivers, constructors, and other tables
cur.execute("UPDATE Drivers SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.raceposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.raceposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.starting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.fastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET SprintWins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.sprintposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET SprintPodiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.sprintposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET SprintPoles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.sprintstarting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET SprintFastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.sprintfastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET Championships = (SELECT COUNT(*) FROM DriversChampionship WHERE DriversChampionship.driverid = Drivers.ID AND DriversChampionship.Position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET SeasonsRaced = (SELECT COUNT(DISTINCT GrandsPrix.Season) FROM GrandPrixResults JOIN GrandsPrix ON GrandsPrix.ID = GrandPrixResults.grandprixid WHERE GrandPrixResults.driverid = Drivers.ID AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.racestatus NOT LIKE '%(Did not start)%' AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET SprintStarts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND (GrandPrixResults.sprintstatus NOT LIKE '%(Did not start)%' OR GrandPrixResults.sprintstatus IS NULL) AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET SprintEntries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET DNFs = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND racestatus LIKE '%(Did not finish)%' AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET HatTricks = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND raceposition = 1 AND starting_grid_position = 1 AND fastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND starting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND sprintstarting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET BestSprintQualifyingPosition = (SELECT MIN(sprint_qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND sprint_qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Drivers SET BestChampionshipPosition = (SELECT MIN(Position) FROM DriversChampionship WHERE DriversChampionship.driverid = Drivers.ID AND Position IS NOT NULL AND needstatsupdate = 1)")

print("Drivers stats updated.")

# Update Seasons stats
cur.execute("UPDATE Seasons SET TotalGrandPrix = (SELECT COUNT(*) FROM GrandsPrix WHERE GrandsPrix.Season = Seasons.Season) WHERE needstatsupdate = 1")
cur.execute("UPDATE Seasons SET TotalDrivers = (SELECT COUNT(DISTINCT driverid) FROM GrandPrixResults WHERE GrandPrixResults.grandprixid IN (SELECT ID FROM GrandsPrix WHERE GrandsPrix.Season = Seasons.Season)) WHERE needstatsupdate = 1")
cur.execute("UPDATE Seasons SET TotalConstructors = (SELECT COUNT(DISTINCT constructorid) FROM GrandPrixResults WHERE GrandPrixResults.grandprixid IN (SELECT ID FROM GrandsPrix WHERE GrandsPrix.Season = Seasons.Season)) WHERE needstatsupdate = 1")
cur.execute("UPDATE Seasons SET TotalEngines = (SELECT COUNT(DISTINCT engineid) FROM GrandPrixResults WHERE GrandPrixResults.grandprixid IN (SELECT ID FROM GrandsPrix WHERE GrandsPrix.Season = Seasons.Season)) WHERE needstatsupdate = 1")
cur.execute("UPDATE Seasons SET TotalTeams = (SELECT COUNT(DISTINCT teamid) FROM GrandPrixResults WHERE GrandPrixResults.grandprixid IN (SELECT ID FROM GrandsPrix WHERE GrandsPrix.Season = Seasons.Season)) WHERE needstatsupdate = 1")
cur.execute("UPDATE Seasons SET TotalEngineModels = (SELECT COUNT(DISTINCT enginemodelid) FROM GrandPrixResults WHERE GrandPrixResults.grandprixid IN (SELECT ID FROM GrandsPrix WHERE GrandsPrix.Season = Seasons.Season)) WHERE needstatsupdate = 1")
cur.execute("UPDATE Seasons SET TotalChassis = (SELECT COUNT(DISTINCT chassisid) FROM GrandPrixResults WHERE GrandPrixResults.grandprixid IN (SELECT ID FROM GrandsPrix WHERE GrandsPrix.Season = Seasons.Season)) WHERE needstatsupdate = 1")
cur.execute("UPDATE Seasons SET TotalNationalities = (SELECT COUNT(DISTINCT nationalityid) FROM GrandPrixResults WHERE GrandPrixResults.grandprixid IN (SELECT ID FROM GrandsPrix WHERE GrandsPrix.Season = Seasons.Season)) WHERE needstatsupdate = 1")

print("Seasons stats updated.")


def get_grand_slam_candidates(cur):
    cur.execute("""
        SELECT L.grandprixid, L.lap, L.driverid, L.position
        FROM LapByLap L
        JOIN GrandPrixResults G ON L.driverid = G.driverid AND L.grandprixid = G.grandprixid
        WHERE L.Type = 'grandprix' AND G.needstatsupdate = 1
    """)
    rows = cur.fetchall()

    race_laps = defaultdict(set)
    driver_lap_leads = defaultdict(int)

    for raceID, lapNumber, driverID, position in rows:
        race_laps[raceID].add(lapNumber)
        if position == 1:
            driver_lap_leads[(driverID, raceID)] += 1

    led_every_lap_set = set()
    for (driverID, raceID), laps_led in driver_lap_leads.items():
        if laps_led == len(race_laps[raceID]):
            led_every_lap_set.add((driverID, raceID))

    return led_every_lap_set

led_every_lap_set = get_grand_slam_candidates(cur)

cur.execute("""
    SELECT driverid, grandprixID
    FROM GrandPrixResults 
    WHERE raceposition = 1 
    AND starting_grid_position = 1 
    AND fastestlap = 1
    AND racestatus NOT LIKE '%(Did not finish)%'
    AND racestatus NOT LIKE '%(Did not start)%'
    AND racestatus NOT LIKE '%(Disqualified)%'
    AND needstatsupdate = 1
""")
possible_grandslams = cur.fetchall()

grand_slam_counter = Counter()

for driverID, raceID in possible_grandslams:
    if (driverID, raceID) in led_every_lap_set:
        grand_slam_counter[driverID] += 1

for driverID, count in grand_slam_counter.items():
    cur.execute("UPDATE Drivers SET GrandSlams = ? WHERE ID = ?", (count, driverID))


#constructors now:
cur.execute("UPDATE Constructors SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.raceposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.raceposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.starting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.fastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET SprintWins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.sprintposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET SprintPodiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.sprintposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET SprintPoles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.sprintstarting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET SprintFastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.sprintfastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET Championships = (SELECT COUNT(*) FROM ConstructorsChampionship WHERE ConstructorsChampionship.constructorid = Constructors.ID AND ConstructorsChampionship.Position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET SeasonsRaced = (SELECT COUNT(DISTINCT GrandsPrix.Season) FROM GrandPrixResults JOIN GrandsPrix ON GrandsPrix.ID = GrandPrixResults.grandprixid WHERE GrandPrixResults.constructorid = Constructors.ID AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.racestatus NOT LIKE '%(Did not start)%' AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET SprintStarts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND (GrandPrixResults.sprintstatus NOT LIKE '%(Did not start)%' OR GrandPrixResults.sprintstatus IS NULL) AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET SprintEntries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET DNFs = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND racestatus LIKE '%(Did not finish)%' AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND starting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND sprintstarting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET BestSprintQualifyingPosition = (SELECT MIN(sprint_qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND sprint_qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Constructors SET BestChampionshipPosition = (SELECT MIN(Position) FROM ConstructorsChampionship WHERE ConstructorsChampionship.constructorid = Constructors.ID AND Position IS NOT NULL AND needstatsupdate = 1)")
print("Constructors stats updated.")

#exact same thing for engines as constructors
cur.execute("UPDATE Engines SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.raceposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.raceposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.starting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.fastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET SprintWins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.sprintposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET SprintPodiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.sprintposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET SprintPoles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.sprintstarting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET SprintFastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.sprintfastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET Championships = (SELECT COUNT(*) FROM ConstructorsChampionship WHERE ConstructorsChampionship.engineid = Engines.ID AND ConstructorsChampionship.Position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET SeasonsRaced = (SELECT COUNT(DISTINCT GrandsPrix.Season) FROM GrandPrixResults JOIN GrandsPrix ON GrandsPrix.ID = GrandPrixResults.grandprixid WHERE GrandPrixResults.engineid = Engines.ID AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.racestatus NOT LIKE '%(Did not start)%' AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET SprintStarts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND (GrandPrixResults.sprintstatus NOT LIKE '%(Did not start)%' OR GrandPrixResults.sprintstatus IS NULL) AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET SprintEntries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET DNFs = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND racestatus LIKE '%(Did not finish)%' AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND starting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND sprintstarting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Engines SET BestSprintQualifyingPosition = (SELECT MIN(sprint_qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND sprint_qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
print("Engines stats updated.")

#chassis now:
cur.execute("UPDATE Chassis SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.raceposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.raceposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.starting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.fastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET SprintWins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.sprintposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET SprintPodiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.sprintposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET SprintPoles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.sprintstarting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET SprintFastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.sprintfastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET SeasonsRaced = (SELECT COUNT(DISTINCT GrandsPrix.Season) FROM GrandPrixResults JOIN GrandsPrix ON GrandsPrix.ID = GrandPrixResults.grandprixid WHERE GrandPrixResults.chassisid = Chassis.ID AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.racestatus NOT LIKE '%(Did not start)%' AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET SprintStarts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND (GrandPrixResults.sprintstatus NOT LIKE '%(Did not start)%' OR GrandPrixResults.sprintstatus IS NULL) AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET SprintEntries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET DNFs = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND racestatus LIKE '%(Did not finish)%' AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND starting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND sprintstarting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Chassis SET BestSprintQualifyingPosition = (SELECT MIN(sprint_qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND sprint_qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
print("Chassis stats updated.")

#engine models now:
cur.execute("UPDATE EngineModels SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.raceposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.raceposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.starting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.fastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET SprintWins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.sprintposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET SprintPodiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.sprintposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET SprintPoles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.sprintstarting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET SprintFastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.sprintfastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET Championships = (SELECT COUNT(*) FROM ConstructorsChampionship WHERE ConstructorsChampionship.enginemodelid = EngineModels.ID AND ConstructorsChampionship.Position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET SeasonsRaced = (SELECT COUNT(DISTINCT GrandsPrix.Season) FROM GrandPrixResults JOIN GrandsPrix ON GrandsPrix.ID = GrandPrixResults.grandprixid WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.racestatus NOT LIKE '%(Did not start)%' AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET SprintStarts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND (GrandPrixResults.sprintstatus NOT LIKE '%(Did not start)%' OR GrandPrixResults.sprintstatus IS NULL) AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET SprintEntries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET DNFs = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND racestatus LIKE '%(Did not finish)%' AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND starting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND sprintstarting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE EngineModels SET BestSprintQualifyingPosition = (SELECT MIN(sprint_qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND sprint_qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
print("EngineModels stats updated.")

#tyres now:
cur.execute("UPDATE Tyres SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.raceposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.raceposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.starting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.fastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET SprintWins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.sprintposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET SprintPodiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.sprintposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET SprintPoles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.sprintstarting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET SprintFastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.sprintfastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET SeasonsRaced = (SELECT COUNT(DISTINCT GrandsPrix.Season) FROM GrandPrixResults JOIN GrandsPrix ON GrandsPrix.ID = GrandPrixResults.grandprixid WHERE GrandPrixResults.tyreid = Tyres.ID AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.racestatus NOT LIKE '%(Did not start)%' AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET SprintStarts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND (GrandPrixResults.sprintstatus NOT LIKE '%(Did not start)%' OR GrandPrixResults.sprintstatus IS NULL) AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET SprintEntries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET DNFs = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND racestatus LIKE '%(Did not finish)%' AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND starting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND sprintstarting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Tyres SET BestSprintQualifyingPosition = (SELECT MIN(sprint_qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND sprint_qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
print("Tyres stats updated.")

#teams too:
cur.execute("UPDATE Teams SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.raceposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.raceposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.starting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.fastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET SprintWins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.sprintposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET SprintPodiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.sprintposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET SprintPoles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.sprintstarting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET SprintFastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.sprintfastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET SeasonsRaced = (SELECT COUNT(DISTINCT GrandsPrix.Season) FROM GrandPrixResults JOIN GrandsPrix ON GrandsPrix.ID = GrandPrixResults.grandprixid WHERE GrandPrixResults.teamid = Teams.ID AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.racestatus NOT LIKE '%(Did not start)%' AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET SprintStarts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND (GrandPrixResults.sprintstatus NOT LIKE '%(Did not start)%' OR GrandPrixResults.sprintstatus IS NULL) AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET SprintEntries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET DNFs = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND racestatus LIKE '%(Did not finish)%' AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND starting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND sprintstarting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Teams SET BestSprintQualifyingPosition = (SELECT MIN(sprint_qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND sprint_qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
print("Teams stats updated.")

#nationalities:
cur.execute("UPDATE Nationalities SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.raceposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.raceposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.starting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.fastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET SprintWins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.sprintposition = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET SprintPodiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.sprintposition <= 3 AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET SprintPoles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.sprintstarting_grid_position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET SprintFastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.sprintfastestlap = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET Championships = (SELECT COUNT(*) FROM DriversChampionship JOIN Drivers ON DriversChampionship.DriverID = Drivers.ID WHERE Drivers.NationalityID = Nationalities.ID AND DriversChampionship.Position = 1 AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET SeasonsRaced = (SELECT COUNT(DISTINCT GrandsPrix.Season) FROM GrandPrixResults JOIN GrandsPrix ON GrandsPrix.ID = GrandPrixResults.grandprixid WHERE GrandPrixResults.nationalityid = Nationalities.ID AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.racestatus NOT LIKE '%(Did not start)%' AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET SprintStarts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND (GrandPrixResults.sprintstatus NOT LIKE '%(Did not start)%' OR GrandPrixResults.sprintstatus IS NULL) AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET SprintEntries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET DNFs = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND racestatus LIKE '%(Did not finish)%' AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND starting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND sprintstarting_grid_position IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND raceposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND sprintposition IS NOT NULL AND needstatsupdate = 1)")
cur.execute("UPDATE Nationalities SET BestSprintQualifyingPosition = (SELECT MIN(sprint_qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND sprint_qualifyingposition IS NOT NULL AND needstatsupdate = 1)")
print("Nationalities stats updated.")

def update_laps_led_for_component(cur, component_table, component_id_column):
    # Grand Prix Laps Led
    query_gp = f"""
    SELECT G.{component_id_column}, COUNT(*) AS laps_led
    FROM LapByLap AS L
    JOIN GrandPrixResults AS G ON L.driverid = G.driverid AND L.grandprixid = G.grandprixid
    WHERE L.position = 1
      AND L.Type = 'grandprix'
      AND G.{component_id_column} IS NOT NULL
      AND G.needstatsupdate = 1
    GROUP BY G.{component_id_column}
    """
    cur.execute(query_gp)
    results_gp = cur.fetchall()

    for component_id, laps_led in results_gp:
        cur.execute(
            f"UPDATE {component_table} SET GrandPrixLapsLed = ? WHERE ID = ?",
            (laps_led, component_id)
        )

    # Sprint Laps Led
    query_sprint = f"""
    SELECT G.{component_id_column}, COUNT(*) AS laps_led
    FROM LapByLap AS L
    JOIN GrandPrixResults AS G ON L.driverid = G.driverid AND L.grandprixid = G.grandprixid
    WHERE L.position = 1
      AND L.Type = 'sprint'
      AND G.{component_id_column} IS NOT NULL
      AND G.needstatsupdate = 1
    GROUP BY G.{component_id_column}
    """
    cur.execute(query_sprint)
    results_sprint = cur.fetchall()

    for component_id, laps_led in results_sprint:
        cur.execute(
            f"UPDATE {component_table} SET SprintLapsLed = ? WHERE ID = ?",
            (laps_led, component_id)
        )


update_laps_led_for_component(cur, "Constructors", "constructorid")
update_laps_led_for_component(cur, "Engines", "engineid")
update_laps_led_for_component(cur, "Chassis", "chassisid")
update_laps_led_for_component(cur, "EngineModels", "enginemodelid")
update_laps_led_for_component(cur, "Tyres", "tyreid")
update_laps_led_for_component(cur, "Teams", "teamid")
update_laps_led_for_component(cur, "Drivers", "driverid")
update_laps_led_for_component(cur, "Nationalities", "nationalityid")
print("GrandPrixLapsLed and SprintLapsLed stats updated.")

#flip all things back to 0 now that we're done
cur.execute("UPDATE Drivers SET needstatsupdate = 0 WHERE needstatsupdate = 1")
cur.execute("UPDATE Constructors SET needstatsupdate = 0 WHERE needstatsupdate = 1")
cur.execute("UPDATE Engines SET needstatsupdate = 0 WHERE needstatsupdate = 1")
cur.execute("UPDATE Chassis SET needstatsupdate = 0 WHERE needstatsupdate = 1")
cur.execute("UPDATE EngineModels SET needstatsupdate = 0 WHERE needstatsupdate = 1")
cur.execute("UPDATE Tyres SET needstatsupdate = 0 WHERE needstatsupdate = 1")
cur.execute("UPDATE Teams SET needstatsupdate = 0 WHERE needstatsupdate = 1")
cur.execute("UPDATE Nationalities SET needstatsupdate = 0 WHERE needstatsupdate = 1")
cur.execute("UPDATE Seasons SET needstatsupdate = 0 WHERE needstatsupdate = 1")

print("All stats updated successfully. Closing database connection...")


conn.commit() 
conn.close()
#fi.close()
