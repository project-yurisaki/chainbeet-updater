from pathlib import Path, PurePosixPath
import hashlib
import json
import os
import tempfile
import traceback
from urllib.parse import quote, urljoin
import zipfile

import requests


_base_url = 'https://d83fi0em6vlid.cloudfront.net/assets/'


def check_update(dir_path: str | Path) -> bool:
    manifest_url = _base_url + 'android.manifest'
    try:
        response = requests.get(manifest_url)
        if response.status_code != 200:
            return False  # Assume no update is needed when the remote manifest is unavailable.
        remote_manifest = response.json()
    except Exception:
        return False  # Assume no update is needed on network errors.

    remote_version = remote_manifest.get('version', '')

    local_manifest_path = Path(dir_path) / 'android.manifest'
    if not local_manifest_path.exists():
        return True  # An update is needed when the local manifest is missing.

    try:
        with open(local_manifest_path, 'r', encoding='utf-8') as f:
            local_manifest = json.load(f)
        local_version = local_manifest.get('version', '')
        return remote_version != local_version
    except Exception:
        return True  # An update is needed when the local manifest is invalid.


def _asset_path(root: Path, asset_name: str) -> Path:
    """Return a safe local path for a manifest asset name."""
    relative_path = PurePosixPath(asset_name)
    if relative_path.is_absolute() or '..' in relative_path.parts:
        raise ValueError(f'Invalid asset path: {asset_name}')
    return root.joinpath(*relative_path.parts)


def _asset_url(package_url: str, asset_name: str) -> str:
    """Build an asset URL while preserving path separators and escaping names."""
    return urljoin(package_url.rstrip('/') + '/', quote(asset_name, safe='/'))


def _write_asset(destination: Path, content: bytes, expected_md5: str) -> None:
    """Verify content and atomically replace the destination file."""
    actual_md5 = hashlib.md5(content).hexdigest()
    if expected_md5 and actual_md5.lower() != expected_md5.lower():
        raise ValueError(
            f'MD5 mismatch for {destination}: expected {expected_md5}, got {actual_md5}'
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_file_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='wb', dir=destination.parent, delete=False
        ) as temp_file:
            temp_file.write(content)
            temp_file_path = Path(temp_file.name)
        os.replace(temp_file_path, destination)
    finally:
        if temp_file_path is not None and temp_file_path.exists():
            temp_file_path.unlink()


def _download_asset(package_url: str, asset_name: str, asset_info: dict, root: Path) -> None:
    response = requests.get(_asset_url(package_url, asset_name))
    if response.status_code != 200:
        raise RuntimeError(f'Unable to download {asset_name}: HTTP {response.status_code}')

    _write_asset(
        _asset_path(root, asset_name),
        response.content,
        asset_info.get('md5', ''),
    )


def _install_master_database(package_url: str, asset_info: dict, root: Path) -> None:
    """Download master.zip and replace master.db with the archived database."""
    response = requests.get(_asset_url(package_url, 'master.zip'))
    if response.status_code != 200:
        raise RuntimeError(f'Unable to download master.zip: HTTP {response.status_code}')

    zip_content = response.content
    expected_md5 = asset_info.get('md5', '')
    actual_md5 = hashlib.md5(zip_content).hexdigest()
    if expected_md5 and actual_md5.lower() != expected_md5.lower():
        raise ValueError(
            f'MD5 mismatch for master.zip: expected {expected_md5}, got {actual_md5}'
        )

    temp_zip_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as temp_zip:
            temp_zip.write(zip_content)
            temp_zip_path = Path(temp_zip.name)

        with zipfile.ZipFile(temp_zip_path, 'r') as zip_ref:
            # master.db is the only file installed from this archive.
            with zip_ref.open('master.db') as archived_db:
                _write_asset(root / 'master.db', archived_db.read(), '')
    finally:
        if temp_zip_path is not None and temp_zip_path.exists():
            temp_zip_path.unlink()


def _write_manifest(root: Path, manifest: dict) -> None:
    manifest_content = json.dumps(manifest, indent=4, ensure_ascii=False).encode('utf-8')
    _write_asset(root / 'android.manifest', manifest_content, '')


def do_update(dir_path: str | Path) -> bool:
    manifest_url = _base_url + 'android.manifest'
    root = Path(dir_path)
    root.mkdir(parents=True, exist_ok=True)

    try:
        response = requests.get(manifest_url)
        if response.status_code != 200:
            return False
        remote_manifest = response.json()

        package_url = remote_manifest.get('packageUrl', _base_url)
        assets = remote_manifest.get('assets', {})
        if not isinstance(package_url, str) or not isinstance(assets, dict):
            raise ValueError('Invalid android.manifest')

        master_asset = assets.get('master.zip')
        if master_asset is not None:
            if not isinstance(master_asset, dict):
                raise ValueError('Invalid master.zip entry')
            _install_master_database(package_url, master_asset, root)

        # Other manifest entries are regular files and retain their listed paths.
        for asset_name, asset_info in assets.items():
            if asset_name == 'master.zip':
                continue
            if not isinstance(asset_name, str) or not isinstance(asset_info, dict):
                raise ValueError('Invalid asset entry')
            _download_asset(package_url, asset_name, asset_info, root)

        # Commit the version only after every asset was successfully installed.
        _write_manifest(root, remote_manifest)
    except Exception:
        traceback.print_exc()
        return False
    return True
