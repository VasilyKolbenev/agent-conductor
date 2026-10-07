"""Literal owned-loopback request and absolute response deadline."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,HTTPServer
from threading import Thread,Event
import time
import pytest
from conductor.quota_loopback import fetch_loopback_json,wait_quota_loopback
from conductor.quota_transport import QuotaFetchError

@contextmanager
def server(mode):
    calls=[];stop=Event()
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            calls.append((self.path,self.headers.get('Authorization')))
            if mode=='redirect':
                self.send_response(302);self.send_header('Location','https://other.invalid/secret');self.end_headers();return
            self.send_response(200);self.send_header('Content-Type','application/json')
            if mode=='oversize':self.send_header('Content-Length','65537')
            self.end_headers()
            try:
                if mode=='trickle':
                    for chunk in [b'{',b'"',b'a',b'"',b':',b'1',b'}']:
                        self.wfile.write(chunk);self.wfile.flush()
                        if stop.wait(.12):break
                else:self.wfile.write(b'{"code":0}')
            except (OSError,ValueError):pass
        def log_message(self,*args):pass
    http=HTTPServer(('127.0.0.1',0),Handler);worker=Thread(target=http.serve_forever);worker.start()
    try:yield http.server_port,calls
    finally:stop.set();http.shutdown();worker.join();http.server_close()


def test_exact_literal_endpoint_and_bearer():
    with server('normal') as (port,calls):
        assert fetch_loopback_json(port=port,path='/api/v1/auth',bearer='synthetic-token')=={'code':0}
        assert calls==[('/api/v1/auth','Bearer synthetic-token')]
        with pytest.raises(QuotaFetchError):fetch_loopback_json(port=port,path='/api/v1/auth?other=true',bearer='synthetic-token')
        assert len(calls)==1


@pytest.mark.parametrize('mode',['redirect','oversize'])
def test_redirect_and_oversized_response_refuse(mode):
    with server(mode) as (port,calls):
        with pytest.raises(QuotaFetchError) as error:fetch_loopback_json(port=port,path='/api/v1/oauth/usage',bearer='private-test-token')
        assert 'private-test-token' not in str(error.value) and len(calls)==1


def test_trickle_hits_whole_call_deadline_and_retires_timer():
    with server('trickle') as (port,_):
        start=time.monotonic()
        with pytest.raises(QuotaFetchError):fetch_loopback_json(port=port,path='/api/v1/auth',bearer='test',timeout=.25)
        assert time.monotonic()-start < 1


def test_readiness_has_a_deadline_and_never_accepts_port_zero():
    with pytest.raises(QuotaFetchError):wait_quota_loopback(lambda:None,timeout=.05)
    with pytest.raises(QuotaFetchError):wait_quota_loopback(lambda:(0,'test'),timeout=.05)
