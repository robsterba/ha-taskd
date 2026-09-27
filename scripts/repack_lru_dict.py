"""One-off helper: repackage lru-dict 1.4.1 wheel as 1.3.0 for HA pin resolution.

HA 2026.2 pins lru-dict==1.3.0, which has no cp313 Windows wheel and no
MSVC build tools exist on this machine. The LRUCache API used by HA is
unchanged between 1.3.0 and 1.4.1, so we relabel the real 1.4.1 wheel.
"""

import os
import subprocess
import sys
import tempfile
import zipfile

SRC = os.path.join(tempfile.gettempdir(), "wheels", "lru_dict-1.4.1-cp313-cp313-win_amd64.whl")
DST = os.path.join(tempfile.gettempdir(), "lru_dict-1.3.0-cp313-cp313-win_amd64.whl")


def main() -> None:
    with (
        zipfile.ZipFile(SRC) as zin,
        zipfile.ZipFile(DST, "w", zipfile.ZIP_DEFLATED) as zout,
    ):
        names = []
        for item in zin.infolist():
            data = zin.read(item.filename)
            new_name = item.filename.replace(
                "lru_dict-1.4.1.dist-info", "lru_dict-1.3.0.dist-info"
            )
            if new_name.endswith("METADATA"):
                data = data.replace(b"Version: 1.4.1", b"Version: 1.3.0")
            if not new_name.endswith("RECORD"):
                zout.writestr(new_name, data)
                names.append(new_name)
        record = "\n".join(f"{name},," for name in names) + "\n"
        zout.writestr("lru_dict-1.3.0.dist-info/RECORD", record)

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--force-reinstall", DST],
        capture_output=True,
        text=True,
    )
    print(result.stdout[-400:] or result.stderr[-400:])


if __name__ == "__main__":
    main()
