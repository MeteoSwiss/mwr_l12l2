#!/bin/bash
# execute the mars request specified in REQ_FILE

REQ_FILE=mwr_l12l2/data/output/ecmwf/mars_request.txt

nohup mars $REQ_FILE &