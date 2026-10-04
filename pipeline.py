"""Independent FCC ULS batch processor. Private cache must be outside Hosting public/dist.

No Google APIs, billing changes, Website deployment or authentication writes.
"""
import argparse
import contextlib
import datetime as D
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import urllib.request
import zipfile
from functools import lru_cache
from pathlib import Path
from freshness import assess

UTC=D.timezone.utc
BASE='https://data.fcc.gov/download/pub/uls/'
CLASSES={'T':'Technician','G':'General','E':'Amateur Extra','A':'Advanced','N':'Novice'}
PREFIXES=('KP4','KP3','WP4','WP3','NP4','NP3')
APPLICATION_LINK="""SELECT ad.*,am.vanity,am.prevcall,am.prevclass,am.systematic,am.trustee,am.trustind,am.class,e.state,e.applicant
 FROM en e INDEXED BY en_frn CROSS JOIN ad ON ad.k=e.k AND ad.id=e.id
 CROSS JOIN grants g ON g.k=ad.k AND g.id=ad.id LEFT JOIN am ON am.k=ad.k AND am.id=ad.id
 WHERE e.k='a' AND e.frn=? AND ad.purpose='NE' AND ad.status='G' AND g.date=?"""
PRIOR_LICENSE="SELECT 1 FROM en e INDEXED BY en_frn CROSS JOIN hd h ON h.k=e.k AND h.id=e.id WHERE e.k='l' AND e.frn=? AND h.grant_date<>'' AND h.grant_date<? LIMIT 1"
PRIOR_INITIAL="""SELECT 1 FROM en e INDEXED BY en_frn CROSS JOIN ad ON ad.k=e.k AND ad.id=e.id
 CROSS JOIN grants g ON g.k=ad.k AND g.id=ad.id WHERE e.k='a' AND e.frn=?
 AND ad.purpose='NE' AND ad.status='G' AND g.date<? LIMIT 1"""
FIELDS={'hd':[1,2,4,5,6,7], 'en':[1,7,17,22,23],
        'am':[1,5,8,9,12,13,15,16], 'ad':[1,2,4,5,15]}
MIN_FIELDS={'HD':44,'EN':24,'AM':17,'AD':16,'HS':6,'VC':6}
SCHEMA='''
CREATE TABLE IF NOT EXISTS hd(k TEXT,id TEXT,file TEXT,call TEXT,status TEXT,service TEXT,grant_date TEXT,PRIMARY KEY(k,id));
CREATE TABLE IF NOT EXISTS en(k TEXT,id TEXT,name TEXT,state TEXT,frn TEXT,applicant TEXT,PRIMARY KEY(k,id));
CREATE TABLE IF NOT EXISTS am(k TEXT,id TEXT,class TEXT,trustee TEXT,trustind TEXT,systematic TEXT,vanity TEXT,prevcall TEXT,prevclass TEXT,PRIMARY KEY(k,id));
CREATE TABLE IF NOT EXISTS ad(k TEXT,id TEXT,file TEXT,purpose TEXT,status TEXT,original TEXT,PRIMARY KEY(k,id));
CREATE TABLE IF NOT EXISTS grants(k TEXT,id TEXT,date TEXT,PRIMARY KEY(k,id,date));
CREATE TABLE IF NOT EXISTS vc(k TEXT,id TEXT,PRIMARY KEY(k,id));
CREATE TABLE IF NOT EXISTS ledger(hash TEXT PRIMARY KEY,k TEXT,coverage TEXT,complete INTEGER);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT);
CREATE INDEX IF NOT EXISTS en_frn ON en(k,frn);
CREATE INDEX IF NOT EXISTS hd_grant ON hd(k,grant_date);
CREATE INDEX IF NOT EXISTS ad_file ON ad(k,file);
'''

class SourceError(ValueError): pass

@lru_cache(maxsize=65536)
def iso_date(value):
    if not value:return ''
    try:return D.datetime.strptime(value,'%m/%d/%Y').date().isoformat()
    except ValueError as e:raise SourceError('Invalid FCC date') from e

