# Office display — data job (free, public sources; no API keys)

Sources: **MET Norway** locationforecast + sunrise (global, CC BY 4.0), national observations where they exist —
**Buienradar** stations (NL, free with attribution), **DWD via Bright Sky** (DE, CC BY 4.0), **FMI** open data (FI, CC BY 4.0) —
**Buienradar** and **MET** radar nowcasts for "raining now", and **ECMWF Open Data** (CC BY 4.0) for the cloud/precipitation
and wave grids. No provider key anywhere. The display carries the attribution line these licences require.

## Three ways to run it — pick one
1. **No backend at all.** The display already does the local-weather part itself: it calls MET Norway (identifying
   itself by its Origin header, as MET's terms allow), the radar nowcasts and, where available, the national
   observation, once every 5 minutes per screen — ~300 calls/day per screen against MET's 20 requests/second cap.
   What it cannot do is decode ECMWF GRIB in a browser, so the cloud and wave grids stay as the snapshot embedded at
   build time (refreshed whenever the display is rebuilt). Nothing to operate, nothing to secure.
2. **GitHub Actions → HubSpot Files** (this folder). Offices every 15 min, ECMWF grids every 3 h; the job replaces
   `office-weather.json` and `office-fields.json` in Files → Office_Screen. The only secret is HubSpot's own Private App
   token (scope `files`) kept in GitHub Secrets — an internal credential, not a third-party key. Adds live grids and a
   second opinion (station readings) to the card.
3. **Fully inside HubSpot** — only with **Content Hub Enterprise**: a serverless function (`/_hcms/api/office-weather`)
   called by the display every 5 min would fetch MET/radar/observations server-side. HubSpot has no 15-minute scheduler
   (workflows schedule daily at the finest), no Python or GRIB runtime and a 10-second function limit, so the grids
   would stay embedded as in option 1. On Content Hub Professional this option does not exist.

## Set-up for option 2 (~15 minutes)
1. Put `backend/` and `.github/workflows/office-weather.yml` in a repository (private is fine).
2. Edit `offices.json` — one entry per screen location.
3. HubSpot → **Development → Keys → Service keys → Create service key** → scope `files` → Show → copy the key. (Service Keys
   replace UI-created private apps, which HubSpot now lists as Legacy Apps and stops creating on 2026-10-26.)
4. Repository → Settings → Secrets and variables → Actions → New repository secret `HUBSPOT_SERVICE_KEY`.
5. Actions → *office-display weather* → Run workflow. Expect `offices 3/3 with weather` and two upload lines.
6. Nothing to change in HubSpot: the loader already points the display at the two file URLs; until the first run the
   display uses option 1 by itself.

## Budgets (F21 rule: daily counts in the provider's units)
MET Norway: 3 offices × 96 runs × 2 calls ≈ 580/day, far under the 20 req/s application cap. Buienradar: ≈ 200/day.
Bright Sky: ≈ 100/day. ECMWF Open Data: 8 downloads/day of ~3 MB (they ask for ≤ 500 simultaneous connections).

## Local dry run
`OFFICES=offices.json POINTS_FILE=grid-points.json python3 office_weather.py && DRY_RUN=1 python3 hubspot_upload.py office-weather.json office-fields.json`
(`pip install ecmwf-opendata eccodes` for the grids; `SKIP_GRIDS=1` to skip them.)
