"""
scrape_engine_models.py

Scrapes engine model spec data from statsf1.com for every EngineModel row
in the database that does not yet have StatsF1Data populated.

For each unique EngineMake, fetches:
    https://www.statsf1.com/en/moteur-{slug}.aspx

Parses every engine entry on the page, translates French keys/values to
English using deep_translator, and writes a JSON blob to
EngineModels.StatsF1Data for the matching row.
"""

import json
import re
import sqlite3
import time
import unicodedata
from typing import Optional
from ollama import chat
import requests
from bs4 import BeautifulSoup
from deep_translator import GoogleTranslator
from rapidfuzz import fuzz


SYSTEM_PROMPT = """
You are an expert in Formula One engine manufacturers and engine model naming conventions.

Your task is to match a Formula One engine model name from StatsF1 to the most appropriate engine model in our database.

Input will be provided as JSON in the following format:

{
    "model_to_be_matched": "<string>",
    "list_of_contenders": ["<string>", "<string>", ...]
}

Field definitions:

- model_to_be_matched:
  A string containing the engine model name as it appears in StatsF1.

- list_of_contenders:
  A list of strings containing engine model names from the database.
  You must select the single database entry that best corresponds to the StatsF1 engine model.

Matching guidelines:

- Engine names may differ due to abbreviations, formatting, spelling variations, manufacturer naming conventions, or missing version identifiers.
- Consider manufacturer, engine family, generation, and historical usage by F1 teams.
- Prefer the closest real-world equivalent even if the names are not identical.
- If multiple contenders are similar, choose the most specific and accurate match.
- If no contender is a reasonable match, return null.

Output format:
**PLEASE RENDER YOUR OUTPUT IN JSON FORMAT. RESPONSE SHOULD START WITH { AND END WITH } . NO CHARACTERS BEFORE OR AFTER!** 
"matched_model" must be exactly one of the strings provided in "list_of_contenders", or null if none are suitable.
"confidence" must be a number between 0.0 and 1.0, representing the confidence in the match.
"reasoning" must be a brief explanation of why you chose the matched model.
{
    "matched_model": "<selected contender or null>",
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation>"
}


Examples:

1. Exact model family + displacement:
Input: {"model_to_be_matched": "BRM P56 1.5", "list_of_contenders": ["P56 V8 1.5", "P56 V8 2.0", "L4 c 3.0"]}
Output: {"matched_model": "P56 V8 1.5", "confidence": 0.95, "reasoning": "Identical model code and displacement"}

2. Known historical alias (different name, same engine):
Input: {"model_to_be_matched": "Ferrari Tipo 033", "list_of_contenders": ["033D V6 t 1.5", "033E V6 t 1.5", "Tipo 044/1"]}
Output: {"matched_model": "033D V6 t 1.5", "confidence": 0.95, "reasoning": "Tipo 033 is the 1987 engine with code 033D"}

3. Manufacturer prefix ignored:
Input: {"model_to_be_matched": "Coventry Climax FPF 2.5", "list_of_contenders": ["FPF L4 2.5", "FPF L4 1.5", "V8 2.5"]}
Output: {"matched_model": "FPF L4 2.5", "confidence": 0.95, "reasoning": "FPF 2.5 with manufacturer prefix removed"}

4. Layout + displacement + flags match when DB row has no model name:
Input: {"model_to_be_matched": "Alta 1.5 L4C", "list_of_contenders": ["L4 c 1.5", "GP L4 2.5", "L4 1.5"]}
Output: {"matched_model": "L4 c 1.5", "confidence": 0.85, "reasoning": "Inline‑4 supercharged 1.5L, L4C = L4 'c'"}

5. Pre‑1960 engine with no model code—match on layout and displacement:
Input: {"model_to_be_matched": "Cadillac V8", "list_of_contenders": ["V8 4.5", "L8 2.5"]}
Output: {"matched_model": "V8 4.5", "confidence": 0.85, "reasoning": "V8 4.5 makes the most sense here in the list of contenders"}

6. No reasonable match:
Input: {"model_to_be_matched": "Ferrari DS50 (Lancia DS50)", "list_of_contenders": ["044/1 V10 3.0", "Tipo 033 2.5"]}
Output: {"matched_model": null, "confidence": 0.0, "reasoning": "No reasonable match in the DB"}

7. Ambiguous match:
Input: {"model_to_be_matched": "Ford XV5", "list_of_contenders": ["XV5 2.5", "XV5 3.0"]}
Output: {"matched_model": null, "confidence": 0.0, "reasoning": "Ambiguous match between 2.5 and 3.0. Returned null to avoid poisoning the data."}

High-value examples (StatsF1 ↔ DB):
- "Alta 2.5 L4" ↔ "GP L4 2.5"
- "BRM P56 1.5" ↔ "P56 V8 1.5"
- "Coventry Climax FPF 2.5" ↔ "FPF L4 2.5"
- "Ferrari Tipo 033" ↔ "033D V6 t 1.5"
- "Ferrari Tipo 033E" ↔ "033E V6 t 1.5"
- "Renault RS1" ↔ "RS1 V10 3.5"
- "Maserati A6G" ↔ "A6 L6 2.0"
- "Alta 1.5 L4C" ↔ "L4 c 1.5"
- "Offenhauser 3.0 L4C" ↔ "L4 c 3.0"
- Pre-1960 fallback by layout+displacement:
  "Cadillac V8" ↔ "V8 4.5", "Bugatti 2.5 L8" ↔ "L8 2.5", "JAP" ↔ "V2 1.1"
"""
# ---------------------------------------------------------------------------
# Hardcoded multi-DB-row → single statsf1 mapping
# Some DB rows differ only in naming convention but refer to the same
# statsf1 engine. Map (EngineMake, statsf1_short_code) → list of DB
# EngineModel names that should all receive the same statsf1 data.
# ---------------------------------------------------------------------------

