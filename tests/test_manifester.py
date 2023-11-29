from unittest.mock import Mock

from functools import cached_property
from requests import request
from manifester import Manifester
from manifester.settings import settings
from manifester.helpers import MockStub, fake_http_response_code
import pytest
import random
import string
import uuid

manifest_data = {
    "log_level": "debug",
    "offline_token": "test",
    "proxies": {"https:" ""},
    "url": {
        "token_request": "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token",
        "allocations": "https://api.access.redhat.com/management/v1/allocations",
    },
    "sat_version": "sat-6.14",
    "subscription_data": [
        {
            "name": "Red Hat Enterprise Linux Server, Premium (Physical or Virtual Nodes)", 
            "quantity": 1,
            },
        {
            "name": "Red Hat Satellite Infrastructure Subscription",
            "quantity": 1
        },
    ],
    "simple_content_access": "enabled",
}

sub_pool_response = {
    'body':
    [
        {
            'id': f'{uuid.uuid4().hex}',
            'subscriptionName': 'Red Hat Satellite Infrastructure Subscription',
            'entitlementsAvailable': 8,
        },
        {
            'id': f'{uuid.uuid4().hex}',
            'subscriptionName': 'Red Hat Enterprise Linux for Virtual Datacenters, Premium',
            'entitlementsAvailable': 8,
        },
        {
            'id': f'{uuid.uuid4().hex}',
            'subscriptionName': 'Red Hat Beta Access',
            'entitlementsAvailable': 8,
        },
        {
            'id': f'{uuid.uuid4().hex}',
            'subscriptionName': 'Red Hat Enterprise Linux Server, Premium (Physical or Virtual Nodes)',
            'entitlementsAvailable': 8,
        },
    ],
}
class RhsmApiStub(MockStub):

    def __init__(self, in_dict=None, **kwargs):
        self._good_codes = kwargs.get("good_codes", [200])
        self._bad_codes = kwargs.get("bad_codes", [429, 500, 504])
        self._fail_rate = kwargs.get("fail_rate", 10)
        self._has_offset = kwargs.get("has_offset", False)
        super().__init__(in_dict)

    @cached_property
    def status_code(self):
        return fake_http_response_code(self._good_codes, self._bad_codes, self._fail_rate)

    def post(self, *args, **kwargs):
        """Simulate responses to POST requests for RHSM API endpoints used by Manifester"""

        if args[0].endswith("openid-connect/token"):
            self.access_token = "this is a simulated access token"
            return self
        if args[0].endswith("allocations"):
            self.uuid = "1234567890"
            return self
        if args[0].endswith("entitlements"):
            self.params = kwargs["params"]
            return self

    def get(self, *args, **kwargs):
        """"Simulate responses to GET requests for RHSM API endpoints used by Manifester"""

        if args[0].endswith("versions"):
            self.version_response = {'body': [
                {'value': 'sat-6.14', 'description': 'Satellite 6.14'},
                {'value': 'sat-6.13', 'description': 'Satellite 6.13'},
                {'value': 'sat-6.12', 'description': 'Satellite 6.12'},
            ]}
            return self
        if args[0].endswith("pools") and not self._has_offset:
            self.pool_response = sub_pool_response
            return self
        if args[0].endswith("pools") and self._has_offset:
            if kwargs["params"]["offset"] != 50:
                self.pool_response = {'body': []}
                for x in range(50):
                    self.pool_response["body"].append({
                        'id': f'{"".join(random.sample(string.ascii_letters, 12))}', 
                        'subscriptionName': 'Red Hat Satellite Infrastructure Subscription', 
                        'entitlementsAvailable': random.randrange(100),
                        })
                return self
            else:
                self.pool_response["body"] += sub_pool_response["body"]
                return self
        if "allocations" in args[0] and not ("export" in args[0] or "pools" in args[0]):
            self.allocation_data = "this allocation data also includes entitlement data"
            return self
        if args[0].endswith("export"):
            self.body = {'exportJobID': '123456', 'href': 'exportJob'}
            return self
        if "exportJob" in args[0]:
            del self.status_code
            if self.force_export_failure is True and not self._has_offset:
                self._good_codes = [202]
            else:
                self._good_codes = [202, 200]
            self.body = {'exportID': 27, 'href': 'https://example.com/export/98ef892ac11'}
            return self
        if "export" in args[0] and not args[0].endswith("export"):
            del self.status_code
            self._good_codes = [200]
            # Manifester expects a bytes-type object to be returned as the manifest
            self.content = b"this is a simulated manifest"
            return self

    def delete(self, *args, **kwargs):
        """Simulate responses to DELETE requests for RHSM API endpoints used by Manifester"""

        if args[0].endswith("allocations/1234567890") and kwargs["params"]["force"] == "true":
            del self.status_code
            self.content = b""
            self._good_codes=[204]
            return self


