import base64
import json
import os
import shutil
import tarfile
import tempfile
from typing import Optional
from urllib import error, request


class RestNodeAdapter:
    """
    Minimal node adapter that maps MFLib node operations onto a REST API.
    """

    def __init__(self, base_url: str, auth_token: Optional[str] = None, timeout=300):
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout
        self._metadata = None

    def execute(self, command, quiet=False):
        response = self._request(
            "/execute",
            {
                "command": command,
                "quiet": quiet,
            },
        )
        return response.get("stdout", ""), response.get("stderr", "")

    def upload_file(self, local_file_path, remote_file_path):
        with open(local_file_path, "rb") as local_file:
            content = base64.b64encode(local_file.read()).decode("ascii")

        return self._request(
            "/upload-file",
            {
                "remote_file_path": remote_file_path,
                "content_base64": content,
            },
        )

    def download_file(self, local_file_path, remote_file_path, retry=None):
        response = self._request(
            "/download-file",
            {
                "remote_file_path": remote_file_path,
            },
        )
        local_dir_path = os.path.dirname(local_file_path)
        if local_dir_path:
            os.makedirs(local_dir_path, exist_ok=True)
        with open(local_file_path, "wb") as local_file:
            local_file.write(base64.b64decode(response["content_base64"]))
        return {"local_file_path": local_file_path, "retry": retry}

    def upload_directory(self, local_directory_path, remote_directory_path):
        local_directory_path = os.path.normpath(local_directory_path)
        if not os.path.isdir(local_directory_path):
            raise FileNotFoundError(f"Directory not found: {local_directory_path}")

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_base_path = os.path.join(tmpdir, "mflib_upload")
            archive_filename = shutil.make_archive(
                archive_base_path,
                "gztar",
                root_dir=os.path.dirname(local_directory_path),
                base_dir=os.path.basename(local_directory_path),
            )
            with open(archive_filename, "rb") as archive_file:
                archive_base64 = base64.b64encode(archive_file.read()).decode("ascii")

        return self._request(
            "/upload-directory",
            {
                "remote_directory_path": remote_directory_path,
                "archive_base64": archive_base64,
                "archive_format": "gztar",
            },
            timeout=max(self.timeout, 900),
        )

    def get_management_ip(self):
        return self._metadata_value("management_ip")

    def get_username(self):
        return self._metadata_value("username")

    def get_name(self):
        return self._metadata_value("name") or "direct-meas-node"

    def _metadata_value(self, key):
        if self._metadata is None:
            self._metadata = self._request("/metadata", None, method="GET")
        return self._metadata.get(key, "")

    def _request(self, path, payload, method="POST", timeout=None):
        headers = {}
        data = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            data = json.dumps(payload).encode("utf-8")
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        req = request.Request(
            url=f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )

        try:
            with request.urlopen(req, timeout=timeout or self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"REST node request failed with status {exc.code}: {body}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"REST node request failed: {exc}") from exc
