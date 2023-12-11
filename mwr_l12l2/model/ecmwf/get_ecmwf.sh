#!/bin/bash
# execute the mars request specified in REQ_FILE

input_folder=/home/eric/ecmwf
bucket_name=s3://eprofile-ecmwf-data/

echo "write and start MARS request"
/usr/bin/python3 /home/eric/mwr_l12l2/mwr_l12l2/model/ecmwf/request_ecmwf.py

