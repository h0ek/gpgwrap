# GPGWrap

GPGWrap is a lightweight Linux desktop GUI for common OpenPGP tasks using the system `gpg` binary.

It provides a simple interface for encrypting, decrypting, signing, and verifying text or files, plus basic key management and key generation.

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
- List available public and secret keys
- Import keys from file
- Export public keys
- Copy public key to clipboard
- Delete keys
- Generate new keys

## Requirements

- Linux desktop environment
- Python 3.10+
- `gpg`
- `gpg-agent`
- `pinentry`

## Install with pipx

Install directly from GitHub:

```bash
pipx install git+https://github.com/h0ek/gpgwrap.git
```

## Run
```bash
gpgwrap
```

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

## Uninstall

Remove the application:

```bash
pipx uninstall gpgwrap
```

Remove desktop entry and icon (optional):

rm ~/.local/share/applications/gpgwrap.desktop
rm ~/.local/share/icons/hicolor/256x256/apps/gpgwrap.png
