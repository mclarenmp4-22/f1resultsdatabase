# Roadmap for f1resultsdatabase

## Project summary:
Formula One isn't just fast cars going around in circles. It is about shaving off every single millisecond that you can get away with. It is about aerodynamics, throttle position, how the driver trailbrakes, what upgrades were brought onto the circuit. 

Thus, for any F1 fan, the access to data is invaluable and is the reason why we started this project.
These are also all features that are currently **not** available in the database, but are crucial for understanding the history and current happenings of Formula 1.

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
1. We want to add telemetry data to the database. This should include throttle position, brake state, DRS state, speed, gear, and all other publicly available data. We may also want to add mini-sectors if it is found viable. This will be added from the FastF1 package mostly and the mini-sectors can be added from the OpenF1 API. 

We might want to add the telemetry data in a Parquet file to save space. We want the highest telemetry frequency available to the public to be added to the database.

2. We will also need the circuit info from FastF1 such as marshalling light positions, corner rotation, and corner positions to be added to the database

3. We want to add historical weather data to the database. Grands Prix depend a lot on the weather, and FastF1 also unfortunately does not have the exact precipitation, it just has a boolean on whether it rains or not. We will want granular weather data accurate to a very small precision and regularly updated wherever available. For older races, we might have to settle for lower accuracy and/or less regular updates.
However, for newer races, we want to have the most accurate data possible. We might want soil temperature as a substitute for track temperature. We can have air temperature and pressure, humidity, precipitation, and other important weather data.

## Medium-term goals:
1. From the OpenF1 API, we want to add mini-sector data, and the overtakes data. As the OpenF1 API has data from 2023 onwards, we want to ingest data from 2018 onwards and use that data to update the database.
2. We want to add the team radio mp3 recordings from the OpenF1 API to the database, again from 2018 if possible.
3. We want to add the sporting, technical, financial, and general regulation PDFs for as many seasons as possible.
4. We want to scrape FIA's decision documents to get information. This needs to be able to handle various different types of documents, and also save images or, the bounding boxes for the image regions in the database.
5. We would like to upgrade the Sessions table, such that it includes all sessions that we go through, such as warm-up sessions and pre-qualifying sessions. Further, this would also include the session name, session type, and session length, and session time.
6. We would like to use agentic scraping to scrapee multiple websites for race reports and other sessions as well. Every single detail should be there in the race report.
7. It seems like the F1.com website in the past had additional info like best sector times, speed trap data (for seasons we don't have), and so on. We would like to add that to the database. We might go about that by using the archive.org wayback machine.
8. Try to get live timing data like sector times from seasons in the 2000s and 2010s as well. (https://github.com/TUMFTM/f1-timing-database, https://f1.tfeed.net/)
9. Make sure this can be updated before the whole race weekend ends, that is after FP1, after FP2, and so on. It should be updatable between sessions.
10. Parse the schedule of past and present seasons and add them to the database. (If possible, check versions of the schedule as well.)

## Long-term goals:
1. Migrate the lap by lap and sector and tyre info from Pitwall and TracingInsights to Jolpica and FastF1. This requires a huge refactoring of writedb.py. Pitwall can be a fallback if Jolpica is not available or rate-limited.
 

## Other features we want to implement:

