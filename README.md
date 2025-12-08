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

---

#### Note:
This database has every single Grand Prix part of the _World Championship_. It does not contain non-Championship Grands Prix. When the word "Grand Prix" is used here, it refers to a World Championship Grand Prix. Similarly, when the word "Formula One", "F1", "Formula 1", or any of its variants have been used here, it refers to the _World Championship_, even though the 1952 and 1953 seasons were run to F2 regulations. The terms "Formula One", "Grand Prix", and "World Championship" are used synonymously.


## Download the latest version:
To download the latest version of the database, please visit this link: [https://drive.google.com/file/d/1M3ijJIWDEGqGOw4Prx2AXFhts2cv-J1d/view](https://drive.google.com/file/d/1M3ijJIWDEGqGOw4Prx2AXFhts2cv-J1d/view)


OR

```bash
pip install gdown 
python download_db.py
```
**Last updated: 2025 Abu Dhabi Grand Prix**

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
- The column "GrandSlams" for the table "Drivers" is zero for every single driver.



## Tables

1. ### Seasons
   This table contains a set of all seasons in F1, from 1950 to the present day.  
   **Columns:**
   - **Season**: The year (e.g. 1982). _INTEGER PRIMARY KEY_
   - **DriversRacesCounted**: How many races counted for drivers. _TEXT_ 

   From 1950 till 1990, you could drop your worst results. In other words, say, for a season, only the points collected for a driver's best 11 races would count towards the championship. It could also be like the best 6 races from the first 7 races, and the best 7 results from the last eight races counted towards the championship.

   Values can range from "Best 11 scores." to 
   
   "Best 5 scores from first 7 races.

   Best 5 scores from last 7 races."

   to "All scores and points are doubled for the last Grand Prix." for the 2014 season. If all races are counted, the value is "All scores."
   - **PointsSharedForSharedCars**: Whether points were shared for shared cars. _BOOLEAN_

   From 1950 till 1957, drivers who shared the same car would have their points shared proportionate to the laps they drove. In other words, Driver A could do 20 laps in a Grand Prix and Driver B would do the other 40 laps. Points would be shared accordingly to both drivers, although it would get a bit complicated. To see an example of this, you may see the results of the [1955 Argentine Grand Prix](https://www.formula1.com/en/results/1955/races/135/argentina/race-result).

   The value is ```true``` if points were shared for shared cars and ```false``` if points were not shared for shared cars.
   - **GrandPrixPointsSystemDrivers**: Points system for drivers. (JSON) _TEXT_
   
   For any row, the data is stored in the following format:

   **Keys**:
   Position (as a string, e.g, "1")/ "Fastest Lap"/ "Fastest Lap (only for finishing in the top 10)" (2019-2024, where the fastest lap point was only awarded for finishing in the top ten)

   **Values**: the points alloted for that specific position or fastest lap.

   For the 1959 season, the value would be:
   ``` 
   {"1": 8, "2": 6, "3": 4, "4": 3, "5": 2, "Fastest Lap": 1}
   ```

   - **SprintPointsSystemDrivers**: Sprint points system for drivers. (JSON) _TEXT_

   For any row, the data is stored in the following format:

   **Keys**:
   Position (as a string, e.g, "1")

   **Values**: the points alloted for that specific position.

   For the 2025 season, the value would be:
   ```
   {"1": 8, "2": 7, "3": 6, "4": 5, "5": 4, "6": 3, "7": 2, "8": 1}
   ```

   - **ConstructorsRacesCounted**: How many races counted for constructors. _TEXT_

   From 1958 (the first year the Constructors' Championship was awarded) till 1978, you could drop your worst results. In other words, say, for a season, only the points collected for a constructor's best 11 races would count towards the championship. It could also be like the best 6 races from the first 7 races, and the best 7 results from the last eight races counted towards the championship.   

   Values can range from "Best 11 scores." to 
   
   "Best 5 scores from first 7 races.

   Best 5 scores from last 7 races."
   to "All scores and points are doubled for the last Grand Prix." for the 2014 season. If all races are counted, the value is "All scores."   
   - **PointsOnlyForTopScoringCar**: Only top scoring car counted for constructors. _BOOLEAN_

   From 1958 till 1978 only the highest finishing car of a Constructor would be awarded points. For example, if the cars of a particular Constructor finished fourth and fifth, only the points scored for fourth place would count towards the Constructors' Championship.

   The value is ```true``` if points were only given towards the Constructors' Championship for the highest placed car and ```false``` if points were not given towards the Constructors' Championship for the highest placed car.   

   - **GrandPrixPointsSystemConstructors**: Points system for constructors. (JSON) _TEXT_

   It is important to note that the same points system wasn't always used for the Drivers' and Constructors' Championship. In 1959 and 1960, the point for Fastest Lap didn't count towards the Constructors' Championship, hence the necessity for this column.

   For any row, the data is stored in the following format:

   **Keys**:
   Position (as a string, e.g, "1")/ "Fastest Lap (only for finishing in the top 10)" (2019-2024, where the fastest lap point was only awarded for finishing in the top ten)

   **Values**: the points alloted for that specific position or fastest lap.

   For the 2024 season, the value would be:
   ``` 
   {"1": 8, "2": 7, "3": 6, "4": 5, "5": 4, "6": 3, "7": 2, "8": 1}
   ```
   - **SprintPointsSystemConstructors**: Sprint points system for constructors. (JSON) _TEXT_

   For any row, the data is stored in the following format:

   **Keys**:
   Position (as a string, e.g, "1")

   **Values**: the points alloted for that specific position.

   For the 2021 season, the value would be:
   ```
   {"1": 3, "2": 2, "3": 1}
   ```
  
   - **RegulationNotes**: Notes about regulations for that season. (JSON) _TEXT_

   The notes are in the form of an array. For the 2020 season, the value would be:
   ```
   ["On 7 August 2020, following a protest by Renault at the Styria GP, the International Automobile Federation's stewards withdrew 15 points from Racing Point for copying the design of Mercedes' brake scoops.", "Qualifying is divided into 3 sessions.", "At the end of the first 18-minute session (Q1), the 5 slowest drivers are eliminated and placed on positions 16 to 20.", "At the end of the second 15-minute session (Q2), the 5 slowest drivers are eliminated and placed on positions 11 to 15.", "A final session (Q3) lasting 12 minutes determines positions 1 to 10 for the 10 remaining drivers.", "At the end of Q1, drivers whose time exceeds 107% of the best time do not qualify."]
   ```
   - **MinimumWeightofCars**: Minimum car weight. _TEXT_

   The values can vary from  "500 kg" to "500 kg (naturally aspirated) or 540 kg (supercharged)" or even "595 kg with driver". It does not get into too much detail about how much weight must be shared by the front and rear tyres, how much the driver and the seat alone must weigh, and so on. For seasons with no weight limit, the value is "free".
   - **EngineType**: Engine type. _TEXT_

   For the turbo-hybrid era, the value is "hybrid, reciprocating 4-stroke with pistons and electric". For previous seasons, the value wold be "reciprocating 4-stroke with pistons". If there is no restriction to the type of engine, the value would be "free".
   - **Supercharging**: Whether forced induction (supercharging or turbocharging) is allowed for that season. _TEXT_

   For seasons where it is allowed, the value would be "authorized". For seasons where it is not allowed, the value would be "forbidden". For 1986, where every single team had turbos, even though there was no rule mandating turbos, the value is "imposed". From 2014 onwards, where turbos are mandatory, the value would be "madatatory".
   - **MaxCylinderCapacity**: Maximum engine displacement. Also can be the allowed engine displacement. _TEXT_

   Values can range from "1500 cc" to "3000 cc (naturally aspirated) or 1500 cc (supercharged)".
   - **NumberOfCylinders**: Number of cylinders, or engine configuration. _TEXT_

   For seasons with no restrictions, the value would be "free". For seasons with a cap on maximum number of cylinders, the value would be, for example, "maximum 12". For seasons where the configuration was mandated, the value could be "V10". For 2006, where every other team except Toro Rosso had V8s, because the FIA granted special permission for Toro Rosso to continue using V10s, the value would be "V8 or V10".
   - **MaxRPM**: Maximum RPM the engine can rev to. _TEXT_

   For seasons where there was no limit on the maximum RPM of the engine, the value would be "free". Otherwise, the value would be the maximum RPM, for example "19 000".
   - **NumberOfEnginesAllowedPerSeason**: Engine allocation per season. _TEXT_

   The values can range from "1 engine per Grand Prix" to  "1 engine for 2 Grand Prix" to "3 per season". For seasons with no cap on the number of engines used, the value would be "free".
   - **FuelType**: Fuel type. _TEXT_

   For seasons where teams could use any type of fuel they wanted, the value would be "free". Otherwise it would tell the type of fuel that the teams could use.
   - **RefuellingAllowed**: Whether refuelling was allowed during a race. _TEXT_

   For seasons where refuelling was allowed, the value would be "authorized". For seasons where refuelling was not allowed, the value would be "forbidden".
   - **MaxFuelConsumption**: Maximum fuel consumption. _TEXT_

   For seasons where there was no limit, the value would be "free". The values can also range from "200 litres" to "free (naturally aspirated) or 195 litres (supercharged)" to "100 kg and 100 kg/hour". In the last example, the first part ("100 kg") shows the fuel tank capacity (the maximum amount of fuel consumed per race) annd the second part ("100 kg/hour") shows the fuel flow limit.

2. ### Circuits
   This table contains all circuits which have hosted a Grand Prix.  
   **Columns:**
   - **ID**: Unique circuit ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
   - **CircuitName**: Name of the circuit. _TEXT_
   - **FirstGrandPrix**: First Grand Prix held in that circuit. _TEXT_
   - **LastGrandPrix**: Last Grand Prix held in that circuit. _TEXT_
   - **GrandPrixCount**: Number of GPs held in that circuit. _INTEGER DEFAULT 0_
   - **FirstGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
   - **LastGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_

3. ### GrandsPrix
   This table contains all Grands Prix.  
   **Columns:**
   - **ID**: Unique Grand Prix ID. The ID corresponds to which Grand Prix it is from the start of the world championship; the Grand Prix with the ID 1000 will be the 1000th world championship Grand Prix (2019 Chinese Grand Prix). _INTEGER PRIMARY KEY_
   - **Season**: Year of the Grand Prix. _INTEGER_
   - **GrandPrixName**: Name of the Grand Prix. _TEXT_
   - **RoundNumber**: Round number in the season. For example, if a race was the seventeenth Grand Prix of the season, the value would be "17".  _INTEGER_
   - **CircuitName**: Name of the circuit. _TEXT_
   - **Date**: Date of the Grand Prix. For example, "Sunday, 2 August 2020" _TEXT_
   - **DateInDateTime**: Date as datetime. _TEXT_
   - **Laps**: Number of laps the race was held. _INTEGER_
   - **CircuitLength**: The length of the circuit in which the race was held. _TEXT_
   - **Weather**: Weather conditions. For example "Sunny", "Overcast", "Cloudy", "Night", "Rain", etc. _TEXT_
   - **Notes**: Notes about the race. _TEXT_
   - **SprintWeekend**: Whether it was a sprint weekend. _BOOLEAN_

   If it is a sprint weekend, the value is ```true```, if it is not, the value is ```false```.
   - **CircuitID**: Foreign key to Circuits. _INTEGER_
   - **EntrantsNotes**: Notes about the entrants to the race. _TEXT_
   - **QualifyingNotes**: Notes about qualifying. _TEXT_
   - **StartingGridNotes**: Notes about the starting grid. _TEXT_
   - **RaceResultNotes**: Notes about the race result. _TEXT_
   - **SprintNotes**: Notes about the sprint. _TEXT_
   - **SprintGridNotes**: Notes about the sprint grid. _TEXT_

4. ### Drivers
   This table contains all drivers who have entered a World Championship Grand Prix (this includes FP1 appearances and  third/substitute drivers).  
   **Columns:**
   - **ID**: Unique driver ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
   - **Name**: Full name of that driver. _TEXT UNIQUE_
   - **Nationality**: Nationality of that driver. _TEXT_
   - **Birthdate**: Birth date of that driver. _TEXT_
   - **Wins**: Number of wins of that driver. _INTEGER_
   - **Podiums**: Number of podiums of that driver. _INTEGER_
   - **Poles**: Number of pole positions of that driver. _INTEGER_
   - **FastestLaps**: Number of fastest laps of that driver. _INTEGER_
   - **Championships**: Number of championships of that driver. _INTEGER_
   - **Points**: Total points of that driver. _REAL_
   - **Starts**: Number of starts of that driver. _INTEGER_
   - **Entries**: Number of entries of that driver. _INTEGER_
   - **DNFs**: Number of DNFs of that driver. Only classified non-finishes are counted. For example, if a driver did not finish a race but has a classified finish in the race result, it is not counted here. _INTEGER_
   - **LapsLed**: Number of laps led (sprint + grand prix) of that driver. _INTEGER_
   - **HatTricks**: Number of hat tricks (pole + win + fastest lap) of that driver. _INTEGER_
   - **GrandSlams**: Number of grand slams (pole + win + fastest lap + led every lap) of that driver. _INTEGER_
   - **BestGridPosition**: Best grid position of that driver. _INTEGER_
   - **BestSprintGridPosition**: Best sprint grid position of that driver. _INTEGER_
   - **BestQualifyingPosition**: Best qualifying position of that driver. _INTEGER_
   - **BestRacePosition**: Best race position of that driver. _INTEGER_
   - **BestSprintPosition**: Best sprint position of that driver. _INTEGER_
   - **BestChampionshipPosition**: Best championship position of that driver. _INTEGER_
   - **FirstGrandPrix**: First Grand Prix of that driver. _TEXT_
   - **LastGrandPrix**: Last Grand Prix of that driver. _TEXT_
   - **NationalityID**: Foreign key to Nationalities. _INTEGER_
   - **FirstGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
   - **LastGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_

5. ### Teams
   This table contains all teams that have entered a Grand Prix. A constructor and a team are two very different things. A constructor is an entity that constructs a chassis for Formula One, while a team can also include private entries from people who don't construct a chassis. In a more modern sense, a constructor is just the chassis name (i.e, Mercedes), while a team also includes the sponsor names (i.e, Mercedes AMG Petronas Formula One Team). The team names are according to the entry list for that race.

   **Columns:**
   - **ID**: Unique team ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
   - **TeamName**: Name of the team. _TEXT UNIQUE_
   - **FirstGrandPrix**: First Grand Prix of that team. _TEXT_
   - **LastGrandPrix**: Last Grand Prix of that team. _TEXT_
   - **Wins**: Number of wins of that team. _INTEGER_
   - **Podiums**: Number of podiums of that team. _INTEGER_
   - **Poles**: Number of pole positions of that team. _INTEGER_
   - **FastestLaps**: Number of fastest laps of that team. _INTEGER_
   - **LapsLed**: Number of laps led (sprint + grand prix) of that team. _INTEGER_
   - **Starts**: Number of starts of that team. _INTEGER_
   - **Entries**: Number of entries of that team. _INTEGER_
   - **DNFs**: Number of DNFs of that team. Only classified non-finishes are counted. _INTEGER_
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
   - **Wins**: Number of wins of that constructor. _INTEGER_
   - **Podiums**: Number of podiums of that constructor. _INTEGER_
   - **Poles**: Number of pole positions of that constructor. _INTEGER_
   - **FastestLaps**: Number of fastest laps of that constructor. _INTEGER_
   - **Championships**: Number of championships of that constructor. _INTEGER_
   - **Points**: Total points of that constructor. _REAL_
   - **Starts**: Number of starts of that constructor. _INTEGER_
   - **Entries**: Number of entries of that constructor. _INTEGER_
   - **DNFs**: Number of DNFs of that constructor. Only classified non-finishes are counted. _INTEGER_
   - **LapsLed**: Number of laps led (sprint + grand prix) of that constructor. _INTEGER_
   - **BestGridPosition**: Best grid position of that constructor. _INTEGER_
   - **BestSprintGridPosition**: Best sprint grid position of that constructor. _INTEGER_
   - **BestQualifyingPosition**: Best qualifying position of that constructor. _INTEGER_
   - **BestRacePosition**: Best race position of that constructor. _INTEGER_
   - **BestSprintPosition**: Best sprint position of that constructor. _INTEGER_
   - **BestChampionshipPosition**: Best championship position of that constructor. _INTEGER_
   - **FirstGrandPrix**: First Grand Prix of that constructor. _TEXT_
   - **LastGrandPrix**: Last Grand Prix of that constructor. _TEXT_
   - **FirstGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
   - **LastGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_

7. ### Engines
   This table contains all engine manufacturers to power an entry in a Grand Prix. Rebadged engines like Acer, Mecachrome, etc. are also included.

   **Columns:**
   - **ID**: Unique engine manufacturer ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
   - **EngineName**: Name of the engine manufacturer. _TEXT UNIQUE_
   - **Wins**: Number of wins of that engine manufacturer. _INTEGER_
   - **Podiums**: Number of podiums of that engine manufacturer. _INTEGER_
   - **Poles**: Number of pole positions of that engine manufacturer. _INTEGER_
   - **FastestLaps**: Number of fastest laps of that engine manufacturer. _INTEGER_
   - **Championships**: Number of championships of that engine manufacturer. _INTEGER_
   - **Points**: Total points of that engine manufacturer. _REAL_
   - **Starts**: Number of starts of that engine manufacturer. _INTEGER_
   - **Entries**: Number of entries of that engine manufacturer. _INTEGER_
   - **DNFs**: Number of DNFs of that engine manufacturer. Only classified non-finishes are counted. _INTEGER_
   - **LapsLed**: Number of laps led (sprint + grand prix) of that engine manufacturer. _INTEGER_
   - **BestGridPosition**: Best grid position of that engine manufacturer. _INTEGER_
   - **BestSprintGridPosition**: Best sprint grid position of that engine manufacturer. _INTEGER_
   - **BestQualifyingPosition**: Best qualifying position of that engine manufacturer. _INTEGER_
   - **BestRacePosition**: Best race position of that engine manufacturer. _INTEGER_
   - **BestSprintPosition**: Best sprint position of that engine manufacturer. _INTEGER_
   - **FirstGrandPrix**: First Grand Prix of that engine manufacturer. _TEXT_
   - **LastGrandPrix**: Last Grand Prix of that engine manufacturer. _TEXT_
   - **FirstGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
   - **LastGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_

8. ### Tyres
   This table contains all tyre manufacturers that have provided tyres to an entry.  
   **Columns:**
   - **ID**: Unique tyre ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
   - **TyreName**: Name of the tyre. _TEXT UNIQUE_
   - **Wins**: Number of wins of that tyre manufacturer. _INTEGER_
   - **Podiums**: Number of podiums of that tyre manufacturer. _INTEGER_
   - **Poles**: Number of pole positions of that tyre manufacturer. _INTEGER_
   - **FastestLaps**: Number of fastest laps of that tyre manufacturer. _INTEGER_
   - **Points**: Total points of that tyre manufacturer. _REAL_
   - **Starts**: Number of starts of that tyre manufacturer. _INTEGER_
   - **Entries**: Number of entries of that tyre manufacturer. _INTEGER_
   - **DNFs**: Number of DNFs of that tyre manufacturer. Only classified non-finishes are counted. _INTEGER_
   - **LapsLed**: Number of laps led (sprint + grand prix) of that tyre manufacturer. _INTEGER_
   - **BestGridPosition**: Best grid position of that tyre manufacturer. _INTEGER_
   - **BestSprintGridPosition**: Best sprint grid position of that tyre manufacturer. _INTEGER_
   - **BestQualifyingPosition**: Best qualifying position of that tyre manufacturer. _INTEGER_
   - **BestRacePosition**: Best race position of that tyre manufacturer. _INTEGER_
   - **BestSprintPosition**: Best sprint position of that tyre manufacturer. _INTEGER_
   - **FirstGrandPrix**: First Grand Prix of that tyre manufacturer. _TEXT_
   - **LastGrandPrix**: Last Grand Prix of that tyre manufacturer. _TEXT_
   - **FirstGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
   - **LastGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_

9. ### Chassis
   This table contains all chassis to enter a race in Formula One (e.g, the Lotus 72).  
   **Columns:**
   - **ID**: Unique chassis ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
   - **ConstructorName**: Name of the constructor that made that chasis. _TEXT_
   - **ChassisName**: Name of the chassis. _TEXT UNIQUE_
   - **ConstructorID**: Foreign key to Constructors. _INTEGER_
   - **Wins**: Number of wins of that chassis. _INTEGER_
   - **Podiums**: Number of podiums of that chassis. _INTEGER_
   - **Poles**: Number of pole positions of that chassis. _INTEGER_
   - **FastestLaps**: Number of fastest laps of that chassis. _INTEGER_
   - **Championships**: Number of championships of that chassis. _INTEGER_
   - **Points**: Total points of that chassis. _REAL_
   - **Starts**: Number of starts of that chassis. _INTEGER_
   - **Entries**: Number of entries of that chassis. _INTEGER_
   - **DNFs**: Number of DNFs of that chassis. Only classified non-finishes are counted. _INTEGER_
   - **LapsLed**: Number of laps led (sprint + grand prix). _INTEGER_
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
    This table contains all engine models used in F1 (e.g, the Cosworth DFV).  
    **Columns:**
    - **ID**: Unique engine model ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
    - **EngineMake**: Engine make (e.g "Mercedes" for "M11 EQ Performance V6 t h 1.6"). _TEXT_
    - **EngineModel**: Engine model. It also includes some specifications of the engine like displacement, configuration, turbocharged or not, hybrid or not. For example, the DFV is stored as "DFV V8 3.0". _TEXT UNIQUE_
    - **EngineMakeID**: Foreign key to Engines. _INTEGER_
    - **Wins**: Number of wins of that engine manufacturer. _INTEGER_
    - **Podiums**: Number of podiums of that engine manufacturer. _INTEGER_
    - **Poles**: Number of pole positions of that engine manufacturer. _INTEGER_
    - **FastestLaps**: Number of fastest laps of that engine manufacturer. _INTEGER_
    - **Championships**: Number of championships of that engine manufacturer. _INTEGER_
    - **Points**: Total points of that engine manufacturer. _REAL_
    - **Starts**: Number of starts of that engine manufacturer. _INTEGER_
    - **Entries**: Number of entries of that engine manufacturer. _INTEGER_
    - **DNFs**: Number of DNFs of that engine manufacturer. Only classified non-finishes are counted. _INTEGER_
    - **LapsLed**: Number of laps led (sprint + grand prix) of that engine manufacturer. _INTEGER_
    - **BestGridPosition**: Best grid position of that engine manufacturer. _INTEGER_
    - **BestSprintGridPosition**: Best sprint grid position of that engine manufacturer. _INTEGER_
    - **BestQualifyingPosition**: Best qualifying position of that engine manufacturer. _INTEGER_
    - **BestRacePosition**: Best race position of that engine manufacturer. _INTEGER_
    - **BestSprintPosition**: Best sprint position of that engine manufacturer. _INTEGER_
    - **FirstGrandPrix**: First Grand Prix of that engine manufacturer. _TEXT_
    - **LastGrandPrix**: Last Grand Prix of that engine manufacturer. _TEXT_
    - **EngineMakeID**: Foreign key to Engines of that engine manufacturer. _INTEGER_
    - **FirstGrandPrixID**: Foreign key to GrandsPrix of that engine manufacturer. _INTEGER_
    - **LastGrandPrixID**: Foreign key to GrandsPrix of that engine manufacturer. _INTEGER_

11. ### GrandPrixResults
    This table contains all race entrants for each Grand Prix, with all session results and penalties. It then has all the results for each session that driver competed in. For shared cars, there are separate entries for each driver but it has the _same_ car number. 
    
    Q1 and Q2 can mean different things over different qualifying regulations. From 1950 till 1995, there were two different qualifying sessions, one on Friday (Q1), and one on Saturday (Q2). The best time from both sessions for each driver was counted towards the overall qualifying. In 2003 and 2004, during the first qualifying session (Q1), all the drivers set one lap in championship order, with the last going first and first going last. Then, on the second qualifying session (Q2), the drivers went on another lap, with the last on the first session going first, and the first going last. Then, for the first six races in 2005, there were two different sessions; one on low fuel (Q1), and one on race fuel(Q2). Then the two times would be aggregated to set the overall qualifying times. From 2006, the slowest drivers were eliminated in Q1 and Q2, now just part of qualifying, not two separate sessions. 

    We also have data for practice sessions. This must not be confused with qualifying being called practice previously. There were up to four practice sessions in previous years, with the pre-race warm ups as well. There have been only two practice sessions in some years, and in Sprint weekends we only have one. We currently have three practice sessions in normal weekends.

    We have data for Q1 and Q2 only after 1983. To find drivers who did not pre-qualify or qualify, it is there in overall qualifying. We have data for the Sunday morning warm-up session from 1984 till 2003, when the session no longer happened. 

    In 2021, the Qualifying session set the grid for the Sprint race, and the Sprint set the grid for the Grand Prix, with the top 3 finishers getting 3, 2, and 1 point respectively.

    In 2022, the Qualifying session set the grid for both the Sprint and the race.

    From 2023, there is one qualifying session for the race and one for the sprint.

    **Columns:**
    - **grandprix**: Grand Prix name. _TEXT_
    - **number**: Car number. _INTEGER_
    - **driver**: Driver name. _TEXT_
    - **nationality**: Nationality of the driver. _TEXT_
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
    - **gridpenalty**: Any grid penalty applied. It can be a pit lane start ("Start from pit lane"), start from the back of the grid ("Demoted to the back of the grid"), or a grid penalty by x number of postions (e.g, "Demoted by 7 places"). _TEXT_
    - **gridpenalty_reason**: Grid penalty reason (e.g "Modifying car under Parc Fermé conditions", "Exceeding quota of powertrain elements", and so on.). _TEXT_
    - **sprintstarting_grid_position**: Sprint starting grid position. _INTEGER_
    - **sprintgridpenalty**: Sprint grid penalty. Same format as `gridpenalty` _TEXT_
    - **sprintgridpenalty_reason**: Sprint grid penalty reason. Same format as  `gridpenalty_reason` _TEXT_
    - **fastestlap**: Fastest lap position (e.g, out of each drivers' fastest laps, this driver set the sixth fastest lap). _INTEGER_
    - **fastestlapinseconds**: Fastest lap in seconds. _REAL_
    - **fastestlapgapinseconds**: Fastest lap gap in seconds. _REAL_
    - **fastestlap_time**: Fastest lap time. _TEXT_
    - **fastestlap_gap**: Fastest lap gap. _TEXT_
    - **fastestlap_lap**: Lap of fastest lap (e.g, driver set their fastest lap on the 17th lap). _INTEGER_
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
    - **warmuptime**: Warmup time. It only shows the gap for those who are not the leader. _TEXT_
    - **warmupgap**: Warmup gap. _TEXT_
    - **warmuptimeinseconds**: Warmup time in seconds. _REAL_
    - **warmuplaps**: Warmup laps. _INTEGER_
    - **practice1position**: Practice 1 position. _INTEGER_
    - **practice1time**: Practice 1 time. It only shows the gap for those who are not the leader. _TEXT_
    - **practice1gap**: Practice 1 gap. _TEXT_
    - **practice1timeinseconds**: Practice 1 time in seconds. _REAL_
    - **practice1laps**: Practice 1 laps. _INTEGER_
    - **practice2position**: Practice 2 position. _INTEGER_
    - **practice2time**: Practice 2 time. It only shows the gap for those who are not the leader. _TEXT_
    - **practice2gap**: Practice 2 gap. _TEXT_
    - **practice2timeinseconds**: Practice 2 time in seconds. _REAL_
    - **practice2laps**: Practice 2 laps. _INTEGER_
    - **practice3position**: Practice 3 position. _INTEGER_
    - **practice3time**: Practice 3 time. It only shows the gap for those who are not the leader. _TEXT_
    - **practice3gap**: Practice 3 gap. _TEXT_
    - **practice3timeinseconds**: Practice 3 time in seconds. _REAL_
    - **practice3laps**: Practice 3 laps. _INTEGER_
    - **practice4position**: Practice 4 position. _INTEGER_
    - **practice4time**: Practice 4 time. It only shows the gap for those who are not the leader. _TEXT_
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
    - **racetime**: Race time. If the car retired, did not start, got disqualified, or anything else, the reason for retirement is given. _TEXT_
    - **racepoints**: Race points. _REAL_
    - **racetimeinseconds**: Race time in seconds. _REAL_
    - **racegap**: Race gap. _TEXT_
    - **racegapinseconds**: Race gap in seconds. _REAL_
    - **penalties**: Penalties (JSON). _TEXT_

      It has the following keys:

      - penalty: The nature and magnitude of the penalty. (e.g, "5 seconds", "10 seconds", "10 seconds Stop and Go", "Drive-through", etc.)
      - reason: The reason the penalty was given.
      - type: It has two types:

         - during_the_race: Served during the race (in a pit stop).
         - added_after_chequered_flag: Added to race time after the race.

      For example, here's Esteban Ocon's penalties at the 2023 Austrian Grand Prix:          
      ```
      [{"penalty": "5 seconds", "reason": "Unsafe release from pit stop", "type": "during_the_race"}, {"penalty": "5 seconds", "reason": "Crossing track limits", "type": "added_after_chequered_flag", "lost_position": 0}, {"penalty": "5 seconds", "reason": "Crossing track limits", "type": "added_after_chequered_flag", "lost_position": 0}, {"penalty": "10 seconds", "reason": "Crossing track limits", "type": "added_after_chequered_flag", "lost_position": 0}, {"penalty": "10 seconds", "reason": "Crossing track limits", "type": "added_after_chequered_flag", "lost_position": 2}]
      ```

    - **sprint_penalties**: Sprint penalties (JSON). Same format as `penalties`. _TEXT_
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
    - **GrandPrix**: Name of the Grand Prix. _TEXT_
    - **Number**: Car number. _INTEGER_
    - **Driver**: Driver name. _TEXT_
    - **Constructor**: Constructor name. _TEXT_
    - **StopNumber**: Stop number (e.g, it's the driver's second stop). _INTEGER_
    - **Lap**: Lap of the stop. _INTEGER_
    - **DurationSpentInPitLane**: Duration in _pit lane_. Not to be confused as the duration stationary in the pit stop _TEXT_
    - **TimeInSeconds**: Duration in seconds. _REAL_
    - **TimeOfDayStopped**: Time of day. _TEXT_
    - **TotalTimeSpentInPitLane**: Total pit lane time (all the stops combined till that point). _TEXT_
    - **TotalTimeinSeconds**: Total pit lane time in seconds. _REAL_
    - **GrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
    - **DriverID**: Foreign key to Drivers. _INTEGER_
    - **ConstructorID**: Foreign key to Constructors. _INTEGER_

13. ### LapByLap
    This table has the lap-by-lap data for each race.  
    **Columns:**
    - **GrandPrix**: Name of the Grand Prix. _TEXT_
    - **Driver**: Driver name. _TEXT_
    - **Position**: Position on that lap. _INTEGER_
    - **Lap**: Lap number. _INTEGER_
    - **Type**: Session type. For Grands Prix, the type is "grandprix", and for Sprints, the type is "sprint" _TEXT_
    - **SafetyCar**: Safety car/ Virtual Safety car status. `true` for Safety Car/Virtual Safety Car in force that lap, `false` otherwise. _BOOLEAN_
    - **Time**: Lap time. Available from 1996. _TEXT_
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

      It has the following format:

      **Key**: It is the Grand Prix.

      **Value**: In the form of an array. The 0th element has the number of points scored. The 1st element has the info whether the score was dropped(whether it did not count towards the championship). `true` means the score was dropped. `false` means the score was not dropped. `null` means the driver scored 0 points in that race.

      For example, here's Alain Prost's `RaceByRace` during the 1988 season:
      ```
      {"Brazil": [9.0, false], "San Marino": [6.0, false], "Monaco": [9.0, false], "Mexico": [9.0, false], "Canada": [6.0, false], "Detroit": [6.0, false], "France": [9.0, false], "Britain": [0, null], "Germany": [6.0, false], "Hungary": [6.0, true], "Belgium": [6.0, true], "Italy": [0, null], "Portugal": [9.0, false], "Spain": [9.0, false], "Japan": [6.0, true], "Australia": [9.0, false]}
      ```
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
    - **RaceByRace**: JSON of race-by-race points. Same format as `RaceByRace` in `DriversChampionship`. _TEXT_
    - **ConstructorID**: Foreign key to Constructors. _INTEGER_
    - **EngineID**: Foreign key to Engines. _INTEGER_
    - **EngineModelID**: Foreign key to EngineModels. _INTEGER_

16. ### InSeasonProgressDrivers
    This table has the progress of each driver over the season. It is recorded after each race.  
    **Columns:**
    - **ID**: Unique ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
    - **GrandPrix**: Name of the Grand Prix. _TEXT_
    - **PositionAtThisPoint**: Position at this point, that is, after this race. _INTEGER_
    - **Driver**: Driver name. _TEXT_
    - **PointsAtThisPoint**: Points at this point, that is, after this race. _REAL_
    - **GrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
    - **DriverID**: Foreign key to Drivers. _INTEGER_

17. ### InSeasonProgressConstructors
    This table has the progress of each constructor over the season. It is recorded after each race.    
    **Columns:**
    - **ID**: Unique ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
    - **GrandPrix**: Name of the Grand Prix. _TEXT_
    - **PositionAtThisPoint**: Position at this point, that is, after this race. _INTEGER_
    - **Constructor**: Constructor name. _TEXT_
    - **Engine**: Engine name. _TEXT_
    - **PointsAtThisPoint**: Points at this point, that is, after this race. _REAL_
    - **GrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
    - **ConstructorID**: Foreign key to Constructors. _INTEGER_
    - **EngineID**: Foreign key to Engines. _INTEGER_

18. ### Nationalities
    This table contains all nationalities that have participated in F1.  
    **Columns:**
    - **ID**: Unique nationality ID. _INTEGER PRIMARY KEY AUTOINCREMENT_
    - **Nationality**: Nationality. _TEXT UNIQUE_
    - **FirstGrandPrix**: First Grand Prix of that nationality. _TEXT_
    - **LastGrandPrix**: Last Grand Prix of that nationality. _TEXT_
    - **DriverCount**: Number of drivers of that nationality. _INTEGER DEFAULT 0_
    - **Wins**: Number of wins of that nationality. _INTEGER DEFAULT 0_
    - **Podiums**: Number of podiums of that nationality. _INTEGER DEFAULT 0_
    - **Poles**: Number of pole positions of that nationality. _INTEGER DEFAULT 0_
    - **FastestLaps**: Number of fastest laps of that nationality. _INTEGER DEFAULT 0_
    - **Championships**: Number of championships of that nationality. _INTEGER DEFAULT 0_
    - **Points**: Total points of that nationality. _REAL DEFAULT 0_
    - **Starts**: Number of starts of that nationality. _INTEGER DEFAULT 0_
    - **Entries**: Number of entries of that nationality. _INTEGER DEFAULT 0_
    - **DNFs**: Number of DNFs of that nationality. Only classified non-finishes are counted. _INTEGER DEFAULT 0_
    - **LapsLed**: Number of laps led (sprint + grand prix) of that nationality. _INTEGER DEFAULT 0_
    - **BestGridPosition**: Best grid position of that nationality. _INTEGER_
    - **BestSprintGridPosition**: Best sprint grid position of that nationality. _INTEGER_
    - **BestQualifyingPosition**: Best qualifying position of that nationality. _INTEGER_
    - **BestRacePosition**: Best race position of that nationality. _INTEGER_
    - **BestSprintPosition**: Best sprint position of that nationality. _INTEGER_
    - **FirstGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
    - **LastGrandPrixID**: Foreign key to GrandsPrix. _INTEGER_
    - **FirstDriver**: First driver. _TEXT_
    - **LastDriver**: Last driver. _TEXT_
    - **FirstDriverID**: Foreign key to Drivers. _INTEGER_
    - **LastDriverID**: Foreign key to Drivers. _INTEGER_

