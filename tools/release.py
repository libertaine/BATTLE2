from pathlib import Path
from typing import Iterable, Union, Optional
def pack_release_linux(
    build_dir: Union[str, Path],
    out_dir: Union[str, Path],
    *,
    app_name: str,
    version: str,
    include: Iterable[Union[str, Path]],
    strip_prefix: Optional[Union[str, Path]] = None,
    symlinks: Optional[dict[str, str]] = None,  # {"battle2": "bin/battle2"}
    write_checksums: bool = True,
) -> Path:
    pass