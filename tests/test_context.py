"""Tests for tenantkit.tenancy.context — thread-local storage."""

import threading
import pytest
from tenantkit.tenancy.context import (
    set_current_tenant,
    get_current_tenant,
    set_current_db_alias,
    get_current_db_alias,
    set_current_request,
    get_current_request,
    clear_context,
)


class TestThreadLocalContext:

    def setup_method(self):
        clear_context()

    def teardown_method(self):
        clear_context()

    # -- tenant name --

    def test_set_and_get_tenant(self):
        set_current_tenant('acme')
        assert get_current_tenant() == 'acme'

    def test_get_tenant_returns_none_when_not_set(self):
        assert get_current_tenant() is None

    def test_overwrite_tenant(self):
        set_current_tenant('acme')
        set_current_tenant('globex')
        assert get_current_tenant() == 'globex'

    # -- db alias --

    def test_set_and_get_db_alias(self):
        set_current_db_alias('tenant_acme')
        assert get_current_db_alias() == 'tenant_acme'

    def test_get_db_alias_returns_none_when_not_set(self):
        assert get_current_db_alias() is None

    # -- request --

    def test_set_and_get_request(self):
        fake_request = object()
        set_current_request(fake_request)
        assert get_current_request() is fake_request

    def test_get_request_returns_none_when_not_set(self):
        assert get_current_request() is None

    # -- clear --

    def test_clear_context_resets_all(self):
        set_current_tenant('acme')
        set_current_db_alias('tenant_acme')
        set_current_request(object())
        clear_context()
        assert get_current_tenant() is None
        assert get_current_db_alias() is None
        assert get_current_request() is None

    def test_clear_context_safe_when_nothing_set(self):
        clear_context()  # should not raise

    # -- thread isolation --

    def test_tenant_is_isolated_per_thread(self):
        set_current_tenant('main_thread')
        results = {}

        def worker():
            results['child_before'] = get_current_tenant()
            set_current_tenant('child_thread')
            results['child_after'] = get_current_tenant()

        t = threading.Thread(target=worker)
        t.start()
        t.join()

        # Parent context is unaffected by child thread changes
        assert get_current_tenant() == 'main_thread'
        # Child sets its own tenant independently
        assert results['child_after'] == 'child_thread'
        # Child's change does not bleed into parent
        assert get_current_tenant() == 'main_thread'
