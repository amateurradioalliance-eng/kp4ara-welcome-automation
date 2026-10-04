from pathlib import Path
import copy,datetime as D,hashlib,json,unittest
from publisher import publish,fingerprint,PATH
CONFIG={'rewrites':[{'glob':'**','path':'/index.html'}]}
FILES={'/index.html':'synthetic-html','/assets/app.js':'synthetic-js'}
TODAY=D.date(2026,10,3)
FEED={'items':[{'callsign':'K1TEST','name':'Synthetic Test Person','license_class':'General','grant_date':'2026-10-02'}],
      'meta':{'source_through_date':'2026-10-02','window_start':'2026-09-03','window_end':'2026-10-03','stale':False}}
class Fake:
    def __init__(self):
        self.current={'version':'mock-approved-welcome-version','config':copy.deepcopy(CONFIG),'files':{**FILES,PATH:'old-public-json-hash'}}
        self.state=None;self.releases=[];self.uploads=[];self.reads=0;self.conflict_at=None;self.billing=False;self.bad_manifest=False;self.extra_upload=False
    def live(self):
        self.reads+=1
        if self.reads==self.conflict_at:self.current={**self.current,'version':'mock-external-deployment'}
        return copy.deepcopy(self.current)
    def billing_enabled(self):return self.billing
    def create_version(self,config):self.state={'version':'mock-new-version','config':copy.deepcopy(config),'files':{}};return self.state['version']
    def populate(self,version,mapping):self.state['files']=copy.deepcopy(mapping);return [mapping[PATH]]+(['unexpected'] if self.extra_upload else [])
    def upload(self,version,digest,body):assert hashlib.sha256(body).hexdigest()==digest;self.uploads.append(digest)
    def finalize(self,version):pass
    def manifest(self,version):
        result=copy.deepcopy(self.state)
        if self.bad_manifest:result['files']['/index.html']='corrupt'
        return result
    def release(self,version):self.current=copy.deepcopy(self.state);self.releases.append(version)
def anchor(api):return {'version':api.current['version'],'protected_sha256':fingerprint(api.current['config'],api.current['files'])}
class Rules(unittest.TestCase):
    def reject(self,api,data=FEED,ref=None):
        with self.assertRaises(ValueError):publish(api,ref or anchor(api),data,TODAY)
        self.assertEqual(api.releases,[])
    def test_only_json_changes_synthetic_manifest(self):
        api=Fake();before=copy.deepcopy(api.current);ref=anchor(api);result=publish(api,ref,FEED,TODAY)
        changed=[k for k in api.current['files'] if api.current['files'][k]!=before['files'][k]]
        self.assertEqual(changed,[PATH]);self.assertEqual(len(api.uploads),1);self.assertEqual(result['protected_sha256'],ref['protected_sha256'])
    def test_wrong_version_abort_before_mutation(self):
        api=Fake();ref=anchor(api);ref['version']='unexpected';self.reject(api,ref=ref);self.assertIsNone(api.state)
    def test_protected_changed(self):
        api=Fake();ref=anchor(api);api.current['files']['/index.html']='changed';self.reject(api,ref=ref)
    def test_before_prepare_conflict(self):api=Fake();api.conflict_at=2;self.reject(api);self.assertIsNone(api.state)
    def test_before_release_conflict(self):api=Fake();api.conflict_at=3;self.reject(api)
    def test_private_field(self):api=Fake();data=copy.deepcopy(FEED);data['items'][0]['frn']='SYNTHETIC-FORBIDDEN';self.reject(api,data)
    def test_unknown_metadata(self):api=Fake();data=copy.deepcopy(FEED);data['meta']['private']='forbidden';self.reject(api,data)
    def test_stale_fcc(self):api=Fake();data=copy.deepcopy(FEED);data['meta']['stale']=True;self.reject(api,data)
    def test_incomplete_coverage(self):api=Fake();data=copy.deepcopy(FEED);data['meta']['source_through_date']='2026-09-01';self.reject(api,data)
    def test_duplicate(self):api=Fake();data=copy.deepcopy(FEED);data['items'].append(data['items'][0]);self.reject(api,data)
    def test_expired(self):api=Fake();data=copy.deepcopy(FEED);data['items'][0]['grant_date']='2026-01-01';self.reject(api,data)
    def test_manifest_corrupt(self):api=Fake();api.bad_manifest=True;self.reject(api)
    def test_unrelated_upload(self):api=Fake();api.extra_upload=True;self.reject(api)
    def test_billing_enabled(self):api=Fake();api.billing=True;self.reject(api);self.assertIsNone(api.state)
    def test_no_welcome_yet(self):api=Fake();del api.current['files'][PATH];self.reject(api)
    def test_valid_empty_list(self):api=Fake();data=copy.deepcopy(FEED);data['items']=[];publish(api,anchor(api),data,TODAY);self.assertEqual(len(api.releases),1)
if __name__=='__main__':unittest.main(verbosity=2)
