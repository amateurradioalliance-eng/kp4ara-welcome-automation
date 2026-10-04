"""Transport-injected model. No real HTTP adapter or credential handling in this evaluation."""
import datetime as D, gzip, hashlib, json
from freshness import assess
PATH='/new-pr-hams.json'
META={'last_updated','source_through_date','generated_at','window_start','window_end','stale','source'}
def fingerprint(config,files):
    protected={k:v for k,v in files.items() if k!=PATH}
    encoded=json.dumps({'config':config,'files':protected},sort_keys=True,separators=(',',':')).encode()
    return hashlib.sha256(encoded).hexdigest()
def validate(data,today,now=None):
    if set(data)!={'items','meta'} or not isinstance(data['items'],list):raise ValueError('Invalid root')
    meta=data['meta']
    if not isinstance(meta,dict) or set(meta)-META or meta.get('stale') is not False:raise ValueError('Invalid/stale metadata')
    if assess(meta['source_through_date'],today,now)['stale']:raise ValueError('Coverage incomplete')
    if meta.get('window_end')!=today.isoformat() or meta.get('window_start')!=(today-D.timedelta(days=30)).isoformat():raise ValueError('Wrong window')
    calls=set()
    for item in data['items']:
        if set(item)!={'callsign','name','license_class','grant_date'}:raise ValueError('Private/unapproved fields')
        if not all(isinstance(v,str) for v in item.values()) or not item['name'].strip():raise ValueError('Invalid values')
        if item['license_class'] not in ('Technician','General','Amateur Extra','Advanced','Novice'):raise ValueError('Class')
        if item['callsign'] in calls:raise ValueError('Duplicate')
        calls.add(item['callsign'])
        if not today-D.timedelta(days=30)<=D.date.fromisoformat(item['grant_date'])<=today:raise ValueError('Expired/future')
    return json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
def publish(api,anchor,data,today,now=None):
    raw=validate(data,today,now)
    if api.billing_enabled():raise ValueError('Billing must remain disabled')
    before=api.live()
    if before['version']!=anchor['version']:raise ValueError('Unexpected production version')
    if fingerprint(before['config'],before['files'])!=anchor['protected_sha256']:raise ValueError('Protected production changed')
    if PATH not in before['files']:raise ValueError('Welcome not initially published/approved')
    compressed=gzip.compress(raw,compresslevel=9,mtime=0)
    digest=hashlib.sha256(compressed).hexdigest()
    mapping={**before['files'],PATH:digest}
    if fingerprint(before['config'],mapping)!=anchor['protected_sha256']:raise ValueError('Protected files altered')
    if api.live()['version']!=before['version']:raise ValueError('Concurrent change before prepare')
    version=api.create_version(before['config'])
    required=api.populate(version,mapping)
    if set(required)-{digest}:raise ValueError('Unexpected upload requested')
    if digest in required:api.upload(version,digest,compressed)
    api.finalize(version)
    prepared=api.manifest(version)
    if prepared['files']!=mapping or prepared['config']!=before['config']:raise ValueError('Prepared manifest differs')
    if api.live()['version']!=before['version']:raise ValueError('Concurrent change before release')
    api.release(version)
    after=api.live()
    if after['version']!=version or after['files']!=mapping:raise ValueError('Post-release verification failed; no automatic rollback')
    return {'version':version,'protected_sha256':anchor['protected_sha256']}
