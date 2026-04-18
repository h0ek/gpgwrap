# GPGWrap

GPGWrap is a lightweight Linux desktop GUI for common OpenPGP tasks using the system `gpg` binary.

It provides a simple interface for encrypting, decrypting, signing, and verifying text or files, plus basic key management and key generation.

![GPGWrap screenshot](https://raw.githubusercontent.com/h0ek/gpgwrap/main/screenshot.webp)

## Features

### Text mode
- Encrypt text
- Decrypt text
- Sign text
- Verify clear-signed text
- Verify detached signatures

### File mode
- Encrypt files
- Decrypt files
- Sign files
- Verify file signatures

### Key management
- Import keys from file
- Import armored keys directly from clipboard
- Export public keys
- Copy public key to clipboard
- Delete keys
- Generate new keys
- Sign public keys (local or exportable) after fingerprint verification
- Set ownertrust independently of key signing

## Requirements

- Linux desktop environment
- Python 3.10+
- `gpg`
- `gpg-agent`
- `pinentry`

## Install with pipx

```bash
pipx install gpgwrap
```

Install directly from GitHub:

```bash
pipx install git+https://github.com/h0ek/gpgwrap.git
```

## Run
```bash
gpgwrap
```

## Keyboard shortcuts

- `Ctrl+E` — switch to Encrypt and run the action in the current mode
- `Ctrl+D` — switch to Decrypt and run the action in the current mode

## Install desktop launcher and icon

After installation, you can install the desktop entry and icon for the current user:
```bash
gpgwrap-install-desktop
```
After that, GPGWrap should appear in your application menu.

## Notes
- GPGWrap uses the system GnuPG installation.
- Your keys remain managed by your local GPG setup.
- The application is intended for desktop Linux use.
- If a message decrypts successfully but the signer public key is missing, GPGWrap will still show the decrypted plaintext and report that signature verification could not be completed.

## Upgrade

```bash
pipx upgrade gpgwrap
```

If you installed GPGWrap from GitHub, you may need to force reinstall to get the latest version:

```bash
pipx install --force git+https://github.com/h0ek/gpgwrap.git
```

## Uninstall

Remove the application:

```bash
pipx uninstall gpgwrap
```

Remove desktop entry and icon (optional):

```bash
rm ~/.local/share/applications/gpgwrap.desktop
rm ~/.local/share/icons/hicolor/256x256/apps/gpgwrap.png
```
