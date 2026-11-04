"""Regression tests for the complete M49 gazetteer publication scope."""
import unittest
from build import PUBLISHED_SCOPE, PENDING, SCOPE
from query import select


class PublicationScope(unittest.TestCase):
    def test_sixteen_of_sixteen(self):
        self.assertEqual(len(SCOPE),16)
        self.assertEqual(PUBLISHED_SCOPE,SCOPE)
        self.assertEqual(PENDING,set())

    def test_ar_py_queries_supported(self):
        for cc in ['AR','PY']:
            with self.subTest(country=cc):
                rows=list(select(cc,kind='admin_subdivision',level=1))
                self.assertTrue(rows)
                self.assertTrue(all(r['country_code']==cc and r['parent_id']=='country:'+cc for r in rows))

    def test_out_of_scope_query_rejected(self):
        with self.assertRaisesRegex(ValueError,'not included'):
            list(select('MX'))


if __name__=='__main__':unittest.main()