def atomic_json(path,payload):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.pending')
    with tmp.open('w',encoding='utf8') as f:
        json.dump(payload,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
    os.replace(tmp,path)

def inspect_archive(path,kind,complete,now):
    """Cutoff comes from FCC's embedded creation date, never a hard-coded weekday.
    The closed-day watermark is previous day. Current snapshots also contain partial
    creation-day events (observed in FCC's actual 2026-10-03 exports).
    All contents are read to EOF on ingestion, checking CRC and FCC counts.
    """
    path=Path(path)
    with zipfile.ZipFile(path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)) or 'counts' not in names:raise SourceError('ZIP member manifest invalid')
        if any('/' in n or '\\' in n or n.startswith('.') for n in names):raise SourceError('Unexpected ZIP member')
        counts=z.read('counts').decode('ascii')
        match=re.search(r'File Creation Date:\s+(\w{3}\s+\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+(EST|EDT)\s+(\d{4})',counts)
        if not match:raise SourceError('FCC export creation/cutoff unavailable')
        generated=D.datetime.strptime(match[1]+' '+match[3],'%a %b %d %H:%M:%S %Y').replace(tzinfo=D.timezone(D.timedelta(hours=-5 if match[2]=='EST' else -4)))
        if generated>now+D.timedelta(minutes=15):raise SourceError('Future export')
        coverage=(generated.date()-D.timedelta(days=1)).isoformat()
        if not complete:
            day=re.search(r'_(sun|mon|tue|wed|thu|fri|sat)\.zip$',path.name)
            if day and D.date.fromisoformat(coverage).strftime('%a').lower()!=day[1]:raise SourceError('Delta weekday/cutoff mismatch')
        expected={Path(n).name:int(c) for c,n in re.findall(r'^\s*(\d+)\s+([^\s]+\.dat)\s*$',counts,re.M)}
        # Empty files are accepted only with a dated manifest and explicit zero total.
        empty=not expected and names==['counts'] and not complete
        required={'HD.dat','EN.dat','AM.dat','HS.dat'}|({'AD.dat'} if kind=='a' else set())
        if complete and (empty or not expected.get('HD.dat')):raise SourceError('Empty full snapshot')
        if not empty and (not required.issubset(names) or set(n for n in names if n.endswith('.dat'))!=set(expected)):
            raise SourceError('Missing records or counts manifest mismatch')
    with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    return {'path':str(path),'kind':kind,'complete':complete,'coverage':coverage,'generated_day':generated.date().isoformat(),'generated':generated.isoformat(),'sha256':digest,'counts':expected,'empty':empty}

def connect(path):
    db=sqlite3.connect(path);db.execute('PRAGMA cache_size=-131072');db.executescript(SCHEMA);return db

def metadata(db):return dict(db.execute('SELECT key,value FROM meta'))
def setmeta(db,key,value):db.execute('INSERT OR REPLACE INTO meta VALUES (?,?)',(key,str(value)))

