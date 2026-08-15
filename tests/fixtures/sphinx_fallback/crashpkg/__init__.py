"""Package whose attribute access raises during autodoc member gathering.

This mimics a third-party object that raises on attribute access in a way the
napoleon ``_skip_member`` patch does NOT catch (it only guards
``__qualname__``). When autodoc introspects ``Boom``, accessing any attribute
raises, aborting the build. Mocking the package via ``autodoc_mock_imports``
makes autodoc skip importing it, so the converter's fallback recovers.
"""


class Boom:
    def __getattribute__(self, name):
        raise RuntimeError("crash during autodoc member gathering")
