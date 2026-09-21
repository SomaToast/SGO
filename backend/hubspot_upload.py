#!/usr/bin/env python3
"""hubspot_upload.py — replace files in HubSpot Files (Files API v3) so their public URLs stay stable.

Env: HUBSPOT_SERVICE_KEY (Development -> Keys -> Service keys, scope: files) or a legacy HUBSPOT_PRIVATE_APP_TOKEN;
HUBSPOT_FOLDER (default Office_Screen), DRY_RUN=1 to print only.
Usage: python3 hubspot_upload.py office-weather.json office-fields.json
Behaviour (HubSpot Files API v3, docs 2026-09): search the folder for the file; if found -> PUT /files/v3/files/{id}
(replace file data, URL unchanged); else -> POST /files/v3/files with folderPath, fileName and options
{access: PUBLIC_NOT_INDEXABLE, overwrite: true}. The owner's first Run workflow is the live test.
"""
import os, sys, json, mimetypes, uuid, urllib.request, urllib.parse, urllib.error

# Service Key (current) or legacy private-app token: both are Bearer tokens
TOKEN = os.environ.get('HUBSPOT_SERVICE_KEY') or os.environ.get('HUBSPOT_PRIVATE_APP_TOKEN'); FOLDER = os.environ.get('HUBSPOT_FOLDER', 'Office_Screen'); DRY = os.environ.get('DRY_RUN') == '1'
API = 'https://api.hubapi.com'

HINTS = {401: "the key is wrong or revoked — re-copy it into the repository secret",
         403: "the key lacks the 'files' scope, or the account cannot use the Files API",
         404: "check HUBSPOT_FOLDER matches the Files folder name exactly",
         429: "HubSpot rate limit — the next scheduled run will retry"}
def call(method, path, body=None, headers=None, raw=None):
    req = urllib.request.Request(API + path, method=method)
    req.add_header('Authorization', 'Bearer ' + TOKEN)
    if body is not None: req.add_header('Content-Type', 'application/json'); data = json.dumps(body).encode()
    else: data = raw
    for k, v in (headers or {}).items(): req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, data=data, timeout=60) as r: return json.loads(r.read().decode() or '{}')
    except urllib.error.HTTPError as e:
        detail = (e.read().decode('utf-8', 'replace') or '')[:300]
        sys.exit(f"HubSpot {method} {path} -> HTTP {e.code}. {HINTS.get(e.code, '')}\n  response: {detail}")

def multipart(fields, filename, content, ctype):
    b = uuid.uuid4().hex; out = b''
    for k, v in fields.items():
        out += f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    out += f'--{b}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'.encode() + content + f'\r\n--{b}--\r\n'.encode()
    return out, f'multipart/form-data; boundary={b}'

def find_file(name):
    stem, ext = name.rsplit('.', 1)
    res = call('GET', f'/files/v3/files/search?name={urllib.parse.quote(stem)}&extension={ext}&limit=50')
    for f in res.get('results', []):
        if f.get('name') == stem and f.get('extension') == ext and (f.get('path') or '').strip('/').startswith(FOLDER.strip('/')):
            return f
    return None

def upload(path):
    name = os.path.basename(path); content = open(path, 'rb').read(); ctype = mimetypes.guess_type(name)[0] or 'application/json'
    if DRY: print(f'[dry-run] would upload {name} ({len(content)} bytes) to /{FOLDER}'); return
    existing = find_file(name)
    options = json.dumps({"access": "PUBLIC_NOT_INDEXABLE", "overwrite": True})
    if existing:
        body, ct = multipart({"options": json.dumps({"access": "PUBLIC_NOT_INDEXABLE"})}, name, content, ctype)
        res = call('PUT', f"/files/v3/files/{existing['id']}", raw=body, headers={'Content-Type': ct})
    else:
        body, ct = multipart({"options": options, "folderPath": '/' + FOLDER.strip('/'), "fileName": name}, name, content, ctype)
        res = call('POST', '/files/v3/files', raw=body, headers={'Content-Type': ct})
    print('uploaded', name, '->', res.get('url') or res.get('id'))

if __name__ == '__main__':
    if not TOKEN and not DRY:
        sys.exit("No HubSpot credential in the environment. Looked for HUBSPOT_SERVICE_KEY, then HUBSPOT_PRIVATE_APP_TOKEN.\n"
                 "Create a Service Key in HubSpot (Development -> Keys -> Service keys, scope 'files'), then add it as the\n"
                 "repository secret HUBSPOT_SERVICE_KEY (Settings -> Secrets and variables -> Actions). Or set DRY_RUN=1 to test.")
    for p in sys.argv[1:]: upload(p)
