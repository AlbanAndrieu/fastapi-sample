{ pkgs ? import (fetchTarball "https://channels.nixos.org/nixos-25.11/nixexprs.tar.xz") { config = { allowUnfree = true; }; } }:

pkgs.mkShellNoCC {
  packages = with pkgs; [
    poetry
    python3
    virtualenv
    nodejs
    git
    cowsay
  ];

  shellHook = ''
    echo "Welcome to the Shell! May your pipelines be green." | cowsay -f dragon
  '';
}
