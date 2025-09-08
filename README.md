If you're an F1 nerd like me, sometimes questions arise in your mind:

  - When was the last time two people shared a car in a Grand Prix?

  - Both the Toyotas were on dry tyres at the end of the 2008 Brazilian Grand Prix, so how did Glock's lap times compare to Trulli's?

  - What was the fastest and slowest lap times ever?

  - How many laps have been raced in Formula One history?

  - How much distance has Formula One raced? 

  - What was the race with the most shared cars ever?

  - How many laps in Formula One have been under the safety car/virtual safety car?

Some of this questions cannot be answered by search engines unfortunately.

So, if you're a programmer like me, your answer is just a few SELECTs away.

Or, you can do some cool data analysis with all this data.



## Download the latest version:
To download the latest version of the database, please visit this link: [https://drive.google.com/file/d/1M3ijJIWDEGqGOw4Prx2AXFhts2cv-J1d/view](https://drive.google.com/file/d/1M3ijJIWDEGqGOw4Prx2AXFhts2cv-J1d/view)


OR

```bash
pip install gdown 
python download_db.py
```
**Last updated: 2025 Italian Grand Prix**

## Update the database:
If you want to update the database, all you need to do is run this command:
```bash
pip install beautifulsoup4
python writedb.py
```

## Reset/initialise the database:
If, for whatever reason, you want to wipe out all the data in the database or you want to create the database with all the tables and columns, run this command:
```bash
python reset.py
```

## Known errors
- Practice times for everyone who is not the leader is just the gap.
- GrandSlams is not working
- Take the stats in the subtables with a pinch of salt, isn't always accurate.




## Tables

1. ### Seasons
   This table contains a set of all seasons in F1, from 1950 to the present day.  
   **Columns:**
   - **Season**: The year (e.g. 1982). _INTEGER PRIMARY KEY_
   - **DriversRacesCounted**: How many races counted for drivers. _TEXT_
   - **PointsSharedForSharedCars**: Whether points were shared for shared cars. _BOOLEAN_
   - **GrandPrixPointsSystemDrivers**: Points system for drivers. _TEXT_
   - **SprintPointsSystemDrivers**: Sprint points system for drivers. _TEXT_
   - **ConstructorsRacesCounted**: How many races counted for constructors. _TEXT_
   - **PointsOnlyForTopScoringCar**: Only top scoring car counted for constructors. _BOOLEAN_
   - **GrandPrixPointsSystemConstructors**: Points system for constructors. _TEXT_
   - **SprintPointsSystemConstructors**: Sprint points system for constructors. _TEXT_
   - **RegulationNotes**: Notes about regulations. _TEXT_
   - **MinimumWeightofCars**: Minimum car weight. _TEXT_
   - **EngineType**: Engine type. _TEXT_
   - **Supercharging**: Supercharging allowed. _TEXT_
   - **MaxCylinderCapacity**: Maximum cylinder capacity. _TEXT_
   - **NumberOfCylinders**: Number of cylinders. _TEXT_
   - **MaxRPM**: Maximum RPM. _TEXT_
   - **NumberOfEnginesAllowedPerSeason**: Engine allocation per season. _TEXT_
   - **FuelType**: Fuel type. _TEXT_
   - **RefuellingAllowed**: Refuelling allowed. _TEXT_
   - **MaxFuelConsumption**: Maximum fuel consumption. _TEXT_

2. ### Circuits
   This table contains all circuits which have hosted a Grand Prix.  
   **Columns:**
   - **ID**: Unique circuit ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
   - **CircuitName**: Name of the circuit. _TEXT_
   - **FirstGrandPrix**: First Grand Prix held. _TEXT_
   - **LastGrandPrix**: Last Grand Prix held. _TEXT_
   - **GrandPrixCount**: Number of GPs held. _INTEGER DEFAULT 0_
   - **FirstGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
   - **LastGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_

3. ### GrandsPrix
   This table contains all Grands Prix in the database.  
   **Columns:**
   - **ID**: Unique Grand Prix ID. _INTEGER PRIMARY KEY_
   - **Season**: Year of the Grand Prix. _INTEGER_
   - **GrandPrixName**: Name of the Grand Prix. _TEXT_
   - **RoundNumber**: Round number in the season. _INTEGER_
   - **CircuitName**: Name of the circuit. _TEXT_
   - **Date**: Date of the Grand Prix. _TEXT_
   - **DateInDateTime**: Date as datetime. _TEXT_
   - **Laps**: Number of laps. _INTEGER_
   - **CircuitLength**: Circuit length. _TEXT_
   - **Weather**: Weather conditions. _TEXT_
   - **Notes**: Notes about the race. _TEXT_
   - **SprintWeekend**: Whether it was a sprint weekend. _BOOLEAN_
   - **CircuitID**: Foreign key to Circuits. _INTEGER_
   - **EntrantsNotes**: Notes about entrants. _TEXT_
   - **QualifyingNotes**: Notes about qualifying. _TEXT_
   - **StartingGridNotes**: Notes about starting grid. _TEXT_
   - **RaceResultNotes**: Notes about race result. _TEXT_
   - **SprintNotes**: Notes about sprint. _TEXT_
   - **SprintGridNotes**: Notes about sprint grid. _TEXT_

4. ### Drivers
   This table contains all drivers who have entered a World Championship Grand Prix.  
   **Columns:**
   - **ID**: Unique driver ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
   - **Name**: Full name. _TEXT UNIQUE_
   - **Nationality**: Nationality. _TEXT_
   - **Birthdate**: Birth date. _TEXT_
   - **Wins**: Number of wins. _INTEGER_
   - **Podiums**: Number of podiums. _INTEGER_
   - **Poles**: Number of pole positions. _INTEGER_
   - **FastestLaps**: Number of fastest laps. _INTEGER_
   - **Championships**: Number of championships. _INTEGER_
   - **Points**: Total points. _REAL_
   - **Starts**: Number of starts. _INTEGER_
   - **Entries**: Number of entries. _INTEGER_
   - **DNFs**: Number of DNFs. _INTEGER_
   - **LapsLed**: Number of laps led. _INTEGER_
   - **HatTricks**: Number of hat tricks. _INTEGER_
   - **GrandSlams**: Number of grand slams. _INTEGER_
   - **BestGridPosition**: Best grid position. _INTEGER_
   - **BestSprintGridPosition**: Best sprint grid position. _INTEGER_
   - **BestQualifyingPosition**: Best qualifying position. _INTEGER_
   - **BestRacePosition**: Best race position. _INTEGER_
   - **BestSprintPosition**: Best sprint position. _INTEGER_
   - **BestChampionshipPosition**: Best championship position. _INTEGER_
   - **FirstGrandPrix**: First Grand Prix. _TEXT_
   - **LastGrandPrix**: Last Grand Prix. _TEXT_
   - **NationalityID**: Foreign key to Nationalities. _INTEGER_
   - **FirstGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
   - **LastGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_

5. ### Teams
   This table contains all teams that have entered a Grand Prix.  
   **Columns:**
   - **ID**: Unique team ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
   - **TeamName**: Name of the team. _TEXT UNIQUE_
   - **FirstGrandPrix**: First Grand Prix. _TEXT_
   - **LastGrandPrix**: Last Grand Prix. _TEXT_
   - **Wins**: Number of wins. _INTEGER_
   - **Podiums**: Number of podiums. _INTEGER_
   - **Poles**: Number of pole positions. _INTEGER_
   - **FastestLaps**: Number of fastest laps. _INTEGER_
   - **LapsLed**: Number of laps led. _INTEGER_
   - **Starts**: Number of starts. _INTEGER_
   - **Entries**: Number of entries. _INTEGER_
   - **DNFs**: Number of DNFs. _INTEGER_
   - **Points**: Total points. _REAL_
   - **BestGridPosition**: Best grid position. _INTEGER_
   - **BestSprintGridPosition**: Best sprint grid position. _INTEGER_
   - **BestQualifyingPosition**: Best qualifying position. _INTEGER_
   - **BestRacePosition**: Best race position. _INTEGER_
   - **BestSprintPosition**: Best sprint position. _INTEGER_
   - **FirstGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
   - **LastGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_

6. ### Constructors
   This table contains all constructors who have made a chassis that entered a Grand Prix.  
   **Columns:**
   - **ID**: Unique constructor ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
   - **ConstructorName**: Name of the constructor. _TEXT UNIQUE_
   - **Wins**: Number of wins. _INTEGER_
   - **Podiums**: Number of podiums. _INTEGER_
   - **Poles**: Number of pole positions. _INTEGER_
   - **FastestLaps**: Number of fastest laps. _INTEGER_
   - **Championships**: Number of championships. _INTEGER_
   - **Points**: Total points. _REAL_
   - **Starts**: Number of starts. _INTEGER_
   - **Entries**: Number of entries. _INTEGER_
   - **DNFs**: Number of DNFs. _INTEGER_
   - **LapsLed**: Number of laps led. _INTEGER_
   - **BestGridPosition**: Best grid position. _INTEGER_
   - **BestSprintGridPosition**: Best sprint grid position. _INTEGER_
   - **BestQualifyingPosition**: Best qualifying position. _INTEGER_
   - **BestRacePosition**: Best race position. _INTEGER_
   - **BestSprintPosition**: Best sprint position. _INTEGER_
   - **BestChampionshipPosition**: Best championship position. _INTEGER_
   - **FirstGrandPrix**: First Grand Prix. _TEXT_
   - **LastGrandPrix**: Last Grand Prix. _TEXT_
   - **FirstGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
   - **LastGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_

7. ### Engines
   This table contains all engines to power an entry in a Grand Prix.  
   **Columns:**
   - **ID**: Unique engine ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
   - **EngineName**: Name of the engine. _TEXT UNIQUE_
   - **Wins**: Number of wins. _INTEGER_
   - **Podiums**: Number of podiums. _INTEGER_
   - **Poles**: Number of pole positions. _INTEGER_
   - **FastestLaps**: Number of fastest laps. _INTEGER_
   - **Championships**: Number of championships. _INTEGER_
   - **Points**: Total points. _REAL_
   - **Starts**: Number of starts. _INTEGER_
   - **Entries**: Number of entries. _INTEGER_
   - **DNFs**: Number of DNFs. _INTEGER_
   - **LapsLed**: Number of laps led. _INTEGER_
   - **BestGridPosition**: Best grid position. _INTEGER_
   - **BestSprintGridPosition**: Best sprint grid position. _INTEGER_
   - **BestQualifyingPosition**: Best qualifying position. _INTEGER_
   - **BestRacePosition**: Best race position. _INTEGER_
   - **BestSprintPosition**: Best sprint position. _INTEGER_
   - **FirstGrandPrix**: First Grand Prix. _TEXT_
   - **LastGrandPrix**: Last Grand Prix. _TEXT_
   - **FirstGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
   - **LastGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_

8. ### Tyres
   This table contains all tyre manufacturers that have provided tyres to an entry.  
   **Columns:**
   - **ID**: Unique tyre ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
   - **TyreName**: Name of the tyre. _TEXT UNIQUE_
   - **Wins**: Number of wins. _INTEGER_
   - **Podiums**: Number of podiums. _INTEGER_
   - **Poles**: Number of pole positions. _INTEGER_
   - **FastestLaps**: Number of fastest laps. _INTEGER_
   - **Points**: Total points. _REAL_
   - **Starts**: Number of starts. _INTEGER_
   - **Entries**: Number of entries. _INTEGER_
   - **DNFs**: Number of DNFs. _INTEGER_
   - **LapsLed**: Number of laps led. _INTEGER_
   - **BestGridPosition**: Best grid position. _INTEGER_
   - **BestSprintGridPosition**: Best sprint grid position. _INTEGER_
   - **BestQualifyingPosition**: Best qualifying position. _INTEGER_
   - **BestRacePosition**: Best race position. _INTEGER_
   - **BestSprintPosition**: Best sprint position. _INTEGER_
   - **FirstGrandPrix**: First Grand Prix. _TEXT_
   - **LastGrandPrix**: Last Grand Prix. _TEXT_
   - **FirstGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
   - **LastGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_

9. ### Chassis
   This table contains all chassis to enter a race in Formula One.  
   **Columns:**
   - **ID**: Unique chassis ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
   - **ConstructorName**: Name of the constructor. _TEXT_
   - **ChassisName**: Name of the chassis. _TEXT UNIQUE_
   - **ConstructorID**: Foreign key to Constructors. _INTEGER_
   - **Wins**: Number of wins. _INTEGER_
   - **Podiums**: Number of podiums. _INTEGER_
   - **Poles**: Number of pole positions. _INTEGER_
   - **FastestLaps**: Number of fastest laps. _INTEGER_
   - **Championships**: Number of championships. _INTEGER_
   - **Points**: Total points. _REAL_
   - **Starts**: Number of starts. _INTEGER_
   - **Entries**: Number of entries. _INTEGER_
   - **DNFs**: Number of DNFs. _INTEGER_
   - **LapsLed**: Number of laps led. _INTEGER_
   - **BestGridPosition**: Best grid position. _INTEGER_
   - **BestSprintGridPosition**: Best sprint grid position. _INTEGER_
   - **BestQualifyingPosition**: Best qualifying position. _INTEGER_
   - **BestRacePosition**: Best race position. _INTEGER_
   - **BestSprintPosition**: Best sprint position. _INTEGER_
   - **FirstGrandPrix**: First Grand Prix. _TEXT_
   - **LastGrandPrix**: Last Grand Prix. _TEXT_
   - **ConstructorID**: Foreign key to Constructors. _INTEGER_
   - **FirstGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
   - **LastGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_

10. ### EngineModels
    This table contains all engine models used in F1.  
    **Columns:**
    - **ID**: Unique engine model ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
    - **EngineMake**: Engine make. _TEXT_
    - **EngineModel**: Engine model. _TEXT UNIQUE_
    - **EngineMakeID**: Foreign key to Engines. _INTEGER_
    - **Wins**: Number of wins. _INTEGER_
    - **Podiums**: Number of podiums. _INTEGER_
    - **Poles**: Number of pole positions. _INTEGER_
    - **FastestLaps**: Number of fastest laps. _INTEGER_
    - **Championships**: Number of championships. _INTEGER_
    - **Points**: Total points. _REAL_
    - **Starts**: Number of starts. _INTEGER_
    - **Entries**: Number of entries. _INTEGER_
    - **DNFs**: Number of DNFs. _INTEGER_
    - **LapsLed**: Number of laps led. _INTEGER_
    - **BestGridPosition**: Best grid position. _INTEGER_
    - **BestSprintGridPosition**: Best sprint grid position. _INTEGER_
    - **BestQualifyingPosition**: Best qualifying position. _INTEGER_
    - **BestRacePosition**: Best race position. _INTEGER_
    - **BestSprintPosition**: Best sprint position. _INTEGER_
    - **FirstGrandPrix**: First Grand Prix. _TEXT_
    - **LastGrandPrix**: Last Grand Prix. _TEXT_
    - **EngineMakeID**: Foreign key to Engines. _INTEGER_
    - **FirstGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
    - **LastGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_

11. ### GrandPrixResults
    This table contains all race entrants for each Grand Prix, with all session results and penalties.  
    **Columns:**
    - **grandprix**: Grand Prix name. _TEXT_
    - **number**: Car number. _INTEGER_
    - **driver**: Driver name. _TEXT_
    - **nationality**: Nationality. _TEXT_
    - **team**: Team name. _TEXT_
    - **constructor**: Constructor name. _TEXT_
    - **chassis**: Chassis name. _TEXT_
    - **engine**: Engine name. _TEXT_
    - **enginemodel**: Engine model. _TEXT_
    - **tyre**: Tyre name. _TEXT_
    - **substituteorthirddriver**: Substitute or third driver. _BOOLEAN_
    - **qualifyingposition**: Qualifying position. _INTEGER_
    - **qualifyingtime**: Qualifying time. _TEXT_
    - **qualifyinggap**: Qualifying gap. _TEXT_
    - **qualifyingtimeinseconds**: Qualifying time in seconds. _REAL_
    - **qualifyinggapseconds**: Qualifying gap in seconds. _REAL_
    - **starting_grid_position**: Starting grid position. _INTEGER_
    - **gridpenalty**: Grid penalty. _TEXT_
    - **gridpenalty_reason**: Grid penalty reason. _TEXT_
    - **sprintstarting_grid_position**: Sprint starting grid position. _INTEGER_
    - **sprintgridpenalty**: Sprint grid penalty. _TEXT_
    - **sprintgridpenalty_reason**: Sprint grid penalty reason. _TEXT_
    - **fastestlap**: Fastest lap position. _INTEGER_
    - **fastestlapinseconds**: Fastest lap in seconds. _REAL_
    - **fastestlapgapinseconds**: Fastest lap gap in seconds. _REAL_
    - **fastestlap_time**: Fastest lap time. _TEXT_
    - **fastestlap_gap**: Fastest lap gap. _TEXT_
    - **fastestlap_lap**: Lap of fastest lap. _INTEGER_
    - **sprintfastestlap**: Sprint fastest lap position. _INTEGER_
    - **sprintfastestlapinseconds**: Sprint fastest lap in seconds. _REAL_
    - **sprintfastestlapgapinseconds**: Sprint fastest lap gap in seconds. _REAL_
    - **sprintfastestlap_time**: Sprint fastest lap time. _TEXT_
    - **sprintfastestlap_gap**: Sprint fastest lap gap. _TEXT_
    - **sprintfastestlap_lap**: Sprint fastest lap lap. _INTEGER_
    - **qualifying2position**: Q2 position. _INTEGER_
    - **qualifying2time**: Q2 time. _TEXT_
    - **qualifying2gap**: Q2 gap. _REAL_
    - **qualifying2timeinseconds**: Q2 time in seconds. _REAL_
    - **qualifying2laps**: Q2 laps. _INTEGER_
    - **qualifying1position**: Q1 position. _INTEGER_
    - **qualifying1time**: Q1 time. _TEXT_
    - **qualifying1gap**: Q1 gap. _REAL_
    - **qualifying1timeinseconds**: Q1 time in seconds. _REAL_
    - **qualifying1laps**: Q1 laps. _INTEGER_
    - **qualifyinglaps**: Qualifying laps. _INTEGER_
    - **qualifying3time**: Q3 time. _TEXT_
    - **qualifying3gap**: Q3 gap. _REAL_
    - **qualifying3timeinseconds**: Q3 time in seconds. _REAL_
    - **sprint_qualifyingposition**: Sprint qualifying position. _INTEGER_
    - **sprint_qualifying1time**: Sprint Q1 time. _TEXT_
    - **sprint_qualifying2time**: Sprint Q2 time. _TEXT_
    - **sprint_qualifying3time**: Sprint Q3 time. _TEXT_
    - **sprint_qualifying1gap**: Sprint Q1 gap. _REAL_
    - **sprint_qualifying2gap**: Sprint Q2 gap. _REAL_
    - **sprint_qualifying3gap**: Sprint Q3 gap. _REAL_
    - **sprint_qualifyinggap**: Sprint qualifying gap. _REAL_
    - **sprint_qualifying1timeinseconds**: Sprint Q1 time in seconds. _REAL_
    - **sprint_qualifying2timeinseconds**: Sprint Q2 time in seconds. _REAL_
    - **sprint_qualifying3timeinseconds**: Sprint Q3 time in seconds. _REAL_
    - **sprint_qualifyinglaps**: Sprint qualifying laps. _INTEGER_
    - **sprint_qualifyingtime**: Sprint qualifying time. _TEXT_
    - **sprint_qualifyingtimeinseconds**: Sprint qualifying time in seconds. _REAL_
    - **warmupposition**: Warmup position. _INTEGER_
    - **warmuptime**: Warmup time. _TEXT_
    - **warmupgap**: Warmup gap. _TEXT_
    - **warmuptimeinseconds**: Warmup time in seconds. _REAL_
    - **warmuplaps**: Warmup laps. _INTEGER_
    - **practice1position**: Practice 1 position. _INTEGER_
    - **practice1time**: Practice 1 time. _TEXT_
    - **practice1gap**: Practice 1 gap. _TEXT_
    - **practice1timeinseconds**: Practice 1 time in seconds. _REAL_
    - **practice1laps**: Practice 1 laps. _INTEGER_
    - **practice2position**: Practice 2 position. _INTEGER_
    - **practice2time**: Practice 2 time. _TEXT_
    - **practice2gap**: Practice 2 gap. _TEXT_
    - **practice2timeinseconds**: Practice 2 time in seconds. _REAL_
    - **practice2laps**: Practice 2 laps. _INTEGER_
    - **practice3position**: Practice 3 position. _INTEGER_
    - **practice3time**: Practice 3 time. _TEXT_
    - **practice3gap**: Practice 3 gap. _TEXT_
    - **practice3timeinseconds**: Practice 3 time in seconds. _REAL_
    - **practice3laps**: Practice 3 laps. _INTEGER_
    - **practice4position**: Practice 4 position. _INTEGER_
    - **practice4time**: Practice 4 time. _TEXT_
    - **practice4gap**: Practice 4 gap. _TEXT_
    - **practice4timeinseconds**: Practice 4 time in seconds. _REAL_
    - **practice4laps**: Practice 4 laps. _INTEGER_
    - **sprintposition**: Sprint position. _INTEGER_
    - **sprintlaps**: Sprint laps. _INTEGER_
    - **sprinttime**: Sprint time. _TEXT_
    - **sprintpoints**: Sprint points. _REAL_
    - **sprinttimeinseconds**: Sprint time in seconds. _REAL_
    - **sprintgap**: Sprint gap. _TEXT_
    - **sprintgapinseconds**: Sprint gap in seconds. _REAL_
    - **raceposition**: Race position. _INTEGER_
    - **racelaps**: Race laps. _INTEGER_
    - **racetime**: Race time. _TEXT_
    - **racepoints**: Race points. _REAL_
    - **racetimeinseconds**: Race time in seconds. _REAL_
    - **racegap**: Race gap. _TEXT_
    - **racegapinseconds**: Race gap in seconds. _REAL_
    - **penalties**: Penalties (JSON). _TEXT_
    - **sprint_penalties**: Sprint penalties (JSON). _TEXT_
    - **driverid**: Foreign key to Drivers. _INTEGER_
    - **teamid**: Foreign key to Teams. _INTEGER_
    - **constructorid**: Foreign key to Constructors. _INTEGER_
    - **chassisid**: Foreign key to Chassis. _INTEGER_
    - **engineid**: Foreign key to Engines. _INTEGER_
    - **enginemodelid**: Foreign key to EngineModels. _INTEGER_
    - **tyreid**: Foreign key to Tyres. _INTEGER_
    - **grandprixid**: Foreign key to GrandsPrix. _INTEGER_
    - **nationalityid**: Foreign key to Nationalities. _INTEGER_

12. ### PitStopSummary
    This table shows the pit stops done during the race.  
    **Columns:**
    - **ID**: Unique pit stop ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
    - **GrandPrix**: Name of the Grand Prix. _TEXT_
    - **Number**: Car number. _INTEGER_
    - **Driver**: Driver name. _TEXT_
    - **Constructor**: Constructor name. _TEXT_
    - **StopNumber**: Stop number. _INTEGER_
    - **Lap**: Lap of the stop. _INTEGER_
    - **DurationSpentInPitLane**: Duration in pit lane. _TEXT_
    - **TimeInSeconds**: Duration in seconds. _REAL_
    - **TimeOfDayStopped**: Time of day. _TEXT_
    - **TotalTimeSpentInPitLane**: Total pit lane time. _TEXT_
    - **TotalTimeinSeconds**: Total pit lane time in seconds. _REAL_
    - **GrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
    - **DriverID**: Foreign key to Drivers. _INTEGER_
    - **ConstructorID**: Foreign key to Constructors. _INTEGER_

13. ### LapByLap
    This table has the lap-by-lap data for each race.  
    **Columns:**
    - **ID**: Unique lap-by-lap ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
    - **GrandPrix**: Name of the Grand Prix. _TEXT_
    - **Driver**: Driver name. _TEXT_
    - **Position**: Position on lap. _INTEGER_
    - **Lap**: Lap number. _INTEGER_
    - **Type**: Session type. _TEXT_
    - **SafetyCar**: Safety car status. _BOOLEAN_
    - **Time**: Lap time. _TEXT_
    - **TimeInSeconds**: Lap time in seconds. _REAL_
    - **GrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
    - **DriverID**: Foreign key to Drivers. _INTEGER_

14. ### DriversChampionship
    This table has the championship results for drivers for every year.  
    **Columns:**
    - **ID**: Unique ID (year+driver). _TEXT PRIMARY KEY_
    - **Season**: Year. _INTEGER_
    - **Position**: Position in standings. _INTEGER_
    - **Driver**: Driver name. _TEXT_
    - **Points**: Points scored. _REAL_
    - **OutOf**: Points out of. _REAL_
    - **RaceByRace**: JSON of race-by-race points. _TEXT_
    - **DriverID**: Foreign key to Drivers. _INTEGER_
    - **NationalityID**: Foreign key to Nationalities. _INTEGER_

15. ### ConstructorsChampionship
    This table has the championship results for constructors for every year.  
    **Columns:**
    - **ID**: Unique ID (year+constructor+engine). _TEXT PRIMARY KEY_
    - **Season**: Year. _INTEGER_
    - **Position**: Position in standings. _INTEGER_
    - **Constructor**: Constructor name. _TEXT_
    - **Engine**: Engine name. _TEXT_
    - **Points**: Points scored. _REAL_
    - **OutOf**: Points out of. _REAL_
    - **RaceByRace**: JSON of race-by-race points. _TEXT_
    - **ConstructorID**: Foreign key to Constructors. _INTEGER_
    - **EngineID**: Foreign key to Engines. _INTEGER_
    - **EngineModelID**: Foreign key to EngineModels. _INTEGER_

16. ### InSeasonProgressDrivers
    This table has the progress of each driver over the season.  
    **Columns:**
    - **ID**: Unique ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
    - **GrandPrix**: Name of the Grand Prix. _TEXT_
    - **PositionAtThisPoint**: Position at this point. _INTEGER_
    - **Driver**: Driver name. _TEXT_
    - **PointsAtThisPoint**: Points at this point. _REAL_
    - **GrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
    - **DriverID**: Foreign key to Drivers. _INTEGER_

17. ### InSeasonProgressConstructors
    This table has the progress of each constructor over the season.  
    **Columns:**
    - **ID**: Unique ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
    - **GrandPrix**: Name of the Grand Prix. _TEXT_
    - **PositionAtThisPoint**: Position at this point. _INTEGER_
    - **Constructor**: Constructor name. _TEXT_
    - **Engine**: Engine name. _TEXT_
    - **PointsAtThisPoint**: Points at this point. _REAL_
    - **GrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
    - **ConstructorID**: Foreign key to Constructors. _INTEGER_
    - **EngineID**: Foreign key to Engines. _INTEGER_

18. ### Nationalities
    This table contains all nationalities that have participated in F1.  
    **Columns:**
    - **ID**: Unique nationality ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
    - **Nationality**: Nationality. _TEXT UNIQUE_
    - **FirstGrandPrix**: First Grand Prix. _TEXT_
    - **LastGrandPrix**: Last Grand Prix. _TEXT_
    - **DriverCount**: Number of drivers. _INTEGER DEFAULT 0_
    - **Wins**: Number of wins. _INTEGER DEFAULT 0_
    - **Podiums**: Number of podiums. _INTEGER DEFAULT 0_
    - **Poles**: Number of pole positions. _INTEGER DEFAULT 0_
    - **FastestLaps**: Number of fastest laps. _INTEGER DEFAULT 0_
    - **Championships**: Number of championships. _INTEGER DEFAULT 0_
    - **Points**: Total points. _REAL DEFAULT 0_
    - **Starts**: Number of starts. _INTEGER DEFAULT 0_
    - **Entries**: Number of entries. _INTEGER DEFAULT 0_
    - **DNFs**: Number of DNFs. _INTEGER DEFAULT 0_
    - **LapsLed**: Number of laps led. _INTEGER DEFAULT 0_
    - **BestGridPosition**: Best grid position. _INTEGER_
    - **BestSprintGridPosition**: Best sprint grid position. _INTEGER_
    - **BestQualifyingPosition**: Best qualifying position. _INTEGER_
    - **BestRacePosition**: Best race position. _INTEGER_
    - **BestSprintPosition**: Best sprint position. _INTEGER_
    - **FirstGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
    - **LastGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
    - **FirstDriver**: First driver. _TEXT_
    - **LastDriver**: Last driver. _TEXT_
    - **FirstDriverID**: Foreign key to Drivers. _INTEGER_
    - **LastDriverID**: Foreign key to Drivers. _INTEGER_

