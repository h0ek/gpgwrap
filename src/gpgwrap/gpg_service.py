from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

from .models import GPGKey, GPGResult, GPGStatus


class GPGService:
    def __init__(self, gpg_binary: str = "gpg") -> None:
        self.gpg_binary = gpg_binary

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

    def _run_text(self, args: List[str], input_text: Optional[str] = None) -> GPGResult:
        cmd = [self.gpg_binary, "--batch", "--yes", "--status-fd=2", *args]

        try:
            completed = subprocess.run(
                cmd,
                input=input_text,
                text=True,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            return GPGResult(
                ok=False,
                stdout="",
                stderr="gpg binary not found in PATH.",
                returncode=127,
                statuses=[],
            )

        return GPGResult(
            ok=(completed.returncode == 0),
            stdout=completed.stdout,
            stderr=completed.stderr,
            returncode=completed.returncode,
            statuses=self._parse_statuses(completed.stderr),
        )

    def _run_binary(
        self, args: List[str], input_bytes: Optional[bytes] = None
    ) -> GPGResult:
        cmd = [self.gpg_binary, "--batch", "--yes", "--status-fd=2", *args]

        try:
            completed = subprocess.run(
                cmd,
                input=input_bytes,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            return GPGResult(
                ok=False,
                stdout="",
                stderr="gpg binary not found in PATH.",
                returncode=127,
                statuses=[],
            )

        stdout_text = completed.stdout.hex()
        stderr_text = completed.stderr.decode("utf-8", errors="replace")

        return GPGResult(
            ok=(completed.returncode == 0),
            stdout=stdout_text,
            stderr=stderr_text,
            returncode=completed.returncode,
            statuses=self._parse_statuses(stderr_text),
        )

    def _mark_ok_if_status_present(self, result: GPGResult, *tags: str) -> GPGResult:
        present = {item.tag for item in result.statuses}
        if any(tag in present for tag in tags):
            result.ok = True
        return result

    # ---------- list keys ----------

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
                    disabled=("d" in trust.lower()),
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

    # ---------- text operations ----------

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
        return self._mark_ok_if_status_present(result, "DECRYPTION_OKAY")

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
        return self._run_text(["--verify"], input_text=signed_text)

    def verify_detached_signature(self, text: str, signature: str) -> GPGResult:
        with tempfile.TemporaryDirectory(prefix="gpgwrap-verify-") as tmpdir:
            text_path = Path(tmpdir) / "message.txt"
            sig_path = Path(tmpdir) / "signature.asc"

            text_path.write_text(text, encoding="utf-8")
            sig_path.write_text(signature, encoding="utf-8")

            return self._run_text(["--verify", str(sig_path), str(text_path)])

    # ---------- file operations ----------

    def encrypt_file(
        self,
        input_file: str,
        output_file: str,
        recipients: List[str],
        armor: bool = False,
        sign_with: Optional[str] = None,
    ) -> GPGResult:
        args: List[str] = ["--output", output_file]

        if armor:
            args.append("--armor")

        if sign_with:
            args.extend(["--local-user", sign_with, "--sign", "--encrypt"])
        else:
            args.append("--encrypt")

        for recipient in recipients:
            args.extend(["--recipient", recipient])

        args.append(input_file)
        return self._run_text(args)

    def decrypt_file(self, input_file: str, output_file: str) -> GPGResult:
        result = self._run_text(["--output", output_file, "--decrypt", input_file])
        return self._mark_ok_if_status_present(result, "DECRYPTION_OKAY")

    def sign_file(
        self,
        input_file: str,
        output_file: str,
        signer: str,
        detached: bool = True,
        armor: bool = True,
    ) -> GPGResult:
        args: List[str] = ["--local-user", signer, "--output", output_file]

        if armor:
            args.append("--armor")

        if detached:
            args.append("--detach-sign")
        else:
            args.append("--sign")

        args.append(input_file)
        return self._run_text(args)

    def verify_file_signature(self, file_path: str, signature_path: str) -> GPGResult:
        return self._run_text(["--verify", signature_path, file_path])

    # ---------- key management ----------

    def import_key_text(self, armored_text: str) -> GPGResult:
        return self._run_text(["--import"], input_text=armored_text)

    def export_public_key_ascii(self, fingerprint: str) -> GPGResult:
        return self._run_text(["--armor", "--export", fingerprint])

    def export_public_key_to_file(
        self, fingerprint: str, output_file: str
    ) -> GPGResult:
        return self._run_text(
            ["--output", output_file, "--armor", "--export", fingerprint]
        )

    def import_key_file(self, file_path: str) -> GPGResult:
        return self._run_text(["--import", file_path])

    def delete_key(self, fingerprint: str, secret_too: bool = False) -> GPGResult:
        if secret_too:
            secret_result = self._run_text(["--delete-secret-key", fingerprint])
            if not secret_result.ok:
                return secret_result

        return self._run_text(["--delete-key", fingerprint])

    def generate_key(
        self,
        name: str,
        email: str,
        comment: str,
        preset: str,
        expiry: str,
        passphrase: str,
    ) -> GPGResult:
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

    # ---------- helper messages ----------

    def _status_tags(self, result: GPGResult) -> set[str]:
        return {item.tag for item in result.statuses}

    def describe_verify_result(self, result: GPGResult) -> str:
        tags = self._status_tags(result)

        if "GOODSIG" in tags and "VALIDSIG" in tags:
            return "Signature is valid."
        if "BADSIG" in tags:
            return "Signature is invalid."
        if "ERRSIG" in tags:
            return "Signature verification failed."
        if "NO_PUBKEY" in tags:
            return "Missing public key required for verification."
        if "NODATA" in tags:
            return "No valid OpenPGP data detected for this verification mode."
        if result.ok:
            return "Verification completed."
        return "Verification failed."

    def describe_decrypt_result(self, result: GPGResult) -> str:
        tags = self._status_tags(result)

        if "DECRYPTION_OKAY" in tags and "GOODSIG" in tags and "VALIDSIG" in tags:
            return "Decryption successful. Signature is valid."
        if "DECRYPTION_OKAY" in tags and "BADSIG" in tags:
            return "Decryption successful, but signature is invalid."
        if "DECRYPTION_OKAY" in tags and "NO_PUBKEY" in tags:
            return "Decryption successful, but signer public key is missing."
        if "DECRYPTION_OKAY" in tags:
            return "Decryption successful."
        if "NO_SECKEY" in tags:
            return "Missing secret key required for decryption."
        if "DECRYPTION_FAILED" in tags:
            return "Decryption failed."
        if result.ok:
            return "Operation completed successfully."
        return "Operation failed."

    def describe_encrypt_result(self, result: GPGResult) -> str:
        tags = self._status_tags(result)

        if "END_ENCRYPTION" in tags:
            return "Encryption completed."
        if "INV_RECP" in tags:
            return "Recipient key is unusable or not trusted enough for encryption."
        if "NO_PUBKEY" in tags:
            return "Recipient public key is missing."
        if result.ok:
            return "Encryption completed."
        return "Encryption failed."

    def describe_sign_result(self, result: GPGResult) -> str:
        tags = self._status_tags(result)

        if "SIG_CREATED" in tags:
            return "Signing completed."
        if "NO_SECKEY" in tags:
            return "Missing secret key required for signing."
        if result.ok:
            return "Signing completed."
        return "Signing failed."

    def describe_generic_failure(self, result: GPGResult) -> str:
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
        args = ["--local-user", signer]
        args.append("--quick-lsign-key" if local_only else "--quick-sign-key")
        args.append(target_fingerprint)
        return self._run_text(args)

    def set_ownertrust(self, target_fingerprint: str, trust_level: str) -> GPGResult:
        return self._run_text(
            ["--quick-set-ownertrust", target_fingerprint, trust_level]
        )