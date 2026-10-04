import copy,datetime as D,unittest
from cold_run import safe_candidate
from test_publisher import FEED,TODAY

class Privacy(unittest.TestCase):
    def test_aggregate_does_not_include_names_or_ids(self):
        result=safe_candidate(FEED,TODAY)
        self.assertNotIn('items',result)
        self.assertNotIn('callsign',result)
        self.assertEqual(result['records'],1)
    def test_private_extra_field_rejected(self):
        data=copy.deepcopy(FEED);data['items'][0]['usi']='SYNTHETIC_FORBIDDEN'
        with self.assertRaises(ValueError):safe_candidate(data,TODAY)
    def test_rollover_requires_current_window(self):
        with self.assertRaises(ValueError):safe_candidate(FEED,TODAY+D.timedelta(days=1))

if __name__=='__main__':unittest.main()
