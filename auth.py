"""Password hashes stored in Streamlit secrets, not in GitHub."""
import hashlib
import hmac
import secrets


def make_hash(password, salt=None):
    salt = salt or secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 310000)
    return f"pbkdf2_sha256$310000${salt.hex()}${dk.hex()}"


def verify(password, encoded):
    try:
        method, iterations, salt, digest = encoded.split("$")
        if method != "pbkdf2_sha256" or int(iterations) < 200000: return False
        computed = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(computed, bytes.fromhex(digest))
    except (ValueError, TypeError, AttributeError): return False


if __name__ == "__main__":
    import getpass
    print(make_hash(getpass.getpass("Create dashboard password: ")))
