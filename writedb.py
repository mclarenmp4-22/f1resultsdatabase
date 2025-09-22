import sqlite3
import urllib.request, urllib.parse, urllib.error
from bs4 import BeautifulSoup
import time
import re
import datetime
import json
import unicodedata

conn = sqlite3.connect('sessionresults.db')
cur = conn.cursor()
#cur.execute("PRAGMA foreign_keys = ON")




# 🚫 means comment this line out later
# 🚫✔️ means it is commented out

#Functions:
headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'} #Mimics the browser user agent to avoid being blocked by the website
#This is the open_url function that opens the url and returns the soup object
'''
def open_url(url):
    req = urllib.request.Request(url, headers=headers)
    html = urllib.request.urlopen(req).read()
    global soup
    soup = BeautifulSoup(html, 'html.parser')
    return soup
    '''
import socket
def open_url(url, retries=3):
    req = urllib.request.Request(url, headers=headers)
    for attempt in range(retries):
        try:
            html = urllib.request.urlopen(req, timeout=30).read()
            global soup
            soup = BeautifulSoup(html, 'html.parser')
            return soup
        except (urllib.error.URLError, socket.timeout, TimeoutError, Exception) as e:
            print(f"Attempt {attempt + 1} failed for URL {url}: {e}")
            time.sleep(5)  # Wait 5 seconds before retrying
    raise RuntimeError(f"Failed to open URL {url} after {retries} attempts.")
#Finds all the seasons

#fi = open('needtosee.html','a') #For debugging purposes, we write the soup to a file to see what it looks like 🚫

'''
def parse_points_system(html_content):
    """
    Parses the points system for Drivers and Constructors from the given HTML content.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Find all aligncenter sections
    aligncenter_sections = soup.find_all('div', class_='aligncenter')

    # Initialize variables for Drivers and Constructors
    drivers_scores = "All Scores"
    drivers_points_shared = False
    drivers_grand_prix_points = {}
    drivers_sprint_points = None  # Initialize sprint points for Drivers
    constructors_scores = "All Scores"
    constructors_topscoring = False
    constructors_grand_prix_points = {}
    constructors_sprint_points = None

    # Process each aligncenter section
    for index, section in enumerate(aligncenter_sections):
        if index == 0:  # Assume the first aligncenter is for Drivers
            drivers_scores_text = section.find(string=lambda t: "scores" in t.lower())
            drivers_scores = drivers_scores_text.strip() if drivers_scores_text else "All Scores"

            drivers_points_shared = "Points shared for shared drives" in section.get_text().lower()

            drivers_table = section.find('table', class_='bareme')
            if drivers_table:
                drivers_rows = drivers_table.find_all('tr')
                for i, cell in enumerate(drivers_rows[1].find_all('td')[1:], start=1):  # Skip "Position" column
                    position = i if i <= 5 else "Fastest Lap"
                    points = int(cell.get_text(strip=True)) if cell.get_text(strip=True).isdigit() else 0
                    drivers_grand_prix_points[position] = points

                if len(drivers_rows) > 2:  # Check if Sprint row exists for Drivers
                    drivers_sprint_points = {}
                    for i, cell in enumerate(drivers_rows[2].find_all('td')[1:], start=1):  # Skip "Points" and "Sprint"
                        drivers_sprint_points[i] = int(cell.get_text(strip=True)) if cell.get_text(strip=True).isdigit() else 0
            else:
                print("Drivers' table not found.")
        elif index == 1:  # Assume the second aligncenter is for Constructors
            constructors_scores_text = section.find(string=lambda t: "scores" in t.lower())
            constructors_scores = constructors_scores_text.strip() if constructors_scores_text else "All Scores"

            constructors_topscoring = "Point only for highest placed car." in section.get_text()

            constructors_table = section.find('table', class_='bareme')
            if constructors_table:
                constructors_rows = constructors_table.find_all('tr')
                for i, cell in enumerate(constructors_rows[1].find_all('td')[2:], start=1):  # Skip "Points" and "Grand Prix"
                    constructors_grand_prix_points[i] = int(cell.get_text(strip=True)) if cell.get_text(strip=True).isdigit() else 0

                if len(constructors_rows) > 2:  # Check if Sprint row exists
                    constructors_sprint_points = {}
                    for i, cell in enumerate(constructors_rows[2].find_all('td')[2:], start=1):  # Skip "Points" and "Sprint"
                        constructors_sprint_points[i] = int(cell.get_text(strip=True)) if cell.get_text(strip=True).isdigit() else 0
            else:
                print("Constructors' table not found.")

    # Final structure for Drivers
    points_system_drivers = {
        "scores": drivers_scores,
        "pointssharedforsharedcars": drivers_points_shared,
        "grandprix": drivers_grand_prix_points,
        "sprint": drivers_sprint_points  # Include parsed sprint points for Drivers
    }

    # Final structure for Constructors
    points_system_constructors = {
        "scores": constructors_scores,
        "topscoring": constructors_topscoring,
        "grandprix": constructors_grand_prix_points,
        "sprint": constructors_sprint_points
    }

    return points_system_drivers, points_system_constructors


def fetch_driver_info(driver_name):
    # Convert "George Russell" → "george-russell"
    slug = unicodedata.normalize('NFKD', driver_name).encode('ascii', 'ignore').decode('ascii').lower().replace(" ", "-")
    url = f"https://www.statsf1.com/en/{slug}.aspx"

    open_url(url)  # You provide this and it returns a BeautifulSoup object

    # --- Nationality ---
    nationality_tag = soup.find("a", id="ctl00_CPH_Main_HL_Pays")
    nationality = nationality_tag.text.strip() if nationality_tag else None

    # --- Birthdate ---
    birth_field = soup.find("div", class_="field", string=re.compile(r"Born the"))
    if not birth_field:
        # fallback: find all .field and search manually
        for div in soup.find_all("div", class_="field"):
            if "Born the" in div.text:
                birth_field = div
                break
    if not birth_field:
        print(f"Birthdate not found for {driver_name}")
    match = re.search(r"Born the ([0-9]{1,2} [a-zA-Z]+ [0-9]{4})", birth_field.text)
    if not match:
        raise Exception(f"Could not parse birthdate for {driver_name}, content: {birth_field.text}")

    birthdate_obj = datetime.datetime.strptime(match.group(1), "%d %B %Y")
    birthdate = birthdate_obj.strftime("%Y-%m-%d")

    return nationality, birthdate'''

def fetch_driver_info(driver_name):
    # Convert "George Russell" → "george-russell"
    slug = unicodedata.normalize('NFKD', driver_name).encode('ascii', 'ignore').decode('ascii').lower().replace(" ", "-")
    url = f"https://www.statsf1.com/en/{slug}.aspx"

    open_url(url)  # You provide this and it returns a BeautifulSoup object

    # --- Nationality ---
    nationality_tag = soup.find("a", id="ctl00_CPH_Main_HL_Pays")
    nationality = nationality_tag.text.strip() if nationality_tag else None

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

'''
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

        if not drivers_found and not constructors_found:
            # → Likely the Drivers table
            drivers_found = True
            if "scores" in full_text:
                drivers_info["scores"] = section.find(string=lambda t: "scores" in t.lower()).strip()
            if "points shared for shared drives" in full_text:
                drivers_info["pointssharedforsharedcars"] = True

            if len(rows) >= 2:
                for i, cell in enumerate(rows[1].find_all('td')[1:], start=1):
                    position = i if i <= 5 else "Fastest Lap"
                    value = cell.get_text(strip=True)
                    drivers_info["grandprix"][position] = int(value) if value.isdigit() else 0

            if len(rows) >= 3:
                drivers_info["sprint"] = {}
                for i, cell in enumerate(rows[2].find_all('td')[1:], start=1):
                    value = cell.get_text(strip=True)
                    drivers_info["sprint"][i] = int(value) if value.isdigit() else 0

        elif not constructors_found and drivers_found:
            # → Likely the Constructors table
            constructors_found = True
            if "scores" in full_text:
                constructors_info["scores"] = section.find(string=lambda t: "scores" in t.lower()).strip()
            if "point only for highest placed car" in full_text:
                constructors_info["topscoring"] = True

            if len(rows) >= 2:
                for i, cell in enumerate(rows[1].find_all('td')[2:], start=1):
                    value = cell.get_text(strip=True)
                    constructors_info["grandprix"][i] = int(value) if value.isdigit() else 0

            if len(rows) >= 3:
                constructors_info["sprint"] = {}
                for i, cell in enumerate(rows[2].find_all('td')[2:], start=1):
                    value = cell.get_text(strip=True)
                    constructors_info["sprint"][i] = int(value) if value.isdigit() else 0

    if not drivers_found:
        print("Drivers' points table not found.")
        return None, None

    if not constructors_found:
        print("Constructors' points table not found.")
        return drivers_info, {}

    return drivers_info, constructors_info



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

            if len(rows) >= 2:
                # Use header row to determine keys
                header_cells = [cell.get_text(strip=True) for cell in rows[0].find_all('td')[1:]]
                point_cells = rows[1].find_all('td')[1:]
                for header, cell in zip(header_cells, point_cells):
                    header_clean = re.sub(r'\s*\d+(st|nd|rd|th)?\.?$', '', header, flags=re.IGNORECASE)
                    value = cell.get_text(strip=True)
                    # Use header as key, or map to integer if it's a position
                    if header_clean.lower().startswith('fastest'):
                        key = "Fastest Lap"
                    else:
                        # Try to extract the position number
                        match = re.match(r'(\d+)', header)
                        key = int(match.group(1)) if match else header
                    drivers_info["grandprix"][key] = int(value) if value.isdigit() else 0

            if len(rows) >= 3:
                drivers_info["sprint"] = {}
                for i, cell in enumerate(rows[2].find_all('td')[1:], start=1):
                    value = cell.get_text(strip=True)
                    drivers_info["sprint"][i] = int(value) if value.isdigit() else 0

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

            if len(rows) >= 2:
                # Use header row to determine keys (skip only the first column for constructors)
                header_cells = [cell.get_text(strip=True) for cell in rows[0].find_all('td')[1:]]
                point_cells = rows[1].find_all('td')[1:]
                for header, cell in zip(header_cells, point_cells):
                    header_clean = re.sub(r'\s*\d+(st|nd|rd|th)?\.?$', '', header, flags=re.IGNORECASE)
                    value = cell.get_text(strip=True)
                    if header_clean.lower().startswith('fastest'):
                        key = "Fastest Lap"
                    else:
                        match = re.match(r'(\d+)', header)
                        key = int(match.group(1)) if match else header
                    constructors_info["grandprix"][key] = int(value) if value.isdigit() else 0

            if len(rows) >= 3:
                constructors_info["sprint"] = {}
                for i, cell in enumerate(rows[2].find_all('td')[2:], start=1):
                    value = cell.get_text(strip=True)
                    constructors_info["sprint"][i] = int(value) if value.isdigit() else 0

    # Fallback if nothing found
    if not drivers_found:
        print("Drivers' points table not found.")
        return None, None

    if not constructors_found:
        print("Constructors' points table not found.")
        return drivers_info, {}

    return drivers_info, constructors_info
'''


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
'''
def parse_regulations(html_content):
    """
    Parses the regulations for a given season from the provided HTML content.
    """
    soup = BeautifulSoup(html_content, 'html.parser')

    # Find the regulations section
    regulations_section = soup.find('div', id='ctl00_CPH_Main_P_Note1', class_='yearinfo')
    if not regulations_section:
        print("Regulations section not found.")
        return None  # Return None if regulations are not found

    # Extract the table within the regulations section
    regulations_table = regulations_section.find('table')
    if not regulations_table:
        print("Regulations table not found.")
        return None
    regulations_notes =  regulations_section.find('span', id = 'ctl00_CPH_Main_LB_Note1')
    # Parse the regulations table
    regulations = {}
    regulations_notes = regulations_section.find('span', id='ctl00_CPH_Main_LB_Note1')
    if regulations_notes:
        notes = extract_regulations_notes(regulations_notes)
        if notes:
            regulations['notes'] = notes
        else:
            regulations['notes'] = None    
    rows = regulations_table.find_all('tr')
    current_category = None
    for row in rows:
        if row.find('th'):  # If the row contains a category header
            current_category = row.get_text(strip=True)
            regulations[current_category] = {}
        else:  # If the row contains key-value pairs
            cells = row.find_all('td')
            if len(cells) == 2:
                key = cells[0].get_text(strip=True).rstrip(':')  # Remove trailing colon
                value = cells[1].get_text(strip=True)
                if current_category:
                    regulations[current_category][key] = value
                else:
                    regulations[key] = value

    return regulations

def format_name_from_caps(raw_name):
    parts = raw_name.split()
    formatted = []

    for part in parts:
        if part.isupper():
            formatted.append(part.lower().capitalize())
        else:
            formatted.append(part)

    return " ".join(formatted)
    '''