HARDCODED_MULTI_MATCH = {
    ("Ferrari", "125 F1"): ["125 V12 c 1.5", "125 V12 1.5"],
    ("Ferrari", "126 C"): ["021 V6 t 1.5", "031 V6 t 1.5", "032 V6 t 1.5"],
    ("Ferrari", "Tipo B12"): ["001 F12 3.0", "001/1 F12 3.0", "001/11 F12 3.0", "015 F12 3.0"],
    ("Ferrari", "Tipo 047"): ["047 V10 3.0", "048 V10 3.0"],
}

# ---------------------------------------------------------------------------
# Name helpers (from writedb.py)
# ---------------------------------------------------------------------------

def normalize_name(name: str) -> str:
    if not name:
        return ""
    if name.lower() == "gianmaria bruni":
        return "gimmi bruni"
    elif name.lower() == "zhou guanyu":
        return "guanyu zhou"
    return (
        unicodedata.normalize("NFKD", name.lower())
        .encode("ascii", "ignore")
        .decode("ascii")
        .replace("-", " ")
    )


def slugify_statsf1_constructor_name(name: str) -> str:
    if "?" in name:
        name = name.replace("?", "-")
    name = name.replace("°", "-")
    return (
        re.sub(r"[^a-z0-9.]", "-", normalize_name(name))
        .replace("/", "-")
        .replace("(", "-")
        .replace(")", "-")
    )


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def parse_used_by_teams(raw: str) -> list[str]:
    """Parse statsf1 'Utilisé par' value into a list of team names."""
    teams = []
    for part in raw.split(","):
        part = part.strip()
        part = re.sub(r"\s*\(\d{4}(?:-\d{2,4})?\)\s*$", "", part).strip()
        if part:
            teams.append(part)
    return teams


def parse_year_range(years: str) -> Optional[tuple[int, int]]:
    """Parse statsf1 year text like '1962-1965' or '1967' into (start, end)."""
    if not years:
        return None
    m = re.fullmatch(r"(\d{4})(?:-(\d{4}))?", years.strip())
    if not m:
        return None
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else start
    return (start, end)


def years_overlap(
    a_start: int, a_end: int,
    b_start: int, b_end: int,
) -> bool:
    return not (a_end < b_start or b_end < a_start)


def gp_year_from_name(gp_name: str) -> Optional[int]:
    if not gp_name or len(gp_name) < 4:
        return None
    year = gp_name[:4]
    return int(year) if year.isdigit() else None


def normalize_code(code: str) -> str:
    """Lowercase, strip trailing turbo/evo, collapse punctuation to spaces (keeping dots)."""
    code = code.lower().strip()
    code = re.sub(r"\s+(turbo|evo|suralimenté)$", "", code).strip()
    # Keep decimals intact, replace dashes/slashes with spaces
    code = re.sub(r"[\-\/]+", " ", code).strip()
    # Collapse multiple spaces
    code = re.sub(r"\s+", " ", code).strip()
    return code


