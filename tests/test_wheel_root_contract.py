"""The installed-road callers attest the current entry and the legacy Studio separately."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

import pytest

from conductor.hub.assets import HUB_ASSETS
from conductor.server_assets import PANEL_ASSETS

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "src/conductor/panel"
READS = ("/state.json", "/harnesses.json", "/command/session", "/command/tasks",
         "/command/workflows", "/command/runs", "/command/quotas")


def digest(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


@pytest.fixture(scope="module")
def installed(tmp_path_factory):
    """A real isolated interpreter, without pip, dependencies or an editable source import."""
    prefix = tmp_path_factory.mktemp("installed")
    venv.EnvBuilder(with_pip=False).create(prefix)
    python = prefix / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    query_code = "import json, sysconfig; print(json.dumps(sysconfig.get_path('purelib')))"
    query = subprocess.run([str(python), "-I", "-c", query_code],
                           check=True, capture_output=True, text=True, encoding="utf-8")
    library = Path(json.loads(query.stdout))
    assert library.resolve().is_relative_to(prefix.resolve()), "venv owns its purelib"
    package = library / "conductor"
    shutil.copytree(ROOT / "src/conductor", package,
                    ignore=shutil.ignore_patterns("__pycache__"))
    metadata = library / "agent_conductor-0.1.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text("Name: agent-conductor\nVersion: 0.1.0\n",
                                      encoding="utf-8")
    return prefix, python, package


@pytest.mark.parametrize("entry", ["arachnid.html", "entry-witness.html"])
def test_isolated_probe_reads_the_installed_owners_entry(installed, entry):
    prefix, python, package = installed
    owner = package / "server_assets.py"
    original = owner.read_text(encoding="utf-8")
    assert 'ENTRY_PAGE = "arachnid.html"' in original, "known owning constant in copied source"
    target = package / "panel" / entry
    if entry != "arachnid.html":
        target.write_bytes(b"<!doctype html><title>Independent entry witness</title>")
    try:
        owner.write_text(original.replace('ENTRY_PAGE = "arachnid.html"',
                                         f'ENTRY_PAGE = "{entry}"'), encoding="utf-8")
        done = subprocess.run([str(python), "-I", "-B", str(ROOT / "scripts/installed_probe.py")],
                              cwd=prefix, check=True, capture_output=True,
                              text=True, encoding="utf-8")
        facts = json.loads(done.stdout)
        assert Path(facts["package"]).resolve() == package.resolve()
        assert Path(facts["package"]).resolve().is_relative_to(prefix.resolve())
        assert facts["routes"]["/"] == {"file": entry,
                                          "content_type": "text/html; charset=utf-8"}
        assert facts["files"]["panel/" + entry] == digest(target.read_bytes())
    finally:
        owner.write_text(original, encoding="utf-8")
        if entry != "arachnid.html":
            target.unlink()


@pytest.fixture
def road():
    spec = importlib.util.spec_from_file_location("wheel_root_road", ROOT / "scripts/wheel_road.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def corpus():
    """Expected hashes come from local files, independently of any response from the network."""
    bodies = {path.name: path.read_bytes() for path in PANEL.iterdir() if path.is_file()}
    routes = {route: {"content_type": kind, "file": name}
              for route, (kind, name) in PANEL_ASSETS.items()}
    routes["/"] = {"file": "arachnid.html", "content_type": "text/html; charset=utf-8"}
    facts = {"routes": routes, "files": {"panel/" + name: digest(body)
                                         for name, body in bodies.items()},
             "hub_files": sorted({name for _, name in HUB_ASSETS.values()} | {"hub.html"})}
    return facts, bodies


class Response(io.BytesIO):
    def __init__(self, body, url, content_type, status=200):
        super().__init__(body)
        self.status = status
        self.url = url
        self.headers = {"Content-Type": content_type}

    def geturl(self):
        return self.url


def attach_http(monkeypatch, road, facts, bodies, *, content_type=None, redirect=False, status=200):
    """Only urllib's IO boundary is replaced; the real caller judges bytes and metadata."""
    seen = []
    routes = copy.deepcopy(facts["routes"])

    class Opener:
        def open(self, url, timeout):
            assert timeout == 5
            route = url.removeprefix("http://127.0.0.1:7777")
            seen.append(route)
            if route in READS:
                return Response(b"{}", url, "application/json")
            row = routes[route]
            return Response(bodies[row["file"]], url + ("/redirected" if redirect else ""),
                            content_type or row["content_type"], status)

    monkeypatch.setattr(road.urllib.request, "build_opener", lambda *_args: Opener())
    return seen


