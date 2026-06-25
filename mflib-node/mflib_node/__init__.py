"""
FABRIC Measurement Framework Node Server - REST API server for the measurement node.
"""
__version_info__ = [0, 1, 0, "dev", 0]

__version__ = f"{__version_info__[0]}.{__version_info__[1]}.{__version_info__[2]}"

if __version_info__[3] != "f":
    __version__ = f"{__version__}{__version_info__[3]}{__version_info__[4]}"

description = "FABRIC Measurement Framework Node Server"