def format_name_from_caps(raw_name):
    parts = raw_name.split()
    formatted = []

    for part in parts:
        # Handle hyphenated parts
        subparts = part.split('-')
        formatted_subparts = []

        for subpart in subparts:
            if subpart.isupper():
                subpart = subpart.lower().capitalize()
            # Handle Mc prefix
            if subpart.startswith("Mc") and len(subpart) > 2:
                subpart = "Mc" + subpart[2].upper() + subpart[3:].lower()
            formatted_subparts.append(subpart)

        formatted.append('-'.join(formatted_subparts))

    return " ".join(formatted).replace("*", '')


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
        "circuit_name": someelements[3],
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
        circuit_match = re.search(r'^(.*?)\s+(Saturday|Sunday),', gpinfo_text)
        if circuit_match:
            race_info["track_name"] = circuit_match.group(1).strip()

        # Extract date
        date_match = re.search(r'(Saturday|Sunday),\s+\d{1,2}\s+\w+\s+\d{4}', gpinfo_text)
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

    return h * 3600 + m * 60 + s

def tts(t):
    parts = t.strip().split(":")
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    elif len(parts) == 2:
        minutes, seconds = parts
        return int(minutes) * 60 + float(seconds)
    elif len(parts) == 1:
        return float(parts[0]) if parts[0].replace('.', '', 1).isdigit() else None
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

def parse_statsf1_grid(soup, entrants, prefix=""):
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
                    if entrant['driver'] in format_name_from_caps(driver_name):
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
                            if entrant['driver'] in format_name_from_caps(driver_name):
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
                    if entrant['driver'] in format_name_from_caps(driver_name):
                        entrant[penalty_field] = penalty
                        entrant[penalty_reason_field] = reason
                        if 'Start from pit lane' in penalty:
                            entrant[grid_field] = None
                        break

def sort_links(links):
    def key(link):
        href = link['href']
        if href.endswith('engages.aspx'):
            return 0
        if href.endswith('/qualification.aspx'):  # pre-1996
            return 1
        if href.endswith('/qualifying/1'):
            return 2
        if href.endswith('/qualifying/2'):
            return 3
        if href.endswith('/qualifying/0'):  # depends on Q1 and Q2
            return 4
        if href.endswith('/qualifying'):    # modern style
            return 5
        if href.endswith('/grille.aspx'):
            return 6
        if href.endswith('/classement.aspx'):
            return 7
        if href.endswith('/meilleur-tour.aspx'):
            return 8
        if href.endswith('/sprint-qualifying'):
            return 9
        if href.endswith('/sprint.aspx?grille'):
            return 10
        if href.endswith('/sprint.aspx?en-tete'):
            return 11
        if href.endswith('/sprint.aspx?mt'):
            return 12
        if href.endswith('/sprint.aspx?tpt'):
            return 13
        if href.endswith('/sprint.aspx'):
            return 14
        if href.endswith('/practice/0'):
            return 15
        if href.endswith('/practice/1'):
            return 16
        if href.endswith('/practice/2'):
            return 17
        if href.endswith('/practice/3'):
            return 18
        if href.endswith('/practice/4'):
            return 19
        if href.endswith('/championnat.aspx'):
            return 99
        return 100  # fallback
    return sorted(links, key=key)