def is_config_token(token: str) -> bool:
    """True for tokens that describe cylinder layout/displacement, not model identity."""
    return bool(re.fullmatch(
        r"v\d+|l\d+|f\d+|h\d+|w\d+|t|h|c|s|tbn|\d+[\.,]\d+",
        token, re.I
    ))


def db_identity(engine_model: str) -> str:
    """
    Strip config/displacement suffix tokens from a DB EngineModel string,
    returning just the identity portion normalized for comparison.
    e.g. 'M12/13 L4 t 1.5' → 'm12 13'
         '056 V8 2.4'       → '056'
         'FO 110D V10 3.0'  → 'fo 110d'
         'EQ Power+ V6 1.6' → 'eq power'
    """
    tokens = []
    for tok in engine_model.split():
        tok_clean = re.sub(r"[+]+$", "", tok)
        if is_config_token(tok_clean.lower()):
            break
        if tok_clean:
            tokens.append(tok_clean)
    return normalize_code(" ".join(tokens))


def team_name_matches(statsf1_team: str, db_team: str, db_constructor: str) -> bool:
    sf1_norm = normalize_name(statsf1_team)
    if not sf1_norm:
        return False
    for db_name in (db_team, db_constructor):
        db_norm = normalize_name(db_name)
        if not db_norm:
            continue
        if sf1_norm in db_norm or db_norm in sf1_norm:
            return True
        if fuzz.partial_ratio(sf1_norm, db_norm) >= 85:
            return True
    return False


def team_overlap_score(
    statsf1_teams: list[str],
    usage_rows: list[tuple[int, str, str]],
    overlap_start: int,
    overlap_end: int,
) -> int:
    db_entries = [
        (team, constructor)
        for season, team, constructor in usage_rows
        if overlap_start <= season <= overlap_end
    ]
    if not statsf1_teams or not db_entries:
        return 0
    score = 0
    for sf1_team in statsf1_teams:
        if any(team_name_matches(sf1_team, team, constructor) for team, constructor in db_entries):
            score += 1
    return score


def _fuzzy_match_candidates(
    statsf1_short_code: str,
    candidates: list[tuple[int, str]],
) -> Optional[int]:
    """Fuzzy-match a statsf1 short code against a restricted candidate list."""
    THRESHOLD = 80
    if not statsf1_short_code.strip():
        return None
    sf1_is_disp = bool(re.fullmatch(r"\d+[\.,]\d+", statsf1_short_code.strip()))
    sf1 = normalize_code(statsf1_short_code)
    sf1_nospace = sf1.replace(" ", "")

    scores: list[tuple[float, int, str]] = []

    for em_id, em_name in candidates:
        norm_full_db = normalize_code(em_name)

        if sf1_is_disp:
            disp = statsf1_short_code.strip().replace(",", ".")
            raw_tokens = em_name.split()
            score = 100.0 if disp in raw_tokens else 0.0
        else:
            identity = db_identity(em_name)

            if not identity:
                score = fuzz.token_set_ratio(sf1, norm_full_db)
            else:
                score_id = max(
                    fuzz.token_set_ratio(sf1, identity),
                    fuzz.token_sort_ratio(sf1, identity),
                )
                score_nospace = fuzz.token_set_ratio(sf1_nospace, identity.replace(" ", ""))
                score_full = fuzz.token_set_ratio(sf1, norm_full_db)
                score = max(score_id, score_nospace, score_full)

        if score >= THRESHOLD:
            scores.append((score, em_id, em_name))

    if not scores:
        return None

    scores.sort(key=lambda x: -x[0])
    best_score = scores[0][0]
    top = [s for s in scores if s[0] >= best_score - 1]

    if len(top) == 1:
        return top[0][1]

    sf1_identity = " ".join(
        t for t in normalize_code(statsf1_short_code).split() if not is_config_token(t)
    )
    exact = [s for s in top if db_identity(s[2]) == sf1_identity]
    if len(exact) == 1:
        return exact[0][1]

    exact_ns = [
        s for s in top
        if db_identity(s[2]).replace(" ", "") == sf1_identity.replace(" ", "")
    ]
    if len(exact_ns) == 1:
        return exact_ns[0][1]
    exact_ns = [
            s for s in top
            if db_identity(s[2]).replace(" ", "") == sf1_identity.replace(" ", "")
        ]
    if len(exact_ns) == 1:
        return exact_ns[0][1]

    # === INSERT THIS NEW TIE-BREAKER HERE ===
    word_matches = [s for s in top if sf1_identity in db_identity(s[2]).split()]
    if len(word_matches) == 1:
        return word_matches[0][1]
    # =======================================

   
    sf1_disp = extract_displacement(statsf1_short_code)
    if sf1_disp:
        disp_match = [s for s in top if extract_displacement(s[2]) == sf1_disp]
        if len(disp_match) == 1:
            return disp_match[0][1]

    top.sort(key=lambda s: len(db_identity(s[2])))
    if len(db_identity(top[0][2])) < len(db_identity(top[1][2])):
        return top[0][1]

    print(f"    Ambiguous: '{statsf1_short_code}' → {[(s[2], s[0]) for s in top]}")
    return None


