[![CI](https://github.com/MeteoSwiss/mwr_l12l2/actions/workflows/CI_tests.yaml/badge.svg)](https://github.com/MeteoSwiss/mwr_l12l2/actions/workflows/CI_tests.yaml)
[![Documentation Status](https://readthedocs.org/projects/mwr-l12l2/badge/?version=latest)](https://mwr-l12l2.readthedocs.io/en/latest/?badge=latest)


# mwr_l12l2
This repository contains tools for running optimal estimation retrievals for humidity and temperature profiling for 
ground-based microwave radiometers in combination with a model background. This encompasses tools for requesting the 
needed ECMWF forecast data, preprocessing tools for running TROPoe as well as postrocessing functions to extract 
quality-controlled E-PROFILE level 2 NetCDF formats. The package contains pre-computed a priori statistics for 
radiosonde sites representing typical European climates. Each instrument needs an own config file.

The operational service of E-PROFILE uses this package to run centralised near real-time retrievals and generate level2 
NetCDF messages from its network of ground-based microwave radiometers.

## External dependencies
* **TROPoe**: https://hub.docker.com/r/davidturner53/tropoe
* **podman**: https://podman.io/
* for using ECMWF forecasts:
  * **libeccodes0** and **libeccodes-tools**: grib file utilities available through apt
  * **mars**: command line utility to obtain ECMWF data, see https://confluence.ecmwf.int/display/UDOC/MARS+user+documentation

For short descriptions on these dependencies and installation instructions please refer to the 
[mwr_l12l2 official documentation](https://mwr-l12l2.readthedocs.io)

## Installation

Once the external dependencies have been installed *mwr_l12l2* along with its python dependencies is installable
using *pip*, *poetry* or any other tools which understand dependency specifications in pyproject.toml.

### from *pypi*
The package will be released on pypi once it has been thoroughly tested and quality controlled.
Until then, install from *git*

[//]: # (UNCOMMENT THE FOLLOWING LINES ONCE THE PACKAGE IS ON PYPI. in pycharm: Code > Comment with Line Comment)

[//]: # ()
[//]: # (*mwr_l12l2* is directly installable through *pip*. To install the latest released version and its dependencies do)

[//]: # ()
[//]: # ()
[//]: # (    pip install mwr_l12l2)

[//]: # ()
[//]: # ()
[//]: # (for more colorful logging you may instead want to do)

[//]: # ()
[//]: # ()
[//]: # (    pip install mwr_l12l2[colorlog])

### from *git*
To install *mwr_l12l2* from the source code do the following
1. clone this repository

    `git clone https://github.com/MeteoSwiss/mwr_l12l2.git`

2. go into the package directory and install
    - with *pip* (>=21.3)
   
        - `pip install .`
   
        - or for including the colorful logging
   
          `pip install .[colorlog]`
   
    - with *poetry*
   
        - `poetry install`
   
        - or for including the colorful logging
      
          `poetry install -E colorlog`
          
    


## Documentation
The official documentation is available [here](https://mwr-l12l2.readthedocs.io)

## License
[BSD 3-Clause](LICENSE)