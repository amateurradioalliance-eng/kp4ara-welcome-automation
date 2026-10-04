import datetime as D
import importlib.util
import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import pipeline as p

TODAY=D.date(2026,10,3);NOW=D.datetime(2026,10,3,15,tzinfo=p.UTC)

def person(db,call='WP4ABC',state='PR',purpose='NE',klass='T',grant='2026-10-02',id='1',frn='one',individual='I',trustee='',vanity='',priorclass='',previous=''):
    db.execute('INSERT INTO hd VALUES (?,?,?,?,?,?,?)',('l',id,'file'+id,call,'A','HA',grant))
    db.execute('INSERT INTO en VALUES (?,?,?,?,?,?)',('l',id,'FCC Name',state,frn,individual))
    db.execute('INSERT INTO am VALUES (?,?,?,?,?,?,?,?,?)',('l',id,klass,trustee,'','','','',''))
    db.execute('INSERT INTO ad VALUES (?,?,?,?,?,?)',('a',id,'file'+id,purpose,'G',''))
    db.execute('INSERT INTO en VALUES (?,?,?,?,?,?)',('a',id,'FCC Name',state,frn,individual))
    db.execute('INSERT INTO am VALUES (?,?,?,?,?,?,?,?,?)',('a',id,klass,trustee,'','N',vanity,previous,priorclass))
    db.execute('INSERT INTO grants VALUES (?,?,?)',('a',id,grant))

