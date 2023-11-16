from unittest.mock import Mock

from requests import request
from manifester import Manifester
from manifester.settings import settings
from manifester.helpers import MockStub, fake_http_response_code
import pytest
import random

def test_basic_init(manifest_category="golden_ticket"):
    """Test that manifester can initialize with the minimum required arguments and verify that resulting object has an access token attribute"""

    manifester_inst = Manifester(manifest_category=manifest_category, requester=RhsmApiStub(in_dict=None))
    assert isinstance(manifester_inst, Manifester)
    assert manifester_inst.access_token == "this is a simulated access token"

class RhsmApiStub(MockStub):

    def __init__(self, in_dict=None, **kwargs):
        self._good_codes = kwargs.get("good_codes", [200])
        self._bad_codes = kwargs.get("bad_codes", [429, 500, 504])
        self._fail_rate = kwargs.get("fail_rate", 10)
        self.status_code = kwargs.get("status_code") or fake_http_response_code(self._good_codes, self._bad_codes, self._fail_rate)
        super().__init__(in_dict)

    def post(*args, **kwargs):
        """Simulate responses to POST requests for RHSM API endpoints used by Manifester"""

        if args[1].endswith("openid-connect/token"):
            return RhsmApiStub(in_dict={"access_token": "this is a simulated access token"})
        if args[1].endswith("allocations"):
            return RhsmApiStub(in_dict={"uuid": "1234567890"})
        if args[1].endswith("entitlements"):
            return RhsmApiStub(in_dict={"params": kwargs["params"]}, status_code=200)

    def get(*args, **kwargs):
        """"Simulate responses to GET requests for RHSM API endpoints used by Manifester"""

        if args[1].endswith("versions"):
            return RhsmApiStub(in_dict={"valid_sat_versions": ["sat-6.12", "sat-6.13", "sat-6.14"]})
        if args[1].endswith("pools"):
            # question: how to fake > 50 pools to test use of offset parameter?
            return RhsmApiStub(in_dict={'body': [{'id': '987adf2a8977', 'subscriptionName': 'Red Hat Satellite Infrastructure Subscription', 'entitlementsAvailable': 13}]})
        if "allocations" in args[1] and not ("export" in args[1] or "pools" in args[1]):
            return RhsmApiStub(in_dict={"allocation_data": "this allocation data also includes entitlement data"})
        if args[1].endswith("export"):
            return RhsmApiStub(in_dict={'body': {'exportJobID': '123456', 'href': 'exportJob'}})
        if "exportJob" in args[1]:
            responses = [202, 200]
            return RhsmApiStub(in_dict={'body': {'exportID': 27, 'href': 'https://example.com/export/98ef892ac11'}}, status_code=random.choice(responses))
        if "export" in args[1] and not args[1].endswith("export"):
            return RhsmApiStub(in_dict={"content": b"this is a simulated manifest"})

    def delete(*args, **kwargs):
        """Simulate responses to DELETE requests for RHSM API endpoints used by Manifester"""

        if args[1].endswith("allocations/1234567890") and kwargs["params"]["force"] == "true":
            return RhsmApiStub(in_dict={"content": b""}, good_codes=[204])


def test_create_allocation():
    """Test that manifester's create_subscription_allocation method returns a UUID"""

    manifester = Manifester(manifest_category="golden_ticket", requester=RhsmApiStub(in_dict=None))
    allocation_uuid = manifester.create_subscription_allocation()
    assert allocation_uuid == "1234567890"

def test_negative_export_limit_exceeded():
    """Test that exceeding the limit when checking an export job's status results in an exception"""

def test_get_manifest():
    """Test that manifester's get_manifest method returns a manifest"""

    manifester = Manifester(manifest_category="golden_ticket", requester=RhsmApiStub(in_dict=None))
    manifest = manifester.get_manifest()
    assert manifest.content.decode("utf-8") == "this is a simulated manifest"
    assert manifest.status_code == 200

def test_delete_subscription_allocation():
    """Test that manifester's delete_subscription_allocation method deletes a subscription allocation"""

    manifester = Manifester(manifest_category="golden_ticket", requester=RhsmApiStub(in_dict=None))
    manifester.get_manifest()
    response = manifester.delete_subscription_allocation()
    assert response.status_code == 204
    assert response.content == b""
