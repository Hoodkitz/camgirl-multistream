from datetime import datetime, timedelta

import pytest

from apps.domain import vault
from apps.domain.automation import goal_progress, render_template, should_greet
from apps.domain.ratelimit import TokenBucket
from apps.domain.signing import sign, verify

MK = "ZGV2LW1hc3Rlci1rZXktZG8tbm90LXVzZS1pbi1wciE="


def test_envelope_roundtrip_und_aad_bindung():
    kms = vault.LocalKMS(MK)
    kek = kms.create_kek("t1")
    s = vault.seal(kms, kek, "t1", "stripchat", b"geheim")
    assert b"geheim" not in s.ciphertext and len(s.iv) == 12 and len(s.auth_tag) == 16
    assert vault.unseal(kms, kek, "t1", "stripchat", s) == b"geheim"
    with pytest.raises(vault.DecryptionError):  # in fremden Mandanten kopiert
        vault.unseal(kms, kek, "t2", "stripchat", s)
    with pytest.raises(vault.DecryptionError):
        vault.unseal(kms, kek, "t1", "chaturbate", s)


def test_manipulation_erkannt():
    kms = vault.LocalKMS(MK)
    kek = kms.create_kek("t1")
    s = vault.seal(kms, kek, "t1", "x", b"geheim")
    s.ciphertext = bytes([s.ciphertext[0] ^ 1]) + s.ciphertext[1:]
    with pytest.raises(vault.DecryptionError):
        vault.unseal(kms, kek, "t1", "x", s)


def test_crypto_shredding():
    kms = vault.LocalKMS(MK)
    kek = kms.create_kek("t1")
    s = vault.seal(kms, kek, "t1", "x", b"geheim")
    kms.destroy_kek(kek)
    with pytest.raises(vault.KeyDestroyed):
        vault.unseal(kms, kek, "t1", "x", s)


def test_template_nur_erlaubte_platzhalter():
    assert render_template("Hi {username} auf {platform}!", username="Max", platform="sc") == "Hi Max auf sc!"
    assert render_template("{__class__} {0} {username.x}", username="M") == "{__class__} {0} {username.x}"
    assert len(render_template("a" * 2000)) == 500


def test_greet_cooldown():
    now = datetime(2026, 1, 2, 12)
    assert should_greet(None, now, 24)
    assert not should_greet(now - timedelta(hours=3), now, 24)
    assert should_greet(now - timedelta(hours=25), now, 24)


def test_goal_nur_einmal_neu_erreicht():
    assert goal_progress(900, 50, 1000).newly_reached is False
    p = goal_progress(950, 100, 1000)
    assert p.reached and p.newly_reached and p.total == 1050
    assert goal_progress(1050, 10, 1000).newly_reached is False


def test_token_bucket():
    b = TokenBucket(capacity=2, refill_per_sec=1)
    assert b.take("u", 0)[0] and b.take("u", 0)[0]
    ok, retry = b.take("u", 0)
    assert not ok and retry == pytest.approx(1.0)
    assert b.take("u", 1.0)[0]
    assert b.take("anderer", 0)[0]


def test_hmac_signatur():
    h = sign("s", b"{}", ts=1000)
    assert verify("s", b"{}", h, now=1000)
    assert not verify("s", b"{} ", h, now=1000)
    assert not verify("x", b"{}", h, now=1000)
    assert not verify("s", b"{}", h, now=2000)  # Replay ausserhalb Toleranz
    assert not verify("s", b"{}", "kaputt")
