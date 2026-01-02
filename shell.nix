let
  pkgs = (import "${builtins.getEnv "HOME"}/nix" { }).pkgs;

  music-assistant-deps = pkgs.music-assistant.override {
    providers = [ "snapcast" ];
  };
  customPython = music-assistant-deps.python.withPackages (
    p: with p; [
      chardet
    ]
  );
in

pkgs.mkShell {
  packages = [
    customPython
  ];
  buildInputs = [
    music-assistant-deps.dependencies
  ]
  ++ (with pkgs; [
    ffmpeg-headless
    snapcast
  ]);
  shellHook = ''
    export PYTHONPATH="$PYTHONPATH:${music-assistant-deps.pythonPath}"
  '';
}