def match_engine_model(
    entry: dict,
    db_models: list[tuple[int, str]],
    season_range: dict[int, tuple[int, int]],
    usage_by_model: dict[int, list[tuple[int, str, str]]],
) -> Optional[tuple[int, str]]:
    """
    Match a statsf1 entry to a DB EngineModelID.
    Returns (em_id, stage) where stage is 'era', 'teams', or 'fuzzy'.
    """
    statsf1_short_code = entry["short_code"]
    sf1_years = parse_year_range(entry.get("years") or "")
    statsf1_teams = entry.get("used_by_teams") or []

    if sf1_years:
        era_candidates = [
            (em_id, em_name)
            for em_id, em_name in db_models
            if em_id in season_range
            and years_overlap(
                sf1_years[0], sf1_years[1],
                season_range[em_id][0], season_range[em_id][1],
            )
        ]
    else:
        era_candidates = list(db_models)

    if len(era_candidates) == 1:
        return era_candidates[0][0], "era"

    fuzzy_pool = era_candidates if era_candidates else list(db_models)

    if len(era_candidates) > 1 and statsf1_teams and sf1_years:
        overlap_start, overlap_end = sf1_years
        scored: list[tuple[int, int, str]] = []
        for em_id, em_name in era_candidates:
            model_rows = usage_by_model.get(em_id, [])
            if model_rows:
                model_min = min(s for s, _, _ in model_rows)
                model_max = max(s for s, _, _ in model_rows)
                eff_start = max(overlap_start, model_min)
                eff_end = min(overlap_end, model_max)
            else:
                eff_start, eff_end = overlap_start, overlap_end
            score = team_overlap_score(statsf1_teams, model_rows, eff_start, eff_end)
            if score > 0:
                scored.append((score, em_id, em_name))

        if scored:
            scored.sort(key=lambda x: -x[0])
            best = scored[0][0]
            top = [s for s in scored if s[0] == best]
            if len(top) == 1:
                return top[0][1], "teams"

    em_id = _fuzzy_match_candidates(statsf1_short_code, fuzzy_pool)
    if em_id is not None:
        return em_id, "fuzzy"
    # --- LLM MATCHING FALLBACK ---
    
    # 1. Extract just the names for the LLM to evaluate
    contender_names = [name for _, name in fuzzy_pool]
    
    # 2. Build the payload dynamically
    payload = {
        "model_to_be_matched": entry["statsf1_name"],
        "list_of_contenders": contender_names
    }
    
    max_retries = 3
    
    for attempt in range(max_retries):
        try:
            if attempt > 0:
                print(f"  ↻ LLM Retry attempt {attempt + 1}/{max_retries} for {entry['statsf1_name']}...")
                time.sleep(2) # Brief backoff before hitting the local server again
                
            response = chat(
                model='llama3.1:8b',
                messages=[
                    {'role': 'system', 'content': SYSTEM_PROMPT}, 
                    {'role': 'user', 'content': json.dumps(payload)}
                ],
                options={'temperature': 0.0}
            )
            
            raw_output = response.message.content.strip()
            
            # 3. Strip potential markdown wrapping from the LLM output
            if raw_output.startswith("```json"):
                raw_output = raw_output[7:-3].strip()
            elif raw_output.startswith("```"):
                raw_output = raw_output[3:-3].strip()
                
            # 4. Parse safely
            parsed_json = json.loads(raw_output)
            matched_model_name = parsed_json.get("matched_model")
            
            # 5. Map the string name back to the DB ID and return the tuple
            if matched_model_name:
                for em_id, em_name in fuzzy_pool:
                    if em_name == matched_model_name:
                        return em_id, "llm"
                        
            # If parsed successfully but "matched_model" is null, return None
            return None 
            
        except json.JSONDecodeError as e:
            print(f"  ⚠ LLM JSON Parse Error (Attempt {attempt + 1}): {e}")
            continue # Try again
        except Exception as e:
            print(f"  ⚠ LLM Execution/Connection Error (Attempt {attempt + 1}): {e}")
            continue # Try again
            
    # If the loop exhausts all retries
    print(f"  ✗ LLM Failed to match after {max_retries} attempts.")
    return None


