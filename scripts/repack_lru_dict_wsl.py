"""Relabel the installed lru-dict 1.4.1 as version 1.3.0.

HA 2026.2 pins lru-dict==1.3.0, which has no cp313 wheel and no compiler
is available in this environment. The LRUCache API used by HA is
unchanged between 1.3.0 and 1.4.1, so we rewrite the installed
dist-info instead of building the old version.
"""

import os
import shutil
import sysconfig


def main() -> None:
    site = sysconfig.get_paths()["purelib"]
    old = os.path.join(site, "lru_dict-1.4.1.dist-info")
    new = os.path.join(site, "lru_dict-1.3.0.dist-info")
    assert os.path.isdir(old), "lru-dict 1.4.1 is not installed"

    with open(os.path.join(old, "METADATA"), "rb") as fh:
        metadata = fh.read().replace(b"Version: 1.4.1", b"Version: 1.3.0")
    with open(os.path.join(old, "RECORD"), "rb") as fh:
        record = fh.read().replace(b"lru_dict-1.4.1.dist-info", b"lru_dict-1.3.0.dist-info")

    shutil.move(old, new)
    with open(os.path.join(new, "METADATA"), "wb") as fh:
        fh.write(metadata)
    with open(os.path.join(new, "RECORD"), "wb") as fh:
        fh.write(record)
    print("lru-dict relabelled to 1.3.0")


if __name__ == "__main__":
    main()
