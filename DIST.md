### Building Distribution Packages

Before running the build script, ensure you have the required dependencies:

- `./artifacts` directory with `pipeline-zen.env` and `pipeline-zen-gcp-key.json` (ask a team member for these files)

```bash

To build distribution packages for nodes:

```bash
./scripts/build-artifacts.sh
```

This will create an artifacts directory with:

- `abis.tar.gz` (from `../contracts/out`)
- `addresses.json` (from `../contracts/address.json`)
- `pipeline-zen.tar.gz` (from cloning `pipeline-zen` in a temporary directory)

And will upload the artifacts to the Lumino GCS buckets.

### Publishing to PyPI

After building the packages, update the `VERSION` file, and publish to PyPI with:

```bash
./scripts/push-to-pypi.sh
```