def ingest(db,item):
    if db.execute('SELECT 1 FROM ledger WHERE hash=?',(item['sha256'],)).fetchone():return False
    k=item['kind'];m=metadata(db);watermark=m.get(k+'_through')
    if not item['complete']:
        if not watermark:raise SourceError('Delta without baseline')
        if item['coverage']<=watermark:return False
        if D.date.fromisoformat(item['coverage'])!=D.date.fromisoformat(watermark)+D.timedelta(days=1):raise SourceError('Delta coverage gap: full reconciliation required')
    else:
        if watermark and item['coverage']<watermark:raise SourceError('Snapshot would regress coverage')
        for table in ['hd','en','am','ad','grants','vc']:db.execute(f'DELETE FROM {table} WHERE k=?',(k,))
        db.execute('DELETE FROM ledger WHERE k=?',(k,))
        setmeta(db,k+'_snapshot',item['coverage'])
    with zipfile.ZipFile(item['path']) as z:
        # Read HD first, then every declared DAT. This checks CRC on every member and counts.
        names=sorted(item['counts'],key=lambda n:(n!='HD.dat',n))
        for name in names:
            print('Validating',Path(item['path']).name,name,flush=True)
            code=name[:-4];table=code.lower();count=0;batch=[];seen_ids=set() if not item['complete'] else None
            with z.open(name) as f:
                for line in f:
                    count+=1
                    r=line.decode('latin1').rstrip('\r\n').split('|')
                    if code in MIN_FIELDS and (len(r)<MIN_FIELDS[code] or r[0]!=code or not r[1].isdigit()):raise SourceError('Schema mismatch '+name)
                    if code not in MIN_FIELDS:continue
                    if table in FIELDS:
                        if code=='EN' and r[5]!='L':continue
                        values=[r[i] for i in FIELDS[table]]
                        if code=='HD':
                            values[-1]=iso_date(values[-1])
                            if values[-1] and values[-1]>item['generated_day']:raise SourceError('Grant after export creation date')
                        if seen_ids is not None:
                            if r[1] in seen_ids:raise SourceError('Duplicate identity in delta '+code)
                            seen_ids.add(r[1])
                        batch.append((k,*values))
                        if len(batch)>=10000:
                            db.executemany(f'INSERT OR REPLACE INTO {table} VALUES ({",".join("?" for _ in batch[0])})',batch);batch=[]
                    elif code=='HS':
                        day=iso_date(r[4])
                        if day>item['generated_day']:raise SourceError('History after export creation date')
                        if k=='a' and r[5]=='APGRT':batch.append((k,r[1],day))
                        if len(batch)>=10000:db.executemany('INSERT OR IGNORE INTO grants VALUES (?,?,?)',batch);batch=[]
                    elif code=='VC':
                        batch.append((k,r[1]))
                        if len(batch)>=10000:db.executemany('INSERT OR IGNORE INTO vc VALUES (?,?)',batch);batch=[]
            if count!=item['counts'][name]:raise SourceError('FCC record count mismatch '+name)
            if batch:
                if table in FIELDS:db.executemany(f'INSERT OR REPLACE INTO {table} VALUES ({",".join("?" for _ in batch[0])})',batch)
                elif code=='HS':db.executemany('INSERT OR IGNORE INTO grants VALUES (?,?,?)',batch)
                elif code=='VC':db.executemany('INSERT OR IGNORE INTO vc VALUES (?,?)',batch)
    db.execute('INSERT INTO ledger VALUES (?,?,?,?)',(item['sha256'],k,item['coverage'],int(item['complete'])))
    setmeta(db,k+'_through',item['coverage']);return True

def extract(db,today):
    start=(today-D.timedelta(days=30)).isoformat();end=today.isoformat();items=[];audit=[];people=set();calls=set()
    db.row_factory=sqlite3.Row
    query='''SELECT h.*,e.name,e.state,e.frn,e.applicant,a.class,a.trustee,a.trustind,a.vanity,a.prevcall,a.prevclass
      FROM hd h JOIN en e ON e.k=h.k AND e.id=h.id LEFT JOIN am a ON a.k=h.k AND a.id=h.id
      WHERE h.k='l' AND h.grant_date>=? AND h.grant_date<=? ORDER BY h.grant_date DESC,h.call DESC'''
    for r in db.execute(query,(start,end)).fetchall():
        if r['state']!='PR' and not r['call'].startswith(PREFIXES):continue
        reasons=[]
        if r['state']!='PR':reasons.append('State outside PR')
        if r['status']!='A' or r['service'] not in ('HA','HV'):reasons.append('Inactive/non-Amateur')
        if r['applicant']!='I' or not r['class'] or r['trustee'] or r['trustind']=='Y':reasons.append('Club/trustee/non-individual')
        if not r['frn']:reasons.append('Identity unavailable')
        links=db.execute(APPLICATION_LINK,(r['frn'],r['grant_date'])).fetchall() if r['frn'] else []
        if len(links)!=1:reasons.append('NE/G/APGRT missing or ambiguous')
        else:
            app=links[0]
            # File numbers match unless a later operation replaced the license header's pointer.
            if app['state']!='PR' or app['applicant']!='I' or not app['class'] or app['trustee'] or app['trustind']=='Y':reasons.append('Initial applicant not individual PR')
            if app['vanity'] or app['prevcall'] or app['prevclass'] or app['systematic'] not in ('','N'):reasons.append('Previous/vanity/systematic change')
            if db.execute("SELECT 1 FROM vc WHERE k='a' AND id=?",(app['id'],)).fetchone():reasons.append('Vanity requested')
        if r['frn']:
            if db.execute(PRIOR_LICENSE,(r['frn'],r['grant_date'])).fetchone():reasons.append('Earlier Amateur grant available')
            if db.execute(PRIOR_INITIAL,(r['frn'],r['grant_date'])).fetchone():reasons.append('Earlier granted NE available')
        if r['class'] not in CLASSES:reasons.append('Unknown class')
        if not reasons and (r['frn'] in people or r['call'] in calls):reasons.append('Duplicate person/callsign')
        audit.append({'callsign':r['call'],'included':not reasons,'reasons':reasons})
        if not reasons:
            people.add(r['frn']);calls.add(r['call']);items.append({'callsign':r['call'],'name':r['name'],'license_class':CLASSES[r['class']],'grant_date':r['grant_date']})
    db.row_factory=None
    return items,audit

