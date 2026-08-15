"""Module used to exercise the napoleon skip-member robustness patch.

It defines a member whose ``__qualname__`` access raises a non-AttributeError.
This mimics the failure mode of pydantic models during autodoc member
gathering: napoleon's ``_skip_member`` does
``getattr(obj, "__qualname__", "")`` which, on such objects, raises and
(without the robustness patch) aborts the whole Sphinx build.
"""


class _RaisingQualname:
    """Object whose ``__qualname__`` access raises a non-AttributeError.

    ``__getattribute__`` is invoked for every attribute access (including
    dunders), so accessing ``__qualname__`` reliably raises here — mirroring
    how pydantic's mock val/ser objects raise when their ``__qualname__`` is
    accessed during autodoc member gathering.
    """

    def __getattribute__(self, name):
        if name == "__qualname__":
            raise RuntimeError("boom: cannot access __qualname__")
        return super().__getattribute__(name)


class Thing:
    """A class with a private member that raises on qualname access.

    Attributes:
        _secret: a member whose ``__qualname__`` access raises.
    """

    _secret = _RaisingQualname()

    def public_method(self):
        """A normal public method."""
        return 42
