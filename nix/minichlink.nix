# minichlink — cnlohr's programmer/debugger for the CH32V003's SWIO
# single-wire debug port (PD1 on the node, quirks.md §Debug), the
# WCH-LinkE flashing path of DESIGN.md §6. nixpkgs has no package
# (verified via GitHub code search), so the minichlink/ subdir of
# ch32v003fun builds here from a pinned master rev.
{ stdenv, fetchFromGitHub, libusb1, udev }:

stdenv.mkDerivation {
  pname = "minichlink";
  version = "0-unstable-2026-10-07";

  src = fetchFromGitHub {
    owner = "cnlohr";
    repo = "ch32v003fun";
    rev = "a800cbd1f1ca5e250c73da83c669f0965d2052e5";
    hash = "sha256-kaUyWaFL5FXwojqT33RohlRqBL/C0KVFT5okMrb4Sv8=";
  };

  sourceRoot = "source/minichlink";

  dontConfigure = true;

  buildInputs = [
    libusb1
    udev
  ];

  # The Makefile's Linux branch hardcodes gcc and -lpthread -lusb-1.0
  # -ludev (pkg-config only enters on the darwin/BSD branches) and
  # compiles against its own vendored libusb.h. Build just the CLI —
  # the .so is minichlink-as-library for host tooling we don't use.
  # SHASUM detection shells out to `which`, absent in the sandbox;
  # pin it or the binary embeds an empty VERSION string.
  buildTargets = [ "minichlink" ];
  makeFlags = [ "SHASUM=sha1sum" ];

  # Upstream's only install target is install_udev_rules, which writes
  # to /etc — a host decision. The binary goes to bin/, the shipped
  # udev rules (WCH-LinkE VID/PID pairs → plugdev/dialout) ride along
  # for the host to opt into.
  installPhase = ''
    runHook preInstall
    install -Dm755 minichlink $out/bin/minichlink
    install -Dm644 99-minichlink.rules $out/lib/udev/rules.d/99-minichlink.rules
    runHook postInstall
  '';
}
