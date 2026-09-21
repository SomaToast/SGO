# office-display-data

Scheduled data job for the Solnet office display. Fetches free, public weather and space-data sources (MET Norway,
Buienradar, DWD/Bright Sky, FMI, ECMWF Open Data, NDBC, SETI meteor detections) and publishes small JSON/text files
into HubSpot Files → Office_Screen, where the display reads them. No provider API keys. The only secret is the HubSpot
Private App token (`HUBSPOT_PRIVATE_APP_TOKEN`) in this repository's Actions secrets.

Set-up and operation: see `GUIDE-github-hubspot-setup.md` in the display package, or `backend/README.md` here.
Schedules (UTC): offices every 15 min · grids + buoys every 3 h · meteors daily 04:41 · manual run = everything.
