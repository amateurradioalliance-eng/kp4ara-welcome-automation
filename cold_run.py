"""Manual dry-run only. No Firebase client, credentials, write API, artifacts or cache."""
import argparse,contextlib,datetime as D,hashlib,json,os,platform,shutil,subprocess,sys,time,uuid
from pathlib import Path
import pipeline
from publisher import validate

def file_bytes(root):
    total=0
    for folder,_,files in os.walk(root):
        for name in files:
            try:total+=(Path(folder)/name).stat().st_size
            except FileNotFoundError:pass
    return total

def safe_candidate(data,today):
    validate(data,today)
    classes={c:sum(x['license_class']==c for x in data['items']) for c in sorted({x['license_class'] for x in data['items']})}
    return {'records':len(data['items']),'classes':classes,'source_through_date':data['meta']['source_through_date'],
            'window_start':data['meta']['window_start'],'window_end':data['meta']['window_end'],'stale':data['meta']['stale']}

def worker(root):
    now=D.datetime.now(pipeline.UTC);today=(now-D.timedelta(hours=4)).date()
    private=root/'private';private.mkdir();public=root/'candidate'/'new-pr-hams.json'
    diagnostic={'stage':'discovery'}
    # Suppress all raw input, exception details, paths and FCC rows from public logs.
    with (private/'processing.log').open('w',encoding='utf8') as log,contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
        try:
            plan=pipeline.discover(private,now)
            diagnostic['stage']='reconstruction'
            result=pipeline.run(private,public,plan,today,now)
            diagnostic.update({'stage':'candidate_validation','records':len(result['items']),'source_through_date':result['meta']['source_through_date'],'window_start':result['meta']['window_start'],'window_end':result['meta']['window_end'],'stale':result['meta']['stale']})
            (root/'diagnostic.json').write_text(json.dumps(diagnostic))
            safe_candidate(result,today)
            return 0
        except Exception as error:
            diagnostic['error_type']=type(error).__name__
            (root/'diagnostic.json').write_text(json.dumps(diagnostic))
            return 1

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--worker');parser.add_argument('--scratch-base',default=os.environ.get('RUNNER_TEMP'))
    args=parser.parse_args()
    if args.worker:return worker(Path(args.worker))
    if not args.scratch_base:raise ValueError('Explicit scratch base required')
    base=Path(args.scratch_base).resolve();checkout=Path(__file__).resolve().parent
    if base==checkout or checkout in base.parents:raise ValueError('Scratch cannot be in checkout')
    base.mkdir(parents=True,exist_ok=True)
    root=base/('kp4ara-dry-'+uuid.uuid4().hex);root.mkdir()
    report={'mode':'DRY_RUN','firebase_writes':0,'fcc_access':'NOT_CONFIRMED','result':'FAIL','platform':platform.platform(),'python':platform.python_version(),'artifacts':False,'persistent_cache':False}
    started=time.perf_counter();peak_disk=peak_rss=0;proc=None
    initial_free=shutil.disk_usage(base).free;min_free=initial_free
    try:
        if initial_free<8*1024**3:raise ValueError('Insufficient free disk')
        proc=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--worker',str(root)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        while proc.poll() is None:
            peak_disk=max(peak_disk,file_bytes(root));min_free=min(min_free,shutil.disk_usage(base).free)
            try:
                status=Path('/proc')/str(proc.pid)/'status'
                if status.exists():
                    for line in status.read_text().splitlines():
                        if line.startswith(('VmRSS:','VmHWM:')):peak_rss=max(peak_rss,int(line.split()[1])*1024)
            except (OSError,ValueError):pass
            if time.perf_counter()-started>6600 or peak_disk>12*1024**3:
                proc.terminate();proc.wait(timeout=30);raise ValueError('Resource guard')
            time.sleep(0.5)
        peak_disk=max(peak_disk,file_bytes(root))
        if sys.platform=='linux':
            import resource
            peak_rss=max(peak_rss,resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss*1024)
        report['download_bytes']=sum(p.stat().st_size for p in (root/'private/downloads').rglob('*.zip'))
        if (root/'diagnostic.json').exists():report['diagnostic']=json.loads((root/'diagnostic.json').read_text())
        if proc.returncode:raise ValueError('FCC reconstruction failed or invalid')
        public=root/'candidate/new-pr-hams.json';raw=public.read_bytes();data=json.loads(raw)
        today=(D.datetime.now(pipeline.UTC)-D.timedelta(hours=4)).date()
        report.update(safe_candidate(data,today));report.update({'result':'PASS','fcc_access':'CONFIRMED','public_json_bytes':len(raw),'public_json_sha256':hashlib.sha256(raw).hexdigest(),'private_fields_in_candidate':False})
    except Exception:
        report['result']='FAIL'
    finally:
        if proc and proc.poll() is None:proc.terminate();proc.wait(timeout=30)
        report.update({'duration_seconds':round(time.perf_counter()-started,3),'peak_worker_rss_bytes':peak_rss,'peak_scratch_bytes_sampled_500ms':peak_disk,'filesystem_used_delta_peak_bytes':max(0,initial_free-min_free),'private_persistent_bytes':0})
        # Delete only this explicitly created run directory, never the scratch base.
        if root.parent!=base or not root.name.startswith('kp4ara-dry-'):raise ValueError('Unsafe cleanup path')
        shutil.rmtree(root)
        report['scratch_removed']=not root.exists()
        sanitized=json.dumps(report,indent=2)
        print(sanitized)
        summary=os.environ.get('GITHUB_STEP_SUMMARY')
        if summary:
            with open(summary,'a',encoding='utf8') as f:f.write('## FCC cold dry-run\n\n```json\n'+sanitized+'\n```\n')
    return 0 if report['result']=='PASS' else 1

if __name__=='__main__':
    try:sys.exit(main())
    except Exception:
        print('DRY_RUN failed: no publication attempted; details suppressed for privacy.');sys.exit(1)
