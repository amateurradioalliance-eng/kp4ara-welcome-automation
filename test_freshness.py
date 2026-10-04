import copy,datetime as D,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import freshness as f
import pipeline as p
from publisher import validate
from test_publisher import FEED

def moment(day,hour=13):return D.datetime.fromisoformat(day+f'T{hour:02d}:00:00-04:00')

class Calendar(unittest.TestCase):
    def check(self,day,expected,hour=13):
        now=moment(day,hour);today=now.date()
        self.assertEqual(f.expected_coverage(today,now).isoformat(),expected)
        return today,now
    def test_saturday(self):self.check('2026-10-03','2026-10-02')
    def test_sunday(self):self.check('2026-10-04','2026-10-02')
    def test_monday(self):self.check('2026-10-05','2026-10-02')
    def test_federal_holiday(self):self.check('2026-10-12','2026-10-09')
    def test_day_after_holiday(self):self.check('2026-10-13','2026-10-09')
    def test_observed_friday_holiday(self):self.check('2026-07-05','2026-07-02')
    def test_legitimate_morning_delay(self):
        today,now=self.check('2026-10-06','2026-10-02',11)
        self.assertFalse(f.assess('2026-10-02',today,now)['stale'])
    def test_exact_deadline(self):
        today,now=self.check('2026-10-06','2026-10-05',12)
        self.assertTrue(f.assess('2026-10-02',today,now)['stale'])
    def test_really_stale_sunday(self):
        today,now=self.check('2026-10-04','2026-10-02')
        self.assertTrue(f.assess('2026-10-01',today,now)['stale'])
    def test_absolute_cap(self):
        self.assertEqual(f.assess('2026-10-09',D.date(2026,10,14),moment('2026-10-14',11))['reason'],'absolute_age_exceeded')
    def test_month_rollover(self):self.check('2026-11-01','2026-10-30')
    def test_year_rollover_observed_new_year(self):self.check('2028-01-02','2027-12-30')
    def test_opm_2026_calendar(self):
        expected={'2026-01-01','2026-01-19','2026-02-16','2026-05-25','2026-06-19','2026-07-03','2026-09-07','2026-10-12','2026-11-11','2026-11-26','2026-12-25'}
        self.assertEqual({x.isoformat() for x in f.holidays(2026) if x.year==2026},expected)
    def test_no_fake_coverage_and_last_updated(self):
        today=D.date(2026,10,4);now=moment('2026-10-04')
        meta={'a_through':'2026-10-02','l_through':'2026-10-03','last_updated':'2026-10-03T12:00:00+00:00'}
        data=p.payload([],meta,today,now)
        self.assertEqual(data['meta']['source_through_date'],'2026-10-02')
        self.assertEqual(data['meta']['last_updated'],meta['last_updated'])
        self.assertFalse(data['meta']['stale'])
        self.assertTrue(p.payload([],meta,today,now,failed=True)['meta']['stale'])
    def test_window_is_real_thirty_calendar_days(self):
        today=D.date(2026,10,4);now=moment('2026-10-04')
        data=copy.deepcopy(FEED);data['meta'].update(window_start='2026-09-04',window_end='2026-10-04')
        for boundary in ('2026-09-04','2026-10-04'):
            data['items'][0]['grant_date']=boundary;validate(data,today,now)
        data['items'][0]['grant_date']='2026-09-03'
        with self.assertRaises(ValueError):validate(data,today,now)
    def test_false_fresh_flag_cannot_bypass_policy(self):
        today=D.date(2026,10,4);data=copy.deepcopy(FEED)
        data['meta'].update(source_through_date='2026-10-01',window_start='2026-09-04',window_end='2026-10-04')
        with self.assertRaises(ValueError):validate(data,today,moment('2026-10-04'))
    def test_no_automatic_calendar_extension(self):
        with self.assertRaises(ValueError):f.expected_coverage(D.date(2031,1,1))
    def test_future_coverage_rejected(self):
        self.assertTrue(f.assess('2026-10-05',D.date(2026,10,4),moment('2026-10-04'))['stale'])
    def test_stale_rebuild_preserves_accepted_base_and_timestamp(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);cache=root/'private';cache.mkdir();public=root/'public/feed.json'
            db=p.connect(cache/'valid.sqlite')
            for k in ('a','l'):p.setmeta(db,k+'_through','2026-10-02')
            p.setmeta(db,'last_updated','2026-10-04T12:00:00+00:00');db.commit();db.close()
            p.atomic_json(cache/'current.json',{'database':'valid.sqlite'})
            original=(cache/'valid.sqlite').read_bytes();pointer=(cache/'current.json').read_bytes()
            result=p.run(cache,public,[],D.date(2026,10,6),moment('2026-10-06'))
            self.assertTrue(result['meta']['stale'])
            self.assertEqual(result['meta']['last_updated'],'2026-10-04T12:00:00+00:00')
            self.assertEqual((cache/'valid.sqlite').read_bytes(),original)
            self.assertEqual((cache/'current.json').read_bytes(),pointer)

if __name__=='__main__':unittest.main()
