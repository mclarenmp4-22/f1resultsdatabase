# AGENTS.md

## Introduction:
This is f1resultsdatabase. This aims to be the most comprehensive database containing all the information about Formula 1 since 1950.
We currently have:
- **Every World Championship Grand Prix** result since 1950.
- **Detailed lap-by-lap data** positions from 1950 onwards, lap times from 1996 onwards, sector times, tyre compounds, and stints from 2018 onwards.
- **Full session coverage**: Complete results for Practice, Qualifying, Sprints, and Races.
- **Accurate historical data**: Includes shared car results, pre-qualifying, and vintage scoring systems.
- **Pit stop summary**: Includes pit stop data from 1983 onwards, including pit stop times from 2018 onwards.
- **Technical Regulations**: Season-by-season rules on engines, weight, fuel, and more.
- **Circuit Metadata**: coordinates and SVG layout paths for every circuit configuration in history.
- **Comprehensive Penalties**: A full database of penalties with official reasons and serving types.
- **In-Season Progress**: Track the championship standings race-by-race.
- **Race Reports**: Narrative reports for every Grand Prix, from Wikipedia.


## Schema:
For schema, please refer to README.md


## Guidelines and rules:
1. When working on the project, ALWAYS check the correct schema and make sure it is the correct column that you are choosing from README.md
2. When creating a new column or table, always add it to the README.md and reset.py
3. Always before assuming anything, think like an F1 expert. What historical caveat have you not accounted for? At the same time, do not overthink and feel free to ask as many questions as you need.
4. Do not make complex try-except exception handling unless it is absolutely necessary. If something fails in our project, we want it to fail loudly. We don't want to mop it up. After all, this database is designed to be the most comprehensive.

