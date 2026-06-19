# Building and Installing the Debian Package

## Build

### Install build dependencies

```sh
sudo apt install -y \
    debhelper \
    dh-sequence-python3 \
    pybuild-plugin-pyproject \
    python3-all \
    python3-gi \
    python3-ibus-1.0 \
    python3-tomli-w \
    python3-httpx \
    python3-sounddevice \
    build-essential \
    dpkg-dev \
    fakeroot
```

Or just run:

```sh
./scripts/build-deb.sh
```

### Build the .deb

From the project root:

```sh
dpkg-buildpackage -us -uc -b --no-sign
```

This produces `../tux-im_0.1.0-1_all.deb`.

## Install

```sh
sudo apt install ./tux-im_0.1.0-1_all.deb
# or
sudo dpkg -i tux-im_0.1.0-1_all.deb
sudo apt -f install
```

The postinst does **not** auto-restart `ibus-daemon` (that requires a user
session). After install, either run `ibus restart` or log out and back in.

## Enable in IBus

1. Open IBus Preferences (`ibus-setup`)
2. Go to the **Input Method** tab
3. Click **Add** → **Chinese** → **TUX IM**
4. Make it the default or use the system tray to switch

## Verify

```sh
dpkg -L tux-im
ibus list-engine | grep tux-im
```

You should see `tux-im` in the list of available IBus engines.

## Uninstall

```sh
sudo apt remove tux-im
```

## Distributing via apt repository (optional)

For hosting on Launchpad PPA, GitHub Pages, etc., the standard flow is:

1. Build source + binary packages:
   ```sh
   dpkg-buildpackage -S -us -uc   # source
   dpkg-buildpackage -b -us -uc   # binary
   ```
2. Sign with `debsign` and `dput` to your PPA, or
3. Use `reprepro` to set up a local apt repo:
   ```sh
   reprepro includedeb resolute tux-im_0.1.0-1_all.deb
   ```

## Files in the .deb

After install:

```
/usr/lib/python3/dist-packages/tux_im/        # Python package
/usr/bin/tux-im-setup                          # settings GUI
/usr/libexec/ibus-engine-tux-im                # IBus launcher
/usr/share/ibus/component/com.github.tux-im.TuxIM.xml
/usr/share/dbus-1/services/com.github.tux-im.TuxIM.service
/usr/share/applications/tux-im-setup.desktop
/usr/share/tux-im/*.yaml                       # sample dicts
```