def payload(items,meta,today,now,failed=False):
    through=min(meta['a_through'],meta['l_through'])
    stale=failed or assess(through,today,now)['stale']
    return {'items':items,'meta':{'last_updated':meta.get('last_updated'),'source_through_date':through,'generated_at':now.isoformat(),'window_start':(today-D.timedelta(days=30)).isoformat(),'window_end':today.isoformat(),'stale':stale,'source':'FCC Universal Licensing System (ULS)'}}

def last_public(path,today,now):
    data=json.loads(Path(path).read_text(encoding='utf8'));seen=set()
    if set(data)!={'items','meta'} or set(data['meta'])-{'last_updated','source_through_date','generated_at','window_start','window_end','stale','source'}:raise SourceError('Unexpected public metadata')
    for item in data['items']:
        if set(item)!={'callsign','name','license_class','grant_date'} or item['license_class'] not in CLASSES.values() or item['callsign'] in seen:raise SourceError('Invalid last public feed')
        D.date.fromisoformat(item['grant_date']);seen.add(item['callsign'])
    D.date.fromisoformat(data['meta']['source_through_date']);D.datetime.fromisoformat(data['meta']['last_updated'])
    start=(today-D.timedelta(days=30)).isoformat()
    data['items']=[item for item in data['items'] if start<=item['grant_date']<=today.isoformat()]
    data['meta'].update(stale=True,generated_at=now.isoformat(),window_start=start,window_end=today.isoformat())
    return data

def run(cache,public,archives,today,now):
    """All-source transaction. Failed batches retain the entire last valid base.
    Public JSON is one atomic replacement; the validated private base is versioned separately.
    """
    cache=Path(cache);public=Path(public);cache.mkdir(parents=True,exist_ok=True)
    if cache.resolve()==public.parent.resolve() or cache.resolve() in public.resolve().parents or public.parent.resolve() in cache.resolve().parents:raise SourceError('Private cache and public directory must be separate')
    lock=(cache/'run.lock').open('a+b')
    lock.seek(0);lock.write(b'0');lock.flush();lock.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:
        lock.close();raise SourceError('Another FCC run is active')
    staging=cache/'staging.sqlite';current=cache/'current.json';previous=json.loads(current.read_text()) if current.exists() else None
    old=cache/previous['database'] if previous else None
    try:
        if staging.exists():staging.unlink()
        staging.with_name(staging.name+'-journal').unlink(missing_ok=True)
        if old:shutil.copyfile(old,staging)
        db=connect(staging)
        with db:
            # Sorting secondary indexes once is cheaper than millions of random updates.
            rebuild_indexes=any(a['complete'] for a in archives)
            if rebuild_indexes:
                for index in ('en_frn','hd_grant','ad_file'):db.execute('DROP INDEX '+index)
            ordered=sorted(archives,key=lambda a:(a['kind'],not a['complete'],a['coverage']))
            for item in ordered:ingest(db,item)
            if rebuild_indexes:
                db.execute('CREATE INDEX en_frn ON en(k,frn)')
                db.execute('CREATE INDEX hd_grant ON hd(k,grant_date)')
                db.execute('CREATE INDEX ad_file ON ad(k,file)')
            m=metadata(db)
            if not {'a_through','l_through'}.issubset(m):raise SourceError('Both source baselines required')
            if assess(min(m['a_through'],m['l_through']),today,now)['stale']:
                raise SourceError('Coverage outside conservative publication policy')
            setmeta(db,'last_updated',now.isoformat());m=metadata(db)
            items,audit=extract(db,today)
        db.close()
        with staging.open('rb') as f:version=hashlib.file_digest(f,'sha256').hexdigest()[:20]+'.sqlite'
        os.replace(staging,cache/version)
        result=payload(items,m,today,now)
        atomic_json(current,{'database':version})
        atomic_json(public,result)
        atomic_json(cache/'audit.json',audit)
        # Only generated database filenames, preserving current + previous valid base.
        for file in cache.glob('*.sqlite'):
            if re.fullmatch(r'[0-9a-f]{20}\.sqlite',file.name) and file.name not in (version,old.name if old else ''):
                with contextlib.suppress(OSError):file.unlink()
        return result
    except Exception:
        with contextlib.suppress(Exception):db.close()
        if staging.exists():staging.unlink()
        if not old:
            if public.exists():
                result=last_public(public,today,now);atomic_json(public,result);return result
            raise
        db=connect(old);m=metadata(db);items,audit=extract(db,today);db.close()
        result=payload(items,m,today,now,True);atomic_json(public,result)
        return result
    finally:lock.close()

