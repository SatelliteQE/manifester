"""Retrieves settings from configuration file and runs Dynaconf validators."""

from dynaconf import Dynaconf, Validator

from manifester._settings import settings_path

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