def load_db_usage_context(
    cur: sqlite3.Cursor,
    make_rows: list,
) -> tuple[dict[int, tuple[int, int]], dict[int, list[tuple[int, str, str]]]]:
    em_ids = [r["ID"] for r in make_rows]
    if not em_ids:
        return {}, {}

    placeholders = ",".join("?" * len(em_ids))
    season_range: dict[int, tuple[int, int]] = {}
    for em_id, min_season, max_season in cur.execute(
        f"""
        SELECT em.ID, MIN(gp.Season), MAX(gp.Season)
        FROM EngineModels em
        JOIN GrandPrixResults gpr ON gpr.enginemodelid = em.ID
        JOIN GrandsPrix gp ON gp.ID = gpr.grandprixid
        WHERE em.ID IN ({placeholders})
        GROUP BY em.ID
        """,
        em_ids,
    ):
        season_range[em_id] = (min_season, max_season)

    for row in make_rows:
        if row["ID"] in season_range:
            continue
        first = gp_year_from_name(row["FirstGrandPrix"])
        last = gp_year_from_name(row["LastGrandPrix"])
        if first is not None and last is not None:
            season_range[row["ID"]] = (first, last)

    usage_by_model: dict[int, list[tuple[int, str, str]]] = {em_id: [] for em_id in em_ids}
    for em_id, season, team, constructor in cur.execute(
        f"""
        SELECT DISTINCT gpr.enginemodelid, gp.Season, gpr.team, gpr.constructor
        FROM GrandPrixResults gpr
        JOIN GrandsPrix gp ON gp.ID = gpr.grandprixid
        WHERE gpr.enginemodelid IN ({placeholders})
        """,
        em_ids,
    ):
        usage_by_model[em_id].append((season, team or "", constructor or ""))

    return season_range, usage_by_model


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

_translator = GoogleTranslator(source="fr", target="en")
_translation_cache: dict[str, str] = {}


