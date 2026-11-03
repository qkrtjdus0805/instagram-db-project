"""Pure unit tests: can be run even before local MySQL is configured."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from security import check_password, make_password_hash


def test_passwords_are_hashed_and_verified():
    stored = make_password_hash('correct horse battery staple')
    assert 'correct horse battery staple' not in stored
    assert check_password('correct horse battery staple', stored)
    assert not check_password('wrong', stored)


def test_salts_differ_per_account():
    assert make_password_hash('secret123') != make_password_hash('secret123')
