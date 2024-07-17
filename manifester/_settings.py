"""Module with settings variables/constants."""
import os
from pathlib import Path

settings_file = "manifester_settings.yaml"
MANIFESTER_DIRECTORY = Path()

if "MANIFESTER_DIRECTORY" in os.environ:
    envar_location = Path(os.environ["MANIFESTER_DIRECTORY"])
    if envar_location.is_dir():
        MANIFESTER_DIRECTORY = envar_location

settings_path = MANIFESTER_DIRECTORY.joinpath(settings_file)
