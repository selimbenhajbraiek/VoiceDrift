"""This laptop's Wi-Fi addresses, and a self-signed HTTPS certificate for them (phones need HTTPS for the mic)."""
import datetime
import ipaddress
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from backend import settings

CERT = settings.CERT_DIR / "phone-link.crt"
KEY = settings.CERT_DIR / "phone-link.key"


def lan_addresses():
    """IPv4 addresses a phone could reach, the one on the default route (usually the Wi-Fi) first."""
    found = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))  # UDP connect only picks a route; nothing is sent
            found.append(s.getsockname()[0])
    except OSError:
        pass  # no default route (offline): fall back to the adapters' addresses
    for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
        found.append(info[4][0])
    keep = [a for a in dict.fromkeys(found) if not a.startswith(("127.", "169.254."))]
    return keep or ["127.0.0.1"]


def certificate_covers(addresses):
    """True if the saved certificate exists, names every address and is valid for at least 30 more days."""
    if not (CERT.exists() and KEY.exists()):
        return False
    cert = x509.load_pem_x509_certificate(CERT.read_bytes())
    names = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    ips = {str(ip) for ip in names.get_values_for_type(x509.IPAddress)}
    soon = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=30)
    return set(addresses) <= ips and cert.not_valid_after_utc > soon


def ensure_certificate(addresses):
    """(cert path, key path), making a new self-signed certificate when the addresses change.

    A new certificate means the phone shows its "not private" warning once more.
    """
    if certificate_covers(addresses):
        return CERT, KEY
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "VoiceDrift phone link")])
    now = datetime.datetime.now(datetime.timezone.utc)
    sans = [x509.DNSName("localhost")] + [x509.IPAddress(ipaddress.ip_address(a))
                                          for a in dict.fromkeys([*addresses, "127.0.0.1"])]
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5)).not_valid_after(now + datetime.timedelta(days=397))
            .add_extension(x509.SubjectAlternativeName(sans), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    settings.CERT_DIR.mkdir(parents=True, exist_ok=True)
    KEY.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                      serialization.NoEncryption()))
    CERT.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return CERT, KEY
