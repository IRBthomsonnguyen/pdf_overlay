# PDF Overlay

A small Streamlit web app for comparing two sets of PDFs:

- old PDFs are colourised red;
- new PDFs are colourised green;
- matching pages are blended into an overlay PDF.

## Run locally

### Recommended: virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

### If Windows will not create a virtual environment

Install the packages for your Windows user account instead:

```powershell
py -m pip install --user -r requirements.txt
py -m streamlit run app.py
```

If PowerShell blocks activation with an execution-policy error, you can allow scripts only for the current terminal window:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

If `python` or `py` is not recognised, install Python from [python.org](https://www.python.org/downloads/windows/) and enable **Add Python to PATH** during installation.

Upload PDFs in the two columns. Files are paired by filename (without the `.pdf` extension). If there are no matching filenames, files are paired alphabetically by upload list order. PDFs with different page counts are reported and skipped.

The output is rasterised at the selected DPI, which makes the colour overlay reliable across vector and scanned PDFs. For best alignment, the old and new PDFs should use the same page size and orientation.