class Rules(unittest.TestCase):
    def setUp(self):self.db=p.connect(':memory:')
    def tearDown(self):self.db.close()
    def test_initial_classes(self):
        for i,c in enumerate(['T','G','E']):person(self.db,id=str(i),frn=str(i),call='WP4AB'+str(i),klass=c)
        items,_=p.extract(self.db,TODAY);self.assertEqual(len(items),3)
    def test_non_initial_purposes(self):
        for i,c in enumerate(['RO','RM','MD','AU','DU','CA','AM','WD']):person(self.db,id=str(i),frn=str(i),call='WP4A'+str(i),purpose=c)
        self.assertEqual(p.extract(self.db,TODAY)[0],[])
    def test_pr_state_controls_prefix(self):
        person(self.db,call='KP4ZZZ',state='FL');person(self.db,id='2',frn='two',call='K1ABC',state='PR')
        self.assertEqual([x['callsign'] for x in p.extract(self.db,TODAY)[0]],['K1ABC'])
    def test_club_trustee(self):
        person(self.db,individual='C');person(self.db,id='2',frn='two',call='WP4AA',trustee='WP3L')
        self.assertEqual(p.extract(self.db,TODAY)[0],[])
    def test_changes(self):
        person(self.db,vanity='A');person(self.db,id='2',frn='two',call='WP4AA',priorclass='T');person(self.db,id='3',frn='three',call='WP4BB',previous='K1ABC')
        self.assertEqual(p.extract(self.db,TODAY)[0],[])
    def test_history_and_status(self):
        person(self.db);self.db.execute("UPDATE ad SET status='P'");self.assertEqual(p.extract(self.db,TODAY)[0],[])
        self.db.execute("UPDATE ad SET status='G'");self.db.execute("UPDATE grants SET date='2026-10-01'");self.assertEqual(p.extract(self.db,TODAY)[0],[])
    def test_prior_license_outside_pr(self):
        person(self.db);self.db.execute('INSERT INTO hd VALUES (?,?,?,?,?,?,?)',('l','old','','K1OLD','E','HA','2000-01-01'));self.db.execute('INSERT INTO en VALUES (?,?,?,?,?,?)',('l','old','FCC Name','TX','one','I'))
        self.assertEqual(p.extract(self.db,TODAY)[0],[])
    def test_inclusive_boundary_and_future(self):
        for i,day in enumerate(['2026-09-02','2026-09-03','2026-10-03','2026-10-04']):person(self.db,id=str(i),frn=str(i),call='WP4AB'+str(i),grant=day)
        self.assertEqual({x['grant_date'] for x in p.extract(self.db,TODAY)[0]},{'2026-09-03','2026-10-03'})
    def test_empty(self):self.assertEqual(p.extract(self.db,TODAY)[0],[])
    def test_duplicate_identity_ambiguous(self):
        person(self.db);person(self.db,id='2',call='WP4AA');self.assertEqual(p.extract(self.db,TODAY)[0],[])
    def test_public_minimization(self):
        person(self.db);items,_=p.extract(self.db,TODAY)
        self.assertEqual(set(items[0]),{'callsign','name','license_class','grant_date'})
    def test_identity_first_query_plans(self):
        for query in [p.APPLICATION_LINK,p.PRIOR_LICENSE,p.PRIOR_INITIAL]:
            plan=self.db.execute('EXPLAIN QUERY PLAN '+query,('test','2026-10-02')).fetchall()
            self.assertIn('SEARCH e USING INDEX en_frn',plan[0][3])
    def test_delta_replay_and_gap(self):
        p.setmeta(self.db,'l_through','2026-10-02');self.db.execute("INSERT INTO ledger VALUES ('same','l','2026-10-02',0)")
        self.assertFalse(p.ingest(self.db,{'sha256':'same'}))
        with self.assertRaises(p.SourceError):p.ingest(self.db,{'sha256':'next','kind':'l','complete':False,'coverage':'2026-10-04'})
    def test_corrupt_and_empty_zip(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'a_am_fri.zip';file.write_bytes(b'corrupt')
            with self.assertRaises(zipfile.BadZipFile):p.inspect_archive(file,'a',False,NOW)
            with zipfile.ZipFile(file,'w') as z:z.writestr('counts','File Creation Date: Sat Oct  3 04:00:00 EDT 2026\r\n')
            self.assertTrue(p.inspect_archive(file,'a',False,NOW)['empty'])
            with self.assertRaises(p.SourceError):p.inspect_archive(file,'a',True,NOW)
    def test_cutoff_uses_manifest_not_fixed_week(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'a_am_fri.zip'
            with zipfile.ZipFile(file,'w') as z:z.writestr('counts','File Creation Date: Sat Oct 10 04:00:00 EDT 2026\r\n')
            item=p.inspect_archive(file,'a',False,NOW+D.timedelta(days=7))
            self.assertEqual(item['coverage'],'2026-10-09')
            with self.assertRaises(p.SourceError):p.inspect_archive(file,'a',False,NOW)
    def test_weekday_mismatch(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'a_am_mon.zip'
            with zipfile.ZipFile(file,'w') as z:z.writestr('counts','File Creation Date: Sat Oct  3 04:00:00 EDT 2026\r\n')
            with self.assertRaises(p.SourceError):p.inspect_archive(file,'a',False,NOW)
    def test_atomic_publication(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'feed.json';p.atomic_json(file,{'items':['old']})
            with patch.object(p.os,'replace',side_effect=OSError('interrupted')):
                with self.assertRaises(OSError):p.atomic_json(file,{'items':['new']})
            self.assertEqual(json.loads(file.read_text()),{'items':['old']})
    def test_private_cache_cannot_be_public_subdirectory(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)/'public'
            with self.assertRaises(p.SourceError):p.run(root/'private',root/'feed.json',[],TODAY,NOW)
    def test_count_and_schema_failure_rolls_back(self):
        with tempfile.TemporaryDirectory() as folder:
            file=Path(folder)/'l_am_fri.zip'
            with zipfile.ZipFile(file,'w') as z:
                z.writestr('counts','File Creation Date: Sat Oct  3 04:00:00 EDT 2026\n1 /x/HD.dat\n1 /x/EN.dat\n1 /x/AM.dat\n1 /x/HS.dat\n4 total\n')
                for n in ['HD','EN','AM','HS']:z.writestr(n+'.dat',n+'|bad\n')
            item=p.inspect_archive(file,'l',False,NOW);p.setmeta(self.db,'l_through','2026-10-01')
            with self.assertRaises(p.SourceError):
                with self.db:p.ingest(self.db,item)
    def test_fcc_failure_last_valid_and_expiry(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cache=root/'private';cache.mkdir();public=root/'public'/'feed.json';db=p.connect(cache/'valid.sqlite');person(db,grant='2026-09-03')
            for k in ['a','l']:p.setmeta(db,k+'_through','2026-10-02')
            p.setmeta(db,'last_updated','2026-10-03T12:00:00+00:00');db.commit();db.close();p.atomic_json(cache/'current.json',{'database':'valid.sqlite'})
            original=(cache/'valid.sqlite').read_bytes()
            with patch.object(p,'ingest',side_effect=p.SourceError('FCC down')):
                result=p.run(cache,public,[{'kind':'a','complete':False,'coverage':'2026-10-03'}],TODAY,NOW)
                self.assertEqual(len(result['items']),1);self.assertTrue(result['meta']['stale']);self.assertEqual(result['meta']['last_updated'],'2026-10-03T12:00:00+00:00')
                result=p.run(cache,public,[{'kind':'a','complete':False,'coverage':'2026-10-03'}],TODAY+D.timedelta(days=1),NOW)
                self.assertEqual(result['items'],[])
            self.assertEqual(original,(cache/'valid.sqlite').read_bytes())
    def test_bootstrap_failure_preserves_accepted_public_seed(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);public=root/'public'/'feed.json'
            items=[{'callsign':'WP4ABC','name':'FCC Name','license_class':'Technician','grant_date':'2026-09-03'}]
            p.atomic_json(public,p.payload(items,{'a_through':'2026-10-02','l_through':'2026-10-02','last_updated':NOW.isoformat()},TODAY,NOW))
            with patch.object(p,'ingest',side_effect=p.SourceError('FCC down')):
                result=p.run(root/'private',public,[{'kind':'a','complete':False,'coverage':'2026-10-03'}],TODAY,NOW)
                self.assertEqual(len(result['items']),1);self.assertTrue(result['meta']['stale'])

if __name__=='__main__':unittest.main(verbosity=2)
