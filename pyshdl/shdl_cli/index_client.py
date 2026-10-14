"""Fetching from a Circuit Circus index (INDEX_FORMAT.md), stdlib-only.

The index URL precedence is ``--index`` > ``$SHDL_INDEX_URL`` >
``[registry] url`` in shdl.toml > the default. ``file://`` URLs work
natively (urllib), which is both the test story and the local-checkout
story. Relative URLs inside index JSON resolve against the URL of the JSON
file that contained them. Archive URLs are also derivable from the pinned
layout (``archives/<name>-<version>.tar.gz``), which lets ``shdl install``
fetch straight from a lock without re-reading the index.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlsplit

from .errors import CliError
from .semver import Version

DEFAULT_INDEX = "https://rafa-rrayes.github.io/CCircus"
ENV_VAR = "SHDL_INDEX_URL"
TIMEOUT = 15  # seconds


def resolve_index_url(cli_flag: str | None, project_url: str | None) -> str:
    url = cli_flag or os.environ.get(ENV_VAR) or project_url or DEFAULT_INDEX
    return url.rstrip("/")


class IndexClient:
    def __init__(self, index_url: str):
        self.index_url = index_url.rstrip("/")
        if urlsplit(self.index_url).scheme not in ("http", "https", "file"):
            raise CliError(
                f"index URL {index_url!r} must start with http://, https:// or file://"
            )
        self.registry_url = f"{self.index_url}/registry.json"
        self._memo: dict[str, bytes] = {}

    # --- transport ---------------------------------------------------------
    def _fetch(self, url: str) -> bytes:
        if url not in self._memo:
            try:
                with urllib.request.urlopen(url, timeout=TIMEOUT) as resp:
                    self._memo[url] = resp.read()
            except urllib.error.HTTPError as e:
                raise CliError(f"index fetch failed: {url}: HTTP {e.code}") from e
            except urllib.error.URLError as e:
                raise CliError(f"index fetch failed: {url}: {e.reason}") from e
            except (OSError, ValueError) as e:
                raise CliError(f"index fetch failed: {url}: {e}") from e
        return self._memo[url]

    def _fetch_json(self, url: str) -> dict:
        try:
            doc = json.loads(self._fetch(url).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise CliError(f"{url}: not valid index JSON: {e}") from e
        if not isinstance(doc, dict):
            raise CliError(f"{url}: not valid index JSON (expected an object)")
        return doc

    # --- the two index levels ----------------------------------------------
    def registry(self) -> dict:
        doc = self._fetch_json(self.registry_url)
        if doc.get("registry_format") != 2:
            raise CliError(
                f"{self.registry_url}: unsupported registry_format "
                f"{doc.get('registry_format')!r} (this toolchain speaks 2)"
            )
        return doc

    def registry_entry(self, name: str) -> dict:
        for p in self.registry().get("packages", []):
            if p.get("name") == name:
                return p
        raise CliError(
            f"package {name!r} not found in the index ({self.registry_url})"
        )

    def package_index(self, name: str) -> dict:
        url = urljoin(self.registry_url, self.registry_entry(name)["index"])
        doc = self._fetch_json(url)
        if doc.get("index_format") != 2:
            raise CliError(
                f"{url}: unsupported index_format {doc.get('index_format')!r} "
                "(this toolchain speaks 2)"
            )
        return doc

    def versions(self, name: str) -> dict[Version, dict]:
        """Parsed version -> version entry, for the resolver."""
        return {
            Version.parse(v): entry
            for v, entry in self.package_index(name)["versions"].items()
        }

    # --- archives ------------------------------------------------------------
    def archive_url(self, name: str, version: str) -> str:
        # the layout is pinned by INDEX_FORMAT.md §5, so no index fetch is needed
        return f"{self.index_url}/archives/{name}-{version}.tar.gz"

    def download_archive(self, name: str, version: str, sha256: str) -> bytes:
        """The archive's bytes, sha256-verified before anything touches them."""
        url = self.archive_url(name, version)
        blob = self._fetch(url)
        got = hashlib.sha256(blob).hexdigest()
        if got != sha256:
            raise CliError(
                f"sha256 mismatch for {name} {version}: expected {sha256}, "
                f"got {got} (from {url}) — refusing to unpack"
            )
        return blob
