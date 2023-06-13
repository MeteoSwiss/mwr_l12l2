#!/bin/bash
# transform GRIB file of ECMWF forecast to NetCDF.
#
# This step is needed as cfgrib cannot decode a file containing vars with different dims (in this case lnsp vs q and T)
# TODO: loop over all new grb forecast files (not needed for z from analysis)
# TODO: evaluate whether to transform this to python

#GRB_FILE=mwr_l12l2/data/ecmwf_fc/ecmwf_fc_0-20000-0-06610_A_202304250000.grb
#NC_FILE=mwr_l12l2/data/ecmwf_fc/ecmwf_fc_0-20000-0-06610_A_202304250000_converted_to.nc
GRB_FILE=../../data/ecmwf_fc/ecmwf_fc_0-20000-0-10393_A_202304250000.grb
NC_FILE=../../data/ecmwf_fc/ecmwf_fc_0-20000-0-10393_A_202304250000_converted_to.nc

grib_to_netcdf -k 4 -o $NC_FILE $GRB_FILE