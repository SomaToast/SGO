#!/usr/bin/env python3
"""office_weather.py — backend fetcher for the Solnet office display. Free, public, licence-clean sources only.

  local weather  MET Norway locationforecast 2.0 (global, CC BY 4.0) + sunrise 3.0
  observations   Buienradar stations (NL, free with attribution), Bright Sky / DWD (DE, CC BY 4.0), FMI open data (FI, CC BY 4.0)
  rain now       Buienradar raintext (NL/Benelux), MET nowcast 2.0 (Nordics)
  grids          ECMWF Open Data (CC BY 4.0): total cloud cover, precipitation, significant wave height, mean wave period
Writes office-weather.json and office-fields.json (unless SKIP_GRIDS=1). No API keys; the only secret in the pipeline is
the HubSpot Private App token used by hubspot_upload.py to replace the files in Files.

Env: OFFICES (JSON or path, default offices.json), POINTS_FILE (default grid-points.json), SKIP_GRIDS, CADENCE_MIN.
"""
import os, sys, json, time, math, re, urllib.request, urllib.parse, datetime as dt

UA = 'solnet-office-display-backend/2.0 github.com/solnet-group (info@solnetgroup.com)'   # MET Norway requires identification
def get(url, timeout=40):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json, text/plain, */*'})
    with urllib.request.urlopen(req, timeout=timeout) as r: return r.read().decode('utf-8', 'replace')
def gjson(url): return json.loads(get(url))
def load_offices():
    raw = os.environ.get('OFFICES') or 'offices.json'
    if os.path.exists(raw): raw = open(raw, encoding='utf-8').read()
    return json.loads(raw)
def km(a, b):
    R = 6371; p1, p2 = math.radians(a[0]), math.radians(b[0]); dp = p2 - p1; dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2; return 2 * R * math.asin(math.sqrt(h))

# MET symbol code -> WMO-like weather code the display already interprets
SYM = [('thunder', 95), ('heavysleet', 67), ('heavysnow', 75), ('heavyrain', 65), ('lightsleet', 66), ('lightsnow', 71), ('lightrain', 61),
       ('sleet', 68), ('snow', 73), ('rain', 63), ('fog', 45), ('cloudy', 3), ('partlycloudy', 2), ('fair', 1), ('clearsky', 0)]
def wmo_from_symbol(sym):
    s = (sym or '').lower()
    for k, c in SYM:
        if k in s: return c
    return 3

def met_office(o):
    j = gjson(f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={o['lat']:.4f}&lon={o['lon']:.4f}")
    ts = j['properties']['timeseries']; now = dt.datetime.now(dt.timezone.utc)
    cur = min(ts, key=lambda t: abs(dt.datetime.fromisoformat(t['time'].replace('Z', '+00:00')) - now))
    d = cur['data']['instant']['details']; n1 = (cur['data'].get('next_1_hours') or {}); det1 = n1.get('details') or {}
    sun = gjson(f"https://api.met.no/weatherapi/sunrise/3.0/sun?lat={o['lat']:.4f}&lon={o['lon']:.4f}&date={now.strftime('%Y-%m-%d')}&offset=%2B00:00")['properties']
    rise = sun.get('sunrise', {}).get('time'); sett = sun.get('sunset', {}).get('time')
    def hm(x): return x[:16] if x else None
    is_day = 1 if (rise and sett and rise[:16] <= now.strftime('%Y-%m-%dT%H:%M') <= sett[:16]) else 0
    mm_1h = det1.get('precipitation_amount', 0.0) or 0.0
    current = {"time": cur['time'][:16], "temperature_2m": d.get('air_temperature'), "relative_humidity_2m": d.get('relative_humidity'),
               "apparent_temperature": None, "is_day": is_day, "precipitation": round(mm_1h / 4.0, 3), "weather_code": wmo_from_symbol(n1.get('summary', {}).get('symbol_code')),
               "cloud_cover": d.get('cloud_area_fraction'), "wind_speed_10m": d.get('wind_speed'), "wind_direction_10m": d.get('wind_from_direction'),
               "source": "MET Norway", "symbol": n1.get('summary', {}).get('symbol_code')}
    return {"current": current, "daily": {"sunrise": [hm(rise)], "sunset": [hm(sett)]}, "source": "met.no locationforecast 2.0 · CC BY 4.0"}

def observation(o):
    """Nearest national observation: Buienradar (NL), Bright Sky/DWD (DE), FMI (FI). Returns temperature/humidity/wind/etc or None."""
    la, lo = o['lat'], o['lon']
    try:
        if 50.5 <= la <= 54 and 3 <= lo <= 7.6:
            j = gjson('https://data.buienradar.nl/2.0/feed/json'); st = min(j['actual']['stationmeasurements'], key=lambda s: km((la, lo), (s['lat'], s['lon'])))
            return {"source": "Buienradar.nl", "station": st['stationname'], "km": round(km((la, lo), (st['lat'], st['lon']))), "time": st['timestamp'][:16],
                    "temperature_2m": st.get('temperature'), "relative_humidity_2m": st.get('humidity'), "wind_speed_10m": st.get('windspeed'), "wind_direction_10m": st.get('winddirectiondegrees'),
                    "precipitation_mmh": st.get('precipitation'), "description": st.get('weatherdescription')}
        if 47 <= la <= 55.1 and 5.8 <= lo <= 15.1:
            j = gjson(f"https://api.brightsky.dev/current_weather?lat={la:.3f}&lon={lo:.3f}"); w = j['weather']; s = (j.get('sources') or [{}])[0]
            return {"source": "DWD via Bright Sky", "station": s.get('station_name'), "km": round(s.get('distance', 0) / 1000), "time": w['timestamp'][:16],
                    "temperature_2m": w.get('temperature'), "relative_humidity_2m": w.get('relative_humidity'), "wind_speed_10m": (w.get('wind_speed_10') or 0) / 3.6,
                    "wind_direction_10m": w.get('wind_direction_10'), "precipitation_mmh": (w.get('precipitation_10') or 0) * 6, "description": w.get('condition')}
        if 59.5 <= la <= 70.1 and 19 <= lo <= 31.6:
            st = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=40)).strftime('%Y-%m-%dT%H:%M:%SZ')
            base = 'https://opendata.fmi.fi/wfs?service=WFS&version=2.0.0&request=getFeature&storedquery_id=fmi::observations::weather::simple&timestep=10&parameters=t2m,rh,ws_10min,wd_10min,ri_10min&starttime=' + st
            x = get(base + '&place=' + urllib.parse.quote(o['name']))
            if '<BsWfs:ParameterName>' not in x: x = get(base + f"&bbox={lo-0.35:.2f},{la-0.2:.2f},{lo+0.35:.2f},{la+0.2:.2f}&maxlocations=1")
            vals = {}
            for m in re.finditer(r'<BsWfs:Time>([^<]+)</BsWfs:Time>.*?<BsWfs:ParameterName>([^<]+)</BsWfs:ParameterName>\s*<BsWfs:ParameterValue>([^<]+)</BsWfs:ParameterValue>', x, re.S):
                t, n, v = m.groups()
                if v != 'NaN': vals[n] = (t, float(v))
            if vals:
                t = max(v[0] for v in vals.values())
                return {"source": "FMI · CC BY 4.0", "time": t[:16], "temperature_2m": vals.get('t2m', (0, None))[1], "relative_humidity_2m": vals.get('rh', (0, None))[1],
                        "wind_speed_10m": vals.get('ws_10min', (0, None))[1], "wind_direction_10m": vals.get('wd_10min', (0, None))[1], "precipitation_mmh": vals.get('ri_10min', (0, None))[1]}
    except Exception as e:
        return {"error": str(e)[:100]}
    return None

def radar(o):
    try:
        if 50.5 <= o['lat'] <= 54 and 3 <= o['lon'] <= 7.6:
            v = int(get(f"https://gpsgadget.buienradar.nl/data/raintext?lat={o['lat']:.2f}&lon={o['lon']:.2f}").split()[0].split('|')[0])
            return {"mmh": 0.0 if v <= 0 else round(10 ** ((v - 109) / 32), 2), "source": "Buienradar.nl"}
        if 54 <= o['lat'] <= 72 and 4 <= o['lon'] <= 32:
            j = gjson(f"https://api.met.no/weatherapi/nowcast/2.0/complete?lat={o['lat']:.3f}&lon={o['lon']:.3f}")
            return {"mmh": j['properties']['timeseries'][0]['data']['instant']['details'].get('precipitation_rate'), "source": "MET Norway nowcast"}
    except Exception as e:
        return {"error": str(e)[:80]}
    return None

def ecmwf_grids(points_file, out_path, snapshot_dir=None):
    """ECMWF Open Data (CC BY 4.0): tcc + tp (step 3, 0-3 h accumulation) and swh + mwp (step 0), sampled at the display's points."""
    from ecmwf.opendata import Client
    import eccodes
    pts = json.load(open(points_file)); c = Client(source="ecmwf", model="ifs", resol="0p25")
    r1 = c.retrieve(type="fc", step=3, param=["tcc", "tp"], target="/tmp/ecmwf_atm.grib2")
    c.retrieve(stream="wave", type="fc", step=0, param=["swh", "mwp"], target="/tmp/ecmwf_wave.grib2")
    fields = {}
    for path in ("/tmp/ecmwf_atm.grib2", "/tmp/ecmwf_wave.grib2"):
        with open(path, 'rb') as f:
            while True:
                gid = eccodes.codes_grib_new_from_file(f)
                if gid is None: break
                name = eccodes.codes_get(gid, 'shortName'); Ni = eccodes.codes_get(gid, 'Ni'); Nj = eccodes.codes_get(gid, 'Nj')
                lat1 = eccodes.codes_get(gid, 'latitudeOfFirstGridPointInDegrees'); lon1 = eccodes.codes_get(gid, 'longitudeOfFirstGridPointInDegrees')
                dj = eccodes.codes_get(gid, 'jDirectionIncrementInDegrees'); di = eccodes.codes_get(gid, 'iDirectionIncrementInDegrees')
                vals = eccodes.codes_get_values(gid).reshape(Nj, Ni); miss = eccodes.codes_get(gid, 'missingValue')
                fields[name] = (vals, lat1, lon1, dj, di, miss); eccodes.codes_release(gid)
    def sample(name, lat, lon):
        v, lat1, lon1, dj, di, miss = fields[name]; j = int(round((lat1 - lat) / dj)) % v.shape[0]; i = int(round(((lon - lon1) % 360) / di)) % v.shape[1]
        x = float(v[j, i]); return None if abs(x - miss) < 1e-6 or x > 1e19 else x
    run = r1.datetime.strftime('%Y-%m-%dT%H:%M')
    cl = pts['cloud']['points']; wv = pts['wave']['points']
    clouds = {"time": run, "cc": [None if (x := sample('tcc', p[0], p[1])) is None else round(x * 100) for p in cl],
              "pr": [None if (x := sample('tp', p[0], p[1])) is None else round(x * 1000 / 3, 3) for p in cl],   # m over 3 h -> mm/h
              "sn": [0 for _ in cl]}                                                                                 # phase not in open data: left to the display's temperature rule
    waves = {"time": run, "h": [sample('swh', p[0], p[1]) for p in wv], "p": [sample('mwp', p[0], p[1]) for p in wv], "d": [None for _ in wv]}
    out = {"generated": dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), "source": "ECMWF Open Data, IFS 0.25°, CC BY 4.0", "run": run, "clouds": clouds, "waves": waves}
    json.dump(out, open(out_path, 'w'), separators=(',', ':'))
    if snapshot_dir:   # refresh the display's embedded fallbacks (bake-time snapshots), same shapes as before
        cp = json.load(open(os.path.join(snapshot_dir, 'cloud-points.json'))); cp['source'] = out['source']; cp['snapshot'] = {"time": run, "cc": clouds['cc'], "pr": clouds['pr'], "sn": clouds['sn'], "wd": [None] * len(cl), "ws": [None] * len(cl)}
        json.dump(cp, open(os.path.join(snapshot_dir, 'cloud-points.json'), 'w'), separators=(',', ':'))
        wp = json.load(open(os.path.join(snapshot_dir, 'wave-points.json'))); wp['source'] = out['source']; wp['snapshot'] = {"time": run, "h": waves['h'], "p": waves['p'], "d": waves['d']}
        json.dump(wp, open(os.path.join(snapshot_dir, 'wave-points.json'), 'w'), separators=(',', ':'))
    return out

def ndbc_mirror(out_path):
    """NDBC latest_obs.txt is not readable from a browser (no CORS header); mirrored to Files it is. Same format, the
    display's parser reads it (config wavesNdbcUrl). US public domain."""
    txt = get('https://www.ndbc.noaa.gov/data/latest_obs/latest_obs.txt', timeout=60)
    if '#STN' not in txt: raise RuntimeError('unexpected NDBC content')
    open(out_path, 'w').write(txt); return txt.count('\n')

def meteors_aggregate(out_path):
    """Latest night with >= 20 detections from meteorshowers.seti.org (GMN, then CAMS), walked back up to 30 nights;
    same shape as the display's SW.meteors so it can be read directly (config meteorsUrl)."""
    for back in range(1, 31):
        d = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=back)).strftime('%Y-%m-%d')
        for src in ('GMN', 'CAMS'):
            try: ms = gjson(f'https://meteorshowers.seti.org/api/meteor?source={src}&date={d}').get('meteors') or []
            except Exception: continue
            if len(ms) >= 20:
                agg = {}
                for x in ms:
                    a = agg.setdefault(x['name'], {"name": x['name'], "iau": x.get('iau'), "n": 0, "scLon": 0.0, "beta": 0.0, "sol": 0.0, "v": 0.0})
                    a['n'] += 1; c = x['location']['coordinates']; a['scLon'] += c[0]; a['beta'] += c[1]; a['sol'] += x.get('sol') or 0; a['v'] += x.get('velocg') or 0
                showers = sorted(agg.values(), key=lambda a: -a['n'])[:12]
                for a in showers:
                    for k in ('scLon', 'beta', 'sol', 'v'): a[k] = round(a[k] / a['n'], 2)
                out = {"date": d, "source": src, "total": len(ms), "showers": showers, "generated": dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
                json.dump(out, open(out_path, 'w'), separators=(',', ':')); return out
        time.sleep(0.5)
    raise RuntimeError('no night with >= 20 detections in 30 days')

def main():
    offices = load_offices(); now = dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    out = {"generated": now, "cadence_min": int(os.environ.get('CADENCE_MIN', '15')), "attribution": "Weather MET Norway (CC BY 4.0) · observations Buienradar.nl, DWD/Bright Sky, FMI (CC BY 4.0) · grids ECMWF Open Data (CC BY 4.0)", "offices": []}
    for o in offices:
        e = {"name": o['name'], "lat": o['lat'], "lon": o['lon'], "tz": o.get('tz')}
        try: e['met'] = met_office(o)
        except Exception as ex: e['met_error'] = str(ex)[:120]
        ob = observation(o);  r = radar(o)
        if ob: e['observation'] = ob
        if r: e['radar'] = r
        if 'met' in e:
            m = dict(e['met']['current'])
            if ob and not ob.get('error'):                       # a real station reading overrides the model where it has one
                for k in ('temperature_2m', 'relative_humidity_2m', 'wind_speed_10m', 'wind_direction_10m'):
                    if ob.get(k) is not None: m[k] = ob[k]
                m['obs_source'] = ob['source']
            if r and r.get('mmh') is not None: m['precipitation'] = round(r['mmh'] / 4.0, 3); m['precip_source'] = r['source']
            elif ob and ob.get('precipitation_mmh') is not None: m['precipitation'] = round(ob['precipitation_mmh'] / 4.0, 3); m['precip_source'] = ob['source']
            e['merged'] = {"current": m, "daily": e['met']['daily']}
        out['offices'].append(e); time.sleep(0.4)
    json.dump(out, open('office-weather.json', 'w'), separators=(',', ':'))
    if os.environ.get('SKIP_GRIDS') != '1':
        try: ecmwf_grids(os.environ.get('POINTS_FILE', 'grid-points.json'), 'office-fields.json', os.environ.get('SNAPSHOT_DIR'))
        except Exception as ex: print('grids skipped:', str(ex)[:160], file=sys.stderr)
    if os.environ.get('PUBLISH_NDBC') == '1':
        try: print('ndbc lines', ndbc_mirror('ndbc-latest_obs.txt'))
        except Exception as ex: print('ndbc skipped:', str(ex)[:120], file=sys.stderr)
    if os.environ.get('PUBLISH_METEORS') == '1':
        try: m = meteors_aggregate('meteors.json'); print('meteors', m['date'], m['source'], m['total'])
        except Exception as ex: print('meteors skipped:', str(ex)[:120], file=sys.stderr)
    ok = sum(1 for e in out['offices'] if 'merged' in e); print(f"offices {ok}/{len(offices)} with weather")
    if not ok:
        for e in out['offices']:
            print(f"  {e['name']}: met_error={e.get('met_error')} observation={(e.get('observation') or {}).get('error')}", file=sys.stderr)
        print("No office produced a forecast. Most likely the runner could not reach api.met.no; the display keeps its "
              "last good file and its own direct sources, so the screen is not blank.", file=sys.stderr)
    return 0 if ok else 1

if __name__ == '__main__': sys.exit(main())
