#!/bin/bash
# execute the mars request specified in REQ_FILE

input_folder=/home/eric/ecmwf
bucket_name=s3://eprofile-ecmwf-data/

for GRB_FILE in $input_folder/ecmwf_fc*.grb
do
    # create the name of the output file
    NC_FILE=${GRB_FILE%.grb}_converted_to.nc

    # Check if NC_FILE already exist
    if [ -f "$NC_FILE" ]; then
        echo "$NC_FILE exists."
    else 
        echo "$NC_FILE does not exist, converting $GRIBFILE"

        # transform the GRIB file to NetCDF
        grib_to_netcdf -k 4 -o $NC_FILE $GRB_FILE
    fi
    s3cmd put $NC_FILE $bucket_name
    echo "$NC_FILE transfered to $bucket_name, deleting it from VM"
    rm $GRB_FILE
    echo "Deleting $GRB_FILE from VM"
    rm $NC_FILE
    echo "Forecast files removed from VM"
done

for GRB_FILE_Z in $input_folder/ecmwf_z*.grb
do
    s3cmd put $GRB_FILE_Z $bucket_name
done
