#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

SIGNATURE_DOMAIN = b"JNS-PACKAGE-V3\x00"

MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_MEMBER_BYTES = 25 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
MAX_MEMBER_COUNT = 1000
MAX_COMPRESSION_RATIO = 200.0

SAFE_PUBLISHER_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,79}$")


class GatewayError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    enabled: bool = True
    require_native_jns_signature: bool = True
    verify_against_jns_trust: bool = True
    allow_trust_enrolment: bool = False


def log(message: str) -> None:
    print(f"[JNS Handoff] {message}", flush=True)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_member_name(value: str) -> str:
    value = str(value).replace("\\", "/")
    if not value or value.startswith("/") or "\x00" in value:
        raise GatewayError(f"Unsafe archive path: {value!r}")
    path = PurePosixPath(value)
    if any(part in ("", ".", "..") for part in path.parts):
        raise GatewayError(f"Unsafe archive path: {value!r}")
    return path.as_posix()


def load_settings(options_file: Path) -> Settings:
    data = json.loads(options_file.read_text(encoding="utf-8"))
    handoff = data.get("jns_handoff", {})
    if not isinstance(handoff, dict):
        raise GatewayError("jns_handoff options must be an object")
    return Settings(
        enabled=bool(handoff.get("enabled", True)),
        require_native_jns_signature=bool(
            handoff.get("require_native_jns_signature", True)
        ),
        verify_against_jns_trust=bool(
            handoff.get("verify_against_jns_trust", True)
        ),
        allow_trust_enrolment=bool(
            handoff.get("allow_trust_enrolment", False)
        ),
    )


def locate_trust_store(ha_config: Path) -> Path:
    candidates = [
        ha_config / "jns" / "trust" / "publishers.json",
        ha_config / "jns" / "publishers.json",
    ]
    for path in candidates:
        if path.is_file():
            return path
    # Canonical v5 path for creation/enrolment.
    return candidates[0]


