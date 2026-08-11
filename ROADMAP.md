# Roadmap for f1resultsdatabase

## Project summary:
Formula One isn't just fast cars going around in circles. It is about shaving off every single millisecond that you can get away with. It is about aerodynamics, throttle position, how the driver trailbrakes, what upgrades were brought onto the circuit. 

Thus, for any F1 fan, the access to data is invaluable and is the reason why we started this project.

This database has been created with the aim of being the most comprehensive database containing all the information about Formula 1 since 1950. We currently have:
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


## Vision:

We want to create the most comprehensive database containing as much information as possible about Formula 1, down to the minutest detail. We want to be able to make this database as up-to-date as possible as well.
**An intelligent agent which has access to this database should be able to answer any question asked about Formula 1 to it.**

In general: **if any information is missing, we want to add it**.

If you have any feature that you want to request for, please open an issue with the label "feature request". 

## How to get involved:

We are so glad that you would like to contribute! We would love to have you as a contributor. Please do check the [contributing guide](https://github.com/mclarenmp4-22/f1resultsdatabase/blob/main/CONTRIBUTING.md) for more info on how to contribute to the project.

Please check the [issues section](https://github.com/mclarenmp4-22/f1resultsdatabase/issues) for any open issues, check the ones labelled "good first issue", for issues that even beginners to this project can work on. If you have any questions, please open an issue and we will get back to you as soon as possible.

## Short term goals:

## Medium-term goals:

## Long-term goals:

We are working on adding more features to the database to make it even more comprehensive. Some of the features and/or changes we want to add in the future include:
- Add robust OCR detection for the circuit layouts. Currently, my attempt of the OCR detection is not very accurate as it includes false positives, false negatives, and incorrect detection. Once a robust OCR detection is added, we can add corner names and numbers to the circuit layout SVGs.
- Check the viability of adding telemetry data and add if viable, including mini-sectors. Telemetry data can be added in a parquet file to reduce file size and bloating of the database.
- Along with telemetry, circuit information from FastF1 needs to be added otherwise the telemetry data is irrelavent.
- Add additional weather data from a weather API or a historical weather API.
- Add mini-sector data from the `openf1` API.
- Implement the overtakes endpoint from openf1 or do it from FastF1 itself.
- Add the team radio mp3 recordings from openf1 to the database.
- Because the openf1 API has data from 2023 onwards, ingest data from 2018 onwards and use that data to update the database.
- If possible, scrape FIA's decision documents to get information
- Add sporting, technical, financial, and general regulation PDFs for as many seasons as possible.
- Migration for lap by lap and sector and tyre info from Pitwall and TracingInsights to Jolpica and FastF1. This requires a huge refactoring of writedb.py.
- Add more information to the Sessions table, to include all sessions that we go through, such as warm-up sessions and pre-qualifying sessions.
- We would also like to use agentic scraping to scrape multiple websites for race reports and other sessions as well. Every single detail should be there in the race report.
- It seems like the F1.com website in the past had additional info like best sector times, speed trap data (for seasons we don't have), and so on. We would like to add that to the database. 
- Try to get live timing data like sector times from seasons in the 2000s and 2010s as well. (https://github.com/TUMFTM/f1-timing-database, https://f1.tfeed.net/)
- Make sure this can be updated before the whole race weekend ends, that is after FP1, after FP2, and so on. It should be updatable between sessions.
- Parse the schedule of past and present seasons and add them to the database. (If possible, check versions of the schedule as well.)

We would like to add more data for your database. If you have any suggestions, please open an issue, or submit a pull request.