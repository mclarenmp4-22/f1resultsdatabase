import sqlite3
conn = sqlite3.connect('sessionresults.db')
cur = conn.cursor()
tables_to_reset = ["Drivers", "Constructors", "Engines", "Chassis", "EngineModels", "Tyres", "Teams", "Nationalities", "Seasons"]
for table in tables_to_reset:
    cur.execute(f"UPDATE {table} SET needstatsupdate = 1 WHERE needstatsupdate = 0")
def update_entity_stats(cur, table_name, fk_column, has_substitute_check=False, champ_table=None, indy500_check=True):
    """
    Dynamically generates and executes a single-pass optimized UPDATE query 
    for F1 entities (Drivers, Constructors, Teams, etc.).
    """
    
    # Only Drivers have the substitute check for SeasonsRaced
    sub_check = "AND gr.substituteorthirddriver = 0" if has_substitute_check else ""
    
    # Determine how to calculate championships
    champ_cte = ""
    champ_joins = ""
    champ_sets = ""
    
    if champ_table:
        # Drivers use DriverID, Constructors/Engines use ConstructorID/EngineID
        champ_fk = "DriverID" if champ_table == "DriversChampionship" else fk_column
        champ_cte = f"""
        , ChampStats AS (
            SELECT {champ_fk} AS id, 
                   SUM(CASE WHEN Position = 1 THEN 1 ELSE 0 END) AS championships,
                   MIN(Position) AS best_champ_pos
            FROM {champ_table}
            GROUP BY {champ_fk}
        )
        """
        champ_joins = f"LEFT JOIN ChampStats cs ON base.id = cs.id"
        champ_sets = """
            Championships = COALESCE(cs.championships, 0),
            BestChampionshipPosition = cs.best_champ_pos,
        """
    query = f"""
    WITH BaseStats AS (
        SELECT 
            {fk_column} AS id,
            SUM(CASE WHEN raceposition = 1 THEN 1 ELSE 0 END) AS wins,
            SUM(CASE WHEN raceposition <= 3 THEN 1 ELSE 0 END) AS podiums,
            SUM(CASE WHEN starting_grid_position = 1 THEN 1 ELSE 0 END) AS poles,
            SUM(CASE WHEN fastestlap = 1 THEN 1 ELSE 0 END) AS fastestlaps,
            SUM(CASE WHEN sprintposition = 1 THEN 1 ELSE 0 END) AS sprintwins,
            SUM(CASE WHEN sprintposition <= 3 THEN 1 ELSE 0 END) AS sprintpodiums,
            SUM(CASE WHEN sprintstarting_grid_position = 1 THEN 1 ELSE 0 END) AS sprintpoles,
            SUM(CASE WHEN sprintfastestlap = 1 THEN 1 ELSE 0 END) AS sprintfastestlaps,
            SUM(IFNULL(racepoints, 0) + IFNULL(sprintpoints, 0)) AS points,
            
            -- FIXED: Ensure racestatus isn't DNS or Withdrew
            SUM(CASE WHEN racestatus IS NOT NULL 
                      AND racestatus NOT LIKE '%Did not start%' 
                      AND racestatus NOT LIKE '%Withdrew%' 
                 THEN 1 ELSE 0 END) AS starts,
                 
            COUNT(*) AS entries,
            
            -- FIXED: Ensure sprintstatus actually exists, and isn't DNS or Withdrew
            SUM(CASE WHEN sprintstatus IS NOT NULL 
                      AND sprintstatus NOT LIKE '%Did not start%' 
                      AND sprintstatus NOT LIKE '%Withdrew%' 
                 THEN 1 ELSE 0 END) AS sprintstarts,
                 
            SUM(CASE WHEN racestatus LIKE '%Did not finish%' THEN 1 ELSE 0 END) AS dnfs,
            MIN(starting_grid_position) AS best_grid,
            MIN(sprintstarting_grid_position) AS best_sprint_grid,
            MIN(qualifyingposition) AS best_qual,
            MIN(raceposition) AS best_race,
            MIN(sprintposition) AS best_sprint,
            MIN(sprint_qualifyingposition) AS best_sprint_qual
        FROM GrandPrixResults
        WHERE {fk_column} IS NOT NULL
        GROUP BY {fk_column}
    ),
    SeasonStats AS (
        SELECT gr.{fk_column} AS id, COUNT(DISTINCT gp.Season) AS seasons_raced
        FROM GrandPrixResults gr
        JOIN GrandsPrix gp ON gr.grandprixid = gp.ID
        WHERE gr.{fk_column} IS NOT NULL {sub_check}
        GROUP BY gr.{fk_column}
    ),
    Indy500Stats AS (
        SELECT gr.{fk_column} AS id,
               COUNT(*) AS total_races,
               SUM(CASE WHEN gp.GrandPrixName LIKE '%Indianapolis 500' THEN 1 ELSE 0 END) AS indy_races
        FROM GrandPrixResults gr
        JOIN GrandsPrix gp ON gr.grandprixid = gp.ID
        WHERE gr.{fk_column} IS NOT NULL
        GROUP BY gr.{fk_column}
    )
    {champ_cte}

    UPDATE {table_name}
    SET 
        Wins = COALESCE(base.wins, 0),
        Podiums = COALESCE(base.podiums, 0),
        Poles = COALESCE(base.poles, 0),
        FastestLaps = COALESCE(base.fastestlaps, 0),
        SprintWins = COALESCE(base.sprintwins, 0),
        SprintPodiums = COALESCE(base.sprintpodiums, 0),
        SprintPoles = COALESCE(base.sprintpoles, 0),
        SprintFastestLaps = COALESCE(base.sprintfastestlaps, 0),
        Points = COALESCE(base.points, 0),
        Starts = COALESCE(base.starts, 0),
        Entries = COALESCE(base.entries, 0),
        SprintStarts = COALESCE(base.sprintstarts, 0),
        DNFs = COALESCE(base.dnfs, 0),
        BestGridPosition = base.best_grid,
        BestSprintGridPosition = base.best_sprint_grid,
        BestQualifyingPosition = base.best_qual,
        BestRacePosition = base.best_race,
        BestSprintPosition = base.best_sprint,
        BestSprintQualifyingPosition = base.best_sprint_qual,
        SeasonsRaced = COALESCE(ss.seasons_raced, 0),
        {"indy500only = CASE WHEN i.total_races > 0 AND i.total_races = i.indy_races THEN 1 ELSE 0 END," if indy500_check else ""}
        {champ_sets}
        needstatsupdate = 0
    FROM BaseStats base
    LEFT JOIN SeasonStats ss ON base.id = ss.id
    LEFT JOIN Indy500Stats i ON base.id = i.id
    {champ_joins}
    WHERE {table_name}.ID = base.id 
      AND {table_name}.needstatsupdate = 1; 
    """
    
    cur.execute(query)
    print(f"{table_name} stats updated.")


