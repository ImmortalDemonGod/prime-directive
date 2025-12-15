import pytest
import sys
from sqlalchemy.util import concurrency


def test_debug_greenlet():
    print(f"\nDEBUG: have_greenlet={concurrency.have_greenlet}")
    try:
        import greenlet

        print(f"DEBUG: greenlet version={greenlet.__version__}")
        print(f"DEBUG: greenlet file={greenlet.__file__}")
    except ImportError:
        print("DEBUG: greenlet module NOT found")
    print(f"DEBUG: sys.path={sys.path}")
