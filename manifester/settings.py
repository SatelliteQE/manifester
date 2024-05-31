"""Retrieves settings from configuration file and runs Dynaconf validators."""
import os
from pathlib import Path

from dynaconf import Dynaconf, Validator

settings_file = "manifester_settings.yaml"
MANIFESTER_DIRECTORY = Path()

if "MANIFESTER_DIRECTORY" in os.environ:
    envar_location = Path(os.environ["MANIFESTER_DIRECTORY"])
    if envar_location.is_dir():
        MANIFESTER_DIRECTORY = envar_location

settings_path = MANIFESTER_DIRECTORY.joinpath("manifester_settings.yaml")
validators = [
    Validator("offline_token", must_exist=True),
    Validator("simple_content_access", default="enabled"),
    Validator("username_prefix", len_min=3),
]
settings = Dynaconf(
    settings_file=str(settings_path.absolute()),
    ENVVAR_PREFIX_FOR_DYNACONF="MANIFESTER",
    load_dotenv=True,
    validators=validators,
)
# settings.validators.validate()