# --- 1. Update Standard Entity Tables ---
update_entity_stats(cur, "Drivers", "driverid", has_substitute_check=True, champ_table="DriversChampionship")
update_entity_stats(cur, "Constructors", "constructorid", champ_table="ConstructorsChampionship")
update_entity_stats(cur, "Engines", "engineid")
update_entity_stats(cur, "Teams", "teamid")
update_entity_stats(cur, "Chassis", "chassisid")
update_entity_stats(cur, "EngineModels", "enginemodelid")
update_entity_stats(cur, "Tyres", "tyreid")
update_entity_stats(cur, "Nationalities", "nationalityid", indy500_check=False)

# --- 2. Update Highly Specific Driver Stats (HatTricks & GrandSlams) ---
# Hat Tricks
cur.execute("""
    UPDATE Drivers
    SET HatTricks = COALESCE(ht.hattricks, 0)
    FROM (
        SELECT driverid, COUNT(*) AS hattricks
        FROM GrandPrixResults
        WHERE raceposition = 1 AND starting_grid_position = 1 AND fastestlap = 1
        GROUP BY driverid
    ) AS ht
    WHERE Drivers.ID = ht.driverid AND Drivers.needstatsupdate = 1;
""")

# Grand Slams (Led Every Lap)
cur.execute("""
    WITH RaceLaps AS (
        SELECT L.grandprixid, L.driverid, COUNT(*) AS total_laps, 
               SUM(CASE WHEN L.position = 1 THEN 1 ELSE 0 END) AS laps_led
        FROM LapByLap L
        JOIN Sessions S ON L.SessionID = S.ID
        WHERE S.SessionName = 'Race'
        GROUP BY L.grandprixid, L.driverid
    ),
    LedEveryLap AS (
        SELECT driverid, grandprixid 
        FROM RaceLaps 
        WHERE total_laps = laps_led AND total_laps > 0
    ),
    GrandSlams AS (
        SELECT g.driverid, COUNT(*) AS grand_slams
        FROM GrandPrixResults g
        JOIN LedEveryLap lel ON g.driverid = lel.driverid AND g.grandprixid = lel.grandprixid
        WHERE g.raceposition = 1 AND g.starting_grid_position = 1 AND g.fastestlap = 1
        GROUP BY g.driverid
    )
    UPDATE Drivers 
    SET GrandSlams = COALESCE(gs.grand_slams, 0)
    FROM GrandSlams gs
    WHERE Drivers.ID = gs.driverid AND Drivers.needstatsupdate = 1;
""")

