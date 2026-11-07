Name:           wubugo
Version:        6.0.1
Release:        1%{?dist}
Summary:        Offline CS:GO mod manager
License:        MIT
Source0:        wubuGO-%{version}-linux-x64-portable.tar.gz
ExclusiveArch:  x86_64
Requires:       libX11, libXext, libXrender, libXft, fontconfig, glibc
# PyInstaller bundles its Python/Tcl/Tk runtime; keep those files intact.
%global __strip /bin/true
%global debug_package %{nil}
%global __os_install_post %{nil}
%description
Python/Tk mod manager for local, insecure CS:GO sessions. Steam and game content
are installed separately. User state and backups are not removed on uninstall.
%prep
%setup -q -n wubuGO
%build
%install
mkdir -p %{buildroot}/opt/wubugo %{buildroot}%{_datadir}/applications %{buildroot}%{_datadir}/icons/hicolor/256x256/apps
cp -a . %{buildroot}/opt/wubugo/
install -m644 wubugo.desktop %{buildroot}%{_datadir}/applications/wubugo.desktop
install -m644 wubugo.png %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/wubugo.png
%files
/opt/wubugo
%{_datadir}/applications/wubugo.desktop
%{_datadir}/icons/hicolor/256x256/apps/wubugo.png
