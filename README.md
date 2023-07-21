[![CI](https://github.com/MeteoSwiss/mwr_l12l2/actions/workflows/CI_tests.yaml/badge.svg)](https://github.com/MeteoSwiss/mwr_l12l2/actions/workflows/CI_tests.yaml)
[![Documentation Status](https://readthedocs.org/projects/mwr-l12l2/badge/?version=latest)](https://mwr-l12l2.readthedocs.io/en/latest/?badge=latest)


This repository contains tools for running optimal estimation retrievals for humidity and temperature profiling for 
ground-based microwave radiometers in combination with a model background. This encompasses tools for requesting the 
needed ECMWF forecast data, preprocessing tools for running TROPoe as well as postrocessing functions to extract 
quality-controlled E-PROFILE level 2 NetCDF formats. The package contains pre-computed a priori statistics for 
radiosonde sites representing typical European climates. Each instrument needs an own config file.

The operational service of E-PROFILE uses this package to run centralised near real-time retrievals and generate level2 
NetCDF messages from its network of ground-based microwave radiometers.

## Dependencies:
* TROPoe: https://hub.docker.com/r/davidturner53/tropoe
* podman: https://podman.io/
* for using ECMWF forecasts:
  * libeccodes0 and libeccodes-tools: grib file utilites available through apt
  * mars: command line utility to obtain ECMWF data, see https://confluence.ecmwf.int/display/UDOC/MARS+user+documentation