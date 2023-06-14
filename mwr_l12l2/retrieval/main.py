import glob
import os
import shutil

import prepare_eprofile
from mwr_l12l2.utils.file_uitls import abs_file_path


def run_retrieval(retrieval_conf, node=0):
    # get retrieval conf
    conf = {'dir_mwr_in': abs_file_path('mwr_l12l2/data/mwr/'),
            'prefix_mwr_in': 'MWR_1C01_',
            'dir_alc_in': abs_file_path('mwr_l12l2/data/alc/'),
            'prefix_alc_in': 'L2_',
            'basedir_tropoe_files': abs_file_path('mwr_l12l2/data/tropoe/')}
    # TODO: put this dict to retrieval config file at retrieval_conf and set up a config reader

    # set up an empty tropoe tmp file directory for the current node (remove old one if existing)
    tropoe_dir = os.path.join(conf['basedir_tropoe_files'], 'node_{}/'.format(node))
    if os.path.exists(tropoe_dir):
        shutil.rmtree(tropoe_dir)
    os.mkdir(tropoe_dir)

    # select instrument which has oldest mwr file in input dir.
    # TODO: implement this
    # TODO: Need to lock lookup for station selection for other nodes until prepare_eprofile_main with delete_mwr_in is done
    pass
    wigos = '0-20000-0-10393'
    inst_id = 'A'

    # get file lists for the selected station
    mwr_files = glob.glob(os.path.join(conf['dir_mwr_in'], '{}*{}_{}*.nc'.format(conf['prefix_mwr_in'], wigos, inst_id)))
    alc_files = glob.glob(os.path.join(conf['dir_alc_in'], '{}*{}*.nc'.format(conf['prefix_alc_in'], wigos)))



    # concatenate E-Profile and deposit in node-n folder under generic name
    prepare_eprofile.main(mwr_files, os.path.join(tropoe_dir, 'MWR.nc'),
                          alc_files, os.path.join(tropoe_dir, 'ALC.nc'),
                          delete_mwr_in=False)  # TODO: switch delete_mwr_in to True for operational processing


    # TODO: adapt drawing on https://meteoswiss.atlassian.net/wiki/spaces/MDA/pages/46564537/L2+retrieval+EWC
    #  by inverting order between interpret_ecmwf and prepare_eprofile


    # find appropriate ECMWF fc (the latest with timestamp before timestamp of infile) and run interpret_ecmwf.py
    # and deposit to node-n folder
    pass




if __name__ == '__main__':
    run_retrieval(None)
