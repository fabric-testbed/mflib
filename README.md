# MFLIB Measurement Framework Library

[![Documentation Status](https://readthedocs.org/projects/fabrictestbed-mflib/badge/?version=latest)](https://fabrictestbed-mflib.readthedocs.io/en/latest/?badge=latest)

Welcome to the FABRIC Measurement Framework Library. MFLib makes it easy to install monitoring systems to a FABRIC experimenter's slice. The monitoring system makes extensive use of industry standards such as Prometheus, Grafana, Elastic Search and Kibana while adding customized monitoring tools and dashboards for quick setup and visualization.

## Documentation Resources
For more information about FABRIC vist [fabric-testbed.net](https://fabric-testbed.net/)
### Example Jupyter Notebooks
[FABRIC Jupyter Examples](https://github.com/fabric-testbed/jupyter-examples) GitHub repository contains many examples for using FABRIC from simple slice setup to advanced networking setups. Look for the MFLib section. These notebooks are designed to be easily used on the [FABRIC JupyterHub](https://jupyter.fabric-testbed.net/)

### FABRIC Learn Site
[FABRIC Knowledge Base](https://learn.fabric-testbed.net/) 

### MFLib Python Package Documentation
Documentation for the package is presented in serveral different forms (and maybe include later in this document):
* [ReadTheDocs](https://fabrictestbed-mflib.readthedocs.io/en/latest/)
* [MFLib.pdf](https://github.com/fabric-testbed/mflib/blob/main/MFLib.pdf) in the source code/GitHub.
* Or you may build the documentation from the source code. See Sphinx Documentation later in this document.

## MFLib Installation

### Instaling via PIP
MFLib may be installed using PIP and PyPI [fabrictestbed-mflib](https://pypi.org/project/fabrictestbed-mflib/)
```
pip install --user fabrictestbed-mflib
```

### Installing via Source Code
If you need a development version, clone the git repo, then use pip to install.
```
git clone https://github.com/fabric-testbed/mflib.git
cd mflib
pip install --user .
```
## Building & Deploying

### Spinx Documentation
This package is documented using sphinx. The `source` directories are already created and populated with reStructuredText ( .rst ) files. The `build` directories are deleted and/or are not included in the repository,

API documentation can also be found at https://fabrictestbed-mflib.readthedocs.io/.

#### Build HTML Documents

Install the extra packages required to build API docs: (sphinx, furo theme, and myst-parser for parsing markdown files):

```
pip install -r docs/requirements.txt
```

Build the documentation by running the following command from the root directory of the repo.
```
./create_html_doc.sh
```

The completed documentation may be accessed by clicking on `/docs/build/html/index.html`. Note that the HTML docs are not saved to the repository.

#### Build PDF Document
Latex must be installed. For Debian use: 
```
sudo apt install texlive-latex-extra 
sudo apt install latexmk

```
Run the bash script to create the MFLIB.pdf documentation. MFLIB.pdf will be placed in the root directory of the repository.
```
./create_pdf_doc.sh
```

### Distribution Package

MFLib package is created using [Flit](https://flit.pypa.io/en/stable/)
Be sure to create and commit the PDF documentation to GitHub before building and publishing to PyPi. The MFLib.pdf is included in the distributition.

To build python package for PyPi run  
```
./create_release.sh
```

#### Uploading to PyPI

First test the package by uploading to test.pypi.org then test the install.
```
flit publish --repository testpypi 
```
Note that if the package has already been published to testpypi, it cannot be published again until the version is updated. There is not an obvious error for this. Instead you will just get the following error: 
```
requests.exceptions.HTTPError: 400 Client Error: Bad Request for url: https://test.pypi.org/legacy/
```
Once install is good, upload to PiPy  
```
flit publish
```
Note that Flit places a .pypirc file in your home directory if you do not already have one. Flit may also store your password in the keyring which may break if the password is changed. see [Flit Controlling package uploads](https://flit.pypa.io/en/stable/upload.html). The password can also be added to the .pypirc file. If password contains % signs it will break the .pypirc file.
