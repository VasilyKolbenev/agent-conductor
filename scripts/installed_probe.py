"""Installed-wheel provenance, executed by the clean venv's own interpreter under -I.

It refuses unless ``conductor`` imported from inside that venv, then prints one JSON object: the
interpreter, the venv prefix, the package directory and version, the sha256 of every installed
package file, and the routes the installed server serves with the panel file behind each.
Used by scripts/wheel_road.py; it reaches nothing but the installed package.
"""
import hashlib
import importlib.metadata
import json
from pathlib import Path
import sys

import conductor
from conductor import server

package = Path(conductor.__file__).resolve().parent
venv = Path(sys.prefix).resolve()
if not package.is_relative_to(venv):
    raise AssertionError("conductor did not import from the clean venv")
files = {str(path.relative_to(package)).replace("\\", "/"):
         hashlib.sha256(path.read_bytes()).hexdigest()
         for path in package.rglob("*") if path.is_file() and "__pycache__" not in path.parts}
routes = {route: {"content_type": value[0], "file": value[1]}
          for route, value in server.PANEL_ASSETS.items()}
routes["/"] = {"content_type": "text/html; charset=utf-8", "file": "studio.html"}
print(json.dumps({"python": sys.executable, "prefix": str(venv),
                  "package": str(package), "version": importlib.metadata.version("agent-conductor"),
                  "files": files, "routes": routes}, sort_keys=True))
