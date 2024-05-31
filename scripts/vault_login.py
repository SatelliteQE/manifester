#!/usr/bin/env python
"""Enables and Disables an OIDC token to access secrets from HashiCorp Vault."""
import sys

from manifester.helpers import Vault

if __name__ == "__main__":
    with Vault() as vclient:
        if sys.argv[-1] == "--login":
            vclient.login()
        elif sys.argv[-1] == "--status":
            vclient.status()
        else:
            vclient.logout()
