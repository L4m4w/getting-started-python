"""Allure TestOps integration helpers.

Offline-only by default: result scanning, scenario mapping, upload-package
building and local state transitions never touch the network. Network calls
go through `client` and run only when the operator passes an explicit mode.
"""
