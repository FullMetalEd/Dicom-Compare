{
  description = "DICOM Compare Tool - Compare DICOM studies from different ZIP exports";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        
        dicom-compare = pkgs.python3Packages.buildPythonApplication {
          pname = "dicom-compare";
          version = "0.1.0";

          src = ./.;

          pyproject = true;

          nativeBuildInputs = with pkgs.python3Packages; [
            hatchling
          ];

          propagatedBuildInputs = with pkgs.python3Packages; [
            pydicom
            typer
            pandas
            rich
            openpyxl
            matplotlib
          ];

          # Skip tests for now
          doCheck = false;

          meta = with pkgs.lib; {
            description = "Compare DICOM studies from different ZIP exports to identify differences";
            homepage = "https://github.com/yourusername/dicom-compare";
            license = licenses.mit;
            maintainers = [ ];
          };
        };
      in
      {
        packages = {
          default = dicom-compare;
          dicom-compare = dicom-compare;
        };

        apps = {
          default = flake-utils.lib.mkApp {
            drv = dicom-compare;
            name = "dicom-compare";  # Changed to match the script name in pyproject.toml
          };
          dicom-compare = flake-utils.lib.mkApp {
            drv = dicom-compare;
            name = "dicom-compare";  # Added this for consistency
          };
        };

        devShells.default = pkgs.mkShell {
          buildInputs = with pkgs; [
            python3
            python3Packages.hatchling
          ] ++ (with pkgs.python3Packages; [
            pydicom
            typer
            pandas
            rich
            openpyxl
            matplotlib
          ]);

          shellHook = ''
            echo "🏥 DICOM Compare development environment"
            echo "Run: python3 -m dicom_compare.main --help"  # Fixed: underscore to match directory
          '';
        };
      });
}