def fetch(url,destination):
    request=urllib.request.Request(url)
    destination=Path(destination)
    fd,name=tempfile.mkstemp(prefix='fcc-',suffix='.download',dir=destination.parent);os.close(fd)
    temp=Path(name);total=0
    try:
        with urllib.request.urlopen(request,timeout=120) as response, temp.open('wb') as f:
            expected=response.headers.get('Content-Length')
            while block:=response.read(1024*1024):f.write(block);total+=len(block)
            if expected and total!=int(expected):raise SourceError('Truncated FCC download')
        with temp.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
        immutable=destination.parent/digest/destination.name
        immutable.parent.mkdir(exist_ok=True);os.utime(immutable.parent,None)
        if not immutable.exists():os.replace(temp,immutable)
        return immutable
    finally:temp.unlink(missing_ok=True)

def discover(cache,now):
    """Choose deltas by actual embedded export cutoff. Reconcile snapshots weekly or on gaps.
    Never derive processing order from sun→fri constants.
    """
    cache=Path(cache);downloads=cache/'downloads';downloads.mkdir(parents=True,exist_ok=True)
    current=cache/'current.json';m={}
    if current.exists():
        db=connect(cache/json.loads(current.read_text())['database']);m=metadata(db);db.close()
    request=urllib.request.Request(BASE+'daily/')
    with urllib.request.urlopen(request,timeout=60) as r:index=r.read().decode('utf8')
    names=set(re.findall(r'href="([al]_am_(?:sun|mon|tue|wed|thu|fri|sat)\.zip)"',index))
    if not names:raise SourceError('FCC daily index unavailable')
    plan=[]
    for k in ('a','l'):
        deltas=[]
        for name in sorted(n for n in names if n.startswith(k+'_')):
            path=fetch(BASE+'daily/'+name,downloads/name);deltas.append(inspect_archive(path,k,False,now))
        through=m.get(k+'_through');snapshot=m.get(k+'_snapshot')
        available=sorted({d['coverage'] for d in deltas if not through or d['coverage']>through})
        expected=(D.date.fromisoformat(through)+D.timedelta(days=1)).isoformat() if through else None
        reconcile=not through or not snapshot or D.date.fromisoformat(snapshot)<now.date()-D.timedelta(days=7) or (available and available[0]!=expected)
        if reconcile:
            name=k+'_amat.zip';path=fetch(BASE+'complete/'+name,downloads/name)
            full=inspect_archive(path,k,True,now);plan.append(full);through=full['coverage']
        for delta in sorted(deltas,key=lambda d:d['coverage']):
            if delta['coverage']>through:plan.append(delta);through=delta['coverage']
    return plan

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--cache',required=True);parser.add_argument('--public',required=True);parser.add_argument('--today');parser.add_argument('--archives',help='Offline manifest: path, kind a/l, complete boolean')
    args=parser.parse_args();now=D.datetime.now(UTC)
    # Puerto Rico is UTC-4 year-round, independent of server locale/DST.
    today=D.date.fromisoformat(args.today) if args.today else (now-D.timedelta(hours=4)).date()
    try:
        if args.archives:archives=[inspect_archive(x['path'],x['kind'],x['complete'],now) for x in json.loads(Path(args.archives).read_text())]
        else:archives=discover(args.cache,now)
    except Exception as error:
        print('FCC source unavailable/invalid; retaining last valid base:',type(error).__name__)
        # Force the failed-batch path, recalculating expiry from last validated private database.
        archives=[{'kind':'a','complete':False,'coverage':'9999-01-01','sha256':'invalid'}]
    result=run(args.cache,args.public,archives,today,now)
    print(json.dumps({'count':len(result['items']),'meta':result['meta']}))

if __name__=='__main__':main()
