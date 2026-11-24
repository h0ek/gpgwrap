from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import List, Optional

from .file_io import AtomicOutput
from .models import GPGKey, GPGResult, GPGSignature, GPGStatus
from .process import execute_process


class GPGService:
    def __init__(self, gpg_binary: str = "gpg", runner=execute_process) -> None:
        self.gpg_binary = gpg_binary
        self.runner = runner

    def check_gpg_available(self) -> bool:
        return shutil.which(self.gpg_binary) is not None

    def _parse_statuses(self, stderr: str) -> List[GPGStatus]:
        items: List[GPGStatus] = []
        for line in stderr.splitlines():
            line = line.strip()
            if not line.startswith("[GNUPG:]"):
                continue
            raw = line[len("[GNUPG:]") :].strip()
            if not raw:
                continue
            parts = raw.split()
            items.append(GPGStatus(tag=parts[0], args=parts[1:]))
        return items

    def _failure(self, message: str, returncode: int = 1) -> GPGResult:
        return GPGResult(False, "", "", returncode, error=message)

    def _run_text(self, args: List[str], input_text: Optional[str] = None) -> GPGResult:
        command = [
            self.gpg_binary,
            "--batch",
            "--no-tty",
            "--status-fd=2",
            "--display-charset",
            "utf-8",
            *args,
        ]
        try:
            data = input_text.encode("utf-8") if input_text is not None else None
            completed = self.runner(command, data)
        except (OSError, ValueError, UnicodeError) as error:
            return self._failure(f"Could not run GPG: {error}")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        result = GPGResult(
            completed.returncode == 0,
            "",
            stderr,
            completed.returncode,
            self._parse_statuses(stderr),
        )
        if completed.returncode == 130:
            result.error = "Operation cancelled."
            return result
        try:
            result.stdout = completed.stdout.decode("utf-8")
        except UnicodeDecodeError:
            result.ok = False
            result.error = "Output is not valid UTF-8 text. Use File mode to preserve the original bytes."
        result.signatures = self._signature_results(result)
        if any(signature.state != "valid" for signature in result.signatures):
            result.ok = False
        return result

    def _signature_results(self, result: GPGResult) -> List[GPGSignature]:
        relevant = {
            "GOODSIG",
            "VALIDSIG",
            "BADSIG",
            "ERRSIG",
            "NO_PUBKEY",
            "EXPSIG",
            "EXPKEYSIG",
            "REVKEYSIG",
            "KEYEXPIRED",
            "SIGEXPIRED",
            "KEYREVOKED",
        }
        groups: List[List[GPGStatus]] = []
        current: List[GPGStatus] | None = None
        for item in result.statuses:
            if item.tag == "NEWSIG":
                if current is not None:
                    groups.append(current)
                current = []
            elif item.tag in relevant:
                if current is None:
                    if item.tag not in {
                        "GOODSIG",
                        "VALIDSIG",
                        "BADSIG",
                        "ERRSIG",
                        "EXPSIG",
                        "EXPKEYSIG",
                        "REVKEYSIG",
                    }:
                        continue
                    current = []
                current.append(item)
        if current is not None:
            groups.append(current)
        signatures = []
        for group in groups:
            tags = {item.tag for item in group}
            key = next(
                (
                    item.args[0]
                    for item in group
                    if item.tag == "VALIDSIG" and item.args
                ),
                "",
            )
            if not key:
                key = next((item.args[0] for item in group if item.args), "unknown key")
            if "BADSIG" in tags:
                state = "invalid"
            elif tags & {"REVKEYSIG", "KEYREVOKED"}:
                state = "revoked"
            elif tags & {"EXPSIG", "EXPKEYSIG", "KEYEXPIRED", "SIGEXPIRED"}:
                state = "expired"
            elif "NO_PUBKEY" in tags:
                state = "missing_key"
            elif "ERRSIG" in tags:
                state = "error"
            elif {"GOODSIG", "VALIDSIG"} <= tags:
                state = "valid"
            else:
                state = "unverified"
            signatures.append(GPGSignature(key, state))
        return signatures

    def _assess_decryption(self, result: GPGResult) -> GPGResult:
        tags = self._status_tags(result)
        fatal = {
            "BADMDC",
            "ERRMDC",
            "DECRYPTION_FAILED",
            "ERROR",
            "NODATA",
            "UNEXPECTED",
        }
        signature_failure = any(item.state != "valid" for item in result.signatures)
        failures = [item for item in result.statuses if item.tag == "FAILURE"]
        unrelated_failure = any(
            not (signature_failure and item.args and item.args[0] == "gpg-exit")
            for item in failures
        )
        result.decryption_ok = (
            "DECRYPTION_OKAY" in tags
            and not tags & fatal
            and not unrelated_failure
            and not result.error
            and (
                result.returncode == 0
                or (result.returncode in (1, 2) and signature_failure)
            )
        )
        if tags & fatal or unrelated_failure:
            result.ok = False
        if not result.decryption_ok and not result.ok:
            result.stdout = ""
        return result

    def _write_file(
        self,
        args: List[str],
        output_file: str,
        input_file: str | None = None,
        overwrite: bool = False,
        decrypt: bool = False,
    ) -> GPGResult:
        try:
            with AtomicOutput(output_file, input_file, overwrite) as output:
                command = ["--yes", "--output", str(output.temporary), *args]
                if input_file is not None:
                    command.extend(
                        ["--", str(Path(input_file).expanduser().resolve(strict=True))]
                    )
                result = self._run_text(command)
                if decrypt:
                    self._assess_decryption(result)
                if result.ok or result.decryption_ok:
                    if "--export" in args and (
                        not output.temporary.exists()
                        or output.temporary.stat().st_size == 0
                    ):
                        return self._failure("No public key was exported.")
                    output.commit()
                return result
        except (OSError, ValueError, RuntimeError) as error:
            return self._failure(f"Could not save output: {error}")

    def list_public_keys(self) -> List[GPGKey]:
        return self._list_keys(secret=False)

    def list_secret_keys(self) -> List[GPGKey]:
        return self._list_keys(secret=True)

    def _list_keys(self, secret: bool) -> List[GPGKey]:
        args = ["--with-colons", "--fingerprint"]
        args.append("--list-secret-keys" if secret else "--list-keys")

        result = self._run_text(args)
        if not result.ok:
            return []

        keys: List[GPGKey] = []
        current: Optional[GPGKey] = None

        for raw_line in result.stdout.splitlines():
            parts = raw_line.split(":")
            if not parts:
                continue

            record_type = parts[0]

            if record_type in ("pub", "sec"):
                if len(parts) < 12:
                    continue

                if current:
                    keys.append(current)

                trust = parts[1]
                capabilities = parts[11]
                key_id = parts[4]

                current = GPGKey(
                    key_type=record_type,
                    key_id=key_id,
                    fingerprint="",
                    user_ids=[],
                    trust=trust,
                    capabilities=capabilities,
                    expired=("e" in trust.lower()),
                    revoked=("r" in trust.lower()),
                    disabled=("d" in trust.lower() or "D" in capabilities),
                )

            elif record_type == "fpr" and current:
                if len(parts) > 9 and not current.fingerprint:
                    current.fingerprint = parts[9].strip()

            elif record_type == "uid" and current:
                if len(parts) > 9:
                    uid = parts[9].strip()
                    if uid:
                        current.user_ids.append(uid)

        if current:
            keys.append(current)

        return keys

    def encrypt_text(
        self,
        text: str,
        recipients: List[str],
        sign_with: Optional[str] = None,
    ) -> GPGResult:
        args: List[str] = ["--armor"]

        if sign_with:
            args.extend(["--local-user", sign_with, "--sign", "--encrypt"])
        else:
            args.append("--encrypt")

        for recipient in recipients:
            args.extend(["--recipient", recipient])

        return self._run_text(args, input_text=text)

    def decrypt_text(self, text: str) -> GPGResult:
        result = self._run_text(["--decrypt"], input_text=text)
        return self._assess_decryption(result)

    def clearsign_text(self, text: str, signer: str) -> GPGResult:
        return self._run_text(
            ["--armor", "--local-user", signer, "--clearsign"],
            input_text=text,
        )

    def detach_sign_text(self, text: str, signer: str) -> GPGResult:
        return self._run_text(
            ["--armor", "--local-user", signer, "--detach-sign"],
            input_text=text,
        )

    def verify_clearsigned_text(self, signed_text: str) -> GPGResult:
        return self._verify(["--verify"], signed_text)

    def _verify(self, args: List[str], text: str | None = None) -> GPGResult:
        result = self._run_text(args, input_text=text)
        if not result.signatures:
            result.ok = False
        return result

    def verify_detached_signature(self, text: str, signature: str) -> GPGResult:
        try:
            with tempfile.TemporaryDirectory(prefix="gpgwrap-verify-") as tmpdir:
                text_path = Path(tmpdir) / "message.txt"
                sig_path = Path(tmpdir) / "signature.asc"
                text_path.write_bytes(text.encode("utf-8"))
                sig_path.write_bytes(signature.encode("utf-8"))
                return self._verify(["--verify", "--", str(sig_path), str(text_path)])
        except (OSError, UnicodeError) as error:
            return self._failure(f"Could not prepare verification: {error}")

    def encrypt_file(
        self,
        input_file: str,
        output_file: str,
        recipients: List[str],
        armor: bool = False,
        sign_with: Optional[str] = None,
        overwrite: bool = False,
    ) -> GPGResult:
        args: List[str] = []

        if armor:
            args.append("--armor")

        if sign_with:
            args.extend(["--local-user", sign_with, "--sign", "--encrypt"])
        else:
            args.append("--encrypt")

        for recipient in recipients:
            args.extend(["--recipient", recipient])

        return self._write_file(args, output_file, input_file, overwrite)

    def decrypt_file(
        self, input_file: str, output_file: str, overwrite: bool = False
    ) -> GPGResult:
        return self._write_file(
            ["--decrypt"], output_file, input_file, overwrite, decrypt=True
        )

    def sign_file(
        self,
        input_file: str,
        output_file: str,
        signer: str,
        detached: bool = True,
        armor: bool = True,
        overwrite: bool = False,
    ) -> GPGResult:
        args: List[str] = ["--local-user", signer]

        if armor:
            args.append("--armor")

        if detached:
            args.append("--detach-sign")
        else:
            args.append("--sign")

        return self._write_file(args, output_file, input_file, overwrite)

    def verify_file_signature(self, file_path: str, signature_path: str) -> GPGResult:
        return self._verify(["--verify", "--", signature_path, file_path])

    def import_key_text(self, armored_text: str) -> GPGResult:
        return self._run_text(["--import"], input_text=armored_text)

    def export_public_key_ascii(self, fingerprint: str) -> GPGResult:
        return self._run_text(["--armor", "--export", fingerprint])

    def export_public_key_to_file(
        self, fingerprint: str, output_file: str, overwrite: bool = False
    ) -> GPGResult:
        return self._write_file(
            ["--armor", "--export", fingerprint], output_file, overwrite=overwrite
        )

    def import_key_file(self, file_path: str) -> GPGResult:
        return self._run_text(["--import", "--", file_path])

    def delete_key(self, fingerprint: str, secret_too: bool = False) -> GPGResult:
        if secret_too:
            secret_result = self._run_text(
                ["--yes", "--delete-secret-key", fingerprint]
            )
            if not secret_result.ok:
                return secret_result

        return self._run_text(["--yes", "--delete-key", fingerprint])

    def generate_key(
        self,
        name: str,
        email: str,
        comment: str,
        preset: str,
        expiry: str,
        passphrase: str,
    ) -> GPGResult:
        fields = (name, email, comment, expiry, passphrase)
        if any(any(char in value for char in "\r\n\0") for value in fields):
            return self._failure(
                "Key fields must not contain line breaks or NUL characters."
            )
        if not name.strip() or not email.strip() or not passphrase:
            return self._failure("Name, email and passphrase are required.")
        if passphrase != passphrase.strip():
            return self._failure(
                "The passphrase must not start or end with whitespace."
            )
        if preset not in {"Modern ECC", "RSA 3072", "RSA 4096"}:
            return self._failure("Unsupported key preset.")
        if not re.fullmatch(r"(?:[0-9]+[dwmy]?|[0-9]{4}-[0-9]{2}-[0-9]{2})", expiry):
            return self._failure(
                "Invalid expiry. Use 0, a duration such as 1y, or YYYY-MM-DD."
            )
        lines: List[str] = []

        if preset == "Modern ECC":
            lines.extend(
                [
                    "Key-Type: eddsa",
                    "Key-Curve: ed25519",
                    "Key-Usage: sign",
                    "Subkey-Type: ecdh",
                    "Subkey-Curve: cv25519",
                    "Subkey-Usage: encrypt",
                ]
            )
        elif preset == "RSA 3072":
            lines.extend(
                [
                    "Key-Type: RSA",
                    "Key-Length: 3072",
                    "Key-Usage: sign",
                    "Subkey-Type: RSA",
                    "Subkey-Length: 3072",
                    "Subkey-Usage: encrypt",
                ]
            )
        else:
            lines.extend(
                [
                    "Key-Type: RSA",
                    "Key-Length: 4096",
                    "Key-Usage: sign",
                    "Subkey-Type: RSA",
                    "Subkey-Length: 4096",
                    "Subkey-Usage: encrypt",
                ]
            )

        lines.append(f"Name-Real: {name}")
        if comment:
            lines.append(f"Name-Comment: {comment}")
        lines.append(f"Name-Email: {email}")
        lines.append(f"Expire-Date: {expiry}")
        lines.append(f"Passphrase: {passphrase}")
        lines.append("%commit")

        batch = "\n".join(lines) + "\n"

        return self._run_text(
            ["--pinentry-mode", "loopback", "--generate-key"],
            input_text=batch,
        )

    def _status_tags(self, result: GPGResult) -> set[str]:
        return {item.tag for item in result.statuses}

    def describe_verify_result(self, result: GPGResult) -> str:
        if result.error:
            return result.error
        signatures = result.signatures or self._signature_results(result)
        descriptions = {
            "valid": "Signature is valid.",
            "invalid": "Signature is invalid.",
            "revoked": "Signing key has been revoked.",
            "expired": "Signature or signing key has expired.",
            "missing_key": "Missing public key required for verification.",
            "error": "Signature verification failed.",
            "unverified": "Signature could not be verified.",
        }
        if signatures:
            summary = "\n".join(
                f"{signature.key}: {descriptions[signature.state]}"
                for signature in signatures
            )
            if not result.ok and all(item.state == "valid" for item in signatures):
                summary += "\nGPG reported an additional error; the operation did not complete successfully."
            return summary
        if "NODATA" in self._status_tags(result):
            return "No valid OpenPGP data detected for this verification mode."
        return "No verified signature was found."

    def describe_decrypt_result(self, result: GPGResult) -> str:
        if result.error:
            return result.error
        tags = self._status_tags(result)
        if result.decryption_ok:
            summary = "Decryption successful."
            if result.signatures:
                summary += "\n" + self.describe_verify_result(result)
            return summary
        if "NO_SECKEY" in tags:
            return "Missing secret key required for decryption."
        if tags & {"BADMDC", "ERRMDC", "DECRYPTION_FAILED"}:
            return "Decryption failed or encrypted data failed its integrity check."
        if result.ok:
            return (
                self.describe_verify_result(result)
                if result.signatures
                else "Operation completed successfully."
            )
        if result.signatures:
            return "Decryption failed.\n" + self.describe_verify_result(result)
        return "Decryption failed."

    def describe_encrypt_result(self, result: GPGResult) -> str:
        tags = self._status_tags(result)

        if result.error:
            return result.error
        if "INV_RECP" in tags:
            return "Recipient key is unusable or not trusted enough for encryption."
        if "NO_PUBKEY" in tags:
            return "Recipient public key is missing."
        if result.ok:
            return "Encryption completed."
        return "Encryption failed."

    def describe_sign_result(self, result: GPGResult) -> str:
        tags = self._status_tags(result)

        if result.error:
            return result.error
        if "NO_SECKEY" in tags:
            return "Missing secret key required for signing."
        if result.ok:
            return "Signing completed."
        return "Signing failed."

    def describe_generic_failure(self, result: GPGResult) -> str:
        if result.error:
            return result.error
        tags = self._status_tags(result)

        if "NO_SECKEY" in tags:
            return "Missing secret key."
        if "NO_PUBKEY" in tags:
            return "Missing public key."
        if "INV_RECP" in tags:
            return "Recipient key is unusable or not trusted enough."
        if "DECRYPTION_FAILED" in tags:
            return "Decryption failed."
        if "NODATA" in tags:
            return "No valid OpenPGP data detected."
        if "BADSIG" in tags:
            return "Signature is invalid."
        if "ERRSIG" in tags:
            return "Signature verification failed."
        if "FAILURE" in tags:
            return "GPG operation failed."
        return "Operation failed."

    def sign_public_key(
        self,
        target_fingerprint: str,
        signer: str,
        local_only: bool = True,
    ) -> GPGResult:
        args = ["--yes", "--local-user", signer]
        args.append("--quick-lsign-key" if local_only else "--quick-sign-key")
        args.append(target_fingerprint)
        return self._run_text(args)

    def set_ownertrust(self, target_fingerprint: str, trust_level: str) -> GPGResult:
        if not re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", target_fingerprint):
            return self._failure("A full hexadecimal key fingerprint is required.")
        levels = {"undefined": 2, "never": 3, "marginal": 4, "full": 5, "ultimate": 6}
        if trust_level not in levels:
            return self._failure("Invalid ownertrust level.")
        value = f"{target_fingerprint.upper()}:{levels[trust_level]}:\n"
        return self._run_text(["--import-ownertrust"], input_text=value)
