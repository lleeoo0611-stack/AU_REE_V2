"""Network validity is separate from source availability and snapshot coverage."""
import json
from pathlib import Path
import socket
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from au_ree_v2 import acquisition as a
import test_strict_acquisition as fixtures


class NetworkValidityTests(unittest.TestCase):
    fixture=fixtures.StrictAcquisitionTests.fixture

    def test_dns_checks_all_hosts_and_does_not_fetch(self):
        registry=dict(sources=[dict(url='https://ok.example/a'),dict(url='https://bad.example/b')])
        def resolve(host,*args,**kwargs):
            if host=='bad.example':raise socket.gaierror(11001,'getaddrinfo failed')
            return [('resolved',)]
        with patch.object(a.socket,'getaddrinfo',side_effect=resolve) as dns, patch.object(a.StrictTransport,'__call__') as fetch:
            rows=a.strict_dns_preflight(registry,[dict(url='https://report.example/a')])
        self.assertEqual(dns.call_count,3);fetch.assert_not_called()
        self.assertEqual([r['status'] for r in rows],['NETWORK_ERROR','DNS_OK','DNS_OK'])

    def test_dns_failure_aborts_before_http_cache_or_database(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);registry,_=self.fixture(root)
            with patch.object(a.socket,'getaddrinfo',side_effect=socket.gaierror(11001,'getaddrinfo failed')), patch.object(a.StrictTransport,'__call__') as fetch:
                with self.assertRaisesRegex(a.InvalidNetworkRun,'RUN_INVALID_NETWORK'):
                    a.strict_refresh(root,registry,root/'work',{},'2026-11-13')
            fetch.assert_not_called()
            report=json.loads((root/'work/network_status.json').read_text())
            self.assertFalse(report['valid_for_delivery'])
            self.assertFalse(list((root/'work').glob('strict-*')))
            self.assertFalse(list((root/'work').rglob('*.sqlite')))

    def test_dns_and_connection_errors_never_become_unavailable_or_fallback(self):
        for exc in (URLError(socket.gaierror(11001,'DNS')),ConnectionResetError('connection reset'),URLError(TimeoutError())):
            with self.subTest(error=type(exc).__name__), tempfile.TemporaryDirectory() as folder:
                root=Path(folder);registry,_=self.fixture(root)
                with patch.object(a,'strict_dns_preflight',return_value=[dict(host='example.com',status='DNS_OK',error='')]), patch.object(a.StrictTransport,'__call__',side_effect=exc):
                    with self.assertRaisesRegex(a.InvalidNetworkRun,'RUN_INVALID_NETWORK'):
                        a.strict_refresh(root,registry,root/'work',{},'2026-11-13')
                report=(root/'work/acquisition_report.csv').read_text()
                self.assertIn('NETWORK_ERROR',report);self.assertNotIn('SNAPSHOT_FALLBACK',report)

    def test_five_percent_boundary_and_no_fallback_masking(self):
        rows=[dict(key=str(i),status='FETCHED_SHA_VERIFIED') for i in range(20)]
        rows[0].update(status='NETWORK_ERROR')
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(a.strict_network_report(folder,rows,[])['status'],'NETWORK_VALID')
            rows[1].update(status='SNAPSHOT_FALLBACK_SAME_SHA',network_error=True)
            result=a.strict_network_report(folder,rows,[])
            self.assertEqual(result['status'],'RUN_INVALID_NETWORK')
            self.assertEqual(result['network_error_sources'],2)

    def test_http_and_stopped_host_are_not_network_error(self):
        self.assertEqual(a.strict_failure_status(HTTPError('https://example.com/a',403,'denied',{},None)),'UNAVAILABLE')
        self.assertEqual(a.strict_failure_status(ValueError('HOST_STOPPED:403')),'HOST_STOPPED')
        self.assertEqual(a.strict_failure_status(ValueError('SOURCE_SHA_CHANGED')),'UNAVAILABLE')

    def probe_registry(self):
        return dict(sources=[dict(key=host+str(i),kind='pdf',url='https://'+host+'/'+str(i)+'.pdf')
                    for host in ('www.asx.com.au','announcements.asx.com.au') for i in range(3)])

    @patch.object(a.time,'sleep')
    def test_probe_denial_stops_only_that_host_and_requests_no_indexes(self,sleep):
        transport=a.StrictTransport(a.STRICT_HOSTS)
        def open_request(req,**kwargs):
            host=a.urllib.parse.urlsplit(req.full_url).hostname
            if host=='www.asx.com.au':raise HTTPError(req.full_url,403,'denied',{},None)
            response=Mock();response.status=200;response.headers={}
            response.geturl.return_value=req.full_url;response.read.return_value=b'%PDF test'
            response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
            return response
        transport.opener.open=Mock(side_effect=open_request)
        rows=a.strict_asx_probe(self.probe_registry(),transport)
        self.assertEqual([r['status'] for r in rows],['UNAVAILABLE','HOST_STOPPED','HOST_STOPPED','FETCHED','FETCHED','FETCHED'])
        self.assertEqual(transport.opener.open.call_count,4)
        self.assertEqual(rows[0]['http_status'],403)
        self.assertEqual(len(transport.probed),3)
        for call in transport.opener.open.call_args_list:self.assertTrue(call.args[0].full_url.endswith('.pdf'))

    def test_successful_probe_is_reused_without_refetch(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);registry,raw=self.fixture(root)
            transport=a.StrictTransport({'example.com':'document'})
            transport.probed['pdf']=(raw,{},200,[dict(host='example.com',http_status=200)])
            with patch.object(a,'strict_dns_preflight',return_value=[]), patch.object(a.StrictTransport,'__call__') as fetch:
                selected,rows=a.strict_refresh(root,registry,root/'work',{},'2026-11-13',transport)
            fetch.assert_not_called();self.assertEqual(len(selected),1)
            self.assertEqual(rows[0]['http_status'],200);self.assertTrue(rows[0]['reused_successful_probe'])

    def test_failed_probe_is_not_retried_in_main_acquisition(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);registry,_=self.fixture(root)
            transport=a.StrictTransport({'example.com':'document'})
            transport.probe_failures['pdf']=(URLError('DNS'),None,[dict(host='example.com',http_status=None,error='NETWORK_ERROR')])
            with patch.object(a,'strict_dns_preflight',return_value=[]), patch.object(a.StrictTransport,'__call__') as fetch:
                with self.assertRaises(a.InvalidNetworkRun):a.strict_refresh(root,registry,root/'work',{},'2026-11-13',transport)
            fetch.assert_not_called()

    def test_stopped_asx_cannot_use_committed_snapshot_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);registry,_=self.fixture(root)
            registry['sources'][0]['url']='https://www.asx.com.au/a.pdf'
            transport=a.StrictTransport(a.STRICT_HOSTS);transport.stopped['www.asx.com.au']='403'
            with patch.object(a,'strict_dns_preflight',return_value=[]), patch.object(a.StrictTransport,'__call__') as fetch:
                selected,rows=a.strict_refresh(root,registry,root/'work',{},'2026-11-13',transport)
            fetch.assert_not_called();self.assertFalse(selected)
            self.assertEqual(rows[0]['status'],'HOST_STOPPED')

    def test_cli_network_failure_exits_nonzero_before_build(self):
        from au_ree_v2 import cli
        root=Path(__file__).resolve().parents[1]
        for dns,probe in ([dict(host='failed',status='NETWORK_ERROR',error='DNS')],[]),([], [dict(key='failed',status='NETWORK_ERROR')]):
            with self.subTest(dns=dns), tempfile.TemporaryDirectory() as folder:
                args=['au-ree-v2','all','--refresh','--as-of','2026-11-13','--root',str(root),'--work',folder]
                with patch.object(sys,'argv',args), patch.object(a,'strict_dns_preflight',return_value=dns), patch.object(a,'strict_asx_probe',return_value=probe), patch.object(a,'strict_refresh') as build, patch.object(sys,'stderr'):
                    with self.assertRaises(SystemExit) as exited:cli.main()
                self.assertEqual(exited.exception.code,1);build.assert_not_called()
                self.assertFalse(list(Path(folder).rglob('*.sqlite')))
                self.assertEqual(json.loads((Path(folder)/'network_status.json').read_text())['status'],'RUN_INVALID_NETWORK')

    @patch.object(a.time,'sleep')
    def test_swallowed_official_exception_retains_network_classification(self,sleep):
        transport=a.StrictTransport({'example.com':'government-api'})
        transport.opener.open=Mock(side_effect=URLError('connection failed'))
        with self.assertRaises(URLError) as error:transport('https://example.com/query')
        self.assertTrue(a.failure_details(error.exception)['network_error'])
        self.assertNotIn('network_error',a.failure_details(URLError('legacy request')))


if __name__=='__main__':unittest.main()
