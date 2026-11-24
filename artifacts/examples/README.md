# MFLib Examples artifact

Notebooks in this folder are packaged by `release/release.py` into
`dist/artifacts/mflib-examples-<version>.tar.gz` and uploaded to the FABRIC
Artifact Manager as **MFLib Examples**.

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

Keep these short and simplified. They are what new users see first.
