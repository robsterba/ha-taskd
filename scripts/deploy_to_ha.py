"""Deploy custom_components/taskd to a Home Assistant box over SSH/SFTP.

Usage (env vars):
  HA_HOST, HA_USER, HA_PASSWORD   SSH target
  HA_CONFIG_DIR (default /config) HA configuration directory
"""

import os
import stat
import sys

import paramiko

REPO = "/mnt/d/ai_projects/ha-taskd"
SRC = f"{REPO}/custom_components/taskd"
REMOTE_DIR = os.environ.get("HA_CONFIG_DIR", "/config") + "/custom_components/taskd"


def main() -> None:
    host = os.environ["HA_HOST"]
    user = os.environ["HA_USER"]
    password = os.environ["HA_PASSWORD"]

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(host, username=user, password=password, timeout=10)
    sftp = client.open_sftp()

    def mkdirs(path: str) -> None:
        parts = path.strip("/").split("/")
        cur = ""
        for part in parts:
            cur += f"/{part}"
            try:
                sftp.stat(cur)
            except FileNotFoundError:
                sftp.mkdir(cur)

    mkdirs(REMOTE_DIR)
    count = 0
    for root, dirs, files in os.walk(SRC):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        rel = os.path.relpath(root, SRC).replace(os.sep, "/")
        remote_root = REMOTE_DIR if rel == "." else f"{REMOTE_DIR}/{rel}"
        for d in dirs:
            mkdirs(f"{remote_root}/{d}")
        for fname in files:
            local = os.path.join(root, fname)
            remote = f"{remote_root}/{fname}"
            sftp.put(local, remote)
            sftp.chmod(remote, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IROTH)
            count += 1
            print(f"put {remote}")

    print(f"DEPLOYED {count} files to {REMOTE_DIR}")
    sftp.close()
    client.close()


if __name__ == "__main__":
    main()
