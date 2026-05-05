import sqlite3
import argparse

conn = sqlite3.connect('sessionresults.db')
cur = conn.cursor()

racetodelete = argparse.ArgumentParser(description='Delete a race from the database')
racetodelete.add_argument('racename', type=str, help='The name of the race to delete')
args = racetodelete.parse_args()

cur.execute("DELETE FROM GrandPrixResults WHERE grandprix = ?", (args.racename,))
cur.execute("DELETE FROM PitStopSummary WHERE GrandPrix = ?", (args.racename,))
cur.execute("DELETE FROM LapByLap WHERE GrandPrix = ?", (args.racename,))
cur.execute("DELETE FROM Sessions WHERE GrandPrix = ?", (args.racename,))
cur.execute("DELETE FROM MaxSpeeds WHERE GrandPrixName = ?", (args.racename,))
cur.execute("DELETE FROM GrandsPrix WHERE GrandPrixName = ?", (args.racename,))
cur.execute("DELETE FROM RaceReports WHERE GrandPrixName = ?", (args.racename,))
#InSeasonProgressDrivers and InSeasonProgressConstructors are not deleted

conn.commit()
conn.close()

print(f"Deleted race: {args.racename}")