import sqlite3
import sys

def delete_season(year):
    try:
        conn = sqlite3.connect("py/sessionresults.db")
        cursor = conn.cursor()
        
        # Check if season exists
        cursor.execute("SELECT 1 FROM Seasons WHERE Season = ?", (year,))
        if not cursor.fetchone():
            print(f"Season {year} not found in database.")
            conn.close()
            return

        print(f"Deleting all data for the {year} season...")

        # 1. Get IDs of Grands Prix for that season
        cursor.execute("SELECT ID FROM GrandsPrix WHERE Season = ?", (year,))
        gp_ids = [row[0] for row in cursor.fetchall()]
        gp_ids_str = ",".join(map(str, gp_ids))

        if gp_ids:
            # 2. Delete from related tables
            print(f" - Deleting results, pit stops, and laps for {len(gp_ids)} Grands Prix...")
            cursor.execute(f"DELETE FROM GrandPrixResults WHERE grandprixid IN ({gp_ids_str})")
            cursor.execute(f"DELETE FROM PitStopSummary WHERE GrandPrixID IN ({gp_ids_str})")
            cursor.execute(f"DELETE FROM LapByLap WHERE GrandPrixID IN ({gp_ids_str})")
            cursor.execute(f"DELETE FROM InSeasonProgressDrivers WHERE GrandPrixID IN ({gp_ids_str})")
            cursor.execute(f"DELETE FROM InSeasonProgressConstructors WHERE GrandPrixID IN ({gp_ids_str})")
            cursor.execute(f"DELETE FROM Sessions WHERE GrandPrixID IN ({gp_ids_str})")
            cursor.execute(f"DELETE FROM RaceReports WHERE ID IN ({gp_ids_str})")

        # 3. Delete championship standings and season info
        print(" - Deleting championship standings...")
        cursor.execute("DELETE FROM DriversChampionship WHERE Season = ?", (year,))
        cursor.execute("DELETE FROM ConstructorsChampionship WHERE Season = ?", (year,))
        cursor.execute("DELETE FROM Seasons WHERE Season = ?", (year,))
        
        # 4. Delete the Grands Prix themselves
        print(" - Deleting Grands Prix records...")
        cursor.execute("DELETE FROM GrandsPrix WHERE Season = ?", (year,))

        # 5. Mark entities for stats update
        print(" - Marking Drivers, Teams, Constructors, etc. for stats recalculation...")
        entity_tables = [
            "Drivers", "Constructors", "Teams", "Engines", "Tyres", 
            "Chassis", "EngineModels", "Circuits", "CircuitLayouts", "Nationalities"
        ]
        
        for table in entity_tables:
            cursor.execute(f"UPDATE {table} SET needstatsupdate = 1")

        conn.commit()
        print(f"\nSuccessfully deleted all data for the {year} season.")
        print("Note: Stats in entity tables have been marked for update.")
        
        conn.close()
    except Exception as e:
        print(f"An error occurred: {e}")
        if 'conn' in locals():
            conn.rollback()
            conn.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python py/deleteseason.py <year>")
    else:
        try:
            year_input = int(sys.argv[1])
            delete_season(year_input)
        except ValueError:
            print("Please provide a valid year as an integer.")
