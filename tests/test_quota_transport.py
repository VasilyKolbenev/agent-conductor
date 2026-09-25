"""Quota HTTPS boundary: no redirects, bounded input, no credential-bearing errors."""
import pytest

from conductor import quota_transport as transport


KEY = 'synthetic-quota-transport-not-a-real-key'
ENDPOINT = 'https://usage.example.test/user/balance'


class Response:
    status = 200
    body = b'{"is_available":true,"balance_infos":[{"currency":"USD","total_balance":"0.1200"}]}'

    def __init__(self):
        self.headers = {'Content-Type': 'application/json; charset=utf-8'}
        self.read_sizes = []

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read(self, size):
        self.read_sizes.append(size)
        return self.body[:size]


@pytest.fixture
def channel(monkeypatch):
    response = Response()
    calls = []

    class Connection:
        closed = False

        def __init__(self, *args, **kwargs):
            calls.append(('connect', args, kwargs))

        def request(self, *args, **kwargs):
            calls.append(('request', args, kwargs))

        def getresponse(self):
            return response

        def close(self):
            self.closed = True
            calls.append(('close',))

    monkeypatch.setattr(transport.http.client, 'HTTPSConnection', Connection)
    return response, calls


def test_fixed_https_request_and_decimal_text_survive(channel, monkeypatch):
    response, calls = channel
    monkeypatch.setenv('HTTPS_PROXY', 'http://must-not-be-used.invalid:9999')
    payload = transport.read_quota_json(ENDPOINT, KEY)
    assert payload['balance_infos'][0]['total_balance'] == '0.1200'
    assert calls == [
        ('connect', ('usage.example.test',), {'port': 443, 'timeout': 5}),
        ('request', ('GET', '/user/balance'), {'headers': {
            'Authorization': 'Bearer ' + KEY, 'Accept': 'application/json',
            'Accept-Encoding': 'identity', 'Connection': 'close'}}),
        ('close',)]
    assert response.read_sizes == [transport.MAX_RESPONSE_BYTES + 1]


@pytest.mark.parametrize('endpoint', [None, '', 'http://usage.example.test/x',
    'https://name:password@usage.example.test/x', 'https://usage.example.test:444/x',
    'https://usage.example.test/x?q=1', 'https://usage.example.test/x?',
    'https://usage.example.test/x#fragment', 'https://usage.example.test/x#',
    'https://usage.example.test', 'https://usage.example.test/\r\nx',
    'https://usage.example.test\\other/x', 'https://usage.example.test:bad/x'])
def test_invalid_endpoint_refuses_before_any_connection(endpoint, channel):
    with pytest.raises(transport.QuotaFetchError, match='^unsupported_endpoint$'):
        transport.read_quota_json(endpoint, KEY)
    assert channel[1] == []


@pytest.mark.parametrize('key', [None, '', 'with space', 'with\rnewline', 'x' * 8193, 'ключ'])
def test_invalid_bearer_never_reaches_headers(key, channel):
    with pytest.raises(transport.QuotaFetchError, match='^unauthorized$'):
        transport.read_quota_json(ENDPOINT, key)
    assert channel[1] == []


@pytest.mark.parametrize('status, reason', [(301, 'unavailable'), (302, 'unavailable'),
    (307, 'unavailable'), (308, 'unavailable'), (401, 'unauthorized'),
    (403, 'unauthorized'), (429, 'rate_limited'), (500, 'unavailable')])
def test_status_never_follows_redirect_or_reads_error_body(status, reason, channel):
    response, calls = channel
    response.status = status
    response.headers['Location'] = 'https://credential-victim.invalid/'
    response.body = KEY.encode()
    with pytest.raises(transport.QuotaFetchError) as caught:
        transport.read_quota_json(ENDPOINT, KEY)
    assert caught.value.reason == reason and str(caught.value) == reason
    assert response.read_sizes == []
    assert len([c for c in calls if c[0] == 'connect']) == 1
    assert calls[-1] == ('close',)


@pytest.mark.parametrize('body', [b'[]', b'null', b'{"a":1,"a":2}',
    b'{"nested":{"a":1,"a":2}}', b'{"a":NaN}', b'{"a":Infinity}', b'{"a":1e999}',
    b'\xff', b'{"private":"' + KEY.encode() + b'"',
    b' ' * (transport.MAX_RESPONSE_BYTES + 1), b'{"a":' + b'[' * 1500 + b'0' + b']' * 1500 + b'}'],
    ids=['array', 'null', 'duplicate', 'nested-duplicate', 'nan', 'infinity', 'overflow',
         'encoding', 'incomplete', 'oversized', 'too-deep'])
def test_bad_or_oversized_json_is_sanitized_and_connection_closed(body, channel):
    response, calls = channel
    response.body = body
    with pytest.raises(transport.QuotaFetchError, match='^invalid_payload$'):
        transport.read_quota_json(ENDPOINT, KEY)
    assert calls[-1] == ('close',)


@pytest.mark.parametrize('headers', [
    {'Content-Length': str(transport.MAX_RESPONSE_BYTES + 1)},
    {'Content-Length': '-1'}, {'Content-Length': 'not-an-integer'},
    {'Transfer-Encoding': 'gzip'}, {'Transfer-Encoding': 'chunked', 'Content-Length': '2'},
    {'Content-Encoding': 'gzip'}, {'Content-Type': 'text/html'}, {'Content-Type': ''}])
def test_unsupported_framing_refuses_without_reading_body(headers, channel):
    response, calls = channel
    response.headers.update(headers)
    with pytest.raises(transport.QuotaFetchError, match='^invalid_payload$'):
        transport.read_quota_json(ENDPOINT, KEY)
    assert not response.read_sizes
    assert calls[-1] == ('close',)


def test_truncated_but_parseable_response_does_not_claim_complete_balance(channel):
    response, calls = channel
    response.body = b'{}'
    response.headers['Content-Length'] = '20'
    with pytest.raises(transport.QuotaFetchError, match='^invalid_payload$'):
        transport.read_quota_json(ENDPOINT, KEY)
    assert calls[-1] == ('close',)


def test_exact_response_byte_boundary_is_allowed(channel):
    response, _ = channel
    response.body = b'{}' + b' ' * (transport.MAX_RESPONSE_BYTES - 2)
    assert transport.read_quota_json(ENDPOINT, KEY) == {}


def test_network_exception_text_never_escapes_and_socket_closes(channel):
    response, calls = channel

    def broken(_size):
        raise OSError('private upstream detail: ' + KEY)

    response.read = broken
    with pytest.raises(transport.QuotaFetchError) as caught:
        transport.read_quota_json(ENDPOINT, KEY)
    assert str(caught.value) == 'unavailable'
    assert caught.value.__suppress_context__
    assert calls[-1] == ('close',)
