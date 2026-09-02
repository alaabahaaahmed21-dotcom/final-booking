import base64
import hashlib
import io
import unittest
from unittest.mock import MagicMock, patch
import requests
from pypdf import PdfWriter
import sheets
from config import APP_SCHEMA_VERSION
from test_request import example
from helpers import calculate_booking_totals


def valid_pdf(label="test"):
    output = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    writer.add_metadata({"/Title": label})
    writer.write(output)
    return output.getvalue()

class ClientTests(unittest.TestCase):
    def test_post_sends_schema_without_get_preflight(self):
        reply=MagicMock(); reply.status_code=200; reply.json.return_value={'ok':True,'saved':True}
        with patch.object(sheets,'backend_is_configured',return_value=True), patch.object(sheets,'_url',return_value='https://example.test/exec'), patch.object(sheets,'_secret',return_value='token'), patch.object(sheets.requests,'get') as get, patch.object(sheets.requests,'post',return_value=reply) as post:
            result=sheets._post('create_booking',{'booking':{}},attempts=1)
            self.assertTrue(result['saved'])
            get.assert_not_called()
            self.assertEqual(post.call_args.kwargs['json']['schema_version'],APP_SCHEMA_VERSION)

    def test_unexpected_version_response_does_not_crash(self):
        reply=MagicMock(); reply.json.return_value=[]
        with patch.object(sheets.requests,'get',return_value=reply):
            self.assertEqual(sheets._check_version('test')['error_code'],'SCHEMA_VERSION')

    def test_fast_save_does_not_generate_pdf(self):
        b=example(); b.update(calculate_booking_totals(b))
        with patch.object(sheets,'_secret',return_value='test'), patch.object(sheets,'generate_pdf',side_effect=AssertionError('PDF must not run on reserve path')) as pdf, patch.object(sheets,'_post',return_value={'ok':True,'saved':True,'invoice_created':False}) as post:
            result=sheets.save_to_google_sheets(b,max_attempts=1)
            self.assertTrue(result.saved)
            pdf.assert_not_called()
            self.assertEqual(post.call_args.args[0],'create_booking')
            self.assertNotIn('invoice',post.call_args.args[1])

    def test_timeout_is_unknown_not_definitively_unsaved(self):
        with patch.object(sheets,'backend_is_configured',return_value=True), patch.object(sheets,'_url',return_value='test'), patch.object(sheets,'_secret',return_value='test'), patch.object(sheets,'_check_version',return_value=None), patch.object(sheets.requests,'post',side_effect=requests.Timeout):
            result=sheets._post('create_booking',{},attempts=1)
            self.assertIn('may already be saved',result['error'])

    def test_load_request_uses_exact_stored_pdf(self):
        stored=valid_pdf()
        response={'ok':True,'saved':True,'invoice_created':True,'invoice_base64':base64.b64encode(stored).decode(),'invoice_sha256':hashlib.sha256(stored).hexdigest()}
        with patch.object(sheets,'_post',return_value=response):
            self.assertEqual(sheets.load_request('ITKF-20260830-ABCDEF123456','grant')['_invoice_pdf_bytes'],stored)

    def test_amendment_uses_same_id_and_revision_invoice(self):
        b=example(); b.update(calculate_booking_totals(b)); b['revision']=2
        auth={'edit_token':'private-token','expected_revision':1,'edit_operation_id':'a'*32}
        with patch.object(sheets,'_secret',return_value='test'),patch.object(sheets,'_post',return_value={'ok':True,'saved':True}) as post:
            sheets.save_to_google_sheets(b,max_attempts=1,edit_context=auth)
            action,body=post.call_args.args
            self.assertEqual(action,'amend_booking')
            self.assertEqual(body['booking']['booking_id'],b['booking_id'])
            self.assertTrue(body['booking']['invoice_no'].endswith('-R2'))
            self.assertEqual(body['expected_revision'],1)
            self.assertNotIn('edit_token',body['booking'])

    def test_code_has_no_automatic_network_retries(self):
        with patch.object(sheets,'_post',return_value={'ok':True}) as post:
            sheets.request_edit_code('itkf-20260830-abcdef123456','example@example.com')
            self.assertEqual(post.call_args.kwargs['attempts'],1)
            self.assertEqual(post.call_args.args[1]['booking_id'],'ITKF-20260830-ABCDEF123456')

    def test_pdf_integrity_failure_is_visible(self):
        result=sheets._decode_pdf({'invoice_base64':base64.b64encode(b'%PDF-fake').decode(),'invoice_sha256':'wrong'})
        self.assertIn('invoice_read_error',result)
        self.assertNotIn('_invoice_pdf_bytes',result)

    def test_normal_document_processing_defers_email(self):
        b=example(); b.update(calculate_booking_totals(b)); b.update(invoice_no='INV-SAVED',invoice_verification_code='saved-code')
        pdf=valid_pdf()
        with patch.object(sheets,'generate_pdf',return_value=pdf),patch.object(sheets,'_post',return_value={'ok':True,'saved':True,'invoice_created':True,'invoice_sha256':hashlib.sha256(pdf).hexdigest()}) as post:
            self.assertTrue(sheets.process_saved_documents(b).saved)
            self.assertTrue(post.call_args.args[1]['defer_email'])

    def test_existing_randomly_protected_pdf_returns_exact_drive_copy(self):
        b=example(); b.update(calculate_booking_totals(b)); b.update(invoice_no='INV-SAVED',invoice_verification_code='saved-code')
        local=valid_pdf('local regenerated copy')
        stored=valid_pdf('authoritative Drive copy')
        first={'ok':True,'saved':True,'invoice_created':True,'invoice_sha256':hashlib.sha256(stored).hexdigest()}
        second={**first,'invoice_base64':base64.b64encode(stored).decode()}
        with patch.object(sheets,'generate_pdf',return_value=local), patch.object(sheets,'_post',side_effect=[first,second]) as post:
            result=sheets.process_saved_documents(b)
            self.assertTrue(result.saved)
            self.assertEqual(result.data['_invoice_pdf_bytes'],stored)
            self.assertEqual(post.call_count,2)
            self.assertTrue(post.call_args_list[1].args[1]['return_pdf'])

    def test_lost_create_response_checks_same_request_before_retry(self):
        b=example(); b.update(calculate_booking_totals(b))
        replies=[
            {'ok':False,'saved':False,'error_code':'CONNECTION'},
            {'ok':True,'saved':True,'booking_id':b['booking_id']},
        ]
        with patch.object(sheets,'_secret',return_value='test'), patch.object(sheets,'_post',side_effect=replies) as post:
            result=sheets.save_to_google_sheets(b,max_attempts=2)
            self.assertTrue(result.saved)
            self.assertEqual([call.args[0] for call in post.call_args_list],['create_booking','booking_status'])

    def test_document_recovery_uses_saved_snapshot(self):
        b=example();b.update(calculate_booking_totals(b));b.update(invoice_no='INV-SAVED-R2',invoice_verification_code='saved-code')
        with patch.object(sheets,'generate_pdf',return_value=b'%PDF-saved') as pdf,patch.object(sheets,'_post',return_value={'ok':True,'saved':True}) as post:
            self.assertTrue(sheets.retry_request_documents(b,'grant').saved)
            self.assertEqual(pdf.call_args.args[0],b)
            self.assertEqual(post.call_args.args[0],'retry_documents')
            self.assertEqual(post.call_args.args[1]['invoice']['verification_code'],'saved-code')

if __name__=='__main__': unittest.main()
