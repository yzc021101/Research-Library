# Third-party components

Project-owned code is AGPL-3.0-only; see ../LICENSE and ../PLATFORM-LINKING-PERMISSION.txt. This does not relicense third-party components. This directory contains notices copied from the exact build dependencies. Python dependency versions are listed per platform. The dotnet-winui inventory contains build-time as well as shipped runtime package notices; the application ships only the publish output.

- PyMuPDF 1.28.2 / MuPDF 1.28.2: AGPL-3.0. Unmodified upstream wheels; full matching source archives accompany the release.
- CPython 3.12.13 (macOS) / 3.12.14 (Windows): PSF license. PyInstaller bootloader: GPL-2.0-or-later with its bootloader exception, reproduced in licenses/.
- certifi: MPL-2.0. tqdm: MPL-2.0 / MIT. Exact source archives accompany the release.
- .NET: MIT and included notices. Windows App SDK: its Microsoft software license terms, reproduced under dotnet-winui/. Those terms govern only the Microsoft components. Users and downstream distributors must agree to those terms for the bundled Microsoft Windows App SDK code; AGPL rights in the project code are unaffected.
- The separately extracted Microsoft Visual C++ CRT DLLs are not shipped. Windows downloads Microsoft's signed official installer when the required system runtime is absent. The user accepts Microsoft's license and installer prompts. Hashed DLL aliases required by upstream wheels are created locally from that user's installed system runtime.
- Tesseract OCR: Apache-2.0; its dynamic dependencies have separate licenses shipped in each optional component. Windows corresponding source/build recipes for copyleft libraries are provided as an additional source archive. Compatible modified dynamic libraries may be substituted, and debugging such modifications is permitted.
- LibreOffice 25.8.6.2: MPL-2.0 / LGPL-3.0-or-later and included third-party notices. Separate optional executable. Its licenses and source URLs are retained; no source modification.
- Model weights are not shipped. Models are optional downloads; see MODELS.md.

All third-party trademarks remain with their owners. No affiliation or endorsement is implied. Detailed source locations are in SOURCES.md.
