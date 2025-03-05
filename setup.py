from setuptools import setup, find_packages

# Read README.md file for long description
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read version from VERSION file
with open("VERSION", "r", encoding="utf-8") as fh:
    version = fh.read()

# Read requirements from requirements.txt file
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = fh.read().splitlines()

setup(
    name="lumino-contracts-client",
    version=version,
    author="Lumino Labs AI",
    author_email="engg@luminolabs.ai",
    license="Apache License 2.0",
    description="Client for interacting with the Lumino Labs protocol",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/luminolabs/contracts-client",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    python_requires=">=3.10",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "lumino-node = lumino.contracts_client.node_client:initialize_lumino_node",
            "lumino-client = lumino.contracts_client.user_client:cli",
        ],
    },
)