def test_basic_init(manifest_category="golden_ticket"):
    """Test that manifester can initialize with the minimum required arguments and verify that resulting object has an access token attribute"""

    manifester_inst = Manifester(manifest_category=manifest_category, requester=RhsmApiStub(in_dict=None))
    assert isinstance(manifester_inst, Manifester)
    assert manifester_inst.access_token == "this is a simulated access token"

def test_create_allocation():
    """Test that manifester's create_subscription_allocation method returns a UUID"""

    manifester = Manifester(manifest_category="golden_ticket", requester=RhsmApiStub(in_dict=None))
    allocation_uuid = manifester.create_subscription_allocation()
    assert allocation_uuid.uuid == "1234567890"

def test_negative_simple_retry_timeout():
    """Test that exceeding the attempt limit when retrying a failed API call results in an exception"""

    manifester = Manifester(manifest_category="golden_ticket", requester=RhsmApiStub(in_dict=None, fail_rate=0))
    manifester.requester._fail_rate = 100
    with pytest.raises(Exception) as exception:
        manifester.get_manifest()
    assert str(exception.value) == "Retry timeout exceeded"

def test_negative_manifest_export_timeout():
    """Test that exceeding the attempt limit when exporting a manifest results in an exception"""

    with pytest.raises(Exception) as exception:
        manifester = Manifester(manifest_category="golden_ticket", requester=RhsmApiStub(in_dict={"force_export_failure": True}))
    assert str(exception.value) == "Export timeout exceeded"

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

def test_ingest_manifest_data_via_dict():
    """Test that manifester is able to read configuration data from a dictionary"""

    manifester = Manifester(manifest_category=manifest_data, requester=RhsmApiStub(in_dict=None))
    assert manifester.subscription_data == manifest_data["subscription_data"]
    assert manifester.simple_content_access == manifest_data["simple_content_access"]
    assert manifester.token_request_url == manifest_data["url"]["token_request"]
    assert manifester.allocations_url == manifest_data["url"]["allocations"]
    assert manifester.sat_version == manifest_data["sat_version"]

def test_get_subscription_pools_with_offset():
    """Tests that manifester can retrieve all subscription pools from an account containing more than 50 pools"""

    manifester = Manifester(manifest_category="golden_ticket", requester=RhsmApiStub(in_dict=None, has_offset=True))
    manifester.get_manifest()
    assert len(manifester.subscription_pools["body"]) > 50

def test_correct_subs_added_to_allocation():
    """Test that the subscriptions added to the subscription allocation match the subscription data defined in manifester's config"""

    manifester = Manifester(manifest_category="golden_ticket", requester=RhsmApiStub(in_dict=None))
    manifester.get_manifest()
    active_subs = sorted([ x["subscriptionName"] for x in manifester._active_pools ])
    sub_names_from_config = sorted([ x["NAME"] for x in manifester.subscription_data ])
    assert active_subs == sub_names_from_config

def test_invalid_sat_version():
    """Test that an invalid sat_version value will be replaced with the latest valid sat_version"""

    manifest_data["sat_version"] = "sat-6.20"
    manifester = Manifester(manifest_category=manifest_data, requester=RhsmApiStub(in_dict=None))
    assert manifester.sat_version == "sat-6.14"