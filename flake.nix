{
  description = "Python Dev Environment for Nixos";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
	  buildInputs = with pkgs; [
	    uv
	    gcc
        python3Packages.numpy
	    (python3.withPackages (ps: with ps; with python3Packages; [
              #jupyter
              #ipython
            ]))
	];

	shellHook = ''
	  rm -rf .venv
	  uv venv .venv
	  source .venv/bin/activate
	  
	  export PIP_REQUIRE_VIRTUALENV=true
	  export PIP_USE_UV=1

	  uv pip install -e .
	'';
      
      };
    });
}
	