def translate(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    if text in _translation_cache:
        return _translation_cache[text]
    try:
        result = _translator.translate(text)
        _translation_cache[text] = result
        return result
    except Exception:
        return text


# ---------------------------------------------------------------------------
# statsf1 short code extraction
# ---------------------------------------------------------------------------

def extract_statsf1_short_code(nom_moteur: str, make: str) -> str:
    """
    Dynamically strip manufacturer prefixes (and compound names) 
    by slicing everything up to and including the 'make'.
    """
    code = nom_moteur.strip()
    lower_code = code.lower()
    lower_make = make.strip().lower()

    # Find the make within the statsf1 string and slice off the prefix
    # E.g., "Ford Cosworth CR-3" (make "Cosworth") -> strips "Ford Cosworth "
    # E.g., "Coventry Climax FPF" (make "Climax") -> strips "Coventry Climax "
    make_idx = lower_code.find(lower_make)
    if make_idx != -1:
        code = code[make_idx + len(lower_make):].strip()

    # Strip Ferrari's "Tipo " designation if it immediately follows
    if code.lower().startswith("tipo "):
        code = code[5:].strip()

    # Fallback: if stripping leaves us with an empty string, return the original
    return code if code else nom_moteur.strip()

def extract_aliases(description_parts: list[str]) -> list[str]:
    """Extract 'also called' variant names from description text."""
    aliases = []
    for part in description_parts:
        # Match patterns like "Ferrari Tipo 021/1 en 1981"
        for m in re.finditer(r"(?:Tipo|Ferrari)\s+([\w/\-]+)", part):
            aliases.append(m.group(1))
    return aliases

def extract_displacement(text: str) -> Optional[str]:
    """Extract a displacement like '1.5', '3.0' from a string."""
    m = re.search(r"(\d+[\.,]\d+)", text)
    return m.group(1).replace(",", ".") if m else None


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def get_year_text(p_tag) -> Optional[str]:
    text = p_tag.get_text(separator=" ").strip()
    m = re.search(r"\((\d{4}(?:-\d{4})?)\)", text)
    return m.group(1) if m else None


def parse_engine_page(html: str, make: str) -> list[dict]:
    """
    Parse a statsf1 engine manufacturer page and return a list of engine
    entry dicts with keys: statsf1_name, short_code, years, era,
    description, specs.
    """
    soup = BeautifulSoup(html, "html.parser")
    biobot = soup.find("div", class_="biobot")
    if not biobot:
        return []

    engines = []
    current_era = ""
    children = list(biobot.children)
    i = 0

    while i < len(children):
        node = children[i]

        if hasattr(node, "name"):
            # Era heading: <span style="font-size: 15px"><strong>...</strong></span>
            if node.name == "span" and "font-size" in node.get("style", ""):
                heading = node.get_text(strip=True)
                if heading:
                    current_era = heading
                i += 1
                continue

            # Era heading inside a <p>
            if node.name == "p":
                inner_span = node.find("span", style=re.compile(r"font-size", re.I))
                if inner_span and inner_span.find(["b", "strong"]):
                    heading = inner_span.get_text(strip=True)
                    if heading:
                        current_era = heading
                    i += 1
                    continue

            # Engine entry
            if node.name == "p":
                nom_span = node.find("span", class_="NomMoteur")
                if nom_span:
                    statsf1_name = nom_span.get_text(strip=True)
                    short_code = extract_statsf1_short_code(statsf1_name, make)
                    year = get_year_text(node)
                    description_parts = []
                    specs = {}

                    j = i + 1
                    while j < len(children):
                        sib = children[j]
                        if not hasattr(sib, "name"):
                            j += 1
                            continue
                        if sib.name == "hr":
                            break
                        if sib.name == "p" and sib.find("span", class_="NomMoteur"):
                            break
                        if sib.name == "p":
                            text = sib.get_text(separator=" ", strip=True)
                            if not text or text == "\xa0":
                                j += 1
                                continue
                            if year is None:
                                y = get_year_text(sib)
                                if y:
                                    year = y
                                    j += 1
                                    continue
                            if text.startswith("-"):
                                kv = text.lstrip("-").strip()
                                if ":" in kv:
                                    key, _, val = kv.partition(":")
                                    specs[key.strip()] = val.strip()
                                else:
                                    specs[kv] = True
                            else:
                                description_parts.append(text)
                        j += 1

                    used_by_raw = specs.get("Utilisé par", "")
                    used_by_teams = (
                        parse_used_by_teams(used_by_raw)
                        if isinstance(used_by_raw, str) else []
                    )

                    engines.append({
                        "statsf1_name": statsf1_name,
                        "short_code": short_code,
                        "years": year,
                        "era": current_era,
                        "used_by_teams": used_by_teams,
                        "description": " ".join(description_parts) if description_parts else None,
                        "specs": specs,
                    })
                    i = j
                    continue

        i += 1

    return engines


# ---------------------------------------------------------------------------
# Translation of parsed engine data
# ---------------------------------------------------------------------------

def translate_engine_entry(entry: dict) -> dict:
    translated_specs = {}
    for key, val in entry["specs"].items():
        en_key = translate(key)
        en_val = translate(val) if isinstance(val, str) else val
        translated_specs[en_key] = en_val

    return {
        "statsf1_name": entry["statsf1_name"],
        "years": entry["years"],
        "era": translate(entry["era"]) if entry["era"] else None,
        "description": translate(entry["description"]) if entry["description"] else None,
        "specs": translated_specs,
    }


# ---------------------------------------------------------------------------
# HTTP fetch
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-GB,en;q=0.9",
    "Referer": "https://www.statsf1.com/en/",
}