def test_http_caller_checks_arachnid_and_all_studio_assets(monkeypatch, road, corpus):
    facts, bodies = corpus
    seen = attach_http(monkeypatch, road, facts, bodies)
    count = road.http_checks("http://127.0.0.1:7777", facts)
    assert count == len(facts["routes"]) + 7
    assert set(seen) == set(facts["routes"]) | set(READS)


@pytest.mark.parametrize("route", ["/", "/panel/studio.html"])
def test_http_caller_requires_document_routes_even_when_alias_preserves_census(
        monkeypatch, road, corpus, route):
    facts, bodies = corpus
    facts["routes"]["/unreachable-alias.html"] = facts["routes"].pop(route)
    attach_http(monkeypatch, road, facts, bodies)
    with pytest.raises(AssertionError):
        road.http_checks("http://127.0.0.1:7777", facts)


@pytest.mark.parametrize("fault", [
    "wrong-body", "content-type", "redirect", "status", "census", "hub"])
def test_http_caller_rejects_integrity_faults(monkeypatch, road, corpus, fault):
    facts, bodies = corpus
    options = {}
    if fault == "wrong-body":
        bodies["arachnid.html"] += b"\n<!-- corrupted bytes -->"
    elif fault == "content-type":
        options["content_type"] = "text/plain"
    elif fault == "redirect":
        options["redirect"] = True
    elif fault == "status":
        options["status"] = 201
    elif fault == "census":
        del facts["routes"]["/panel/arachnid.css"]
    else:
        del facts["files"]["panel/hub.html"]
    attach_http(monkeypatch, road, facts, bodies, **options)
    with pytest.raises(AssertionError):
        road.http_checks("http://127.0.0.1:7777", facts)


@pytest.mark.parametrize("witness", ['id="chat"', 'id="classic"', 'href="/panel/studio.html"'])
def test_root_needs_literal_arachnid_witnesses(monkeypatch, road, corpus, witness):
    facts, bodies = corpus
    assert witness.encode() in bodies["arachnid.html"], "fixture has the chosen root witness"
    bodies["arachnid.html"] = bodies["arachnid.html"].replace(witness.encode(), b"removed")
    # This represents an installed bad document: matching bytes alone must not attest its UI.
    facts["files"]["panel/arachnid.html"] = digest(bodies["arachnid.html"])
    attach_http(monkeypatch, road, facts, bodies)
    with pytest.raises(AssertionError):
        road.http_checks("http://127.0.0.1:7777", facts)


@pytest.mark.parametrize("screen", ["Overview", "Workflow", "Runs", "Decisions", "Agents"])
@pytest.mark.parametrize("prefix", ["screen", "nav"])
def test_explicit_studio_needs_every_screen_and_tab(monkeypatch, road, corpus, screen, prefix):
    facts, bodies = corpus
    witness = f'id="{prefix}{screen}"'.encode()
    assert witness in bodies["studio.html"], "fixture has the chosen Studio witness"
    bodies["studio.html"] = bodies["studio.html"].replace(witness, b"removed")
    facts["files"]["panel/studio.html"] = digest(bodies["studio.html"])
    attach_http(monkeypatch, road, facts, bodies)
    with pytest.raises(AssertionError):
        road.http_checks("http://127.0.0.1:7777", facts)
