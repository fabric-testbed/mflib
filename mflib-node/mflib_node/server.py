import argparse
import base64
import getpass
import os
import shutil
import socket
import subprocess
import tempfile
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel


class ExecuteRequest(BaseModel):
    command: str
    quiet: bool = False
    cwd: Optional[str] = None


class FileTransferRequest(BaseModel):
    remote_file_path: str
    content_base64: Optional[str] = None


class DirectoryTransferRequest(BaseModel):
    remote_directory_path: str
    archive_base64: str
    archive_format: str = "gztar"


def create_app(auth_token: Optional[str] = None, default_cwd: Optional[str] = None):
    app = FastAPI(title="MFLib Node API", version="1.0.0")
    state = {
        "auth_token": auth_token,
        "default_cwd": default_cwd,
    }

    def _authorize(authorization: Optional[str] = Header(default=None)):
        expected = state["auth_token"]
        if not expected:
            return
        if authorization != f"Bearer {expected}":
            raise HTTPException(status_code=401, detail="Unauthorized")

    @app.get("/healthz")
    def healthz(_: None = Depends(_authorize)):
        return {"status": "ok"}

    @app.get("/metadata")
    def metadata(_: None = Depends(_authorize)):
        return {
            "name": os.environ.get("MFLIB_NODE_NAME", socket.gethostname()),
            "username": os.environ.get("MFLIB_NODE_USERNAME", getpass.getuser()),
            "management_ip": os.environ.get("MFLIB_MANAGEMENT_IP", "127.0.0.1"),
        }

    @app.post("/execute")
    def execute(payload: ExecuteRequest, _: None = Depends(_authorize)):
        process = subprocess.run(
            payload.command,
            shell=True,
            capture_output=True,
            text=True,
            executable="/bin/bash",
            cwd=payload.cwd or state["default_cwd"],
        )
        return {
            "stdout": process.stdout,
            "stderr": process.stderr,
            "returncode": process.returncode,
        }

    @app.post("/upload-file")
    def upload_file(payload: FileTransferRequest, _: None = Depends(_authorize)):
        if payload.content_base64 is None:
            raise HTTPException(status_code=400, detail="content_base64 is required")
        parent = os.path.dirname(payload.remote_file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(payload.remote_file_path, "wb") as remote_file:
            remote_file.write(base64.b64decode(payload.content_base64))
        return {"success": True, "remote_file_path": payload.remote_file_path}

    @app.post("/download-file")
    def download_file(payload: FileTransferRequest, _: None = Depends(_authorize)):
        if not os.path.exists(payload.remote_file_path):
            raise HTTPException(status_code=404, detail="Remote file not found")
        with open(payload.remote_file_path, "rb") as remote_file:
            content_base64 = base64.b64encode(remote_file.read()).decode("ascii")
        return {
            "success": True,
            "remote_file_path": payload.remote_file_path,
            "content_base64": content_base64,
        }

    @app.post("/upload-directory")
    def upload_directory(
        payload: DirectoryTransferRequest,
        _: None = Depends(_authorize),
    ):
        if payload.archive_format != "gztar":
            raise HTTPException(status_code=400, detail="Only gztar archives are supported")

        os.makedirs(payload.remote_directory_path, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = os.path.join(tmpdir, "upload.tar.gz")
            with open(archive_path, "wb") as archive_file:
                archive_file.write(base64.b64decode(payload.archive_base64))
            shutil.unpack_archive(archive_path, payload.remote_directory_path, "gztar")

        return {
            "success": True,
            "remote_directory_path": payload.remote_directory_path,
        }

    return app


def main():
    parser = argparse.ArgumentParser(description="Run the MFLib measurement node REST API")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--token", default=os.environ.get("MFLIB_API_TOKEN"))
    parser.add_argument("--cwd", default=None)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(
        create_app(auth_token=args.token, default_cwd=args.cwd),
        host=args.host,
        port=args.port,
    )


if __name__ == "__main__":
    main()