def parse_race_results(links):

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
                        if entrant['driver'] == format_name_from_caps(cells[1].get_text(strip=True)):
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
            '''
            # Parse the starting grid table
            grid_table = soup.find('table', id='ctl00_CPH_Main_TBL_Grille', class_='GPgrid')
            if grid_table:
                grid_rows = grid_table.find_all('div', class_='gridpitlanedriver')
                for row in grid_rows:
                    grid_position = row.get_text(strip=True).split('.')[0]
                    driver_name = row.get_text(strip=True).split('.')[1].split('<br>')[0].strip()
                    for entrant in entrants:
                        if entrant['driver'] in format_name_from_caps(driver_name):
                            entrant['starting_grid_position'] = int(grid_position)
                            break

            # Handle pit lane starts
            pit_lane_div = soup.find('div', class_='gridpitlane')
            if pit_lane_div:
                pit_lane_drivers = pit_lane_div.find_all('div', class_='gridpitlanedriver')
                for driver_div in pit_lane_drivers:
                    driver_name = driver_div.get_text(strip=True).split('.')[1].strip()
                    for entrant in entrants:
                        if entrant['driver'] in format_name_from_caps(driver_name):
                            entrant['starting_grid_position'] = None  # Use None for pit lane starts
                            break

            # Parse penalties and reasons
            penalty_table = soup.find('table', id='ctl00_CPH_Main_GV_PenaltyG', class_='datatable')
            if penalty_table:
                rows = penalty_table.find('tbody').find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) == 3:  # Ensure there are enough columns
                        driver_info = cells[0].get_text(strip=True)
                        penalty = cells[1].get_text(strip=True)
                        reason = cells[2].get_text(strip=True)
                        driver_name = driver_info.split('(')[0].strip()
                        for entrant in entrants:
                            if entrant['driver'] in format_name_from_caps(driver_name):
                                entrant['gridpenalty'] = penalty
                                entrant['gridpenalty_reason'] = reason
                                if 'Start from pit lane' in penalty:
                                    entrant['starting_grid_position'] = None  # Update for pit lane start
                                break '''
        elif link['href'].endswith('/sprint.aspx?grille'):
            open_url(f"https://www.statsf1.com{link['href']}")
            parse_statsf1_grid(soup, entrants, prefix="sprint")
            '''
            # Parse the starting grid table
            grid_table = soup.find('table', id='ctl00_CPH_Main_TBL_Grille', class_='GPgrid')
            if grid_table:
                grid_rows = grid_table.find_all('div', class_='gridpitlanedriver')
                for row in grid_rows:
                    grid_position = row.get_text(strip=True).split('.')[0]
                    driver_name = row.get_text(strip=True).split('.')[1].split('<br>')[0].strip()
                    for entrant in entrants:
                        if entrant['driver'] in format_name_from_caps(driver_name):
                            entrant['sprintstarting_grid_position'] = int(grid_position)
                            break

            # Handle pit lane starts
            pit_lane_div = soup.find('div', class_='gridpitlane')
            if pit_lane_div:
                pit_lane_drivers = pit_lane_div.find_all('div', class_='gridpitlanedriver')
                for driver_div in pit_lane_drivers:
                    driver_name = driver_div.get_text(strip=True).split('.')[1].strip()
                    for entrant in entrants:
                        if entrant['driver'] in format_name_from_caps(driver_name):
                            entrant['sprintstarting_grid_position'] = None  # Use None for pit lane starts
                            break

            # Parse penalties and reasons
            penalty_table = soup.find('table', id='ctl00_CPH_Main_GV_PenaltyG', class_='datatable')
            if penalty_table:
                rows = penalty_table.find('tbody').find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) == 3:  # Ensure there are enough columns
                        driver_info = cells[0].get_text(strip=True)
                        penalty = cells[1].get_text(strip=True)
                        reason = cells[2].get_text(strip=True)
                        driver_name = driver_info.split('(')[0].strip()
                        for entrant in entrants:
                            if entrant['driver'] in format_name_from_caps(driver_name):
                                entrant['sprintgridpenalty'] = penalty
                                entrant['sprintgridpenalty_reason'] = reason
                                if 'Start from pit lane' in penalty:
                                    entrant['sprintstarting_grid_position'] = None  # Update for pit lane start
                                break''' 
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
                        if entrant['driver'] == format_name_from_caps(cells[1].get_text(strip=True)):
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
                        if entrant['driver'] == format_name_from_caps(cells[1].get_text(strip=True)):
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
                table = soup.find('table', class_ = 'f1-table f1-table-with-data w-full')
                rows = table.find('tbody').find_all('tr')
                first_qualifying_time = None
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) == 5:
                        for entrant in entrants:
                            if entrant['number'] == int(cells[1].get_text(strip=True)):
                                x = entrants.index(entrant)
                                #We are going to cross the values now.
                                entrant['qualifying2position'] = int(cells[0].get_text(strip=True))
                                entrant['qualifying2time'] = cells[4].get_text(strip=True)
                                entrant['qualifying2gap'] = tts(first_qualifying_time) - tts(cells[4].get_text(strip=True)) if first_qualifying_time and tts(cells[4].get_text(strip=True)) else None
                                entrant['qualifying2timeinseconds'] = tts(cells[4].get_text(strip=True))
                                entrant['qualifying2laps'] = None
                                entrants[x] = entrant
                                first_qualifying_time = cells[4].get_text(strip=True)
                                break
                    elif len(cells) == 6:  
                        for entrant in entrants:
                            if entrant['number'] == int(cells[1].get_text(strip=True)):
                                x = entrants.index(entrant)
                                #We are going to cross the values now.
                                entrant['qualifying2position'] = int(cells[0].get_text(strip=True)) if cells[0].text.strip().isdigit() else None
                                entrant['qualifying2time'] = cells[4].get_text(strip=True)
                                entrant['qualifying2gap'] = tts(first_qualifying_time) - tts(cells[4].get_text(strip=True)) if first_qualifying_time and tts(cells[4].get_text(strip=True)) else None
                                entrant['qualifying2timeinseconds'] = tts(cells[4].get_text(strip=True))
                                entrant['qualifying2laps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                                entrants[x] = entrant
                                first_qualifying_time = cells[4].get_text(strip=True)
                                break 
        elif link['href'].endswith('/qualifying/1'):
            open_url(f"https://formula1.com{link['href']}")
            #print (link['href'])
            table = soup.find('table', class_ = 'f1-table f1-table-with-data w-full')
            #print (table)
            rows = table.find('tbody').find_all('tr')
            first_qualifying_time = None
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 5:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            #We are going to cross the values now.       
                            entrant['qualifying1position'] = int(cells[0].get_text(strip=True))
                            entrant['qualifying1time'] = cells[4].get_text(strip=True)
                            entrant['qualifying1gap'] = tts(first_qualifying_time) - tts(cells[4].get_text(strip=True)) if first_qualifying_time and tts(cells[4].get_text(strip=True)) else None
                            entrant['qualifying1timeinseconds'] = tts(cells[4].get_text(strip=True))
                            entrants[x] = entrant
                            first_qualifying_time = cells[4].get_text(strip=True)
                            break
                elif len(cells) == 6:  
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            #We are going to cross the values now.
                            entrant['qualifying1position'] = int(cells[0].get_text(strip=True))
                            entrant['qualifying1time'] = cells[4].get_text(strip=True)
                            entrant['qualifying1gap'] = tts(first_qualifying_time) - tts(cells[4].get_text(strip=True)) if first_qualifying_time and tts(cells[4].get_text(strip=True)) else None
                            entrant['qualifying1timeinseconds'] = tts(cells[4].get_text(strip=True))
                            entrant['qualifying1laps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrants[x] = entrant
                            first_qualifying_time = cells[4].get_text(strip=True)
                            break                          
        elif link['href'].endswith('/qualifying/0'):
                open_url(f"https://formula1.com{link['href']}")
                table = soup.find('table', class_ = 'f1-table f1-table-with-data w-full')
                rows = table.find('tbody').find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) == 6:  
                        for entrant in entrants:
                            if entrant['number'] == int(cells[1].get_text(strip=True)):
                                x = entrants.index(entrant)
                                entrant['qualifyinglaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                                entrants[x] = entrant
                                break 
        elif link['href'].endswith('/qualifying'):
            open_url(f"https://formula1.com{link['href']}")
            table = soup.find('table', class_ = 'f1-table f1-table-with-data w-full')
            rows = table.find('tbody').find_all('tr')
            previousq1timeforthepreviousdriver = None
            previousq2timeforthepreviousdriver = None
            previousq3timeforthepreviousdriver = None
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 6:  #1996-2003 qualifying format
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['qualifyinglaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrants[x] = entrant
                            break
                elif len(cells) == 8: #current qualifying format   
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['qualifying1time'] = cells[4].get_text(strip=True)
                            entrant['qualifying2time'] = cells[5].get_text(strip=True)
                            entrant['qualifying3time'] = cells[6].get_text(strip=True)
                            entrant['qualifying2gap'] = tts(cells[5].get_text(strip=True)) - previousq2timeforthepreviousdriver if previousq2timeforthepreviousdriver and tts(cells[5].get_text(strip = True)) else None
                            entrant['qualifying1gap'] = tts(cells[4].get_text(strip=True)) - previousq1timeforthepreviousdriver if previousq1timeforthepreviousdriver and tts(cells[4].get_text(strip = True)) else None
                            entrant['qualifying3gap'] = tts(cells[6].get_text(strip=True)) - previousq3timeforthepreviousdriver if previousq3timeforthepreviousdriver and tts(cells[6].get_text(strip = True)) else None
                            entrant['qualifying1timeinseconds'] = tts(cells[4].get_text(strip=True))
                            entrant['qualifying2timeinseconds'] = tts(cells[5].get_text(strip=True))
                            entrant['qualifying3timeinseconds'] = tts(cells[6].get_text(strip=True))
                            entrant['qualifyinglaps'] = int(cells[7].get_text(strip=True)) if cells[7].get_text(strip=True).isdigit() else None
                            previousq1timeforthepreviousdriver = tts(cells[4].get_text(strip=True))
                            previousq2timeforthepreviousdriver = tts(cells[5].get_text(strip=True))
                            previousq3timeforthepreviousdriver = tts(cells[6].get_text(strip=True))
                            entrants[x] = entrant
                            break
        elif link['href'].endswith('/sprint-qualifying'):
            open_url(f"https://formula1.com{link['href']}")
            table = soup.find('table', class_ = 'f1-table f1-table-with-data w-full')
            rows = table.find('tbody').find_all('tr')
            previousq1timeforthepreviousdriver = None
            previousq2timeforthepreviousdriver = None
            previousq3timeforthepreviousdriver = None
            previoustimeforthepreviousdriver = None             
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 8: #current sprint-qualifying format   
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['sprint_qualifyingposition'] = int(cells[0].get_text(strip=True)) if cells[0].get_text(strip=True).isdigit() else None
                            entrant['sprint_qualifying1time'] = cells[4].get_text(strip=True)
                            entrant['sprint_qualifying2time'] = cells[5].get_text(strip=True)
                            entrant['sprint_qualifying3time'] = cells[6].get_text(strip=True)
                            entrant['sprint_qualifying1gap'] = tts(cells[4].get_text(strip=True)) - previousq1timeforthepreviousdriver if previousq1timeforthepreviousdriver and tts(cells[4].get_text(strip = True)) else None
                            entrant['sprint_qualifying2gap'] = tts(cells[5].get_text(strip=True)) - previousq2timeforthepreviousdriver if previousq2timeforthepreviousdriver and tts(cells[5].get_text(strip = True)) else None
                            entrant['sprint_qualifying3gap'] = tts(cells[6].get_text(strip=True)) - previousq3timeforthepreviousdriver if previousq3timeforthepreviousdriver and tts(cells[6].get_text(strip = True)) else None
                            entrant['sprint_qualifyinggap'] = tts(cells[7].get_text(strip=True)) - previoustimeforthepreviousdriver if previoustimeforthepreviousdriver and tts(cells[7].get_text(strip=True)) else None
                            entrant['sprint_qualifying1timeinseconds'] = tts(cells[4].get_text(strip=True))
                            entrant['sprint_qualifying2timeinseconds'] = tts(cells[5].get_text(strip=True))
                            entrant['sprint_qualifying3timeinseconds'] = tts(cells[6].get_text(strip=True))
                            entrant['sprint_qualifyinglaps'] = int(cells[7].get_text(strip=True)) if cells[7].get_text(strip=True).isdigit() else None
                            if entrant['sprint_qualifying3time'] is not None:
                                entrant['sprint_qualifyingtime'] = entrant['sprint_qualifying3time']
                            elif entrant['sprint_qualifying2time'] is not None:
                                entrant['sprint_qualifyingtime'] = entrant['sprint_qualifying2time']
                            elif entrant['sprint_qualifying1time'] is not None:
                                entrant['sprint_qualifyingtime'] = entrant['sprint_qualifying1time']
                            entrant['sprint_qualifyingtimeinseconds'] = tts(entrant['sprint_qualifyingtime']) if entrant['sprint_qualifyingtime'] is not None else None    
                            previousq1timeforthepreviousdriver = tts(cells[4].get_text(strip=True))
                            previousq2timeforthepreviousdriver = tts(cells[5].get_text(strip=True))
                            previousq3timeforthepreviousdriver = tts(cells[6].get_text(strip=True))
                            previoustimeforthepreviousdriver = tts(entrant['sprint_qualifyingtime']) if entrant['sprint_qualifyingtime'] is not None else None
                            entrants[x] = entrant
                            break                        
        elif link['href'].endswith('/practice/0'):
            open_url(f"https://formula1.com{link['href']}")
            table = soup.find('table', class_ = 'f1-table f1-table-with-data w-full')
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 6:  
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['warmupposition'] = int(cells[0].get_text(strip=True))
                            # Set gap to cells[4] if it starts with '+'
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else cells[5].get_text(strip=True)
                            entrant['warmuptime'] = cells[4].get_text(strip=True)
                            entrant['warmupgap'] = gap
                            entrant['warmuptimeinseconds'] = tts(cells[4].get_text(strip=True))
                            # laps is now cells[5]
                            entrant['warmuplaps'] = int(cells[5].get_text(strip=True))                            
                            entrants[x] = entrant
                            break
                elif len(cells) == 7:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['warmupposition'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else cells[5].get_text(strip=True)
                            entrant['warmuptime'] = cells[4].get_text(strip=True)
                            entrant['warmupgap'] = gap
                            # laps is now cells[5]
                            entrant['warmuplaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrant['warmuptimeinseconds'] = tts(cells[4].get_text(strip=True))
                            entrants[x] = entrant
                            break  
        elif link['href'].endswith('/practice/1'):
            open_url(f"https://formula1.com{link['href']}")
            table = soup.find('table', class_ = 'f1-table f1-table-with-data w-full')
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 6:  
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice1position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else cells[5].get_text(strip=True)
                            entrant['practice1time'] = cells[4].get_text(strip=True)
                            entrant['practice1gap'] = gap
                            entrant['practice1timeinseconds'] = tts(cells[4].get_text(strip=True))
                            # laps is now cells[5]
                            entrant['practice1laps'] = int(cells[5].get_text(strip=True))
                            entrants[x] = entrant
                            break
                elif len(cells) == 7:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice1position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else cells[5].get_text(strip=True)
                            entrant['practice1time'] = cells[4].get_text(strip=True)
                            entrant['practice1gap'] = gap
                            entrant['practice1laps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrant['practice1timeinseconds'] = tts(cells[4].get_text(strip=True))
                            entrants[x] = entrant
                            break                    

        elif link['href'].endswith('/practice/2'):
            open_url(f"https://formula1.com{link['href']}")
            table = soup.find('table', class_ = 'f1-table f1-table-with-data w-full')
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 6:  
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice2position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else cells[5].get_text(strip=True)
                            entrant['practice2time'] = cells[4].get_text(strip=True)
                            entrant['practice2gap'] = gap
                            entrant['practice2timeinseconds'] = tts(cells[4].get_text(strip=True))
                            # laps is now cells[5]
                            entrant['practice2laps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrants[x] = entrant
                            break
                elif len(cells) == 7:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice2position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else cells[5].get_text(strip=True)
                            entrant['practice2time'] = cells[4].get_text(strip=True)
                            entrant['practice2gap'] = gap
                            entrant['practice2laps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrant['practice2timeinseconds'] = tts(cells[4].get_text(strip=True))
                            entrants[x] = entrant
                            break  
        elif link['href'].endswith('/practice/3'):
            open_url(f"https://formula1.com{link['href']}")
            table = soup.find('table', class_ = 'f1-table f1-table-with-data w-full')
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 6:  
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice3position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else cells[5].get_text(strip=True)
                            entrant['practice3time'] = cells[4].get_text(strip=True)
                            entrant['practice3gap'] = gap
                            entrant['practice3timeinseconds'] = tts(cells[4].get_text(strip=True))
                            # laps is now cells[5]
                            entrant['practice3laps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrants[x] = entrant
                            break
                elif len(cells) == 7:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice3position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else cells[5].get_text(strip=True)
                            entrant['practice3time'] = cells[4].get_text(strip=True)
                            entrant['practice3gap'] = gap
                            entrant['practice3laps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrant['practice3timeinseconds'] = tts(cells[4].get_text(strip=True))
                            entrants[x] = entrant
                            break  
        elif link['href'].endswith('/practice/4'):
            table = soup.find('table', class_ = 'f1-table f1-table-with-data w-full')
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                if len(cells) == 6:  
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice4position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else cells[5].get_text(strip=True)
                            entrant['practice4time'] = cells[4].get_text(strip=True)
                            entrant['practice4gap'] = gap
                            entrant['practice4timeinseconds'] = tts(cells[4].get_text(strip=True))
                            # laps is now cells[5]
                            entrant['practice4laps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrants[x] = entrant
                            break
                elif len(cells) == 7:
                    for entrant in entrants:
                        if entrant['number'] == int(cells[1].get_text(strip=True)):
                            x = entrants.index(entrant)
                            entrant['practice4position'] = int(cells[0].get_text(strip=True))
                            gap = cells[4].get_text(strip=True) if cells[4].get_text(strip=True).startswith('+') else cells[5].get_text(strip=True)
                            entrant['practice4time'] = cells[4].get_text(strip=True)
                            entrant['practice4gap'] = gap
                            entrant['practice4laps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrant['practice4timeinseconds'] = tts(cells[4].get_text(strip=True))
                            entrants[x] = entrant
                            break  
        elif link['href'].endswith('/sprint.aspx'):
            sprintweekend = True 
            open_url(f"https://www.statsf1.com{link['href']}")
            sprintpenalties = parse_penalties(soup, is_sprint=True)
            table = soup.find('table', class_ = 'datatable')
            #You need to do shared cars and avoid exceptions when the sprint position is "ab" or something
            rows = table.find('tbody').find_all('tr')
            for row in rows:
                cells = row.find_all('td')
                for entrant in entrants:
                    if  entrant['driver'].lower() in cells[1].get_text(strip=True).lower():
                        x = entrants.index(entrant)
                        # Process the main car entry
                        if cells[0].get_text(strip=True) in ['ab', 'nc', 'np', 'nq', 'npq', 'dsq', 'exc', 'f', 'tf', 't']:
                            entrant['sprintposition'] = None
                            entrant['sprintlaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                            entrant['sprinttime'] = cells[5].get_text(strip=True) + f" ({abbreviations[cells[0].get_text(strip=True)]})"
                            entrant['sprintpoints'] = 0
                        else:
                            entrant['sprintposition'] = int(cells[0].get_text(strip=True))
                            entrant['sprintlaps'] = int(cells[4].get_text(strip=True))
                            entrant['sprinttime'] = cells[5].get_text(strip=True).split('(')[0].replace("'", ":") if '(' in cells[5].get_text(strip=True) else cells[5].get_text(strip=True)
                            entrant['sprinttimeinseconds'] = tts(entrant['sprinttime'])
                            entrant['sprintgap'] = cells[5].get_text(strip=True).split('(')[1].replace(')', '') if '(' in cells[5].get_text(strip=True) and cells[5].get_text(strip=True).split('(')[1].replace(')', '' ).strip().endswith('s')  else None
                            entrant['sprintgapinseconds'] = parse_race_time(entrant['sprintgap'].replace("+", "")) if entrant['sprintgap'] else None
                            entrant['sprintpoints'] = float(cells[7].get_text(strip=True)) if cells[7].get_text(strip=True).replace('.', '', 1).isdigit() else None
                        # Parse penalties during and after the race
                        ''''
                        penalties = []
                        
                        # Penalties during the race
                        race_penalty_table = soup.find('table', id='ctl00_CPH_Main_GV_PenaltyP', class_='datatable')
                        if race_penalty_table:
                            rows = race_penalty_table.find('tbody').find_all('tr')
                            for row in rows:
                                cells = row.find_all('td')
                                if len(cells) == 3:  # Ensure there are enough columns
                                    penalty = {
                                        "driver": cells[0].get_text(strip=True),
                                        "penalty": cells[1].get_text(strip=True),
                                        "reason": cells[2].get_text(strip=True),
                                        "type": "during_race"
                                    }
                                    penalties.append(penalty)
                        # Penalties after the race
                        after_race_penalty_table = soup.find('table', id='ctl00_CPH_Main_GV_PenaltyA', class_='datatable')
                        if after_race_penalty_table:
                            rows = after_race_penalty_table.find('tbody').find_all('tr')
                            for row in rows:
                                cells = row.find_all('td')
                                if len(cells) == 4:  # Ensure there are enough columns
                                    penalty = {
                                        "driver": format_name_from_caps(cells[0].get_text(strip=True)),
                                        "penalty": cells[1].get_text(strip=True),
                                        "reason": cells[2].get_text(strip=True),
                                        "lost_position": int(cells[3].get_text(strip=True)) if cells[3].get_text(strip=True).isdigit() else None,
                                        "type": "after_race"
                                    }
                                    penalties.append(penalty)
                        # Update entrants with penalties
                        for penalty in penalties:
                            for entrant in entrants:
                                if entrant['driver'] in penalty['driver']:
                                    entrant['sprintpenalty'] = penalty['penalty']
                                    entrant['sprintpenalty_reason'] = penalty['reason']
                                    entrant['sprintpenalty_type'] = penalty['type']
                                    if 'lost_position' in penalty:
                                        entrant['sprintlost_position'] = penalty['lost_position']
                                    break
                                '''
                        entrants[x] = entrant
                        break                                                                                                         
        elif link['href'].endswith('/classement.aspx'):
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
                                if entrant['driver'].lower() in cells[2].get_text(strip=True).lower() and entrant['number'] == main_car['number']:
                                    # Create a new entry for the shared car
                                    '''
                                    entrant = {
                                        "raceposition": main_car["raceposition"],
                                        "number": main_car["number"],
                                        "chassis": main_car["chassis"],
                                        "engine": main_car["engine"],
                                        "team": main_car["team"],
                                        "chassis_model": main_car.get("chassis_model", None),
                                        "engine_model": main_car.get("engine_model", None),
                                        "tyre": main_car.get("tyre", None),
                                        "driver": format_name_from_caps(cells[2].get_text(strip=True)),
                                        "racelaps": int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None,
                                        "racetime": cells[6].get_text(strip=True),
                                        "racepoints": float(cells[7].get_text(strip=True)) if cells[7].get_text(strip=True).replace('.', '', 1).isdigit() else None
                                    }
                                    '''
                                    entrant['raceposition'] = main_car["raceposition"]
                                    entrant['racelaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                                    entrant['racetime'] = cells[6].get_text(strip=True)
                                    entrant['racepoints'] = float(cells[7].get_text(strip=True)) if cells[7].get_text(strip=True).replace('.', '', 1).isdigit() else None
                                    if cells[0].get_text(strip=True) in ['ab', 'nc', 'np', 'nq', 'npq', 'dsq', 'exc', 'f', 'tf', 't']:
                                        entrant['raceposition'] = None
                                        entrant['racelaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                                        entrant['racetime'] = cells[6].get_text(strip=True) + f" ({abbreviations[cells[0].get_text(strip=True)]})"
                                        entrant['racepoints'] = 0                            
                                    if entrant["racetime"] is not None:
                                        entrant["racetime"] = entrant["racetime"].split('(')[0] if '(' in entrant["racetime"] else entrant["racetime"]
                                        entrant['racetimeinseconds'] = parse_race_time(entrant['racetime'])
                                        entrant['racegap'] = cells[6].get_text(strip=True).split('(')[1].replace(')', '') if '(' in cells[6].get_text(strip=True) and cells[6].get_text(strip=True).split('(')[1].replace(')', '').strip().endswith('s')  else None
                                        entrant['racegapinseconds'] = parse_race_time(entrant['racegap'].replace("+", "")) if entrant['racegap'] else None
                                    # Append the shared car entry to the race results
                                    #print ("Main car: ", main_car)
                                    #print ("Shared car: ",  entrant)
                                    #entrants[x] = entrant
                                    break
                                elif entrant['driver'].lower() in cells[2].get_text(strip=True).lower() and entrant['number'] != main_car['number']:
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
                                        shared_car['raceposition'] = None
                                        shared_car['racelaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                                        shared_car['racetime'] = cells[6].get_text(strip=True) + f" ({abbreviations[cells[0].get_text(strip=True)]})"
                                        shared_car['racepoints'] = None
                                    if shared_car["racetime"] is not None:
                                        shared_car["racetime"] = shared_car["racetime"].split('(')[0] if '(' in shared_car["racetime"] else shared_car["racetime"]
                                        shared_car['racetimeinseconds'] = parse_race_time(shared_car['racetime'])
                                        shared_car['racegap'] = cells[6].get_text(strip=True).split('(')[1].replace(')', '') if '(' in cells[6].get_text(strip=True) and cells[6].get_text(strip=True).split('(')[1].replace(')', '').strip().endswith('s')  else None
                                        shared_car['racegapinseconds'] = parse_race_time(shared_car['racegap'].replace("+", "")) if shared_car['racegap'] else None
                                    entrants.append(shared_car)
                                    break


                    else:  # Main car entry
                        for entrant in entrants:
                            if entrant['number'] == int(cells[1].get_text(strip=True)) and entrant['driver'].lower() in cells[2].get_text(strip=True).lower():
                                # Process the main car entry
                                if cells[0].get_text(strip=True) in ['ab', 'nc', 'np', 'nq', 'npq', 'dsq', 'exc', 'f', 'tf', 't']:
                                    entrant['raceposition'] = None
                                    entrant['racelaps'] = int(cells[5].get_text(strip=True)) if cells[5].get_text(strip=True).isdigit() else None
                                    entrant['racetime'] = cells[6].get_text(strip=True) + f" ({abbreviations[cells[0].get_text(strip=True)]})"
                                    entrant['racepoints'] = 0
                                else:
                                    entrant['raceposition'] = int(cells[0].get_text(strip=True))
                                    entrant['racelaps'] = int(cells[5].get_text(strip=True))
                                    entrant['racetime'] = cells[6].get_text(strip=True).split('(')[0] if '(' in cells[6].get_text(strip=True) else cells[6].get_text(strip=True)
                                    entrant['racetimeinseconds'] = parse_race_time(entrant['racetime'])
                                    entrant['racegap'] = cells[6].get_text(strip=True).split('(')[1].replace(')', '') if '(' in cells[6].get_text(strip=True) and cells[6].get_text(strip=True).split('(')[1].replace(')', '').strip().endswith('s')  else None
                                    entrant['racegapinseconds'] = parse_race_time(entrant['racegap'].replace("+", "")) if entrant['racegap'] else None
                                    entrant['racepoints'] = float(cells[7].get_text(strip=True)) if cells[7].get_text(strip=True).replace('.', '', 1).isdigit() else None
                                '''    
                                # Parse penalties during and after the race
                                penalties = []
                                #print(entrant)
                                # Penalties during the race
                                race_penalty_table = soup.find('table', id='ctl00_CPH_Main_GV_PenaltyP', class_='datatable')
                                if race_penalty_table:
                                    rows = race_penalty_table.find('tbody').find_all('tr')
                                    for row in rows:
                                        cells = row.find_all('td')
                                        if len(cells) == 3:  # Ensure there are enough columns
                                            penalty = {
                                                "driver": cells[0].get_text(strip=True),
                                                "penalty": cells[1].get_text(strip=True),
                                                "reason": cells[2].get_text(strip=True),
                                                "type": "during_race"
                                            }
                                            penalties.append(penalty)

                                # Penalties after the race
                                after_race_penalty_table = soup.find('table', id='ctl00_CPH_Main_GV_PenaltyA', class_='datatable')
                                if after_race_penalty_table:
                                    rows = after_race_penalty_table.find('tbody').find_all('tr')
                                    for row in rows:
                                        cells = row.find_all('td')
                                        if len(cells) == 4:  # Ensure there are enough columns
                                            penalty = {
                                                "driver": format_name_from_caps(cells[0].get_text(strip=True)),
                                                "penalty": cells[1].get_text(strip=True),
                                                "reason": cells[2].get_text(strip=True),
                                                "lost_position": int(cells[3].get_text(strip=True)) if cells[3].get_text(strip=True).isdigit() else None,
                                                "type": "after_race"
                                            }
                                            penalties.append(penalty)

                                # Update entrants with penalties
                                for penalty in penalties:
                                    for entrant in entrants:
                                        if entrant['driver'] in penalty['driver']:
                                            entrant['penalty'] = penalty['penalty']
                                            entrant['penalty_reason'] = penalty['reason']
                                            entrant['penalty_type'] = penalty['type']
                                            if 'lost_position' in penalty:
                                                entrant['lost_position'] = penalty['lost_position']

                                            break
                                        '''
                                #print (entrant)  
                                '''
                                if entrant['driver'] == 'Tony Rolt':
                                    print ("So IT IS PICKING UP THE WRONG DRIVER")  
                                elif entrant['driver'] == 'Peter Walker':
                                    print ("So IT IS PICKING UP THE RIGHT DRIVER")    
                                #check if "peter walker" is in the row. do it for me:
                                if 'peter walker' in cells[2].get_text(strip=True).lower():
                                    print ("BUT THE RIGHT DRIVER EXISTS")
                                    print (entrant['driver'])  
                                    print (row)  
                                '''
                                #entrants[x] = entrant
                                #print (entrants)
                                #print (race_results)
                                main_car = entrant  # Update the main car reference                                   
                                break  # Exit the loop once the entrant is found
                else:
                    raise ValueError(f"Unexpected number of cells in row: {len(cells)}. Expected at least 8 cells.")
    '''                        
    for penalty in penalties:
        for entrant in entrants:
            if entrant['driver'].lower() == penalty['driver'].lower():
                if penalty['is_sprint']:
                    entrant[str(penalties.index(penalty)) + 'sprintpenalty'] = penalty['penalty']
                    entrant[str(penalties.index(penalty)) + 'sprintpenalty_reason'] = penalty['reason']
                    entrant[str(penalties.index(penalty)) + 'sprintpenalty_type'] = penalty['type']
                    if 'lost_position' in penalty:
                        entrant[str(penalties.index(penalty)) + 'sprintlost_position'] = penalty['lost_position']
                else:
                    entrant[str(penalties.index(penalty)) + 'penalty'] = penalty['penalty']
                    entrant[str(penalties.index(penalty)) + 'penalty_reason'] = penalty['reason']
                    entrant[str(penalties.index(penalty)) + 'penalty_type'] = penalty['type']
                    if 'lost_position' in penalty:
                        entrant[str(penalties.index(penalty)) + 'lost_position'] = penalty['lost_position']
                break
    '''
    for penalty in penalties:
        for entrant in entrants:
            if entrant['driver'].lower() == penalty['driver'].lower():
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
                        
    return entrants.copy()


def parse_pit_stop_summary (pit_table, entrants):
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
    return pitstops.copy()


def parse_lap_by_lap(linkhref, entrants, dataid=None, dataidrace=None):
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
                    full = entrant["driver"].lower()
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
        print("Lap-by-lap data not found.")

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
                                            
                    
    return output

'''
red = parse_race_results ([{'href': "/en/2023/autriche/engages.aspx"}, {'href': "/en/2023/autriche/sprint.aspx"}, {'href': "/en/2023/autriche/qualification.aspx"}, {'href': "/en/2023/autriche/grille.aspx"}, {'href': "/en/2023/autriche/classement.aspx"}, {'href': "/en/2023/autriche/en-tete.aspx"}, {'href': "/en/2023/autriche/meilleur-tour.aspx"}, {'href': "/en/2023/autriche/tour-par-tour.aspx"}, {'href': "/en/2023/autriche/championnat.aspx"}, {'href': "/en/2023/autriche/sprint.aspx?grille"}, {'href': "/en/2023/autriche/sprint.aspx?en-tete"}, {'href': "/en/2023/autriche/sprint.aspx?mt"}, {'href': "/en/2023/autriche/sprint.aspx?tpt"}, {'href': "/en/results/2023/races/1213/austria/race-result"}, {'href': "/en/results/2023/races/1213/austria/fastest-laps"}, {'href': "/en/results/2023/races/1213/austria/pit-stop-summary"}, {'href': "/en/results/2023/races/1213/austria/starting-grid"}, {'href': "/en/results/2023/races/1213/austria/qualifying"}, {'href': "/en/results/2023/races/1213/austria/sprint-results"}, {'href': "/en/results/2023/races/1213/austria/sprint-grid"}, {'href': "/en/results/2023/races/1213/austria/sprint-qualifying"}, {'href': "/en/results/2023/races/1213/austria/practice/1"}])
blue = parse_lap_by_lap("https://www.statsf1.com/en/2023/autriche/tour-par-tour.aspx", red, 76, 1140)
green = parse_lap_by_lap("https://www.statsf1.com/en/2023/autriche/sprint.aspx?tpt", red, None, None)
file = open('test.json', 'w', encoding='utf-8')
import json
file.write(json.dumps((red, blue, green), indent=4, ensure_ascii=False))
'''

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


'''
def parse_in_season_progress (racelink):
    open_url(racelink)
    p = soup.find_all ('table', class_ = 'datatable')
    for x in p:
        rows = x.find('tbody').find_all('tr')
        vx = []
        driversprogress = []
        constructorsprogress = []
        for row in rows:
            cells = row.find_all('td')
            if len(cells) == 3: 
                if p.index(x) == 0:
                    drivers_championship_progress = {
                        "positionatthispoint": int(cells[0].get_text(strip=True).replace('.', '')) if cells[0].get_text(strip=True).replace('.', '').isdigit() else driversprogress[-1]["positionatthispoint"],
                        "driver": format_name_from_caps(cells[1].get_text(strip=True)),
                        "pointsatthispoint": float(cells[2].get_text(strip=True))
                    }
                    driversprogress.append(drivers_championship_progress)
                elif p.index(x) == 1:
                    links = cells[1].find_all('a')
                    constructors_championship_progress = {
                        "positionatthispoint" : int(cells[0].get_text(strip=True).replace('.', '')) if cells[0].get_text(strip=True).replace('.', '').isdigit() else constructorsprogress[-1]["positionatthispoint"],
                        "constructor": links[0].get_text(strip=True) if len(links) > 0 else "",
                        "engine": links[1].get_text(strip=True) if len(links) > 1 else (links[0].get_text(strip=True) if len(links) > 0 else ""),
                        "pointsatthispoint": float(cells[2].get_text(strip=True))
                    }
                    constructorsprogress.append(constructors_championship_progress) 
    vx.append (driversprogress)
    vx.append (constructorsprogress)                
    return vx.copy()   
                               

def parse_championship_results (year, drivermap):
    open_url(f"https://www.statsf1.com/en/{year}.aspx")
    # Drivers: ctl00_CPH_Main_TBL_CHP_Drv
    # Constructors: ctl00_CPH_Main_TBL_CHP_Cst
    vccfjk = []    
    driverschampionship = []
    drivers_table = soup.find('table', id = 'ctl00_CPH_Main_TBL_CHP_Drv')
    driversrows = drivers_table.find_all('tr')
    headercells = driversrows[0].find_all('td')
    for rews in driversrows[1:]:
        cells = rews.find_all('td')
        driverindo = {
            'position': int(cells[0].text.strip().replace('.', '')) if cells[0].get_text(strip=True).replace('.', '').isdigit() else driverschampionship[-1]["position"],
            'driver': drivermap[cells[1].text.strip()]
        }
        if headercells[-1].text.strip() == 'Out of' and headercells[-2].text.strip() == 'Pts':
            driverindo['points'] = float(cells[-2].text.strip())
            driverindo['outof'] = float(cells[-1].text.strip()) if cells[-1].text.strip() != '' else driverindo['points']
            seasonprogress = {}              
            for race in cells[2:-2]:
                i = cells[2:-2].index(race)
                print (i)
                print (race)
                therace = headercells[2:-2][i].find('span', class_ = 'codegp')['title']
                print(therace)
                racepoints = race.text.strip()
                if racepoints == "-":
                    racepoints = 0
                elif racepoints == "":
                    racepoints = None
                else:
                    racepoints = int(racepoints)        
                seasonprogress[therace] = racepoints
        elif headercells[-1].text.strip() == 'Pts':
            driverindo['points'] = float(cells[-1].text.strip())
            driverindo['outof'] = None
            for race in cells[2:-1]:
                i = cells[2:-1].index(race)
                therace = headercells[2:-1][i].find('span', class_ = 'codegp')['title']
                racepoints = race.text.strip()
                if racepoints == "-":
                    racepoints = 0
                elif racepoints == "":
                    racepoints = None
                else:
                    racepoints = int(racepoints)        
                seasonprogress[therace] = racepoints
        driverindo['seasonprogress'] = seasonprogress
        driverschampionship.append(driverindo)  
    vccfjk.append(driverschampionship)          
    constructors_table = soup.find('table', id = 'ctl00_CPH_Main_TBL_CHP_Cst')
    if constructors_table:
        constructorschampionship = []
        constructorsrows = constructors_table.find_all('tr')
        headercells = constructorsrows[0].find_all('td')
        for rews in constructorsrows[1:]:
            cells = rews.find_all('td')
            constructorindo = {
                'position': int(cells[0].text.strip().replace('.', '')) if cells[0].get_text(strip=True).replace('.', '').isdigit() else constructorschampionship[-1]["position"],
                'constructor': cells[1].find_all('a')[0].text.strip(),
                'engine': cells[1].find_all('a')[1].text.strip() if len(cells[1].find_all('a')) == 2 else cells[1].find_all('a')[0].text.strip()
            }
            if headercells[-1].text.strip() == 'Out of' and headercells[-2].text.strip() == 'Pts':
                constructorindo['points'] = float(cells[-2].text.strip())
                constructorindo['outof'] = float(cells[-1].text.strip()) if cells[-1].text.strip() != '' else constructorindo['points']
                seasonprogress = {}              
                for race in cells[2:-2]:
                    i = cells[2:-2].index(race)
                    therace = headercells[2:-2][i].find('span', class_ = 'codegp')['title']
                    racepoints = race.text.strip()
                    if racepoints == "-":
                        racepoints = 0
                    elif racepoints == "":
                        racepoints = None
                    else:
                        racepoints = int(racepoints)        
                    seasonprogress[therace] = racepoints
            elif headercells[-1].text.strip() == 'Pts':
                constructorindo['points'] = float(cells[-1].text.strip())
                constructorindo['outof'] = None
                for race in cells[2:-1]:
                    i = cells[2:-1].index(race)
                    therace = headercells[2:-1][i].find('span', class_ = 'codegp')['title']
                    racepoints = race.text.strip()
                    if racepoints == "-":
                        racepoints = 0
                    elif racepoints == "":
                        racepoints = None
                    else:
                        racepoints = int(racepoints)        
                    seasonprogress[therace] = racepoints 
            constructorindo['seasonprogress'] = seasonprogress
            constructorschampionship.append (constructorindo)  
    vccfjk.append(constructorschampionship)                 
    return vccfjk.copy()'''


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
                    racepoints = (0, None)
                elif racepoints == "":
                    racepoints = (None, None) 
                elif racepoints.startswith('(') and racepoints.endswith (')'):
                    racepoints = (float(racepoints.replace('(', '').replace(')', '').replace(',', '.')), True)       
                else:
                    racepoints = (float(racepoints.replace(',', '.')), False)                 
                seasonprogress[therace] = racepoints
        elif headercells[-1].text.strip() == 'Pts':
            driverindo['points'] = float(cells[-1].text.strip())
            driverindo['outof'] = None
            seasonprogress = {}
            for i, race in enumerate(cells[2:-1]):
                therace = headercells[1:-1][i].find('span', class_ = ['codegp', 'codesp'])['title']
                racepoints = race.text.strip()
                if racepoints == "-":
                    racepoints = (0, None)
                elif racepoints == "":
                    racepoints =( None, None)
                elif racepoints.startswith('(') and racepoints.endswith (')'):
                    racepoints = (float(racepoints.replace('(', '').replace(')', '').replace(',', '.')), True)    
                else:
                    racepoints =(float(racepoints.replace(',', '.')), False)                 
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
                        racepoints = (0, None)
                    elif racepoints == "":
                        racepoints =(None, None)
                    elif racepoints.startswith('(') and racepoints.endswith (')'):
                        racepoints = (float(racepoints.replace('(', '').replace(')', '')), True)    
                    else:
                        racepoints =(float(racepoints.replace(',', '.')), False)                
                    seasonprogress[therace] = racepoints
            elif headercells[-1].text.strip() == 'Pts':
                constructorindo['points'] = float(cells[-1].text.strip())
                constructorindo['outof'] = None
                seasonprogress = {}
                for i, race in enumerate(cells[2:-1]):
                    therace = headercells[1:-1][i].find('span', class_ = ['codegp', 'codesp'])['title']
                    racepoints = race.text.strip()
                    if racepoints == "-":
                        racepoints = (0, None)
                    elif racepoints == "":
                        racepoints =( None, None)
                    elif racepoints.startswith('(') and racepoints.endswith (')'):
                        racepoints = (float(racepoints.replace('(', '').replace(')', '').replace(',', '.')), True)    
                    else:
                        racepoints =(float(racepoints.replace(',', '.')), False)                              
                    seasonprogress[therace] = racepoints   
            constructorindo['racebyrace'] = seasonprogress
            constructorschampionship.append(constructorindo)
        output.append(constructorschampionship) 
    else:
        constructorschampionship = []
        output.append(constructorschampionship)       
    return output.copy()

def parsenotes (links):
    notes = {}
    for link in links:
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
'''
xedde = parse_championship_results(1980, drivermap = {'A. JONES': 'Alan Jones', 'N. PIQUET': 'Nelson Piquet', 'C. REUTEMANN': 'Carlos Reutemann', 'J. LAFFITE': 'Jacques Laffite', 'D. PIRONI': 'Didier Pironi', 'R. ARNOUX': 'René Arnoux', 'E. DE ANGELIS': 'Elio de Angelis', 'J. JABOUILLE': 'Jean-Pierre Jabouille', 'R. PATRESE': 'Riccardo Patrese', 'K. ROSBERG': 'Keke Rosberg', 'J. WATSON': 'John Watson', 'D. DALY': 'Derek Daly', 'J. JARIER': 'Jean-Pierre Jarier', 'G. VILLENEUVE': 'Gilles Villeneuve', 'E. FITTIPALDI': 'Emerson Fittipaldi', 'A. PROST': 'Alain Prost', 'J. MASS': 'Jochen Mass', 'B. GIACOMELLI': 'Bruno Giacomelli', 'J. SCHECKTER': 'Jody Scheckter', 'M. ANDRETTI': 'Mario Andretti', 'H. REBAQUE': 'Héctor Rebaque', 'E. De ANGELIS': 'Elio de Angelis', 'R. GINTHER': 'Richie Ginther', 'J. HUNT': 'James Hunt'})
import json
file = open('test.json', 'w', encoding='utf-8')
file.write(json.dumps(xedde, indent=4, ensure_ascii=False))
print(sort_links([{'href': '/en/1994/bresil/engages.aspx'}, {'href': '/en/1994/bresil/qualification.aspx'}, {'href': '/en/1994/bresil/classement.aspx'}, {'href': '/en/results/1994/races/605/brazil/qualifying/1'}, {'href': '/en/results/1994/races/605/brazil/qualifying/2'}, {'href': '/en/results/1994/races/605/brazil/qualifying/0'}]))
farina = parse_race_results(sort_links([{'href': '/en/1994/bresil/engages.aspx'}, {'href': '/en/1994/bresil/qualification.aspx'}, {'href': '/en/1994/bresil/classement.aspx'}, {'href': '/en/results/1994/races/605/brazil/qualifying/1'}, {'href': '/en/results/1994/races/605/brazil/qualifying/2'}, {'href': '/en/results/1994/races/605/brazil/qualifying/0'}]))
import json
fagioli = open('test.json', 'w', encoding='utf-8')
fagioli.write(json.dumps(farina, indent=4, ensure_ascii=False))'''

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
        cur.execute("SELECT GrandPrixName FROM GrandsPrix ORDER BY ID DESC LIMIT 1")
        xsqqwfejk = cur.fetchone()
        last_grandprix = xsqqwfejk[0] if xsqqwfejk else None
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
        '''
        for race in races:
            #print ("THIS LOOP IS BEING ENTERED INTO")
            open_url (f"https://www.formula1.com/en/results/{year}/{race['href']}")
            theplacewithallthelinks = soup.find('ul', class_ = 'f1-menu-wrapper flex flex-col gap-micro f1-sidebar-wrapper')
            #print (theplacewithallthelinks)
            soup = BeautifulSoup(str(theplacewithallthelinks), 'html.parser')
            f1links = soup.find_all('a', class_ = 'block')'''
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
        drivernames.append(cells[1].text.strip())  
    points_system_drivers, points_system_constructors = parse_points_system(str(soup))
    #print(points_system_drivers, points_system_constructors)
    print ("Points System Parsed")
    '''       
    scoringsystems = soup.find_all('div', class_ = 'yearclass')
    for fsds in scoringsystems:
        soup1 = BeautifulSoup(str(fsds), 'html.parser')
        ##fi.write(soup1.prettify())
        points_system_drivers, points_system_constructors = parse_points_system(str(fsds))
        print (points_system_drivers, points_system_constructors)
        if year < 1958:
            points_system_constructors = {
                "scores": None,
                "topscoring": None,
                "grandprix": None,
                "sprint": None
            }
        print ("Points System Parsed")'''            
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
        cur.execute("INSERT OR IGNORE INTO Circuits (CircuitName, FirstGrandPrix, FirstGrandPrixID) VALUES (?,?,?)", (race_info['circuit_name'], gp, race_info['race_number']))
        cur.execute("SELECT ID FROM Circuits WHERE CircuitName = ?", (race_info['circuit_name'],))
        circuitid = cur.fetchone()[0]
        cur.execute("""INSERT INTO GrandsPrix (ID, Season, GrandPrixName, RoundNumber, CircuitName, Date, DateInDateTime, Laps, CircuitLength, Weather, Notes, SprintWeekend, CircuitID)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, 
        (race_info['race_number'], year, gp, grandsprix.index(grandprix) + 1, race_info['circuit_name'], race_info['date'], race_info['dateindatetime'], race_info['laps'], race_info['circuit_distance'], race_info['weather'], race_info.get('notes'), trigger, circuitid))
        cur.execute('UPDATE Circuits SET LastGrandPrix = ?, LastGrandPrixID = ? WHERE CircuitName = ?', (gp, race_info['race_number'], race_info['circuit_name']))
        print ("Grand Prix info saved to database")                    
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
        print ("Results Parsed")
        
        entrant_keys = [
            "grandprix" ,"number", "driver", "nationality", "nationalityid", "team", "constructor", "chassis", "engine", "enginemodel", "tyre",
            "substituteorthirddriver", "qualifyingposition", "qualifyingtime", "qualifyinggap",
            "qualifyingtimeinseconds", "qualifyinggapseconds", "starting_grid_position",
            "gridpenalty", "gridpenalty_reason", "sprintstarting_grid_position", "sprintgridpenalty",
            "sprintgridpenalty_reason", "fastestlap", "fastestlapinseconds", "fastestlapgapinseconds",
            "fastestlap_time", "fastestlap_gap", "fastestlap_lap", "sprintfastestlap",
            "sprintfastestlapinseconds", "sprintfastestlapgapinseconds", "sprintfastestlap_time",
            "sprintfastestlap_gap", "sprintfastestlap_lap", "qualifying2position", "qualifying2time",
            "qualifying2gap", "qualifying2timeinseconds", "qualifying2laps", "qualifying1position",
            "qualifying1time", "qualifying1gap", "qualifying1timeinseconds", "qualifying1laps",
            "qualifyinglaps", "qualifying1time", "qualifying2time", "qualifying3time",
            "qualifying1gap", "qualifying2gap", "qualifying3gap", "qualifying1timeinseconds",
            "qualifying2timeinseconds", "qualifying3timeinseconds", "sprint_qualifyingposition",
            "sprint_qualifying1time", "sprint_qualifying2time", "sprint_qualifying3time",
            "sprint_qualifying1gap", "sprint_qualifying2gap", "sprint_qualifying3gap",
            "sprint_qualifyinggap", "sprint_qualifying1timeinseconds", "sprint_qualifying2timeinseconds",
            "sprint_qualifying3timeinseconds", "sprint_qualifyinglaps", "sprint_qualifyingtime",
            "sprint_qualifyingtimeinseconds", "warmupposition", "warmuptime", "warmupgap",
            "warmuptimeinseconds", "warmuplaps", "practice1position", "practice1time", "practice1gap",
            "practice1timeinseconds", "practice1laps", "practice2position", "practice2time",
            "practice2gap", "practice2timeinseconds", "practice2laps", "practice3position",
            "practice3time", "practice3gap", "practice3timeinseconds", "practice3laps",
            "practice4position", "practice4time", "practice4gap", "practice4timeinseconds",
            "practice4laps", "sprintposition", "sprintlaps", "sprinttime", "sprintpoints",
            "sprinttimeinseconds", "sprintgap", "sprintgapinseconds", "raceposition", "racelaps",
            "racetime", "racepoints", "racetimeinseconds", "racegap", "racegapinseconds", "penalties", "sprint_penalties",
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
                driver_name_clean = result['driver'].replace('*', '').replace('æ', '-').replace("'", '-').replace('Ø', 'O').replace('ø', 'o')
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
            values[108] = json.dumps(values[108]) if values[108] else None  # Convert penalties to JSON if not None
            values[109] = json.dumps(values[109]) if values[109] else None
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
        print ("Results saved to database")   
        '''        
        for drivername in drivernames:
            fulfilled = False
            while fulfilled == False:
                parts = drivername.lower().replace('.', '').split()
                if len(parts) >= 2:
                    first_initial = parts[0][0]
                    last_name = ' '.join(parts[1:])  # handles multi-word last names like 'de graffenried'
                    for entrant in results:
                        full = entrant["driver"].lower()
                        if full.startswith(first_initial) and full.endswith(last_name):
                            try:
                                _ = name_map[drivername]
                            except KeyError:
                                name_map[drivername] = entrant['driver']
                        fulfilled = True
                    if fulfilled == False:
                        cur.execute("SELECT Driver FROM DriversChampionship WHERE Season = ?", (year,))
                        rows = cur.fetchall()
                        for row in rows:
                            #use same matching logic as above
                            full = row[0].lower()
                            if full.startswith(first_initial) and full.endswith(last_name):
                                try:
                                    _ = name_map[drivername]
                                except KeyError:
                                    name_map[drivername] = row[0]
                        fulfilled = True
            '''
        for drivername in drivernames:
            fulfilled = False
            while not fulfilled:
                parts = drivername.lower().replace('.', '').split()
                if len(parts) >= 2:
                    first_initial = parts[0][0]
                    last_name = ' '.join(parts[1:])
                    # Try to match in results
                    for entrant in results:
                        full = entrant["driver"].lower()
                        if full.startswith(first_initial) and full.endswith(last_name):
                            name_map[drivername] = entrant['driver']
                            fulfilled = True
                            break
                    # If not found, try to match in DB
                    if not fulfilled:
                        cur.execute("SELECT Driver FROM DriversChampionship WHERE Season = ?", (year,))
                        rows = cur.fetchall()
                        for row in rows:
                            full = row[0].lower()
                            if full.startswith(first_initial) and full.endswith(last_name):
                                name_map[drivername] = row[0]
                                fulfilled = True
                                break
                    # If still not found, log and break to avoid infinite loop
                    if not fulfilled:
                        fulfilled = True        
        #print (results)
        for item in grandprixlinks[6:]:
            if item['href'].endswith("/tour-par-tour.aspx"):
                lapbylap = parse_lap_by_lap(f"https://www.statsf1.com{item['href']}", results, dataid, dataidforrace)
                if trigger == True:
                    sprintlapbylap = parse_lap_by_lap(f"https://www.statsf1.com{grandprix['href'].replace('.aspx', '')}/sprint.aspx?tpt", results)
                
                    for instance in sprintlapbylap:
                        driver_id = driverids[instance['driver']]
                        cur.execute("""
                        INSERT INTO LapByLap (GrandPrix, Driver, Position, Lap, Type, SafetyCar, Time, TimeInSeconds, GrandPrixID, DriverID)
                        VALUES (?,?,?,?,?,?,?,?,?,?)
                        """,
                        (gp, instance['driver'], instance['position'], instance['lap'], instance['type'], instance['safetycar'], instance.get('time'), instance.get('time_in_seconds'), grandprix_id, driver_id))                    
                #print (lapbylap)  
                #print (name_map)  
                print ("Lap by lap Parsed")
                
                for instance in lapbylap:
                    driver_id = driverids[instance['driver']]
                    cur.execute("""
                    INSERT INTO LapByLap (GrandPrix, Driver, Position, Lap, Type, SafetyCar, Time, TimeInSeconds, GrandPrixID, DriverID)
                    VALUES (?,?,?,?,?,?,?,?,?,?)
                    """,
                    (gp, instance['driver'], instance['position'], instance['lap'], instance['type'], instance['safetycar'], instance.get('time'), instance.get('time_in_seconds'), grandprix_id, driver_id)) 
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
            tablex = soup.find('table', class_ = 'f1-table f1-table-with-data w-full')
            pitstopsummary = parse_pit_stop_summary(tablex, results) 
            print ("Pit stop summary Parsed") 
            for pitstop in pitstopsummary:
                driver_id = driverids[pitstop['driver']]
                constructor_id = constructorids[pitstop['constructor']]
                cur.execute("""
                INSERT INTO PitStopSummary (GrandPrix, Number, Driver, Constructor, StopNumber, Lap, DurationSpentInPitLane, TimeInSeconds, TimeOfDayStopped, TotalTimeSpentInPitLane, TotalTimeinSeconds, GrandPrixID, DriverID, ConstructorID)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (gp, pitstop['carnumber'], pitstop['driver'], pitstop['constructor'], pitstop['stopnumber'], pitstop['lapstopped'], pitstop['durationspentinpitlane'], pitstop['timeinseconds'], pitstop['timeofday'], pitstop['totaltimeforthewholerace'], pitstop['totaltimeinseconds'], grandprix_id, driver_id, constructor_id))
            #print("Pit Stop Summary:", pitstopsummary) 

        '''          
        for link in grandprixlinks:
            open_url(f"https://www.statsf1.com{link['href']}")
            if link['href'].endswith('engages.aspx'): #If it is a race entrants page, it will have a table with the class 'sortable'
                table = soup.find('table', class_ = 'sortable')
                race_entrants = parse_race_entrants(str(table))
                print("Race Entrants:", race_entrants)
                #print(link['href'])
                #print(soup.prettify())
                #fi.write(soup.prettify())
            elif link['href'].endswith('en-tete.aspx'): #If it is a lap leaders page, we skip it because we have the lap by lap page
                continue
            else: #Other pages have a 'datatable' class table
                table = soup.find('table', class_ = 'datatable')
                if table is not None:
                    soup = BeautifulSoup(str(table), 'html.parser')
                    #fi.write(soup.prettify())
                #print(link['href'])
                #print(soup.prettify())
            if link['href'].endswith('grille.aspx'):  
                table = soup.find('table', class_ = 'ctl00_CPH_Main_TBL_Grille')
                soup = BeautifulSoup(str(table), 'html.parser')
                #fi.write(soup.prettify())
                pitlane = soup.find('div', class_ = 'DV_PitLane')
                soup = BeautifulSoup(str(pitlane), 'html.parser')
                #fi.write(soup.prettify())
            notes = soup.find(id = 'ctl00_CPH_Main_P_Commentaire')
            if notes is not None:
                soup = BeautifulSoup(str(notes), 'html.parser')
                #fi.write(soup.prettify())
        if year > 1982:
            for link in links:
                if link['href'].endswith('race-result') or link['href'].endswith('starting-grid'):
                    continue #There's no extra information on these pages, we skip them
                else:
                    open_url(f"https://www.formula1.com{link['href']}")
                    resulttable = soup.find('table', class_ = 'f1-table f1-table-with-data w-full')
                    soup = BeautifulSoup(str(resulttable), 'html.parser')
                    #fi.write(soup.prettify())   
                    #print(soup.prettify())                                        
            # quit() #For debugging purposes, we quit after the first grand prix  🚫✔️'''
        if trigger2 == True:
            driverschampionship, constructorschampionship = parse_championship_results(year, name_map)
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
cur.execute("UPDATE Drivers SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.raceposition = 1)")
cur.execute("UPDATE Drivers SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.raceposition <= 3)")
cur.execute("UPDATE Drivers SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.qualifyingposition = 1)")
cur.execute("UPDATE Drivers SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.fastestlap = 1)")
cur.execute("UPDATE Drivers SET Championships = (SELECT COUNT(*) FROM DriversChampionship WHERE DriversChampionship.driverid = Drivers.ID AND DriversChampionship.Position = 1)")
cur.execute("UPDATE Drivers SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID)")
cur.execute("UPDATE Drivers SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID  AND GrandPrixResults.racetime NOT LIKE '%(Did not start)%')")
cur.execute("UPDATE Drivers SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID)")
cur.execute("UPDATE Drivers SET DNFs = (SELECT IFNULL(COUNT(*), 0) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND racetime IS NOT NULL AND racetime LIKE '%(Did not finish)%')")
cur.execute("UPDATE Drivers SET LapsLed = (SELECT COUNT(*) FROM LapByLap WHERE LapByLap.driverid = Drivers.ID AND position = 1)")
cur.execute("UPDATE Drivers SET HatTricks = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND raceposition = 1 AND qualifyingposition = 1 AND fastestlap = 1)")
cur.execute("UPDATE Drivers SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.starting_grid_position IS NOT NULL)")
cur.execute("UPDATE Drivers SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.sprintstarting_grid_position IS NOT NULL)")
cur.execute("UPDATE Drivers SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.qualifyingposition IS NOT NULL)")
cur.execute("UPDATE Drivers SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.raceposition IS NOT NULL)")
cur.execute("UPDATE Drivers SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.driverid = Drivers.ID AND GrandPrixResults.sprintposition IS NOT NULL)")
cur.execute("UPDATE Drivers SET BestChampionshipPosition = (SELECT MIN(Position) FROM DriversChampionship WHERE DriversChampionship.driverid = Drivers.ID AND DriversChampionship.Position IS NOT NULL)")
print("Drivers stats updated.")

from collections import defaultdict

def get_grand_slam_candidates(cur):
    # Fetch all lap-by-lap data
    cur.execute("SELECT GrandPrixID, Lap, DriverID, Position FROM LapByLap")
    rows = cur.fetchall()

    # Total laps per race
    race_lap_counts = defaultdict(int)
    # Laps led by driver in each race
    driver_lap_leads = defaultdict(int)

    for raceID, lapNumber, driverID, position in rows:
        race_lap_counts[raceID] += 1
        if position == 1:
            driver_lap_leads[(driverID, raceID)] += 1

    # Determine drivers who led every lap
    led_every_lap_set = set()
    for (driverID, raceID), laps_led in driver_lap_leads.items():
        if laps_led == race_lap_counts[raceID]:
            led_every_lap_set.add((driverID, raceID))

    return led_every_lap_set

led_every_lap_set = get_grand_slam_candidates(cur)

cur.execute("""
    SELECT driverid, grandprixID
    FROM GrandPrixResults
    WHERE raceposition = 1 AND qualifyingposition = 1 AND fastestlap = 1
""")
possible_grandslams = cur.fetchall()

# Count grand slams per driver
from collections import Counter
grand_slam_counter = Counter()

for driverID, raceID in possible_grandslams:
    if (driverID, raceID) in led_every_lap_set:
        grand_slam_counter[driverID] += 1

for driverID, grand_slam_count in grand_slam_counter.items():
    cur.execute("UPDATE Drivers SET GrandSlams = ? WHERE ID = ?", (grand_slam_count, driverID))





#constructors now:
cur.execute("UPDATE Constructors SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.raceposition = 1)")
cur.execute("UPDATE Constructors SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.raceposition <= 3)")
cur.execute("UPDATE Constructors SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.qualifyingposition = 1)")
cur.execute("UPDATE Constructors SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.fastestlap = 1)")
cur.execute("UPDATE Constructors SET Championships = (SELECT COUNT(*) FROM ConstructorsChampionship WHERE ConstructorsChampionship.constructorid = Constructors.ID AND ConstructorsChampionship.Position = 1)")
cur.execute("UPDATE Constructors SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID)")
cur.execute("UPDATE Constructors SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID   AND GrandPrixResults.racetime NOT LIKE '%(Did not start)%')")
cur.execute("UPDATE Constructors SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID)")
cur.execute("UPDATE Constructors SET DNFs = (SELECT IFNULL(COUNT(*), 0) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND racetime IS NOT NULL AND racetime LIKE '%(Did not finish)%')")
cur.execute("UPDATE Constructors SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.starting_grid_position IS NOT NULL)")
cur.execute("UPDATE Constructors SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.sprintstarting_grid_position IS NOT NULL)")
cur.execute("UPDATE Constructors SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.qualifyingposition IS NOT NULL)")
cur.execute("UPDATE Constructors SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.raceposition IS NOT NULL)")
cur.execute("UPDATE Constructors SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.constructorid = Constructors.ID AND GrandPrixResults.sprintposition IS NOT NULL)")
cur.execute("UPDATE Constructors SET BestChampionshipPosition = (SELECT MIN(Position) FROM ConstructorsChampionship WHERE ConstructorsChampionship.constructorid = Constructors.ID AND ConstructorsChampionship.Position IS NOT NULL)")
print("Constructors stats updated.")

#exact same thing for engines as constructors
cur.execute("UPDATE Engines SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.raceposition = 1)")
cur.execute("UPDATE Engines SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.raceposition <= 3)")
cur.execute("UPDATE Engines SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.qualifyingposition = 1)")
cur.execute("UPDATE Engines SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.fastestlap = 1)")
cur.execute("UPDATE Engines SET Championships = (SELECT COUNT(*) FROM ConstructorsChampionship WHERE ConstructorsChampionship.engineid = Engines.ID AND ConstructorsChampionship.Position = 1)")
cur.execute("UPDATE Engines SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID)")
cur.execute("UPDATE Engines SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID   AND GrandPrixResults.racetime NOT LIKE '%(Did not start)%')")
cur.execute("UPDATE Engines SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID)")
cur.execute("UPDATE Engines SET DNFs = (SELECT IFNULL(COUNT(*), 0) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND racetime IS NOT NULL AND racetime LIKE '%(Did not finish)%')")
cur.execute("UPDATE Engines SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.starting_grid_position IS NOT NULL)")
cur.execute("UPDATE Engines SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.sprintstarting_grid_position IS NOT NULL)")
cur.execute("UPDATE Engines SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.qualifyingposition IS NOT NULL)")
cur.execute("UPDATE Engines SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.raceposition IS NOT NULL)")
cur.execute("UPDATE Engines SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.engineid = Engines.ID AND GrandPrixResults.sprintposition IS NOT NULL)")
print("Engines stats updated.")

#chassis now:
cur.execute("UPDATE Chassis SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.raceposition = 1)")
cur.execute("UPDATE Chassis SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.raceposition <= 3)")
cur.execute("UPDATE Chassis SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.qualifyingposition = 1)")
cur.execute("UPDATE Chassis SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.fastestlap = 1)")
cur.execute("UPDATE Chassis SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID  AND GrandPrixResults.racetime NOT LIKE '%(Did not start)%')")
cur.execute("UPDATE Chassis SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID   AND GrandPrixResults.racetime NOT LIKE '%(Did not start)%')")
cur.execute("UPDATE Chassis SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID)")
cur.execute("UPDATE Chassis SET DNFs = (SELECT IFNULL(COUNT(*), 0) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND racetime IS NOT NULL AND racetime LIKE '%(Did not finish)%')")
cur.execute("UPDATE Chassis SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.starting_grid_position IS NOT NULL)")
cur.execute("UPDATE Chassis SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.sprintstarting_grid_position IS NOT NULL)")
cur.execute("UPDATE Chassis SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.qualifyingposition IS NOT NULL)")
cur.execute("UPDATE Chassis SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.raceposition IS NOT NULL)")
cur.execute("UPDATE Chassis SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.chassisid = Chassis.ID AND GrandPrixResults.sprintposition IS NOT NULL)")
print("Chassis stats updated.")

#engine models now:
cur.execute("UPDATE EngineModels SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.raceposition = 1)")
cur.execute("UPDATE EngineModels SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.raceposition <= 3)")
cur.execute("UPDATE EngineModels SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.qualifyingposition = 1)")
cur.execute("UPDATE EngineModels SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.fastestlap = 1)")
cur.execute("UPDATE EngineModels SET Championships = (SELECT COUNT(*) FROM ConstructorsChampionship WHERE ConstructorsChampionship.enginemodelid = EngineModels.ID AND ConstructorsChampionship.Position = 1)")
cur.execute("UPDATE EngineModels SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID)")
cur.execute("UPDATE EngineModels SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID   AND GrandPrixResults.racetime NOT LIKE '%(Did not start)%')")
cur.execute("UPDATE EngineModels SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID)")
cur.execute("UPDATE EngineModels SET DNFs = (SELECT IFNULL(COUNT(*), 0) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND racetime IS NOT NULL AND racetime LIKE '%(Did not finish)%')")
cur.execute("UPDATE EngineModels SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.starting_grid_position IS NOT NULL)")
cur.execute("UPDATE EngineModels SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.sprintstarting_grid_position IS NOT NULL)")
cur.execute("UPDATE EngineModels SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.qualifyingposition IS NOT NULL)")
cur.execute("UPDATE EngineModels SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.raceposition IS NOT NULL)")
cur.execute("UPDATE EngineModels SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.enginemodelid = EngineModels.ID AND GrandPrixResults.sprintposition IS NOT NULL)")
print("EngineModels stats updated.")

#tyres now:
cur.execute("UPDATE Tyres SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.raceposition = 1)")
cur.execute("UPDATE Tyres SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.raceposition <= 3)")
cur.execute("UPDATE Tyres SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.qualifyingposition = 1)")
cur.execute("UPDATE Tyres SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.fastestlap = 1)")      
cur.execute("UPDATE Tyres SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID)")
cur.execute("UPDATE Tyres SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID   AND GrandPrixResults.racetime NOT LIKE '%(Did not start)%')")
cur.execute("UPDATE Tyres SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID)")
cur.execute("UPDATE Tyres SET DNFs = (SELECT IFNULL(COUNT(*), 0) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND racetime IS NOT NULL AND racetime LIKE '%(Did not finish)%')")
cur.execute("UPDATE Tyres SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.starting_grid_position IS NOT NULL)")
cur.execute("UPDATE Tyres SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.sprintstarting_grid_position IS NOT NULL)")
cur.execute("UPDATE Tyres SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.qualifyingposition IS NOT NULL)")
cur.execute("UPDATE Tyres SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.raceposition IS NOT NULL)")
cur.execute("UPDATE Tyres SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.tyreid = Tyres.ID AND GrandPrixResults.sprintposition IS NOT NULL)")
print("Tyres stats updated.")

#teams too:
cur.execute("UPDATE Teams SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.raceposition = 1)")
cur.execute("UPDATE Teams SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.raceposition <= 3)")
cur.execute("UPDATE Teams SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.qualifyingposition = 1)")
cur.execute("UPDATE Teams SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.fastestlap = 1)")
cur.execute("UPDATE Teams SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID)")
cur.execute("UPDATE Teams SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID   AND GrandPrixResults.racetime NOT LIKE '%(Did not start)%')")
cur.execute("UPDATE Teams SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID)")
cur.execute("UPDATE Teams SET DNFs = (SELECT IFNULL(COUNT(*), 0) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND racetime IS NOT NULL AND racetime LIKE '%(Did not finish)%')")
cur.execute("UPDATE Teams SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.starting_grid_position IS NOT NULL)")          
cur.execute("UPDATE Teams SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.sprintstarting_grid_position IS NOT NULL)")    
cur.execute("UPDATE Teams SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.qualifyingposition IS NOT NULL)")
cur.execute("UPDATE Teams SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.raceposition IS NOT NULL)")
cur.execute("UPDATE Teams SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.teamid = Teams.ID AND GrandPrixResults.sprintposition IS NOT NULL)")
print("Teams stats updated.")

#nationalities:
cur.execute("UPDATE Nationalities SET Wins = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.raceposition = 1)")
cur.execute("UPDATE Nationalities SET Podiums = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.raceposition <= 3)")
cur.execute("UPDATE Nationalities SET Poles = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.qualifyingposition = 1)")
cur.execute("UPDATE Nationalities SET FastestLaps = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.fastestlap = 1)")
cur.execute("UPDATE Nationalities SET Championships = (SELECT COUNT(*) FROM DriversChampionship WHERE DriversChampionship.nationalityid = Nationalities.ID AND DriversChampionship.Position = 1)")
cur.execute("UPDATE Nationalities SET Points = (SELECT IFNULL(SUM(IFNULL(GrandPrixResults.racepoints, 0) + IFNULL(GrandPrixResults.sprintpoints, 0)), 0) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID)")
cur.execute("UPDATE Nationalities SET Starts = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID   AND GrandPrixResults.racetime NOT LIKE '%(Did not start)%')")
cur.execute("UPDATE Nationalities SET Entries = (SELECT COUNT(*) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID)")
cur.execute("UPDATE Nationalities SET DNFs = (SELECT IFNULL(COUNT(*), 0) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND racetime IS NOT NULL AND racetime LIKE '%(Did not finish)%')")
cur.execute("UPDATE Nationalities SET BestGridPosition = (SELECT MIN(starting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.starting_grid_position IS NOT NULL)")          
cur.execute("UPDATE Nationalities SET BestSprintGridPosition = (SELECT MIN(sprintstarting_grid_position) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.sprintstarting_grid_position IS NOT NULL)")     
cur.execute("UPDATE Nationalities SET BestQualifyingPosition = (SELECT MIN(qualifyingposition) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.qualifyingposition IS NOT NULL)")
cur.execute("UPDATE Nationalities SET BestRacePosition = (SELECT MIN(raceposition) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.raceposition IS NOT NULL)")   
cur.execute("UPDATE Nationalities SET BestSprintPosition = (SELECT MIN(sprintposition) FROM GrandPrixResults WHERE GrandPrixResults.nationalityid = Nationalities.ID AND GrandPrixResults.sprintposition IS NOT NULL)") 
print("Nationalities stats updated.")

def update_laps_led_for_component(cur, component_table, component_id_column):
    # Count laps led per component (e.g., constructor, engine) by joining LapByLap + GrandPrixResults
    query = f"""
    SELECT G.{component_id_column}, COUNT(*) AS laps_led
    FROM LapByLap AS L
    JOIN GrandPrixResults AS G ON L.driverid = G.driverid AND L.grandprixid = G.grandprixid
    WHERE L.position = 1 AND G.{component_id_column} IS NOT NULL
    GROUP BY G.{component_id_column}
    """
    cur.execute(query)
    results = cur.fetchall()

    # Update the corresponding table with laps led
    for component_id, laps_led in results:
        cur.execute(
            f"UPDATE {component_table} SET LapsLed = ? WHERE ID = ?",
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
print("LapsLed stats updated.")

print("All stats updated successfully. Closing database connection...")

conn.commit() 
conn.close()
#fi.close()

'''
Yes, I know I commented out a lot of code which is not a line of code, but as of the 2024 British Grand Prix, this script has
approximately 2.41 lines of code for every Grand Prix.

Yes, this is very inefficient, but it works, I don't care. I don't want to rewrite it to make it more efficient.

'''