# --- 3. Update Constructors Specific Stats (1-2 Finishes) ---
cur.execute("""
    UPDATE Constructors
    SET OneTwos = COALESCE(ot.one_twos, 0)
    FROM (
        SELECT constructorid, COUNT(*) AS one_twos
        FROM (
            SELECT constructorid, grandprixid
            FROM GrandPrixResults
            WHERE raceposition IN (1, 2)
            GROUP BY constructorid, grandprixid
            HAVING COUNT(DISTINCT raceposition) = 2
        )
        GROUP BY constructorid
    ) AS ot
    WHERE Constructors.ID = ot.constructorid AND Constructors.needstatsupdate = 1;
""")

# --- 4. Update Laps Led (LapsByLap iteration) ---
def update_laps_led_for_component(cur, component_table, component_id_column):
    query = f"""
    WITH LapsLedStats AS (
        SELECT 
            G.{component_id_column} AS id,
            SUM(CASE WHEN S.SessionName = 'Race' THEN 1 ELSE 0 END) AS gp_laps_led,
            SUM(CASE WHEN S.SessionName IN ('Sprint', 'Sprint Qualifying') THEN 1 ELSE 0 END) AS sprint_laps_led
        FROM LapByLap AS L
        JOIN Sessions AS S ON L.SessionID = S.ID
        JOIN GrandPrixResults AS G ON L.driverid = G.driverid AND L.grandprixid = G.grandprixid
        WHERE L.position = 1 AND G.{component_id_column} IS NOT NULL
        GROUP BY G.{component_id_column}
    )
    UPDATE {component_table}
    SET 
        GrandPrixLapsLed = COALESCE(lls.gp_laps_led, 0),
        SprintLapsLed = COALESCE(lls.sprint_laps_led, 0)
    FROM LapsLedStats lls
    WHERE {component_table}.ID = lls.id AND {component_table}.needstatsupdate = 1;
    """
    cur.execute(query)

update_laps_led_for_component(cur, "Constructors", "constructorid")
update_laps_led_for_component(cur, "Engines", "engineid")
update_laps_led_for_component(cur, "Chassis", "chassisid")
update_laps_led_for_component(cur, "EngineModels", "enginemodelid")
update_laps_led_for_component(cur, "Tyres", "tyreid")
update_laps_led_for_component(cur, "Teams", "teamid")
update_laps_led_for_component(cur, "Drivers", "driverid")
update_laps_led_for_component(cur, "Nationalities", "nationalityid")
print("GrandPrixLapsLed and SprintLapsLed stats updated.")

cur.execute("SELECT Season FROM Seasons WHERE needstatsupdate = 1 ORDER BY Season")
seasons_to_update = [row[0] for row in cur.fetchall()]

