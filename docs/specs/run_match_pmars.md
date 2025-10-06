
---

# docs/specs/run_match_pmars.md
```md
# run_match_pmars
**Module:** engine/src/battle_engine/backends/pmars.py  
**Purpose:** Run a deterministic Core War match via pMARS and return `Summary`.

## Signature
```python
from pathlib import Path
from typing import Dict, Union, Optional
def run_match_pmars(
    pmars_bin: Union[str, Path],
    red_a: Union[str, Path],
    red_b: Union[str, Path],
    params: "MatchParams",
    *,
    workdir: Optional[Union[str, Path]] = None,
    env: Optional[Dict[str, str]] = None,
    timeout_sec: int = 30
) -> "Summary":