def fetch_page(url: str, session: requests.Session) -> Optional[str]:
    time.sleep(20)
    try:
        resp = session.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.text
        print(f"  HTTP {resp.status_code} for {url}")
        return None
    except requests.RequestException as e:
        print(f"  Request error for {url}: {e}")
        return None


def scrape_pending_engine_models(
    engine_makes: Optional[set[str]] = None,
    db_path: str = "sessionresults.db",
) -> None:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(EngineModels)")}
    if "StatsF1Data" not in existing_cols:
        print("Adding StatsF1Data column to EngineModels...")
        cur.execute("ALTER TABLE EngineModels ADD COLUMN StatsF1Data TEXT")
        con.commit()

    query = """
        SELECT ID, EngineMake, EngineModel, FirstGrandPrix, LastGrandPrix
        FROM EngineModels
        WHERE StatsF1Data IS NULL
    """
    params: list[str] = []
    if engine_makes is not None:
        if not engine_makes:
            con.close()
            return
        placeholders = ",".join("?" * len(engine_makes))
        query += f" AND EngineMake IN ({placeholders})"
        params.extend(sorted(engine_makes))
    query += " ORDER BY EngineMake, ID"

    rows = cur.execute(query, params).fetchall()
    if not rows:
        if engine_makes is None:
            print("All engine models already have StatsF1Data populated. Nothing to do.")
        con.close()
        return

    by_make: dict[str, list] = {}
    for row in rows:
        by_make.setdefault(row["EngineMake"], []).append(row)

    print(f"Found {len(rows)} engine models across {len(by_make)} makes to scrape.\n")

    session = requests.Session()
    total_matched = 0
    total_unmatched = 0

    for make, make_rows in by_make.items():
        slug = slugify_statsf1_constructor_name(make)
        url = f"https://www.statsf1.com/en/moteur-{slug}.aspx"
        print(f"[{make}] â†’ {url}")
        html = fetch_page(url, session)
        if html is None:
            print(f"  Skipping {make} (fetch failed)\n")
            continue

        entries = parse_engine_page(html, make)
        if not entries:
            print(f"  No engine entries parsed for {make}\n")
            continue

        print(f"  Parsed {len(entries)} entries from statsf1")

        db_models = [(r["ID"], r["EngineModel"]) for r in make_rows]
        season_range, usage_by_model = load_db_usage_context(cur, make_rows)
        matched_ids: set[int] = set()
        db, sf1 = False, False
        for entry in entries:
            hardcoded_key = (make, entry["short_code"])
            hardcoded_models = HARDCODED_MULTI_MATCH.get(hardcoded_key, [])
            if hardcoded_models:
                matched_entry = translate_engine_entry(entry)
                for r in make_rows:
                    if r["EngineModel"] in hardcoded_models:
                        if r["ID"] in matched_ids:
                            continue
                        matched_ids.add(r["ID"])
                        total_matched += 1
                        print(f"  ✓ [hardcoded] {entry['statsf1_name']!r} → DB row '{r['EngineModel']!r}'")
                        cur.execute(
                            "UPDATE EngineModels SET StatsF1Data = ? WHERE ID = ?",
                            (json.dumps(matched_entry, ensure_ascii=False), r["ID"]),
                        )
                continue

            result = match_engine_model(entry, db_models, season_range, usage_by_model)
            if result is None:
                print(f"  ✗ No DB match for statsf1 entry: {entry['statsf1_name']!r}")
                db = True
                continue
            em_id, stage = result
            if em_id in matched_ids:
                print(f"  ⚠ Duplicate match for ID {em_id}, skipping: {entry['statsf1_name']!r}")
                continue

            matched_entry = translate_engine_entry(entry)
            matched_ids.add(em_id)
            total_matched += 1
            db_name = next(r["EngineModel"] for r in make_rows if r["ID"] == em_id)
            print(f"  ✓ [{stage}] {entry['statsf1_name']!r} → DB row '{db_name}'")

            cur.execute(
                "UPDATE EngineModels SET StatsF1Data = ? WHERE ID = ?",
                (json.dumps(matched_entry, ensure_ascii=False), em_id),
            )

        for r in make_rows:
            if r["ID"] not in matched_ids:
                print(f"  ✗ No statsf1 match for DB row: {r['EngineModel']!r}")
                sf1 = True
                total_unmatched += 1

        if (db) or (sf1 and db):
            con.close()
            raise RuntimeError(f"Unmatched entries for {make}, aborting to avoid partial updates.")
        con.commit()
        time.sleep(2)
        print()

    print(f"Done. Matched: {total_matched}, Unmatched: {total_unmatched}")
    con.close()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    con = sqlite3.connect("sessionresults.db")
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # Add StatsF1Data column if it doesn't exist yet
    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(EngineModels)")}
    if "StatsF1Data" not in existing_cols:
        print("Adding StatsF1Data column to EngineModels...")
        cur.execute("ALTER TABLE EngineModels ADD COLUMN StatsF1Data TEXT")
        con.commit()

    # Fetch all EngineModel rows that still need scraping
    rows = cur.execute("""
        SELECT ID, EngineMake, EngineModel, FirstGrandPrix, LastGrandPrix
        FROM EngineModels
        WHERE StatsF1Data IS NULL
        ORDER BY EngineMake, ID
    """).fetchall()

    if not rows:
        print("All engine models already have StatsF1Data populated. Nothing to do.")
        con.close()
        return

    # Group by make
    by_make: dict[str, list] = {}
    for row in rows:
        by_make.setdefault(row["EngineMake"], []).append(row)

    print(f"Found {len(rows)} engine models across {len(by_make)} makes to scrape.\n")

    session = requests.Session()
    total_matched = 0
    total_unmatched = 0

    for make, make_rows in by_make.items():
        slug = slugify_statsf1_constructor_name(make)
        url = f"https://www.statsf1.com/en/moteur-{slug}.aspx"
        print(f"[{make}] → {url}")
        html = fetch_page(url, session)
        if html is None:
            print(f"  Skipping {make} (fetch failed)\n")
            continue

        entries = parse_engine_page(html, make)
        if not entries:
            print(f"  No engine entries parsed for {make}\n")
            continue

        print(f"  Parsed {len(entries)} entries from statsf1")

        db_models = [(r["ID"], r["EngineModel"]) for r in make_rows]
        season_range, usage_by_model = load_db_usage_context(cur, make_rows)
        matched_ids: set[int] = set()
        db, sf1 = False, False
        for entry in entries:
            # Check hardcoded multi-match first
            hardcoded_key = (make, entry["short_code"])
            hardcoded_models = HARDCODED_MULTI_MATCH.get(hardcoded_key, [])
            if hardcoded_models:
                matched_entry = translate_engine_entry(entry)
                for r in make_rows:
                    if r["EngineModel"] in hardcoded_models:
                        if r["ID"] in matched_ids:
                            continue
                        matched_ids.add(r["ID"])
                        total_matched += 1
                        print(f"  ✓ [hardcoded] {entry['statsf1_name']!r} → DB row '{r['EngineModel']!r}'")
                        cur.execute(
                            "UPDATE EngineModels SET StatsF1Data = ? WHERE ID = ?",
                            (json.dumps(matched_entry, ensure_ascii=False), r["ID"]),
                        )
                continue

            result = match_engine_model(entry, db_models, season_range, usage_by_model)
            if result is None:
                print(f"  ✗ No DB match for statsf1 entry: {entry['statsf1_name']!r}")
                db = True
                continue
            em_id, stage = result
            if em_id in matched_ids:
                print(f"  ⚠ Duplicate match for ID {em_id}, skipping: {entry['statsf1_name']!r}")
                continue

            matched_entry = translate_engine_entry(entry)
            matched_ids.add(em_id)
            total_matched += 1
            db_name = next(r["EngineModel"] for r in make_rows if r["ID"] == em_id)
            print(f"  ✓ [{stage}] {entry['statsf1_name']!r} → DB row '{db_name}'")

            cur.execute(
                "UPDATE EngineModels SET StatsF1Data = ? WHERE ID = ?",
                (json.dumps(matched_entry, ensure_ascii=False), em_id),
            )

        for r in make_rows:
            if r["ID"] not in matched_ids:
                print(f"  ✗ No statsf1 match for DB row: {r['EngineModel']!r}")
                sf1 = True
                total_unmatched += 1

        if (db) or (sf1 and db):
            raise RuntimeError(f"Unmatched entries for {make}, aborting to avoid partial updates.")
        con.commit()
        time.sleep(2)
        print()

    print(f"Done. Matched: {total_matched}, Unmatched: {total_unmatched}")
    con.close()


if __name__ == "__main__":
    main()