if seasons_to_update:
    max_season = max(seasons_to_update)

    cur.execute("SELECT Season, COUNT(*) FROM GrandsPrix WHERE Season <= ? GROUP BY Season", (max_season,))
    grand_prix_counts = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("""
        SELECT gp.Season,
               gr.driverid, gr.constructorid, gr.engineid, gr.teamid, gr.enginemodelid,
               gr.chassisid, gr.nationalityid, gr.raceposition, gr.qualifyingposition,
               gr.fastestlap, gr.racepoints, gr.sprintpoints, gr.sprintposition,
               gr.sprint_qualifyingposition, gr.sprintfastestlap
        FROM GrandPrixResults gr
        JOIN GrandsPrix gp ON gr.grandprixid = gp.ID
        WHERE gp.Season <= ?
    """, (max_season,))

    season_stats = {}
    def add_if_not_none(target_set, value):
        if value is not None:
            target_set.add(value)

    for (season, driverid, constructorid, engineid, teamid, enginemodelid,
         chassisid, nationalityid, raceposition, qualifyingposition, fastestlap,
         racepoints, sprintpoints, sprintposition, sprint_qualifyingposition,
         sprintfastestlap) in cur.fetchall():
        
        stats = season_stats.setdefault(season, {
            'drivers': set(), 'constructors': set(), 'engines': set(), 'teams': set(),
            'enginemodels': set(), 'chassis': set(), 'nationalities': set(),
            'unique_winners': set(), 'unique_podiums': set(), 'unique_poles': set(),
            'unique_fastest': set(), 'points_scorers': set(),
            'unique_sprint_winners': set(), 'unique_sprint_podiums': set(),
            'unique_sprint_poles': set(), 'unique_sprint_fastest': set(),
            'sprint_points_scorers': set()
        })

        add_if_not_none(stats['drivers'], driverid)
        add_if_not_none(stats['constructors'], constructorid)
        add_if_not_none(stats['engines'], engineid)
        add_if_not_none(stats['teams'], teamid)
        add_if_not_none(stats['enginemodels'], enginemodelid)
        add_if_not_none(stats['chassis'], chassisid)
        add_if_not_none(stats['nationalities'], nationalityid)

        if raceposition == 1: add_if_not_none(stats['unique_winners'], driverid)
        if raceposition is not None and raceposition <= 3: add_if_not_none(stats['unique_podiums'], driverid)
        if qualifyingposition == 1: add_if_not_none(stats['unique_poles'], driverid)
        if fastestlap == 1: add_if_not_none(stats['unique_fastest'], driverid)
        if (racepoints or 0) > 0 or (sprintpoints or 0) > 0: add_if_not_none(stats['points_scorers'], driverid)
        
        if sprintposition == 1: add_if_not_none(stats['unique_sprint_winners'], driverid)
        if sprintposition is not None and sprintposition <= 3: add_if_not_none(stats['unique_sprint_podiums'], driverid)
        if sprint_qualifyingposition == 1: add_if_not_none(stats['unique_sprint_poles'], driverid)
        if sprintfastestlap == 1: add_if_not_none(stats['unique_sprint_fastest'], driverid)
        if (sprintpoints or 0) > 0: add_if_not_none(stats['sprint_points_scorers'], driverid)

    prior_sets = {
        'points_scorers': set(), 'winners': set(), 'podiums': set(), 'poles': set(),
        'fastest': set(), 'sprint_winners': set(), 'sprint_podiums': set(),
        'sprint_poles': set(), 'sprint_fastest': set(), 'sprint_points_scorers': set()
    }

    for season in sorted(seasons_to_update):
        stats = season_stats.get(season, {
            'drivers': set(), 'constructors': set(), 'engines': set(), 'teams': set(),
            'enginemodels': set(), 'chassis': set(), 'nationalities': set(),
            'unique_winners': set(), 'unique_podiums': set(), 'unique_poles': set(),
            'unique_fastest': set(), 'points_scorers': set(),
            'unique_sprint_winners': set(), 'unique_sprint_podiums': set(),
            'unique_sprint_poles': set(), 'unique_sprint_fastest': set(),
            'sprint_points_scorers': set()
        })

        cur.execute("""
            UPDATE Seasons SET
                TotalGrandPrix = ?, TotalDrivers = ?, TotalConstructors = ?, TotalEngines = ?,
                TotalTeams = ?, TotalEngineModels = ?, TotalChassis = ?, TotalNationalities = ?,
                TotalUniqueWinners = ?, TotalUniquePodiumFinishers = ?, TotalUniquePolePositions = ?, TotalUniqueFastestLapGetters = ?,
                TotalDriversWithPoints = ?, TotalFirstTimePointsScorers = ?, TotalFirstTimeWinners = ?, TotalFirstTimePodiumFinishers = ?,
                TotalFirstTimePoleSitters = ?, TotalFirstTimeFastestLapGetters = ?, TotalUniqueSprintWinners = ?, TotalUniqueSprintPodiumFinishers = ?,
                TotalUniqueSprintPolePositions = ?, TotalUniqueSprintFastestLapGetters = ?, TotalDriversWithSprintPoints = ?, TotalFirstTimeSprintWinners = ?,
                TotalFirstTimeSprintPodiumFinishers = ?, TotalFirstTimeSprintPoleSitters = ?, TotalFirstTimeSprintFastestLapGetters = ?, TotalFirstTimeSprintPointsScorers = ?
            WHERE Season = ?
        """, (
            grand_prix_counts.get(season, 0), len(stats['drivers']), len(stats['constructors']), len(stats['engines']),
            len(stats['teams']), len(stats['enginemodels']), len(stats['chassis']), len(stats['nationalities']),
            len(stats['unique_winners']), len(stats['unique_podiums']), len(stats['unique_poles']), len(stats['unique_fastest']),
            len(stats['points_scorers']), len(stats['points_scorers'] - prior_sets['points_scorers']), len(stats['unique_winners'] - prior_sets['winners']), len(stats['unique_podiums'] - prior_sets['podiums']),
            len(stats['unique_poles'] - prior_sets['poles']), len(stats['unique_fastest'] - prior_sets['fastest']), len(stats['unique_sprint_winners']), len(stats['unique_sprint_podiums']),
            len(stats['unique_sprint_poles']), len(stats['unique_sprint_fastest']), len(stats['sprint_points_scorers']), len(stats['unique_sprint_winners'] - prior_sets['sprint_winners']),
            len(stats['unique_sprint_podiums'] - prior_sets['sprint_podiums']), len(stats['unique_sprint_poles'] - prior_sets['sprint_poles']), len(stats['unique_sprint_fastest'] - prior_sets['sprint_fastest']), len(stats['sprint_points_scorers'] - prior_sets['sprint_points_scorers']),
            season
        ))

        prior_sets['points_scorers'].update(stats['points_scorers'])
        prior_sets['winners'].update(stats['unique_winners'])
        prior_sets['podiums'].update(stats['unique_podiums'])
        prior_sets['poles'].update(stats['unique_poles'])
        prior_sets['fastest'].update(stats['unique_fastest'])
        prior_sets['sprint_winners'].update(stats['unique_sprint_winners'])
        prior_sets['sprint_podiums'].update(stats['unique_sprint_podiums'])
        prior_sets['sprint_poles'].update(stats['unique_sprint_poles'])
        prior_sets['sprint_fastest'].update(stats['unique_sprint_fastest'])
        prior_sets['sprint_points_scorers'].update(stats['sprint_points_scorers'])

print("Seasons stats updated.")

# Flip all things back to 0 now that we're done
tables_to_reset = ["Drivers", "Constructors", "Engines", "Chassis", "EngineModels", "Tyres", "Teams", "Nationalities", "Seasons"]
for table in tables_to_reset:
    cur.execute(f"UPDATE {table} SET needstatsupdate = 0 WHERE needstatsupdate = 1")

conn.commit()
print("All stats successfully updated and flags reset.")

print("Running database optimization (this may take a moment)...")
cur.execute("VACUUM")
print("Database optimization complete.")

conn.close()
#fi.close()
