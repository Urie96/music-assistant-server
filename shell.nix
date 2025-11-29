let
  pkgs = (import "${builtins.getEnv "HOME"}/nix" { }).pkgs;

  music-assistant-deps = pkgs.music-assistant;
in

pkgs.mkShell {
  packages = [
    pkgs.python3
  ];

  buildInputs = [
    music-assistant-deps.dependencies
  ];
}
