# Corresponding source and build provenance

For release v0.6.4, the application source and build scripts are at https://github.com/yzc021101/Research-Library/tree/v0.6.4 . The AGPL license and frontend additional permission are at the repository root. Application binaries are built from this tag; no source modifications were made to PyMuPDF/MuPDF.

Third-party components are unchanged from v0.6.3. Download their matching source assets at https://github.com/yzc021101/Research-Library/releases/tag/v0.6.3 :

- `pymupdf-1.28.2.tar.gz`: official PyPI sdist, includes build scripts and license.
- `mupdf-1.28.2-source.tar.gz`: official complete MuPDF source including bundled libraries; https://mupdf.com/downloads/archive/mupdf-1.28.2-source.tar.gz .
- `python-mpl-corresponding-source.zip`: exact certifi/tqdm sdists with original URLs and SHA256 manifest.
- `ocr-windows-corresponding-source.zip`: exact MSYS2 source archives, build recipes and patches for the copyleft libraries and Tesseract. SOURCE_MANIFEST.json records filenames, URLs and hashes. Built binaries are unmodified packages from https://repo.msys2.org/mingw/mingw64/ . OCR binary SOURCES.json specifies the complete dependency versions. Language data comes from https://github.com/tesseract-ocr/tessdata_fast .

LibreOffice 25.8.6.2 corresponding source (upstream archive server, free of charge):

- https://downloadarchive.documentfoundation.org/libreoffice/old/25.8.6.2/src/libreoffice-25.8.6.2.tar.xz
- https://downloadarchive.documentfoundation.org/libreoffice/old/25.8.6.2/src/libreoffice-dictionaries-25.8.6.2.tar.xz
- https://downloadarchive.documentfoundation.org/libreoffice/old/25.8.6.2/src/libreoffice-help-25.8.6.2.tar.xz
- https://downloadarchive.documentfoundation.org/libreoffice/old/25.8.6.2/src/libreoffice-translations-25.8.6.2.tar.xz

These sources contain upstream build instructions and external dependency recipes. The optional package only relocates the unmodified official application; licenses, source notices and dictionaries are retained. Mac OCR library load paths are relocated for local use; its SOURCES.txt and licenses/ record upstream versions. No source changes. Build recipes are included under packaging/.

CPython source: https://www.python.org/ftp/python/3.12.14/Python-3.12.14.tar.xz . Other Python package versions are in python-macos/dependencies.json and python-windows/dependencies.json; matching official source distributions are available at https://pypi.org/ . Microsoft runtime license texts include their applicable third-party source notices. If an upstream source URL becomes unavailable, report it in the repository so the source can be restored.
