"""Tests for AES-128-ECB crypto utilities."""

import os

from wechat_clawbot.cdn.aes_ecb import aes_ecb_padded_size, decrypt_aes_ecb, encrypt_aes_ecb


class TestAesEcb:
    def test_roundtrip(self):
        key = os.urandom(16)
        plaintext = b"Hello, Weixin CDN!"
        ciphertext = encrypt_aes_ecb(plaintext, key)
        assert ciphertext != plaintext
        decrypted = decrypt_aes_ecb(ciphertext, key)
        assert decrypted == plaintext

    def test_roundtrip_empty(self):
        key = os.urandom(16)
        plaintext = b""
        ciphertext = encrypt_aes_ecb(plaintext, key)
        decrypted = decrypt_aes_ecb(ciphertext, key)
        assert decrypted == plaintext

    def test_roundtrip_exact_block(self):
        key = os.urandom(16)
        plaintext = b"A" * 16  # exact block size
        ciphertext = encrypt_aes_ecb(plaintext, key)
        decrypted = decrypt_aes_ecb(ciphertext, key)
        assert decrypted == plaintext

    def test_roundtrip_large(self):
        key = os.urandom(16)
        plaintext = os.urandom(1024)
        ciphertext = encrypt_aes_ecb(plaintext, key)
        decrypted = decrypt_aes_ecb(ciphertext, key)
        assert decrypted == plaintext

    def test_padded_size(self):
        assert aes_ecb_padded_size(0) == 16
        assert aes_ecb_padded_size(1) == 16
        assert aes_ecb_padded_size(15) == 16
        assert aes_ecb_padded_size(16) == 32
        assert aes_ecb_padded_size(17) == 32

    def test_ciphertext_length_matches_padded_size(self):
        key = os.urandom(16)
        for size in [0, 1, 15, 16, 17, 31, 32, 100]:
            plaintext = b"X" * size
            ciphertext = encrypt_aes_ecb(plaintext, key)
            assert len(ciphertext) == aes_ecb_padded_size(size)
