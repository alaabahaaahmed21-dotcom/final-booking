import base64
import hashlib
import unittest
from unittest.mock import MagicMock, patch
import requests
import sheets
from config import APP_SCHEMA_VERSION
from test_request import example
from helpers import calculate_booking_totals

class ClientTests(unittest.TestCase):
    def test_old_backend_blocked_before_post(self):
        reply=MagicMock(); reply.json.return_value={'version':'2026-08-30-v2'}
        with patch.object(sheets,'backend_is_configured',return_value=True), patch.object(sheets,'_url',return_value='https://example.test/exec'), patch.object(sheets.requests,'get',return_value=reply), patch.object(sheets.requests,'post') as post:
            self.assertEqual(sheets._post('create_booking',{})['error_code'],'SCHEMA_VERSION')
            post.assert_not_called()

    def test_unexpected_version_response_does_not_crash(self):
        reply=MagicMock(); reply.json.return_value=[]
        with patch.object(sheets.requests,'get',return_value=reply):
            self.assertEqual(sheets._check_version('test')['error_code'],'SCHEMA_VERSION')

    def test_pdf_failure_still_submits(self):
        b=example(); b.update(calculate_booking_totals(b))
        with patch.object(sheets,'_secret',return_value='test'), patch.object(sheets,'generate_pdf',side_effect=ValueError('test')), patch.object(sheets,'_post',return_value={'ok':True,'saved':True,'invoice_created':False}) as post:
            result=sheets.save_to_google_sheets(b)
            self.assertTrue(result.saved)
            self.assertEqual(post.call_args.args[1]['invoice'],{})

    def test_timeout_is_unknown_not_definitively_unsaved(self):
        with patch.object(sheets,'backend_is_configured',return_value=True), patch.object(sheets,'_url',return_value='test'), patch.object(sheets,'_secret',return_value='test'), patch.object(sheets,'_check_version',return_value=None), patch.object(sheets.requests,'post',side_effect=requests.Timeout):
            result=sheets._post('create_booking',{},attempts=1)
            self.assertIn('may already be saved',result['error'])

    def test_download_is_exact_stored_pdf(self):
        b=example(); b.update(calculate_booking_totals(b))
        stored=b'%PDF-1.4 stored document'
        response={'ok':True,'saved':True,'invoice_created':True,'invoice_base64':base64.b64encode(stored).decode(),'invoice_sha256':hashlib.sha256(stored).hexdigest()}
        with patch.object(sheets,'_secret',return_value='test'),patch.object(sheets,'generate_pdf',return_value=b'%PDF-1.4 local different bytes'),patch.object(sheets,'_post',return_value=response):
            self.assertEqual(sheets.save_to_google_sheets(b).data['_invoice_pdf_bytes'],stored)

if __name__=='__main__': unittest.main()
