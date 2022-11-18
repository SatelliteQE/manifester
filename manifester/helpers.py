import time

from logzero import logger


def simple_retry(cmd, cmd_args=None, cmd_kwargs=None, max_timeout=240, _cur_timeout=1):
    """Re(Try) a function given its args and kwargs up until a max timeout"""
    cmd_args = cmd_args if cmd_args else []
    cmd_kwargs = cmd_kwargs if cmd_kwargs else {}
    # If additional debug information is needed, the following log entry can be modified to
    # include the data being passed by adding {cmd_kwargs=} to the f-string. Please do so
    # with caution as some data (notably the offline token) should be treated as a secret.
    logger.debug(f"Sending request to endpoint {cmd_args}")
    response = cmd(*cmd_args, **cmd_kwargs)
    logger.debug(f"Response status code is {response.status_code}")
    if response.status_code in [429, 500, 504]:
        new_wait = _cur_timeout * 2
        if new_wait > max_timeout:
            raise Exception("Timeout exceeded")
        logger.debug(f"Trying again in {_cur_timeout} seconds")
        time.sleep(_cur_timeout)
        response = simple_retry(cmd, cmd_args, cmd_kwargs, max_timeout, new_wait)
    return response

def process_sat_version(sat_version, valid_sat_versions):
    """Ensure that the sat_version parameter is properly formatted for the RHSM API when creating
       a subscription allocation with the 'POST allocations' endpoint"""
    if sat_version not in valid_sat_versions:
        # The valid values for the sat_version parameter when creating a subscription allocation
        # are all 8 characters or less (e.g. 'sat-6.11'). Some data sources may include a Z-stream
        # version (e.g. 'sat-6.11.0') when retrieving this value from settings. The conditional
        # below assumes that, if the length of sat_version is greated than 8 characters, it includes
        # a Z-stream version that should be removed.
        if len(sat_version) > 8:
            sat_version = sat_version.split('.')
            sat_version = sat_version[0:2]
            sat_version = ".".join(sat_version)
        # The conditional below assumes that an invalid sat_version with the Z-stream version removed
        # is a Y-stream version in development. New Y-stream versions are not available as valid 
        # sat_version values for the 'POST allocations' endpoint until the corresponding Satellite
        # versions are generally available. As of Satellite 6.12, decrementing the Y-stream version
        # by 1 works around this constraint, but the conditional below may need to be modified to
        # accommodate versioning scheme changes or additional use cases. 
        if sat_version not in valid_sat_versions:
            sat_version = sat_version.split('.')
            sat_version[1] = str(int(sat_version[1]) - 1)
            sat_version = ".".join(sat_version)
        assert sat_version in valid_sat_versions
    return sat_version
