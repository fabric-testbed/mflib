# MFLib Tests artifact

Notebooks in this folder are packaged by `release/release.py` into
`dist/artifacts/mflib-tests-<version>.tar.gz` and uploaded to the FABRIC
Artifact Manager as **MFLib Tests**.

The packager adds two files. Don't create them here:

- `requirements.txt` pins `fabrictestbed-mflib==<version>`. For release
  candidates it also adds the TestPyPI index.
- `RELEASE_INFO.json` records the mflib version, the MeasurementFramework tag,
  and the commit SHAs.

Start every notebook with:

```python
%pip install -q -r requirements.txt
import json, mflib
info = json.load(open("RELEASE_INFO.json"))
assert mflib.__version__ == info["mflib_version"], (mflib.__version__, info)
```

These are the notebooks to run against each release candidate before
`release.py final`.

## Notebooks

- **`route_flow_test.ipynb`**: the end-to-end release test. It builds a fresh
  slice, runs `MFLib(slice)` with the MF release mflib resolves at run time,
  then checks Prometheus, route_flow, Grafana and ELK. It ends with a PASS/FAIL
  summary saved to `release_test_results-<mflib>-<mf>.json`. For an MF rc, set
  `MF_REF`. For an MF final, set `EXPECT_MF`.
