%global pypi_name tux-im
%global version 0.1.0
%global release 17

Name:           tux-im
Version:        %{version}
Release:        %{release}%{?dist}
Summary:        IBus input method engine for Pinyin, Wubi, Wbpy, and ASR
License:        GPL-3.0-or-later
URL:            https://github.com/tux-im/tux-im
Source0:        https://files.pythonhosted.org/packages/source/t/%{pypi_name}/tux_im-%{version}.tar.gz
BuildArch:      noarch

Requires:       ibus
Requires:       python3-gobject
Requires:       python3-pysounddevice
Requires:       python3-httpx
Requires:       python3-tomli-w
# librime-data-wubi and librime-data-luna-pinyin provide the bundled
# Rime dictionary files that the wubi/pinyin modes require at
# runtime.  These package names exist on Debian/Ubuntu but not on
# upstream Fedora.  Marked as Recommends so a `dnf install` works
# without them; users on Fedora who want wubi/pinyin support need
# to install librime + rime-data manually or pull these from a
# third-party repo (e.g. RPM Fusion).
Recommends:     librime-data-wubi
Recommends:     librime-data-luna-pinyin

BuildRequires:  python3-devel
BuildRequires:  python3-pip
BuildRequires:  python3-setuptools
BuildRequires:  python3-wheel

%description
TUX IM is an IBus input method engine focused on Chinese input. It
supports Pinyin, Wubi, Wbpy (mixed Pinyin + Wubi), and ASR (voice
input) modes. Designed for fast startup, type-safe internals, and a
small footprint on modern Linux desktops.

%prep
# PyPI normalizes the project name from tux-im to tux_im in the
# sdist tarball, so the actual file is tux_im-0.1.0.tar.gz but
# extracts to a directory called tux_im-0.1.0.  Do NOT pass
# %{version} to -n: rpm parses -n arguments before macro expansion
# runs, so %{version} would be empty.  Hard-code the directory name.
%autosetup -n tux_im-0.1.0

%build
# Build wheel + install into the buildroot. We use explicit
# python3 -m pip invocations instead of the %pyproject_build /
# %pyproject_install macros because the macro-generated script
# occasionally hits "fg: no job control" in non-interactive
# subshells on Fedora's noarch builders (we ship a pure-Python
# library + three console scripts; no native extension).
python3 -m pip wheel --no-deps --no-build-isolation \
    --wheel-dir %{_pyproject_build_dir} .
python3 -m pip install --no-deps \
    --root %{buildroot} \
    --no-index --ignore-installed \
    --find-links %{_pyproject_build_dir} %{pypi_name}

# IBus component + D-Bus service file (mirrors debian/tux-im.install)
install -D -m 0644 setup/com.github.tux-im.TuxIM.xml \
    %{buildroot}%{_datadir}/ibus/component/com.github.tux-im.TuxIM.xml
install -D -m 0644 setup/com.github.tux-im.TuxIM.service \
    %{buildroot}%{_datadir}/dbus-1/services/com.github.tux-im.TuxIM.service
install -D -m 0644 setup/tux-im-setup.desktop \
    %{buildroot}%{_datadir}/applications/tux-im-setup.desktop

# Bundled dictionary data — installed under /usr/share/tux-im
install -d %{buildroot}%{_datadir}/tux-im
install -m 0644 data/*.yaml %{buildroot}%{_datadir}/tux-im/

%files
%license LICENSE
%doc README.md
%{_bindir}/ibus-engine-tux-im
%{_bindir}/tux-im-setup
%{python3_sitelib}/tux_im/
%{python3_sitelib}/tux_im-*.dist-info/
%{_datadir}/ibus/component/com.github.tux-im.TuxIM.xml
%{_datadir}/dbus-1/services/com.github.tux-im.TuxIM.service
%{_datadir}/applications/tux-im-setup.desktop
%{_datadir}/tux-im/

%changelog
* Sat Aug 29 2026 TUX IM contributors <tux-im@example.com> - 0.1.0-17
- Initial RPM packaging (mirrors Debian package).