def load_publishers(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    if not path.is_file():
        raise GatewayError(f"JNS publisher trust store is missing: {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    pubs = raw.get("publishers", [])
    if not isinstance(pubs, list):
        raise GatewayError("publishers.json has an invalid publishers field")

    enabled: dict[str, dict[str, Any]] = {}
    for item in pubs:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id", "")).strip()
        if pid and item.get("enabled", True):
            enabled[pid] = item
    return raw, enabled


def _validate_archive_safety(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    infos = [info for info in archive.infolist() if info.filename and not info.is_dir()]
    if len(infos) > MAX_MEMBER_COUNT:
        raise GatewayError("Package contains too many archive members")

    by_name: dict[str, zipfile.ZipInfo] = {}
    casefolded: dict[str, str] = {}
    total_uncompressed = 0

    for info in infos:
        name = safe_member_name(info.filename)

        if name in by_name:
            raise GatewayError(f"Duplicate ZIP member: {name}")

        folded = name.casefold()
        if folded in casefolded and casefolded[folded] != name:
            raise GatewayError(
                f"Case-colliding ZIP members: {casefolded[folded]!r} and {name!r}"
            )

        if info.flag_bits & 0x1:
            raise GatewayError(f"Encrypted ZIP member is forbidden: {name}")

        mode = (info.external_attr >> 16) & 0xFFFF
        if mode:
            file_type = stat.S_IFMT(mode)
            if file_type not in (0, stat.S_IFREG, stat.S_IFDIR):
                raise GatewayError(f"Symlink/special ZIP member is forbidden: {name}")

        if info.file_size > MAX_MEMBER_BYTES:
            raise GatewayError(f"ZIP member exceeds maximum size: {name}")

        total_uncompressed += info.file_size
        if total_uncompressed > MAX_TOTAL_UNCOMPRESSED_BYTES:
            raise GatewayError("Package exceeds total uncompressed size limit")

        if (
            info.file_size
            and info.compress_size
            and (info.file_size / info.compress_size) > MAX_COMPRESSION_RATIO
        ):
            raise GatewayError(f"ZIP member compression ratio is too high: {name}")

        by_name[name] = info
        casefolded[folded] = name

    return by_name


def validate_jns_package(
    package_path: Path,
    *,
    trust_store: Path,
    settings: Settings,
) -> dict[str, Any]:
    if package_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise GatewayError("Package exceeds maximum compressed size")

    with zipfile.ZipFile(package_path, "r") as archive:
        members = _validate_archive_safety(archive)

        if "jns_package.json" not in members:
            raise GatewayError("Package is missing jns_package.json")

        raw_manifest = archive.read("jns_package.json")
        try:
            manifest = json.loads(raw_manifest.decode("utf-8"))
        except Exception as exc:
            raise GatewayError(f"Invalid jns_package.json: {exc}") from exc

        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise GatewayError("Package manifest has no declared files")

        seen_source: set[str] = set()
        seen_target: set[str] = set()
        for entry in files:
            if not isinstance(entry, dict):
                raise GatewayError("Manifest file entry must be an object")

            source = safe_member_name(entry.get("source", ""))
            target = safe_member_name(entry.get("target", ""))

            if source in seen_source:
                raise GatewayError(f"Duplicate source path: {source}")
            if target in seen_target:
                raise GatewayError(f"Duplicate target path: {target}")
            seen_source.add(source)
            seen_target.add(target)

            if source not in members:
                raise GatewayError(f"Declared source is missing: {source}")

            expected = str(entry.get("sha256", "")).lower()
            if not re.fullmatch(r"[0-9a-f]{64}", expected):
                raise GatewayError(f"Invalid SHA-256 declaration: {source}")

            actual = sha256_bytes(archive.read(source))
            if actual != expected:
                raise GatewayError(
                    f"Payload SHA-256 mismatch for {source}: expected {expected}, got {actual}"
                )

        allowed_members = seen_source | {"jns_package.json", "jns_signature.json"}
        undeclared = sorted(set(members) - allowed_members)
        if undeclared:
            raise GatewayError(
                "Package contains undeclared files: " + ", ".join(undeclared[:10])
            )

        has_signature = "jns_signature.json" in members
        if settings.require_native_jns_signature and not has_signature:
            raise GatewayError("Unsigned package rejected by Gateway policy")

        if has_signature:
            try:
                signature = json.loads(
                    archive.read("jns_signature.json").decode("utf-8")
                )
            except Exception as exc:
                raise GatewayError(f"Invalid jns_signature.json: {exc}") from exc

            if manifest.get("format") != 3:
                raise GatewayError("Signed JNS package must use format 3")

            if signature.get("algorithm") != "ed25519":
                raise GatewayError("Unsupported JNS signature algorithm")

            publisher_id = str(manifest.get("publisher_id", ""))
            if not publisher_id:
                raise GatewayError("Signed package has no publisher_id")

            if publisher_id != str(signature.get("publisher_id", "")):
                raise GatewayError("Publisher ID mismatch between manifest and signature")

            if sha256_bytes(raw_manifest) != str(
                signature.get("manifest_sha256", "")
            ):
                raise GatewayError("Signed manifest SHA-256 mismatch")

            if settings.verify_against_jns_trust:
                _raw_store, publishers = load_publishers(trust_store)
                pub = publishers.get(publisher_id)
                if not pub:
                    raise GatewayError(f"Publisher is not trusted/enabled: {publisher_id}")

                required_scope = (
                    "platform"
                    if manifest.get("type") == "platform_update"
                    else "config"
                )
                if required_scope not in pub.get("scopes", []):
                    raise GatewayError(
                        f"Publisher {publisher_id} lacks {required_scope!r} scope"
                    )

                try:
                    raw_public_key = base64.b64decode(
                        pub["public_key"], validate=True
                    )
                except Exception as exc:
                    raise GatewayError(
                        f"Trusted public key for {publisher_id} is invalid"
                    ) from exc

                fingerprint = sha256_bytes(raw_public_key)
                if fingerprint != str(pub.get("fingerprint_sha256", "")):
                    raise GatewayError(
                        f"Trusted publisher fingerprint mismatch: {publisher_id}"
                    )

                try:
                    signature_bytes = base64.b64decode(
                        signature["signature"], validate=True
                    )
                    key = Ed25519PublicKey.from_public_bytes(raw_public_key)
                    key.verify(
                        signature_bytes,
                        SIGNATURE_DOMAIN + raw_manifest,
                    )
                except Exception as exc:
                    raise GatewayError("Ed25519 signature verification failed") from exc

        return {
            "package_id": manifest.get("package_id"),
            "name": manifest.get("name"),
            "version": manifest.get("version"),
            "publisher_id": manifest.get("publisher_id"),
            "type": manifest.get("type", "config_package"),
            "sha256": hashlib.sha256(package_path.read_bytes()).hexdigest(),
        }


def enrol_publisher(public_json_path: Path, trust_store: Path) -> dict[str, Any]:
    data = json.loads(public_json_path.read_text(encoding="utf-8"))

    publisher_id = str(data.get("id", "")).strip()
    if not SAFE_PUBLISHER_ID.fullmatch(publisher_id):
        raise GatewayError("Publisher id is missing or invalid")

    if str(data.get("algorithm", "ed25519")).lower() != "ed25519":
        raise GatewayError("Only Ed25519 publishers may be enrolled")

    try:
        public_raw = base64.b64decode(data["public_key"], validate=True)
    except Exception as exc:
        raise GatewayError("Publisher public_key is invalid Base64") from exc

    if len(public_raw) != 32:
        raise GatewayError("Ed25519 public key must be 32 raw bytes")

    fingerprint = sha256_bytes(public_raw)
    if fingerprint != str(data.get("fingerprint_sha256", "")):
        raise GatewayError("Publisher fingerprint does not match public key")

    # Parsing as a key catches malformed 32-byte values early.
    Ed25519PublicKey.from_public_bytes(public_raw)

    trust_store.parent.mkdir(parents=True, exist_ok=True)
    if trust_store.is_file():
        raw_store = json.loads(trust_store.read_text(encoding="utf-8"))
    else:
        raw_store = {"schema": 1, "publishers": []}

    publishers = raw_store.setdefault("publishers", [])
    if not isinstance(publishers, list):
        raise GatewayError("Existing trust store publishers field is invalid")

    for existing in publishers:
        if isinstance(existing, dict) and str(existing.get("id")) == publisher_id:
            existing_fingerprint = str(existing.get("fingerprint_sha256", ""))
            if existing_fingerprint != fingerprint:
                raise GatewayError(
                    "Refusing publisher ID reuse with a different public key"
                )
            return {
                "id": publisher_id,
                "fingerprint_sha256": fingerprint,
                "already_present": True,
            }

    publishers.append(
        {
            "id": publisher_id,
            "name": str(data.get("name", publisher_id)),
            "public_key": base64.b64encode(public_raw).decode("ascii"),
            "fingerprint_sha256": fingerprint,
            "scopes": ["config"],
            "enabled": True,
        }
    )

    tmp = trust_store.with_name(trust_store.name + ".tmp")
    tmp.write_text(json.dumps(raw_store, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, trust_store)

    return {
        "id": publisher_id,
        "fingerprint_sha256": fingerprint,
        "already_present": False,
    }


def _atomic_copy_to_inbox(source: Path, inbox: Path) -> Path:
    inbox.mkdir(parents=True, exist_ok=True)

    safe_name = Path(source.name).name
    final = inbox / safe_name
    if final.exists():
        stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        final = inbox / f"{source.stem}_{stamp}{source.suffix}"

    temp = inbox / f".{final.name}.incoming"
    with source.open("rb") as src, temp.open("xb") as dst:
        shutil.copyfileobj(src, dst, length=1024 * 1024)
        dst.flush()
        os.fsync(dst.fileno())

    if hashlib.sha256(temp.read_bytes()).digest() != hashlib.sha256(
        source.read_bytes()
    ).digest():
        temp.unlink(missing_ok=True)
        raise GatewayError("Read-back SHA-256 failed during inbox handoff")

    os.replace(temp, final)
    source.unlink()
    return final


def quarantine(source: Path, quarantine_dir: Path, reason: str) -> None:
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    destination = quarantine_dir / f"{stamp}_{source.name}"

    try:
        shutil.move(str(source), str(destination))
        reason_path = destination.with_name(destination.name + ".reason.txt")
        reason_path.write_text(reason.rstrip() + "\n", encoding="utf-8")
    except Exception:
        # Last-resort behavior: leave the file in incoming but rename it so the
        # watcher cannot repeatedly process the same rejected artifact.
        rejected = source.with_name(source.name + ".rejected")
        try:
            source.rename(rejected)
        except Exception:
            pass


def is_stable_file(path: Path, state: dict[str, tuple[int, int]]) -> bool:
    try:
        st = path.stat()
    except FileNotFoundError:
        state.pop(str(path), None)
        return False

    current = (st.st_size, st.st_mtime_ns)
    key = str(path)
    previous = state.get(key)
    state[key] = current
    return previous == current


def process_file(
    path: Path,
    *,
    settings: Settings,
    ha_config: Path,
) -> None:
    inbox = ha_config / "jns" / "inbox"
    quarantine_dir = ha_config / "jns" / "quarantine"
    trust_store = locate_trust_store(ha_config)

    name_lower = path.name.lower()

    if name_lower.endswith(".zip"):
        report = validate_jns_package(
            path,
            trust_store=trust_store,
            settings=settings,
        )
        destination = _atomic_copy_to_inbox(path, inbox)
        log(
            "Accepted package "
            f"{report.get('package_id')} v{report.get('version')} "
            f"publisher={report.get('publisher_id')} -> {destination}"
        )
        return

    if name_lower.endswith(".public.json"):
        if not settings.allow_trust_enrolment:
            raise GatewayError(
                "Publisher trust enrolment is disabled by Gateway policy"
            )
        report = enrol_publisher(path, trust_store)
        archive_dir = ha_config / "jns" / "trust" / "enrolments"
        archive_dir.mkdir(parents=True, exist_ok=True)
        destination = archive_dir / path.name
        if destination.exists():
            destination = archive_dir / (
                f"{path.stem}_{int(time.time())}{path.suffix}"
            )
        shutil.move(str(path), str(destination))
        log(
            "Enrolled publisher "
            f"{report['id']} fingerprint={report['fingerprint_sha256']}"
        )
        return

    raise GatewayError("Unsupported incoming file type")


def watch(
    *,
    options_file: Path,
    incoming: Path,
    ha_config: Path,
    poll_seconds: float = 1.0,
) -> None:
    settings = load_settings(options_file)
    if not settings.enabled:
        log("Handoff disabled; worker exiting")
        return

    incoming.mkdir(parents=True, exist_ok=True)
    stable_state: dict[str, tuple[int, int]] = {}

    log(f"Watching {incoming}")
    log(f"JNS inbox: {ha_config / 'jns' / 'inbox'}")
    log(f"Trust store: {locate_trust_store(ha_config)}")

    while True:
        for path in sorted(incoming.iterdir()):
            if not path.is_file() or path.name.startswith("."):
                continue
            if path.name.endswith(".rejected"):
                continue
            if not is_stable_file(path, stable_state):
                continue

            stable_state.pop(str(path), None)
            try:
                process_file(
                    path,
                    settings=settings,
                    ha_config=ha_config,
                )
            except Exception as exc:
                reason = f"{type(exc).__name__}: {exc}"
                log(f"Rejected {path.name}: {reason}")
                quarantine(
                    path,
                    ha_config / "jns" / "quarantine",
                    reason,
                )

        time.sleep(max(0.25, poll_seconds))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="JNS Secure Transfer Gateway package handoff worker"
    )
    parser.add_argument(
        "--options",
        type=Path,
        default=Path("/data/options.json"),
    )
    parser.add_argument(
        "--incoming",
        type=Path,
        default=Path("/srv/jns/incoming"),
    )
    parser.add_argument(
        "--ha-config",
        type=Path,
        default=Path("/homeassistant"),
    )
    parser.add_argument(
        "--verify-one",
        type=Path,
        default=None,
        help="Validate one signed JNS ZIP then exit; used for diagnostics/tests.",
    )
    args = parser.parse_args()

    settings = load_settings(args.options)

    if args.verify_one:
        report = validate_jns_package(
            args.verify_one,
            trust_store=locate_trust_store(args.ha_config),
            settings=settings,
        )
        print(json.dumps(report, indent=2))
        return 0

    watch(
        options_file=args.options,
        incoming=args.incoming,
        ha_config=args.ha_config,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"[JNS Handoff] FATAL: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
