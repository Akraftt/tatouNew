from pathlib import Path
from pgpy import PGPKey, PGPUID
from pgpy.constants import PubKeyAlgorithm, KeyFlags, HashAlgorithm, SymmetricKeyAlgorithm, CompressionAlgorithm

who = "Group_50"
out = Path("clientkeys"); out.mkdir(exist_ok=True)

key = PGPKey.new(PubKeyAlgorithm.RSAEncryptOrSign, 2048)
uid = PGPUID.new(who, email=f"{who.lower()}@example.org")
key.add_uid(uid,
    usage={KeyFlags.Sign, KeyFlags.EncryptCommunications, KeyFlags.EncryptStorage},
    hashes=[HashAlgorithm.SHA256],
    ciphers=[SymmetricKeyAlgorithm.AES256],
    compression=[CompressionAlgorithm.ZLIB]
)

priv = out / f"{who}_private.asc"
pub  = out / f"{who}_public.asc"
priv.write_text(str(key))
pub.write_text(str(key.pubkey))
print("Wrote:", priv, "and", pub)
