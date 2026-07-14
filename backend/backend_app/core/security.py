import base64
import hashlib
import hmac
import os



ALGORITHM="pbkdf2_sha256"

ITERATIONS=600_000

SALT_BYTES=16

HASH_BYTES=32



def _encode(value:bytes):

    return base64.urlsafe_b64encode(
        value
    ).decode("ascii").rstrip("=")



def _decode(value:str):

    padding="="*(-len(value)%4)

    return base64.urlsafe_b64decode(
        value+padding
    )



def hash_password(password:str):

    salt=os.urandom(SALT_BYTES)

    password_hash=hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        ITERATIONS,
        dklen=HASH_BYTES
    )

    return "$".join([
        ALGORITHM,
        str(ITERATIONS),
        _encode(salt),
        _encode(password_hash)
    ])



def verify_password(
    password:str,
    encoded_password:str
):

    try:

        algorithm,iterations_text,salt_text,hash_text=(
            encoded_password.split("$",3)
        )

        iterations=int(iterations_text)


        if (
            algorithm!=ALGORITHM
            or iterations<=0
            or iterations>2_000_000
        ):

            return False


        salt=_decode(salt_text)

        expected_hash=_decode(hash_text)

        actual_hash=hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=len(expected_hash)
        )

        return hmac.compare_digest(
            actual_hash,
            expected_hash
        )

    except (
        AttributeError,
        TypeError,
        ValueError
    ):

        return False
